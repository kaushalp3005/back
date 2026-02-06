from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import os
import uuid
import logging
from datetime import datetime
import shutil
from pathlib import Path
import io
from PIL import Image

from app.core.database import get_db
from app.schemas.label import (
    LabelUploadResponse, LabelInfo, LabelListResponse, 
    LabelDeleteResponse, LabelFormat, LabelStatus, BoxManagementPayload
)

router = APIRouter(prefix="/api/label", tags=["label"])

# Configuration
UPLOAD_DIR = Path("uploads/labels")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file extensions for MS Paint format
ALLOWED_EXTENSIONS = {".bmp", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Label dimension requirements (4 inch width x 2 inch height)
LABEL_WIDTH_INCHES = 4
LABEL_HEIGHT_INCHES = 2

def create_composite_label(qr_label_buffer, uploaded_content) -> bytes:
    """Create a composite label combining QR label with uploaded image overlay"""
    try:
        from PIL import Image
        
        # Create QR label image
        qr_label_buffer.seek(0)
        qr_img = Image.open(qr_label_buffer)
        
        # Create uploaded image
        uploaded_img = Image.open(io.BytesIO(uploaded_content))
        
        # Ensure uploaded image is RGB
        if uploaded_img.mode != 'RGB':
            uploaded_img = uploaded_img.convert('RGB')
        
        # Resize uploaded image to fit as overlay (smaller)
        qr_width, qr_height = qr_img.size
        
        # Make uploaded image 25% of QR label size
        overlay_width = int(qr_width * 0.25)
        overlay_height = int(qr_height * 0.25)
        
        uploaded_img = uploaded_img.resize((overlay_width, overlay_height), Image.Resampling.LANCZOS)
        
        # Position overlay in bottom-right corner
        overlay_x = qr_width - overlay_width - 20
        overlay_y = qr_height - overlay_height - 20
        
        # Create composite image
        composite_img = qr_img.copy()
        composite_img.paste(uploaded_img, (overlay_x, overlay_y))
        
        # Convert to bytes
        composite_buffer = io.BytesIO()
        composite_img.save(composite_buffer, format='PNG', optimize=True)
        composite_buffer.seek(0)
        
        return composite_buffer.getvalue()
        
    except Exception as e:
        logging.error(f"Error creating composite label: {e}")
        # Return just the QR label if composite fails
        qr_label_buffer.seek(0)
        return qr_label_buffer.getvalue()

def validate_file(file: UploadFile) -> tuple[bool, str]:
    """Validate uploaded file"""
    if not file.filename:
        return False, "No filename provided"
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file format. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
    
    # Check file size
    if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
    
    return True, "Valid"

def resize_image_to_label_dimensions(image_bytes: bytes, target_dpi: int = 96) -> bytes:
    """
    Resize image to standard label dimensions (4" x 2" inches)
    Uses inches directly instead of pixel calculations
    Maintains aspect ratio and centers the content with white background
    """
    try:
        # Open image from bytes
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (handles RGBA, P mode images)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Calculate target dimensions in inches
        target_width_inches = LABEL_WIDTH_INCHES
        target_height_inches = LABEL_HEIGHT_INCHES
        
        # Convert target inches to pixels for processing
        target_width_pixels = int(target_width_inches * target_dpi)
        target_height_pixels = int(target_height_inches * target_dpi)
        
        # Calculate scaling to fit within label dimensions while maintaining aspect ratio
        img_width, img_height = image.size
        current_width_inches = img_width / target_dpi  # Convert pixels to inches
        current_height_inches = img_height / target_dpi
        
        # Calculate scale factors in inches
        scale_width = target_width_inches / current_width_inches
        scale_height = target_height_inches / current_height_inches
        scale = min(scale_width, scale_height)  # Use smaller scale to fit completely
        
        # Calculate new dimensions maintaining aspect ratio
        new_width_pixels = int(img_width * scale)
        new_height_pixels = int(img_height * scale)
        resized_image = image.resize((new_width_pixels, new_height_pixels), Image.Resampling.LANCZOS)
        
        # Create final image with label dimensions and white background
        final_image = Image.new('RGB', (target_width_pixels, target_height_pixels), (255, 255, 255))
        
        # Center the resized image on the white background
        x_offset = (target_width_pixels - new_width_pixels) // 2
        y_offset = (target_height_pixels - new_height_pixels) // 2
        final_image.paste(resized_image, (x_offset, y_offset))
        
        # Add metadata with inch dimensions
        final_image.info['dpi'] = (target_dpi, target_dpi)
        
        # Convert back to bytes
        output = io.BytesIO()
        final_image.save(output, format='PNG', quality=95)
        return output.getvalue()
        
    except Exception as e:
        logging.error(f"Error resizing image: {e}")
        # Return original image if resizing fails
        return image_bytes

def get_box_management_payload(db: Session, company: str, transaction_no: str, box_number: int) -> BoxManagementPayload:
    """Get box management payload from database"""
    try:
        # Get table names based on company
        prefix = "cfpl" if company.upper() == "CFPL" else "cdpl"
        box_table = f"{prefix}_boxes"
        article_table = f"{prefix}_articles"
        transaction_table = f"{prefix}_transactions"
        
        # Query to get box and related information
        query = text(f"""
            SELECT 
                b.box_number,
                b.article_description,
                b.net_weight,
                b.gross_weight,
                b.lot_number,
                a.sku_id,
                a.batch_number,
                a.manufacturing_date,
                a.expiry_date,
                a.quality_grade,
                a.uom,
                a.packaging_type,
                a.currency,
                a.unit_rate,
                a.total_amount,
                t.entry_date,
                t.vendor_supplier_name,
                t.customer_party_name
            FROM {box_table} b
            LEFT JOIN {article_table} a ON b.transaction_no = a.transaction_no AND b.article_description = a.item_description
            LEFT JOIN {transaction_table} t ON b.transaction_no = t.transaction_no
            WHERE b.transaction_no = :transaction_no 
            AND b.box_number = :box_number
        """)
        
        result = db.execute(query, {
            "transaction_no": transaction_no,
            "box_number": box_number
        }).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail=f"Box {box_number} not found for transaction {transaction_no}"
            )
        
        # Convert dates to strings
        entry_date = result.entry_date.isoformat() if result.entry_date else datetime.now().isoformat()
        manufacturing_date = result.manufacturing_date.isoformat() if result.manufacturing_date else None
        expiry_date = result.expiry_date.isoformat() if result.expiry_date else None
        
        return BoxManagementPayload(
            company=company,
            transaction_no=transaction_no,
            box_number=result.box_number,
            article_description=result.article_description or "",
            sku_id=result.sku_id or 0,
            net_weight=result.net_weight or 0.0,
            gross_weight=result.gross_weight or 0.0,
            batch_number=result.batch_number or "",
            manufacturing_date=manufacturing_date,
            expiry_date=expiry_date,
            vendor_name=result.vendor_supplier_name,
            customer_name=result.customer_party_name,
            entry_date=entry_date,
            quality_grade=result.quality_grade,
            uom=result.uom,
            packaging_type=result.packaging_type,
            lot_number=result.lot_number,
            currency=result.currency,
            unit_rate=result.unit_rate,
            total_amount=result.total_amount
        )
        
    except Exception as e:
        logging.error(f"Error getting box management payload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get box information: {str(e)}")

@router.post("/send", response_model=LabelUploadResponse)
async def send_label_to_frontend(
    company: str = Form(..., description="Company code (CFPL or CDPL)"),
    transaction_no: str = Form(..., description="Transaction number"),
    box_number: int = Form(..., description="Box number"),
    description: Optional[str] = Form(None, description="Optional description"),
    file: UploadFile = File(..., description="Label file in MS Paint format (BMP, PNG, JPEG)"),
    db: Session = Depends(get_db)
):
    """
    Send a label file to the frontend using multipart form data.
    This is a one-time transfer without storing in database.
    References box_number from cdpl_boxes/cfpl_boxes tables.
    
    **Multipart Form Response:**
    - Returns the uploaded file directly as multipart form data
    - Includes box management payload from cdpl_boxes/cfpl_boxes tables
    - No database storage - one-time transfer only
    
    **Box Box Management Payload:**
    - company: Company code (CFPL/CDPL)
    - transaction_no: Transaction number
    - box_number: Box number from database tables
    - article_description: Article description
    - sku_id: SKU identifier
    - net_weight: Net weight of the box
    - gross_weight: Gross weight of the box
    - batch_number: Batch number
    - manufacturing_date: Manufacturing date (optional)
    - expiry_date: Expiry date (optional)
    - vendor_name: Vendor name (optional)
    - customer_name: Customer name (optional)
    - entry_date: Entry date
    - quality_grade: Quality grade (optional)
    - uom: Unit of measure (optional)
    - packaging_type: Packaging type (optional)
    - lot_number: Lot number (optional)
    - currency: Currency (optional)
    - unit_rate: Unit rate (optional)
    - total_amount: Total amount (optional)
    """
    try:
        # Validate company
        if company.upper() not in ["CFPL", "CDPL"]:
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Validate file
        is_valid, error_msg = validate_file(file)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Validate box_number exists in database and get box data
        box_payload = get_box_management_payload(db, company, transaction_no, box_number)
        
        # Create multipart response - generate complete QR label + transfer uploaded file
        import json
        
        # Generate QR label with complete content
        from app.services.print_service import QRLabelGenerator
        
        try:
            # Create QR label generator
            qr_generator = QRLabelGenerator()
            
            # Convert box payload to QR payload format
            qr_payload = {
                "company": box_payload.company,
                "transaction_no": box_payload.transaction_no,
                "entry_date": box_payload.entry_date.split('T')[0] if 'T' in box_payload.entry_date else box_payload.entry_date,
                "vendor_name": box_payload.vendor_name or "",
                "customer_name": box_payload.customer_name or "",
                "item_description": box_payload.article_description,
                "net_weight": float(box_payload.net_weight),
                "total_weight": float(box_payload.gross_weight),
                "batch_number": box_payload.batch_number or "",
                "manufacturing_date": box_payload.manufacturing_date.split('T')[0] if box_payload.manufacturing_date and 'T' in box_payload.manufacturing_date else box_payload.manufacturing_date,
                "expiry_date": box_payload.expiry_date.split('T')[0] if box_payload.expiry_date and 'T' in box_payload.expiry_date else box_payload.expiry_date,
                "box_number": box_payload.box_number,
                "sku_id": box_payload.sku_id
            }
            
            # Generate complete label with QR code and text
            qr_label_buffer = qr_generator.generate_label_image(qr_payload)
            
            # Also process the uploaded file for composite label (if needed)
            uploaded_content = await file.read()
            resized_upload = resize_image_to_label_dimensions(uploaded_content)
            
            # Create combined label (QR label + user's image overlay)
            composite_label_content = create_composite_label(qr_label_buffer, resized_upload)
            
            # Generate filename
            original_filename = Path(file.filename).stem
            standardized_filename = f"{original_filename}_complete_label_4x2.png"
            
            # Log the transfer
            logging.info(f"Complete QR label generated and sent to frontend: Company: {company}, Transaction: {transaction_no}, Box: {box_number}")
            
            # Return the complete label with QR code and text
            return Response(
                content=composite_label_content,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"attachment; filename={standardized_filename}",
                    "X-Box-Management-Payload": json.dumps(box_payload.dict()),
                    "X-QR-Payload": json.dumps(qr_payload),
                    "X-File-Info": json.dumps({
                        "filename": standardized_filename,
                        "content_type": "image/png",
                        "size": len(composite_label_content),
                        "dimensions": f"4x2 inches (300 DPI)",
                        "original_filename": file.filename,
                        "label_type": "Complete QR Label with Text"
                    }),
                    "X-Message": "Complete QR label generated with QR code, item description, batch number, and all box data"
                }
            )
            
        except Exception as e:
            logging.error(f"Error generating QR label: {e}")
            # Fallback to original file if QR generation fails
            original_filename = Path(file.filename).stem
            standardized_filename = f"{original_filename}_fallback_4x2.png"
            
            # Process original file as fallback
            uploaded_content = await file.read()
            resized_content = resize_image_to_label_dimensions(uploaded_content)
            
            return Response(
                content=resized_content,
                media_type="image/png", 
                headers={
                    "Content-Disposition": f"attachment; filename={standardized_filename}",
                    "X-Box-Management-Payload": json.dumps(box_payload.dict()),
                    "X-Warning": "QR generation failed, returning original file",
                    "X-Message": "Fallback to original uploaded file"
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error sending label to frontend: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send label to frontend: {str(e)}")

@router.get("/download/{label_id}")
def download_label(
    label_id: str,
    company: str = Query(..., description="Company code (CFPL or CDPL)"),
    db: Session = Depends(get_db)
):
    """Download a label file"""
    try:
        # Validate company
        if company.upper() not in ["CFPL", "CDPL"]:
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Look for the label file
        company_dir = UPLOAD_DIR / company.upper()
        label_files = list(company_dir.glob(f"{label_id}.*"))
        
        if not label_files:
            raise HTTPException(status_code=404, detail="Label not found")
        
        file_path = label_files[0]
        
        # Return the file
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error downloading label: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download label: {str(e)}")

@router.get("/list", response_model=LabelListResponse)
def list_labels(
    company: str = Query(..., description="Company code (CFPL or CDPL)"),
    transaction_no: Optional[str] = Query(None, description="Filter by transaction number"),
    box_number: Optional[int] = Query(None, description="Filter by box number"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """List uploaded labels with pagination"""
    try:
        # Validate company
        if company.upper() not in ["CFPL", "CDPL"]:
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # For now, return mock data since we don't have a database table for labels
        # In a real implementation, you would store label metadata in a database
        labels = []
        company_dir = UPLOAD_DIR / company.upper()
        
        if company_dir.exists():
            for file_path in company_dir.glob("*"):
                if file_path.is_file():
                    # Extract label ID from filename
                    label_id = file_path.stem
                    file_ext = file_path.suffix.lower()
                    
                    # Determine format
                    label_format = LabelFormat.BMP if file_ext == ".bmp" else LabelFormat.PNG if file_ext == ".png" else LabelFormat.JPEG
                    
                    # Get file stats
                    stat = file_path.stat()
                    
                    # Create mock box payload (in real implementation, get from database)
                    box_payload = BoxManagementPayload(
                        company=company,
                        transaction_no=transaction_no or "MOCK_TXN",
                        box_number=box_number or 1,
                        article_description="Mock Article",
                        sku_id=1,
                        net_weight=10.0,
                        gross_weight=12.0,
                        batch_number="MOCK_BATCH",
                        entry_date=datetime.now().isoformat()
                    )
                    
                    labels.append(LabelInfo(
                        label_id=label_id,
                        company=company,
                        transaction_no=transaction_no or "MOCK_TXN",
                        box_number=box_number or 1,
                        file_name=file_path.name,
                        file_path=str(file_path),
                        file_size=stat.st_size,
                        label_format=label_format,
                        status=LabelStatus.COMPLETED,
                        uploaded_at=datetime.fromtimestamp(stat.st_ctime),
                        box_management_payload=box_payload
                    ))
        
        # Apply pagination
        total = len(labels)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_labels = labels[start:end]
        
        return LabelListResponse(
            labels=paginated_labels,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=(total + per_page - 1) // per_page
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error listing labels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list labels: {str(e)}")

@router.get("/{label_id}", response_model=LabelInfo)
def get_label(
    label_id: str,
    company: str = Query(..., description="Company code (CFPL or CDPL)"),
    db: Session = Depends(get_db)
):
    """Get specific label information"""
    try:
        # Validate company
        if company.upper() not in ["CFPL", "CDPL"]:
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Look for the label file
        company_dir = UPLOAD_DIR / company.upper()
        label_files = list(company_dir.glob(f"{label_id}.*"))
        
        if not label_files:
            raise HTTPException(status_code=404, detail="Label not found")
        
        file_path = label_files[0]
        file_ext = file_path.suffix.lower()
        
        # Determine format
        label_format = LabelFormat.BMP if file_ext == ".bmp" else LabelFormat.PNG if file_ext == ".png" else LabelFormat.JPEG
        
        # Get file stats
        stat = file_path.stat()
        
        # Create mock box payload (in real implementation, get from database)
        box_payload = BoxManagementPayload(
            company=company,
            transaction_no="MOCK_TXN",
            box_number=1,
            article_description="Mock Article",
            sku_id=1,
            net_weight=10.0,
            gross_weight=12.0,
            batch_number="MOCK_BATCH",
            entry_date=datetime.now().isoformat()
        )
        
        return LabelInfo(
            label_id=label_id,
            company=company,
            transaction_no="MOCK_TXN",
            box_number=1,
            file_name=file_path.name,
            file_path=str(file_path),
            file_size=stat.st_size,
            label_format=label_format,
            status=LabelStatus.COMPLETED,
            uploaded_at=datetime.fromtimestamp(stat.st_ctime),
            box_management_payload=box_payload
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting label: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get label: {str(e)}")

@router.delete("/{label_id}", response_model=LabelDeleteResponse)
def delete_label(
    label_id: str,
    company: str = Query(..., description="Company code (CFPL or CDPL)"),
    db: Session = Depends(get_db)
):
    """Delete a label file"""
    try:
        # Validate company
        if company.upper() not in ["CFPL", "CDPL"]:
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Look for the label file
        company_dir = UPLOAD_DIR / company.upper()
        label_files = list(company_dir.glob(f"{label_id}.*"))
        
        if not label_files:
            raise HTTPException(status_code=404, detail="Label not found")
        
        file_path = label_files[0]
        
        # Delete the file
        file_path.unlink()
        
        logging.info(f"Label deleted: {label_id}, Company: {company}")
        
        return LabelDeleteResponse(
            label_id=label_id,
            status="deleted",
            message="Label deleted successfully",
            deleted_at=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting label: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete label: {str(e)}")

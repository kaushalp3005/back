from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import datetime, date, time
import logging
import os
import uuid
from pathlib import Path

from app.core.database import get_db
from app.services.invoice_extraction_service import get_invoice_extraction_service
from app.schemas.outward import (
    OutwardRecord, OutwardCreateRequest, OutwardUpdateRequest,
    OutwardResponse, OutwardListResponse, OutwardDeleteResponse, OutwardWithDetails,
    ArticleCreate, ArticleUpdate, ArticleResponse,
    BoxCreate, BoxUpdate, BoxResponse,
    ApprovalCreate, ApprovalUpdate, ApprovalResponse, ApprovalWithArticlesBoxes,
    ArticleForApproval, BoxForApproval,
    SitecodeResponse, TransporterResponse, SitecodeCreate, TransporterCreate
)

router = APIRouter(prefix="/outward", tags=["outward"])
logger = logging.getLogger(__name__)

# Business Head Email Mapping
BUSINESS_HEAD_EMAILS = {
    "Rakesh Ratra": "rakesh@candorfoods.in",
    "Prashant Pal": "prashant.pal@candorfoods.in",
    "Yash Gawdi": "yash@candorfoods.in",
    "Ajay Bajaj": "ajay@candorfoods.in"
}

def table_for_company(company: str) -> str:
    """Map company code to corresponding table name"""
    company_upper = company.upper()
    if company_upper == "CFPL":
        return "cfpl_outward"
    elif company_upper == "CDPL":
        return "cdpl_outward"
    else:
        raise ValueError(f"Invalid company: {company}. Must be CFPL or CDPL")

def uppercase_text_fields(data: dict) -> dict:
    """Convert specified text fields to uppercase"""
    uppercase_fields = [
        'consignment_no', 'invoice_no', 'customer_name', 'location', 
        'po_no', 'sitecode', 'transporter_name', 'vehicle_no',
        'billing_address', 'shipping_address'
    ]
    for field in uppercase_fields:
        if field in data and data[field] and isinstance(data[field], str):
            data[field] = data[field].upper()
    return data

def generate_lr_number() -> str:
    """Generate LR number in format YYYYMMDDHHMMSS (utility for frontend)"""
    return datetime.now().strftime('%Y%m%d%H%M%S')

# ============================================
# DROPDOWN ENDPOINTS
# ============================================

@router.get("/dropdowns/sitecodes", response_model=List[SitecodeResponse])
def get_sitecodes(
    active_only: bool = Query(True, description="Return only active sitecodes"),
    db: Session = Depends(get_db)
):
    """Get all sitecodes for dropdown"""
    try:
        where_clause = "WHERE is_active = true" if active_only else ""
        sql = text(f"""
            SELECT id, sitecode, is_active
            FROM sitecodes
            {where_clause}
            ORDER BY sitecode ASC
        """)
        
        results = db.execute(sql).fetchall()
        sitecodes = []
        for row in results:
            sitecodes.append(SitecodeResponse(
                id=row.id,
                sitecode=row.sitecode,
                is_active=row.is_active
            ))
        
        return sitecodes
        
    except Exception as e:
        logger.error(f"Error fetching sitecodes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sitecodes: {str(e)}")

@router.post("/dropdowns/sitecodes", response_model=SitecodeResponse)
def create_sitecode(
    sitecode_data: SitecodeCreate,
    db: Session = Depends(get_db)
):
    """Create new sitecode"""
    try:
        sitecode = sitecode_data.sitecode.upper()
        
        sql = text("""
            INSERT INTO sitecodes (sitecode)
            VALUES (:sitecode)
            RETURNING id, sitecode, is_active
        """)
        
        result = db.execute(sql, {"sitecode": sitecode}).fetchone()
        db.commit()
        
        return SitecodeResponse(
            id=result.id,
            sitecode=result.sitecode,
            is_active=result.is_active
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating sitecode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create sitecode: {str(e)}")

@router.get("/dropdowns/transporters", response_model=List[TransporterResponse])
def get_transporters(
    active_only: bool = Query(True, description="Return only active transporters"),
    db: Session = Depends(get_db)
):
    """Get all transporters for dropdown"""
    try:
        where_clause = "WHERE is_active = true" if active_only else ""
        sql = text(f"""
            SELECT id, transporter_name, contact_no, email, is_active
            FROM transporters
            {where_clause}
            ORDER BY transporter_name ASC
        """)
        
        results = db.execute(sql).fetchall()
        transporters = []
        for row in results:
            transporters.append(TransporterResponse(
                id=row.id,
                transporter_name=row.transporter_name,
                contact_no=row.contact_no,
                email=row.email,
                is_active=row.is_active
            ))
        
        return transporters
        
    except Exception as e:
        logger.error(f"Error fetching transporters: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch transporters: {str(e)}")

@router.post("/dropdowns/transporters", response_model=TransporterResponse)
def create_transporter(
    transporter_data: TransporterCreate,
    db: Session = Depends(get_db)
):
    """Create new transporter"""
    try:
        name = transporter_data.transporter_name.upper()
        
        sql = text("""
            INSERT INTO transporters (transporter_name, contact_no, email)
            VALUES (:name, :contact_no, :email)
            RETURNING id, transporter_name, contact_no, email, is_active
        """)
        
        result = db.execute(sql, {
            "name": name,
            "contact_no": transporter_data.contact_no,
            "email": transporter_data.email
        }).fetchone()
        db.commit()
        
        return TransporterResponse(
            id=result.id,
            transporter_name=result.transporter_name,
            contact_no=result.contact_no,
            email=result.email,
            is_active=result.is_active
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating transporter: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create transporter: {str(e)}")

@router.get("/utils/generate-lr-number")
def get_lr_number():
    """Generate LR number"""
    return {"lr_number": generate_lr_number()}

@router.get("/utils/business-head-email/{business_head}")
def get_business_head_email(business_head: str):
    """Get email for business head"""
    email = BUSINESS_HEAD_EMAILS.get(business_head)
    if not email:
        return {"business_head": business_head, "email": None}
    return {"business_head": business_head, "email": email}

# ============================================
# FILE UPLOAD ENDPOINTS
# ============================================

@router.post("/upload-invoice")
async def upload_invoice_files(
    files: List[UploadFile] = File(...),
    company: str = Query(..., description="Company code (CFPL or CDPL)")
):
    """
    Upload invoice files - returns file paths to include in outward record
    
    **Query Parameters:**
    - company: Company code (CFPL or CDPL)
    
    **Form Data:**
    - files: Multiple invoice files (.pdf, .jpg, .jpeg, .png, .doc, .docx)
    
    **Returns:**
    - Array of file paths to store in outward record
    """
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Allowed file extensions
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'}
        
        # Create upload directory if not exists
        upload_dir = Path("uploads/invoices")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        
        for file in files:
            # Get file extension
            file_extension = os.path.splitext(file.filename)[1].lower()
            
            if file_extension not in allowed_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(allowed_extensions)}"
                )
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            unique_filename = f"{company_upper}_INV_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
            file_path = upload_dir / unique_filename
            
            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            uploaded_files.append(str(file_path))
        
        logger.info(f"Uploaded {len(uploaded_files)} invoice files for company {company_upper}")
        
        return {
            "message": f"Successfully uploaded {len(uploaded_files)} invoice file(s)",
            "files": uploaded_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading invoice files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload invoice files: {str(e)}")

@router.post("/upload-pod")
async def upload_pod_files(
    files: List[UploadFile] = File(...),
    company: str = Query(..., description="Company code (CFPL or CDPL)")
):
    """
    Upload POD (Proof of Delivery) files - returns file paths to include in outward record
    
    **Query Parameters:**
    - company: Company code (CFPL or CDPL)
    
    **Form Data:**
    - files: Multiple POD files (.pdf, .jpg, .jpeg, .png, .doc, .docx)
    
    **Returns:**
    - Array of file paths to store in outward record
    """
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Allowed file extensions
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'}
        
        # Create upload directory if not exists
        upload_dir = Path("uploads/pod")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        
        for file in files:
            # Get file extension
            file_extension = os.path.splitext(file.filename)[1].lower()
            
            if file_extension not in allowed_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(allowed_extensions)}"
                )
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            unique_filename = f"{company_upper}_POD_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
            file_path = upload_dir / unique_filename
            
            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            uploaded_files.append(str(file_path))
        
        logger.info(f"Uploaded {len(uploaded_files)} POD files for company {company_upper}")
        
        return {
            "message": f"Successfully uploaded {len(uploaded_files)} POD file(s)",
            "files": uploaded_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading POD files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload POD files: {str(e)}")

@router.delete("/delete-file")
def delete_uploaded_file(
    file_path: str = Query(..., description="File path to delete")
):
    """
    Delete an uploaded file from server
    
    **Query Parameters:**
    - file_path: Path of the file to delete
    """
    try:
        # Verify file is in uploads directory (security check)
        if not file_path.startswith("uploads/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Delete physical file if exists
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return {
                "message": "File deleted successfully",
                "deleted_file": file_path
            }
        else:
            raise HTTPException(status_code=404, detail="File not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.post("/extract-invoice")
async def extract_invoice_data_endpoint(
    file: UploadFile = File(...),
    api_key: Optional[str] = Query(None, description="OpenAI API key (optional if set in env)")
):
    """
    Extract invoice data from uploaded file using OpenAI GPT-4o Vision
    
    **Form Data:**
    - file: Invoice file (PDF or Image)
    
    **Supported Formats:**
    - PDF: .pdf
    - Images: .jpg, .jpeg, .png, .webp, .gif, .bmp, .tiff, .tif
    
    **Query Parameters:**
    - api_key: OpenAI API key (optional if OPENAI_API_KEY env variable is set)
    
    **Returns:**
    - JSON with extracted invoice data
    
    **Example Response:**
    ```json
    {
        "success": true,
        "filename": "invoice.pdf",
        "file_type": "pdf",
        "extracted_data": {
            "invoice_number": "INV-2025-001",
            "po_number": "PO-123456",
            "customer_name": "ABC ENTERPRISES",
            "dispatch_date": "2025-10-10",
            "total_invoice_amount": 59000.00,
            "total_gst_amount": 9000.00,
            "billing_address": "123 MAIN STREET, MUMBAI",
            "shipping_address": "456 DELIVERY AVENUE, MUMBAI",
            "pincode": "400001"
        }
    }
    ```
    """
    try:
        # Validate file exists
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file uploaded."
            )
        
        # Read file bytes
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # Validate file size (max 10MB)
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File too large. Maximum size is 10MB."
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file uploaded."
            )
        
        # Get extraction service
        extraction_service = get_invoice_extraction_service(api_key)
        
        # Extract invoice data (service will validate file type)
        invoice_data = extraction_service.extract_from_bytes(file_bytes, file.filename)
        
        # Determine file type for response
        file_ext = file.filename.lower().split('.')[-1]
        file_type = "pdf" if file_ext == "pdf" else "image"
        
        logger.info(f"Successfully extracted invoice data from {file.filename}")
        
        return {
            "success": True,
            "filename": file.filename,
            "file_type": file_type,
            "extracted_data": invoice_data
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # File type or configuration errors
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # General extraction errors
        logger.error(f"Error extracting invoice data from {file.filename}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to extract invoice data: {str(e)}"
        )

# ============================================
# OUTWARD CRUD ENDPOINTS
# ============================================

@router.post("/{company}", response_model=OutwardResponse)
def create_outward_record(
    company: str,
    request: OutwardCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new outward record from consignment form"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Prepare data and convert to uppercase
        data = request.dict()
        data = uppercase_text_fields(data)
        data['company_name'] = company_upper
        
        # Handle null fields that have NOT NULL constraints - provide default values
        if data.get('location') is None or data.get('location') == '':
            data['location'] = 'NOT SPECIFIED'
        
        if data.get('billing_address') is None or data.get('billing_address') == '':
            data['billing_address'] = 'NOT SPECIFIED'
            
        if data.get('shipping_address') is None or data.get('shipping_address') == '':
            data['shipping_address'] = 'NOT SPECIFIED'
            
        if data.get('po_no') is None or data.get('po_no') == '':
            data['po_no'] = 'NOT SPECIFIED'
            
        if data.get('sitecode') is None or data.get('sitecode') == '':
            data['sitecode'] = 'NOT SPECIFIED'
            
        if data.get('transporter_name') is None or data.get('transporter_name') == '':
            data['transporter_name'] = 'NOT SPECIFIED'
            
        if data.get('vehicle_no') is None or data.get('vehicle_no') == '':
            data['vehicle_no'] = 'NOT SPECIFIED'
            
        # Note: lr_no can be a numeric field (bigint) in some schemas, so we leave it as None if not provided
        # If the database schema requires a value, consider changing the column to allow NULL or change to text type
        if data.get('lr_no') is None or data.get('lr_no') == '':
            data['lr_no'] = None  # Keep as None instead of 'NOT SPECIFIED' for numeric fields
            
        if data.get('pincode') is None:
            data['pincode'] = 0
        
        # Auto-set business head email if not provided
        if data.get('business_head') and not data.get('business_head_email'):
            data['business_head_email'] = BUSINESS_HEAD_EMAILS.get(data['business_head'])
        
        # Note: All auto-calculated fields (totals, weights) are calculated in frontend
        
        # Insert new record
        insert_sql = text(f"""
            INSERT INTO {table_name} (
                company_name, consignment_no, invoice_no, customer_name, delivery_status,
                location, po_no, boxes, net_weight, gross_weight,
                business_head, business_head_name, business_head_email,
                appt_date, appt_time, sitecode, asn_id,
                transporter_name, vehicle_no, lr_no,
                dispatch_date, estimated_delivery_date, actual_delivery_date,
                invoice_amount, invoice_gst_amount, total_invoice_amount,
                freight_amount, freight_gst_amount, total_freight_amount,
                billing_address, shipping_address, pincode,
                invoice_files, pod_files,
                created_at, updated_at
            ) VALUES (
                :company_name, :consignment_no, :invoice_no, :customer_name, :delivery_status,
                :location, :po_no, :boxes, :net_weight, :gross_weight,
                :business_head, :business_head_name, :business_head_email,
                :appt_date, :appt_time, :sitecode, :asn_id,
                :transporter_name, :vehicle_no, :lr_no,
                :dispatch_date, :estimated_delivery_date, :actual_delivery_date,
                :invoice_amount, :invoice_gst_amount, :total_invoice_amount,
                :freight_amount, :freight_gst_amount, :total_freight_amount,
                :billing_address, :shipping_address, :pincode,
                :invoice_files, :pod_files,
                NOW(), NOW()
            ) RETURNING id, created_at, updated_at
        """)
        
        result = db.execute(insert_sql, data).fetchone()
        db.commit()
        
        # Get the created record
        created_record = get_outward_record_by_id(company, result.id, db)
        
        logger.info(f"Created outward record {result.id} for company {company_upper}")
        return created_record
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating outward record: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create outward record: {str(e)}")

@router.get("/{company}", response_model=OutwardListResponse)
def list_outward_records(
    company: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=1000, description="Items per page"),
    search: Optional[str] = Query(None, description="Search across all fields"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    delivery_status: Optional[str] = Query(None, description="Filter by delivery status"),
    from_date: Optional[str] = Query(None, description="Filter from dispatch date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to dispatch date (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("dispatch_date", description="Sort field"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db)
):
    """List outward records with filtering and pagination"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        if search:
            where_clauses.append("""
                (LOWER(consignment_no) LIKE :search OR 
                 LOWER(invoice_no) LIKE :search OR 
                 LOWER(customer_name) LIKE :search OR 
                 LOWER(transporter_name) LIKE :search OR 
                 LOWER(vehicle_no) LIKE :search)
            """)
            params["search"] = f"%{search.lower()}%"
        
        if customer_name:
            where_clauses.append("LOWER(customer_name) LIKE :customer_name")
            params["customer_name"] = f"%{customer_name.lower()}%"
        
        if delivery_status:
            where_clauses.append("LOWER(delivery_status) = :delivery_status")
            params["delivery_status"] = delivery_status.lower()
        
        if from_date:
            where_clauses.append("dispatch_date >= :from_date")
            params["from_date"] = from_date
        
        if to_date:
            where_clauses.append("dispatch_date <= :to_date")
            params["to_date"] = to_date
        
        where_sql = " AND ".join(where_clauses)
        
        # Validate sort field
        valid_sort_fields = [
            "id", "consignment_no", "invoice_no", "customer_name", "dispatch_date",
            "estimated_delivery_date", "actual_delivery_date", "delivery_status",
            "total_invoice_amount", "total_freight_amount", "created_at"
        ]
        
        if sort_by not in valid_sort_fields:
            sort_by = "dispatch_date"
        
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        
        # Count total records
        count_sql = text(f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE {where_sql}
        """)
        total = db.execute(count_sql, params).scalar_one()
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get paginated records
        list_sql = text(f"""
            SELECT *
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {sort_by} {sort_direction}
            LIMIT :limit OFFSET :offset
        """)
        
        results = db.execute(list_sql, {**params, "limit": per_page, "offset": offset}).fetchall()
        
        # Format records
        records = []
        for row in results:
            record_dict = dict(row._mapping)
            # Convert datetime objects to strings
            for key, value in record_dict.items():
                if isinstance(value, datetime):
                    record_dict[key] = value.isoformat()
                elif isinstance(value, date):
                    record_dict[key] = value.isoformat()
                elif isinstance(value, time):
                    record_dict[key] = value.isoformat()
            
            records.append(OutwardResponse(**record_dict))
        
        total_pages = (total + per_page - 1) // per_page
        
        logger.info(f"Retrieved {len(records)} outward records for company {company_upper}")
        
        return OutwardListResponse(
            records=records,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing outward records: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list outward records: {str(e)}")

@router.get("/{company}/{record_id}", response_model=OutwardWithDetails)
def get_outward_record(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """Get specific outward record by ID with articles, boxes, and approval"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get outward record
        outward = get_outward_record_by_id(company, record_id, db)
        
        # Get articles
        articles = get_articles_for_outward(record_id, company_upper, db)
        
        # Get boxes
        boxes = get_boxes_for_outward(record_id, company_upper, db)
        
        # Get approval
        approval = get_approval_for_outward(record_id, company_upper, db)
        
        return OutwardWithDetails(
            **outward.dict(),
            articles=articles,
            box_details=boxes,  # Using box_details instead of boxes
            approval=approval
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting outward record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get outward record: {str(e)}")

@router.get("/{company}/consignment/{consignment_no}", response_model=OutwardWithDetails)
def get_outward_record_by_consignment(
    company: str,
    consignment_no: str,
    db: Session = Depends(get_db)
):
    """
    Get outward record details by consignment number with articles, boxes, and approval
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    - consignment_no: Consignment number to search for
    
    **Returns:**
    - Complete outward record with all associated articles, boxes, and approval details
    
    **Example Response:**
    ```json
    {
        "id": 1,
        "company_name": "CFPL",
        "consignment_no": "CFPL001",
        "invoice_no": "INV-2025-001",
        "customer_name": "ABC ENTERPRISES",
        "delivery_status": "IN_TRANSIT",
        "location": "MUMBAI",
        "po_no": "PO-123456",
        "boxes": 5,
        "net_weight": "2500 gm",
        "gross_weight": "2600 gm",
        "business_head": "Rakesh Ratra",
        "business_head_name": "Rakesh Ratra",
        "business_head_email": "rakesh@candorfoods.in",
        "appt_date": "2025-01-15",
        "appt_time": "10:00:00",
        "sitecode": "MUM001",
        "asn_id": "ASN-001",
        "transporter_name": "FAST LOGISTICS",
        "vehicle_no": "MH01AB1234",
        "lr_no": "LR123456",
        "dispatch_date": "2025-01-10",
        "estimated_delivery_date": "2025-01-12",
        "actual_delivery_date": null,
        "invoice_amount": 50000.00,
        "invoice_gst_amount": 9000.00,
        "total_invoice_amount": 59000.00,
        "freight_amount": 2000.00,
        "freight_gst_amount": 360.00,
        "total_freight_amount": 2360.00,
        "billing_address": "123 MAIN STREET, MUMBAI",
        "shipping_address": "456 DELIVERY AVENUE, MUMBAI",
        "pincode": 400001,
        "invoice_files": ["uploads/invoices/CFPL_INV_20250110123456_abc123.pdf"],
        "pod_files": [],
        "created_at": "2025-01-10T10:30:00",
        "updated_at": "2025-01-10T10:30:00",
        "articles": [
            {
                "id": 1,
                "outward_id": 1,
                "company_name": "CFPL",
                "material_type": "FG",
                "item_category": "SNACKS",
                "sub_category": "CHIPS",
                "item_description": "POTATO CHIPS - CLASSIC",
                "sku_id": "SKU001",
                "quantity_units": 10,
                "uom": "BOX",
                "pack_size_gm": 100.0,
                "no_of_packets": 20,
                "net_weight_gm": 2000.0,
                "gross_weight_gm": 2100.0,
                "batch_number": "BATCH001",
                "unit_rate": 50.0,
                "created_at": "2025-01-10T10:30:00",
                "updated_at": "2025-01-10T10:30:00"
            }
        ],
        "box_details": [
            {
                "id": 1,
                "article_id": 1,
                "outward_id": 1,
                "company_name": "CFPL",
                "box_number": 1,
                "article_name": "POTATO CHIPS - CLASSIC",
                "lot_number": "LOT001",
                "net_weight_gm": 200.0,
                "gross_weight_gm": 210.0,
                "created_at": "2025-01-10T10:30:00",
                "updated_at": "2025-01-10T10:30:00"
            }
        ],
        "approval": {
            "id": 1,
            "outward_id": 1,
            "company_name": "CFPL",
            "approval_status": "APPROVED",
            "approval_authority": "RAKESH RATRA",
            "approval_date": "2025-01-10",
            "remarks": "Approved for dispatch",
            "created_at": "2025-01-10T10:30:00",
            "updated_at": "2025-01-10T10:30:00"
        }
    }
    ```
    """
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Search for outward record by consignment number
        sql = text(f"""
            SELECT *
            FROM {table_name}
            WHERE UPPER(consignment_no) = UPPER(:consignment_no)
        """)
        
        result = db.execute(sql, {"consignment_no": consignment_no}).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail=f"Outward record with consignment number '{consignment_no}' not found for company {company_upper}"
            )
        
        # Format outward record
        record_dict = dict(result._mapping)
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
            elif isinstance(value, time):
                record_dict[key] = value.isoformat()
        
        outward = OutwardResponse(**record_dict)
        record_id = result.id
        
        # Get articles
        articles = get_articles_for_outward(record_id, company_upper, db)
        
        # Get boxes
        boxes = get_boxes_for_outward(record_id, company_upper, db)
        
        # Get approval
        approval = get_approval_for_outward(record_id, company_upper, db)
        
        logger.info(f"Retrieved outward record for consignment {consignment_no} (ID: {record_id})")
        
        return OutwardWithDetails(
            **outward.dict(),
            articles=articles,
            box_details=boxes,
            approval=approval
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting outward record by consignment {consignment_no}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get outward record by consignment: {str(e)}")

def get_outward_record_by_id(company: str, record_id: int, db: Session) -> OutwardResponse:
    """Helper function to get outward record by ID"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        sql = text(f"""
            SELECT *
            FROM {table_name}
            WHERE id = :record_id
        """)
        
        result = db.execute(sql, {"record_id": record_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Outward record {record_id} not found")
        
        # Format record
        record_dict = dict(result._mapping)
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
            elif isinstance(value, time):
                record_dict[key] = value.isoformat()
        
        return OutwardResponse(**record_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting outward record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get outward record: {str(e)}")

@router.put("/{company}/{record_id}", response_model=OutwardResponse)
def update_outward_record(
    company: str,
    record_id: int,
    request: OutwardUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update existing outward record"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Check if record exists
        check_sql = text(f"""
            SELECT id FROM {table_name} WHERE id = :record_id
        """)
        existing_record = db.execute(check_sql, {"record_id": record_id}).fetchone()
        
        if not existing_record:
            raise HTTPException(status_code=404, detail=f"Outward record {record_id} not found")
        
        # Prepare data and convert to uppercase
        data = request.outward_data.dict()
        data = uppercase_text_fields(data)
        data['record_id'] = record_id
        
        # Handle null fields that have NOT NULL constraints - provide default values
        if data.get('location') is None or data.get('location') == '':
            data['location'] = 'NOT SPECIFIED'
        
        if data.get('billing_address') is None or data.get('billing_address') == '':
            data['billing_address'] = 'NOT SPECIFIED'
            
        if data.get('shipping_address') is None or data.get('shipping_address') == '':
            data['shipping_address'] = 'NOT SPECIFIED'
            
        if data.get('po_no') is None or data.get('po_no') == '':
            data['po_no'] = 'NOT SPECIFIED'
            
        if data.get('sitecode') is None or data.get('sitecode') == '':
            data['sitecode'] = 'NOT SPECIFIED'
            
        if data.get('transporter_name') is None or data.get('transporter_name') == '':
            data['transporter_name'] = 'NOT SPECIFIED'
            
        if data.get('vehicle_no') is None or data.get('vehicle_no') == '':
            data['vehicle_no'] = 'NOT SPECIFIED'
            
        # Note: lr_no can be a numeric field (bigint) in some schemas, so we leave it as None if not provided
        # If the database schema requires a value, consider changing the column to allow NULL or change to text type
        if data.get('lr_no') is None or data.get('lr_no') == '':
            data['lr_no'] = None  # Keep as None instead of 'NOT SPECIFIED' for numeric fields
            
        if data.get('pincode') is None:
            data['pincode'] = 0
        
        # Auto-set business head email if not provided
        if data.get('business_head') and not data.get('business_head_email'):
            data['business_head_email'] = BUSINESS_HEAD_EMAILS.get(data['business_head'])
        
        # Note: All auto-calculated fields (totals, weights) are calculated in frontend
        
        # Update record
        update_sql = text(f"""
            UPDATE {table_name} SET
                consignment_no = :consignment_no,
                invoice_no = :invoice_no,
                customer_name = :customer_name,
                delivery_status = :delivery_status,
                location = :location,
                po_no = :po_no,
                boxes = :boxes,
                net_weight = :net_weight,
                gross_weight = :gross_weight,
                business_head = :business_head,
                business_head_name = :business_head_name,
                business_head_email = :business_head_email,
                appt_date = :appt_date,
                appt_time = :appt_time,
                sitecode = :sitecode,
                asn_id = :asn_id,
                transporter_name = :transporter_name,
                vehicle_no = :vehicle_no,
                lr_no = :lr_no,
                dispatch_date = :dispatch_date,
                estimated_delivery_date = :estimated_delivery_date,
                actual_delivery_date = :actual_delivery_date,
                invoice_amount = :invoice_amount,
                invoice_gst_amount = :invoice_gst_amount,
                total_invoice_amount = :total_invoice_amount,
                freight_amount = :freight_amount,
                freight_gst_amount = :freight_gst_amount,
                total_freight_amount = :total_freight_amount,
                billing_address = :billing_address,
                shipping_address = :shipping_address,
                pincode = :pincode,
                invoice_files = :invoice_files,
                pod_files = :pod_files,
                updated_at = NOW()
            WHERE id = :record_id
        """)
        
        db.execute(update_sql, data)
        db.commit()
        
        # Get updated record
        updated_record = get_outward_record_by_id(company, record_id, db)
        
        logger.info(f"Updated outward record {record_id} for company {company_upper}")
        return updated_record
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating outward record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update outward record: {str(e)}")

@router.delete("/{company}/{record_id}", response_model=OutwardDeleteResponse)
def delete_outward_record(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """Delete outward record and all associated articles, boxes, and approvals"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Get record details before deletion
        get_sql = text(f"""
            SELECT consignment_no FROM {table_name} WHERE id = :record_id
        """)
        result = db.execute(get_sql, {"record_id": record_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Outward record {record_id} not found")
        
        # Delete associated articles (boxes will be cascade deleted)
        delete_articles_sql = text("""
            DELETE FROM outward_articles 
            WHERE outward_id = :record_id AND company_name = :company_name
        """)
        db.execute(delete_articles_sql, {"record_id": record_id, "company_name": company_upper})
        
        # Delete approval
        delete_approval_sql = text("""
            DELETE FROM outward_approvals 
            WHERE outward_id = :record_id AND company_name = :company_name
        """)
        db.execute(delete_approval_sql, {"record_id": record_id, "company_name": company_upper})
        
        # Delete outward record
        delete_sql = text(f"""
            DELETE FROM {table_name} WHERE id = :record_id
        """)
        db.execute(delete_sql, {"record_id": record_id})
        db.commit()
        
        logger.info(f"Deleted outward record {record_id} for company {company_upper}")
        
        return OutwardDeleteResponse(
            id=record_id,
            consignment_no=result.consignment_no,
            status="deleted",
            message="Outward record and all associated data deleted successfully",
            deleted_at=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting outward record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete outward record: {str(e)}")

# ============================================
# ARTICLE MANAGEMENT ENDPOINTS
# ============================================

@router.post("/{company}/{record_id}/articles", response_model=ArticleResponse)
def create_article(
    company: str,
    record_id: int,
    article: ArticleCreate,
    db: Session = Depends(get_db)
):
    """Create new article for outward record"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Verify outward record exists
        get_outward_record_by_id(company, record_id, db)
        
        # Note: batch_number and net_weight_gm are calculated in frontend
        
        # Insert article
        insert_sql = text("""
            INSERT INTO outward_articles (
                outward_id, company_name, material_type, item_category, sub_category,
                item_description, sku_id, quantity_units, uom, pack_size_gm, no_of_packets,
                net_weight_gm, gross_weight_gm, batch_number, unit_rate,
                created_at, updated_at
            ) VALUES (
                :outward_id, :company_name, :material_type, :item_category, :sub_category,
                :item_description, :sku_id, :quantity_units, :uom, :pack_size_gm, :no_of_packets,
                :net_weight_gm, :gross_weight_gm, :batch_number, :unit_rate,
                NOW(), NOW()
            ) RETURNING id, created_at, updated_at
        """)
        
        data = article.dict()
        data['outward_id'] = record_id
        data['company_name'] = company_upper
        
        result = db.execute(insert_sql, data).fetchone()
        article_id = result.id
        
        # Auto-generate boxes for BOX/CARTON UOM
        if article.uom.upper() in ('BOX', 'CARTON') and article.quantity_units > 0:
            create_boxes_for_article(
                article_id, record_id, company_upper, 
                int(article.quantity_units), article.item_description,
                article.pack_size_gm, article.no_of_packets, db
            )
        
        # Update total boxes in outward record
        update_outward_totals(record_id, company_upper, db)
        
        db.commit()
        
        # Get created article
        created_article = get_article_by_id(article_id, db)
        
        logger.info(f"Created article {article_id} for outward {record_id}")
        return created_article
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating article: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create article: {str(e)}")

@router.get("/{company}/{record_id}/articles", response_model=List[ArticleResponse])
def list_articles(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """Get all articles for outward record"""
    try:
        company_upper = company.upper()
        return get_articles_for_outward(record_id, company_upper, db)
        
    except Exception as e:
        logger.error(f"Error listing articles: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list articles: {str(e)}")

def get_articles_for_outward(outward_id: int, company: str, db: Session) -> List[ArticleResponse]:
    """Helper function to get articles for outward"""
    sql = text("""
        SELECT *
        FROM outward_articles
        WHERE outward_id = :outward_id AND company_name = :company_name
        ORDER BY id ASC
    """)
    
    results = db.execute(sql, {"outward_id": outward_id, "company_name": company}).fetchall()
    
    articles = []
    for row in results:
        record_dict = dict(row._mapping)
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
        articles.append(ArticleResponse(**record_dict))
    
    return articles

def get_article_by_id(article_id: int, db: Session) -> ArticleResponse:
    """Helper function to get article by ID"""
    sql = text("""
        SELECT *
        FROM outward_articles
        WHERE id = :article_id
    """)
    
    result = db.execute(sql, {"article_id": article_id}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    
    record_dict = dict(result._mapping)
    for key, value in record_dict.items():
        if isinstance(value, datetime):
            record_dict[key] = value.isoformat()
        elif isinstance(value, date):
            record_dict[key] = value.isoformat()
    
    return ArticleResponse(**record_dict)

@router.put("/{company}/{record_id}/articles/{article_id}", response_model=ArticleResponse)
def update_article(
    company: str,
    record_id: int,
    article_id: int,
    article: ArticleUpdate,
    db: Session = Depends(get_db)
):
    """Update article"""
    try:
        company_upper = company.upper()
        
        # Note: net_weight_gm is calculated in frontend
        
        # Get existing article to check UOM change
        existing = get_article_by_id(article_id, db)
        
        # Update article
        update_sql = text("""
            UPDATE outward_articles SET
                material_type = :material_type,
                item_category = :item_category,
                sub_category = :sub_category,
                item_description = :item_description,
                sku_id = :sku_id,
                quantity_units = :quantity_units,
                uom = :uom,
                pack_size_gm = :pack_size_gm,
                no_of_packets = :no_of_packets,
                net_weight_gm = :net_weight_gm,
                gross_weight_gm = :gross_weight_gm,
                unit_rate = :unit_rate,
                updated_at = NOW()
            WHERE id = :article_id
        """)
        
        data = article.dict()
        data['article_id'] = article_id
        
        db.execute(update_sql, data)
        
        # Handle boxes if UOM is BOX/CARTON
        if article.uom.upper() in ('BOX', 'CARTON'):
            # Delete existing boxes and recreate
            delete_boxes_for_article(article_id, db)
            if article.quantity_units > 0:
                create_boxes_for_article(
                    article_id, record_id, company_upper,
                    int(article.quantity_units), article.item_description,
                    article.pack_size_gm, article.no_of_packets, db
                )
        else:
            # If UOM changed from BOX/CARTON to something else, delete boxes
            if existing.uom.upper() in ('BOX', 'CARTON'):
                delete_boxes_for_article(article_id, db)
        
        # Update totals
        update_outward_totals(record_id, company_upper, db)
        
        db.commit()
        
        updated_article = get_article_by_id(article_id, db)
        
        logger.info(f"Updated article {article_id}")
        return updated_article
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating article: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update article: {str(e)}")

@router.delete("/{company}/{record_id}/articles/{article_id}")
def delete_article(
    company: str,
    record_id: int,
    article_id: int,
    db: Session = Depends(get_db)
):
    """Delete article and associated boxes"""
    try:
        company_upper = company.upper()
        
        # Delete article (boxes will be cascade deleted)
        delete_sql = text("""
            DELETE FROM outward_articles
            WHERE id = :article_id
        """)
        
        result = db.execute(delete_sql, {"article_id": article_id})
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
        
        # Update totals
        update_outward_totals(record_id, company_upper, db)
        
        db.commit()
        
        logger.info(f"Deleted article {article_id}")
        return {"message": "Article deleted successfully", "article_id": article_id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting article: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete article: {str(e)}")

# ============================================
# BOX MANAGEMENT ENDPOINTS
# ============================================

@router.get("/{company}/{record_id}/boxes", response_model=List[BoxResponse])
def list_boxes(
    company: str,
    record_id: int,
    article_id: Optional[int] = Query(None, description="Filter by article ID"),
    db: Session = Depends(get_db)
):
    """Get all boxes for outward record"""
    try:
        company_upper = company.upper()
        
        if article_id:
            sql = text("""
                SELECT *
                FROM outward_boxes
                WHERE outward_id = :outward_id AND company_name = :company_name AND article_id = :article_id
                ORDER BY article_id, box_number ASC
            """)
            results = db.execute(sql, {
                "outward_id": record_id,
                "company_name": company_upper,
                "article_id": article_id
            }).fetchall()
        else:
            sql = text("""
                SELECT *
                FROM outward_boxes
                WHERE outward_id = :outward_id AND company_name = :company_name
                ORDER BY article_id, box_number ASC
            """)
            results = db.execute(sql, {
                "outward_id": record_id,
                "company_name": company_upper
            }).fetchall()
        
        boxes = []
        for row in results:
            record_dict = dict(row._mapping)
            for key, value in record_dict.items():
                if isinstance(value, datetime):
                    record_dict[key] = value.isoformat()
                elif isinstance(value, date):
                    record_dict[key] = value.isoformat()
            boxes.append(BoxResponse(**record_dict))
        
        return boxes
        
    except Exception as e:
        logger.error(f"Error listing boxes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list boxes: {str(e)}")

def get_boxes_for_outward(outward_id: int, company: str, db: Session) -> List[BoxResponse]:
    """Helper function to get boxes for outward"""
    sql = text("""
        SELECT *
        FROM outward_boxes
        WHERE outward_id = :outward_id AND company_name = :company_name
        ORDER BY article_id, box_number ASC
    """)
    
    results = db.execute(sql, {"outward_id": outward_id, "company_name": company}).fetchall()
    
    boxes = []
    for row in results:
        record_dict = dict(row._mapping)
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
        boxes.append(BoxResponse(**record_dict))
    
    return boxes

def create_boxes_for_article(
    article_id: int, outward_id: int, company: str, 
    quantity: int, article_name: str,
    pack_size_gm: float, no_of_packets: int,
    db: Session
):
    """Helper function to create boxes for an article (only box_number is auto-generated)"""
    # Net weight per box calculated from article data
    net_weight_per_box = pack_size_gm * no_of_packets
    
    for box_num in range(1, quantity + 1):
        insert_sql = text("""
            INSERT INTO outward_boxes (
                article_id, outward_id, company_name, box_number, article_name,
                net_weight_gm, gross_weight_gm, created_at, updated_at
            ) VALUES (
                :article_id, :outward_id, :company_name, :box_number, :article_name,
                :net_weight_gm, :gross_weight_gm, NOW(), NOW()
            )
        """)
        
        db.execute(insert_sql, {
            "article_id": article_id,
            "outward_id": outward_id,
            "company_name": company,
            "box_number": box_num,  # Only this is auto-generated
            "article_name": article_name,
            "net_weight_gm": net_weight_per_box,
            "gross_weight_gm": net_weight_per_box  # Default gross = net
        })

def delete_boxes_for_article(article_id: int, db: Session):
    """Helper function to delete all boxes for an article"""
    delete_sql = text("""
        DELETE FROM outward_boxes WHERE article_id = :article_id
    """)
    db.execute(delete_sql, {"article_id": article_id})

@router.put("/{company}/{record_id}/boxes/{box_id}", response_model=BoxResponse)
def update_box(
    company: str,
    record_id: int,
    box_id: int,
    box_update: BoxUpdate,
    db: Session = Depends(get_db)
):
    """Update box details (lot number, gross weight)"""
    try:
        update_fields = []
        data = {"box_id": box_id}
        
        if box_update.lot_number is not None:
            update_fields.append("lot_number = :lot_number")
            data["lot_number"] = box_update.lot_number
        
        if box_update.gross_weight_gm is not None:
            update_fields.append("gross_weight_gm = :gross_weight_gm")
            data["gross_weight_gm"] = box_update.gross_weight_gm
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_sql = text(f"""
            UPDATE outward_boxes SET
                {', '.join(update_fields)},
                updated_at = NOW()
            WHERE id = :box_id
        """)
        
        result = db.execute(update_sql, data)
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Box {box_id} not found")
        
        db.commit()
        
        # Get updated box
        get_sql = text("""
            SELECT * FROM outward_boxes WHERE id = :box_id
        """)
        result = db.execute(get_sql, {"box_id": box_id}).fetchone()
        
        record_dict = dict(result._mapping)
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
        
        logger.info(f"Updated box {box_id}")
        return BoxResponse(**record_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating box: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update box: {str(e)}")

@router.delete("/{company}/{record_id}/boxes/{box_id}")
def delete_box(
    company: str,
    record_id: int,
    box_id: int,
    db: Session = Depends(get_db)
):
    """Delete a box and decrement article quantity"""
    try:
        company_upper = company.upper()
        
        # Get box details
        get_sql = text("""
            SELECT article_id FROM outward_boxes WHERE id = :box_id
        """)
        result = db.execute(get_sql, {"box_id": box_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Box {box_id} not found")
        
        article_id = result.article_id
        
        # Delete box
        delete_sql = text("""
            DELETE FROM outward_boxes WHERE id = :box_id
        """)
        db.execute(delete_sql, {"box_id": box_id})
        
        # Decrement article quantity
        update_article_sql = text("""
            UPDATE outward_articles
            SET quantity_units = quantity_units - 1,
                updated_at = NOW()
            WHERE id = :article_id AND quantity_units > 0
        """)
        db.execute(update_article_sql, {"article_id": article_id})
        
        # Renumber remaining boxes for this article
        renumber_sql = text("""
            WITH numbered_boxes AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY id) as new_number
                FROM outward_boxes
                WHERE article_id = :article_id
            )
            UPDATE outward_boxes
            SET box_number = numbered_boxes.new_number
            FROM numbered_boxes
            WHERE outward_boxes.id = numbered_boxes.id
        """)
        db.execute(renumber_sql, {"article_id": article_id})
        
        # Update totals
        update_outward_totals(record_id, company_upper, db)
        
        db.commit()
        
        logger.info(f"Deleted box {box_id} and renumbered article {article_id} boxes")
        return {"message": "Box deleted successfully", "box_id": box_id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting box: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete box: {str(e)}")

# ============================================
# APPROVAL ENDPOINTS
# ============================================

@router.post("/{company}/{record_id}/approval", response_model=ApprovalResponse)
def create_or_update_approval(
    company: str,
    record_id: int,
    approval: ApprovalCreate,
    db: Session = Depends(get_db)
):
    """Create or update approval for outward record (simple approval only)"""
    try:
        logger.info(f"🔍 APPROVAL DEBUG: Received approval request for {company}/{record_id}")
        logger.info(f"🔍 APPROVAL DEBUG: Approval data: {approval.dict()}")
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Verify outward record exists
        get_outward_record_by_id(company, record_id, db)
        
        # Check if approval exists
        check_sql = text("""
            SELECT id FROM outward_approvals
            WHERE outward_id = :outward_id AND company_name = :company_name
        """)
        existing = db.execute(check_sql, {
            "outward_id": record_id,
            "company_name": company_upper
        }).fetchone()
        
        if existing:
            # Update existing approval
            update_sql = text("""
                UPDATE outward_approvals SET
                    approval_status = :approval_status,
                    approval_authority = :approval_authority,
                    approval_date = :approval_date,
                    remarks = :remarks,
                    updated_at = NOW()
                WHERE outward_id = :outward_id AND company_name = :company_name
            """)
            
            db.execute(update_sql, {
                **approval.dict(),
                "outward_id": record_id,
                "company_name": company_upper
            })
            approval_id = existing.id
        else:
            # Create new approval
            insert_sql = text("""
                INSERT INTO outward_approvals (
                    outward_id, company_name, approval_status, approval_authority,
                    approval_date, remarks, created_at, updated_at
                ) VALUES (
                    :outward_id, :company_name, :approval_status, :approval_authority,
                    :approval_date, :remarks, NOW(), NOW()
                ) RETURNING id
            """)
            
            result = db.execute(insert_sql, {
                **approval.dict(),
                "outward_id": record_id,
                "company_name": company_upper
            })
            approval_id = result.fetchone().id
        
        db.commit()
        
        # Get approval
        approval_response = get_approval_for_outward(record_id, company_upper, db)
        
        logger.info(f"Created/updated approval for outward {record_id}")
        return approval_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating/updating approval: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create/update approval: {str(e)}")

@router.post("/{company}/approval/submit", response_model=ApprovalResponse)
def submit_approval_with_articles_boxes(
    company: str,
    request: ApprovalWithArticlesBoxes,
    db: Session = Depends(get_db)
):
    """
    Submit approval with articles and boxes in one transaction
    
    **Request Body:**
    - consignment_id: Outward record ID
    - approval_authority: Name of approver
    - approval_date: Date of approval
    - approval_status: Status (approved/rejected/pending)
    - approval_remark: Optional remarks
    - articles: Array of article objects
    - boxes: Array of box objects
    """
    try:
        logger.info(f"🔍 APPROVAL SUBMIT DEBUG: Received approval submit request for {company}")
        logger.info(f"🔍 APPROVAL SUBMIT DEBUG: Request data: {request.dict()}")
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        record_id = request.consignment_id
        
        # Verify outward record exists
        get_outward_record_by_id(company, record_id, db)
        
        # 1. Delete existing articles and boxes (if any)
        delete_articles_sql = text("""
            DELETE FROM outward_articles 
            WHERE outward_id = :outward_id AND company_name = :company_name
        """)
        db.execute(delete_articles_sql, {"outward_id": record_id, "company_name": company_upper})
        
        # 2. Insert articles
        article_id_map = {}  # Map frontend ID to database ID
        
        for article_data in request.articles:
            insert_article_sql = text("""
                INSERT INTO outward_articles (
                    outward_id, company_name, material_type, item_category, sub_category,
                    item_description, sku_id, quantity_units, uom, pack_size_gm, no_of_packets,
                    net_weight_gm, gross_weight_gm, batch_number, unit_rate,
                    created_at, updated_at
                ) VALUES (
                    :outward_id, :company_name, :material_type, :item_category, :sub_category,
                    :item_description, :sku_id, :quantity_units, :uom, :pack_size_gm, :no_of_packets,
                    :net_weight_gm, :gross_weight_gm, :batch_number, :unit_rate,
                    NOW(), NOW()
                ) RETURNING id
            """)
            
            # Map frontend field names to database field names
            article_dict = {
                "outward_id": record_id,
                "company_name": company_upper,
                "material_type": article_data.material_type,
                "item_category": article_data.item_category,
                "sub_category": article_data.sub_category,
                "item_description": article_data.item_description,
                "sku_id": str(article_data.sku_id) if article_data.sku_id else None,
                "quantity_units": article_data.quantity_units,
                "uom": article_data.uom,
                "pack_size_gm": article_data.pack_size_gm,
                "no_of_packets": article_data.no_of_packets,
                "net_weight_gm": article_data.net_weight_gm,
                "gross_weight_gm": article_data.gross_weight_gm,
                "batch_number": article_data.batch_number,
                "unit_rate": article_data.unit_rate
            }
            
            result = db.execute(insert_article_sql, article_dict)
            new_article_id = result.fetchone().id
            
            # Map frontend ID to database ID
            article_id_map[article_data.id] = new_article_id
        
        # 3. Insert boxes
        for box_data in request.boxes:
            # Find corresponding article database ID
            # Match box to article by article name/description
            article_db_id = None
            for article in request.articles:
                if article.item_description == box_data.article_name:
                    article_db_id = article_id_map.get(article.id)
                    break
            
            if not article_db_id:
                logger.warning(f"Could not find article for box {box_data.box_number}")
                continue
            
            insert_box_sql = text("""
                INSERT INTO outward_boxes (
                    article_id, outward_id, company_name, box_number, article_name,
                    lot_number, net_weight_gm, gross_weight_gm,
                    created_at, updated_at
                ) VALUES (
                    :article_id, :outward_id, :company_name, :box_number, :article_name,
                    :lot_number, :net_weight_gm, :gross_weight_gm,
                    NOW(), NOW()
                )
            """)
            
            db.execute(insert_box_sql, {
                "article_id": article_db_id,
                "outward_id": record_id,
                "company_name": company_upper,
                "box_number": box_data.box_number,
                "article_name": box_data.article_name,
                "lot_number": box_data.lot_number,
                "net_weight_gm": box_data.net_weight_gm,
                "gross_weight_gm": box_data.gross_weight_gm
            })
        
        # 4. Create/Update approval
        check_approval_sql = text("""
            SELECT id FROM outward_approvals
            WHERE outward_id = :outward_id AND company_name = :company_name
        """)
        existing_approval = db.execute(check_approval_sql, {
            "outward_id": record_id,
            "company_name": company_upper
        }).fetchone()
        
        if existing_approval:
            # Update existing approval
            update_approval_sql = text("""
                UPDATE outward_approvals SET
                    approval_status = :approval_status,
                    approval_authority = :approval_authority,
                    approval_date = :approval_date,
                    remarks = :remarks,
                    updated_at = NOW()
                WHERE outward_id = :outward_id AND company_name = :company_name
            """)
            
            db.execute(update_approval_sql, {
                "approval_status": request.approval_status.upper(),
                "approval_authority": request.approval_authority.upper(),
                "approval_date": request.approval_date,
                "remarks": request.approval_remark,
                "outward_id": record_id,
                "company_name": company_upper
            })
        else:
            # Create new approval
            insert_approval_sql = text("""
                INSERT INTO outward_approvals (
                    outward_id, company_name, approval_status, approval_authority,
                    approval_date, remarks, created_at, updated_at
                ) VALUES (
                    :outward_id, :company_name, :approval_status, :approval_authority,
                    :approval_date, :remarks, NOW(), NOW()
                )
            """)
            
            db.execute(insert_approval_sql, {
                "outward_id": record_id,
                "company_name": company_upper,
                "approval_status": request.approval_status.upper(),
                "approval_authority": request.approval_authority.upper(),
                "approval_date": request.approval_date,
                "remarks": request.approval_remark
            })
        
        # 5. Update outward totals
        update_outward_totals(record_id, company_upper, db)
        
        db.commit()
        
        # Get approval response
        approval_response = get_approval_for_outward(record_id, company_upper, db)
        
        logger.info(f"Submitted approval with {len(request.articles)} articles and {len(request.boxes)} boxes for outward {record_id}")
        return approval_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error submitting approval: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit approval: {str(e)}")

@router.get("/{company}/{record_id}/approval", response_model=ApprovalResponse)
def get_approval(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """Get approval for outward record"""
    try:
        company_upper = company.upper()
        approval = get_approval_for_outward(record_id, company_upper, db)
        
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        
        return approval
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get approval: {str(e)}")

def get_approval_for_outward(outward_id: int, company: str, db: Session) -> Optional[ApprovalResponse]:
    """Helper function to get approval for outward"""
    sql = text("""
        SELECT *
        FROM outward_approvals
        WHERE outward_id = :outward_id AND company_name = :company_name
    """)
    
    result = db.execute(sql, {"outward_id": outward_id, "company_name": company}).fetchone()
    
    if not result:
        return None
    
    record_dict = dict(result._mapping)
    for key, value in record_dict.items():
        if isinstance(value, datetime):
            record_dict[key] = value.isoformat()
        elif isinstance(value, date):
            record_dict[key] = value.isoformat()
    
    return ApprovalResponse(**record_dict)

# ============================================
# HELPER FUNCTIONS
# ============================================

def update_outward_totals(outward_id: int, company: str, db: Session):
    """Update total boxes and weights in outward record"""
    table_name = table_for_company(company)
    
    # Get totals from articles and boxes
    totals_sql = text("""
        SELECT 
            COALESCE(COUNT(DISTINCT b.id), 0) as total_boxes,
            COALESCE(SUM(a.net_weight_gm), 0) as total_net_weight,
            COALESCE(SUM(a.gross_weight_gm), 0) as total_gross_weight
        FROM outward_articles a
        LEFT JOIN outward_boxes b ON a.id = b.article_id
        WHERE a.outward_id = :outward_id AND a.company_name = :company_name
    """)
    
    result = db.execute(totals_sql, {"outward_id": outward_id, "company_name": company}).fetchone()
    
    # Update outward record
    update_sql = text(f"""
        UPDATE {table_name}
        SET boxes = :boxes,
            net_weight = :net_weight,
            gross_weight = :gross_weight,
            updated_at = NOW()
        WHERE id = :outward_id
    """)
    
    db.execute(update_sql, {
        "boxes": result.total_boxes,
        "net_weight": f"{result.total_net_weight} gm",
        "gross_weight": f"{result.total_gross_weight} gm",
        "outward_id": outward_id
    })

# ============================================
# STATISTICS ENDPOINT
# ============================================

@router.get("/{company}/stats/summary")
def get_outward_stats(
    company: str,
    db: Session = Depends(get_db)
):
    """Get outward statistics summary"""
    try:
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        table_name = table_for_company(company_upper)
        
        # Get statistics
        stats_sql = text(f"""
            SELECT 
                COUNT(*) as total_records,
                COUNT(CASE WHEN UPPER(delivery_status) = 'DELIVERED' THEN 1 END) as delivered_count,
                COUNT(CASE WHEN UPPER(delivery_status) = 'IN_TRANSIT' THEN 1 END) as in_transit_count,
                COUNT(CASE WHEN UPPER(delivery_status) = 'PENDING' THEN 1 END) as pending_count,
                COALESCE(SUM(boxes), 0) as total_boxes,
                COALESCE(SUM(total_invoice_amount), 0) as total_invoice_value,
                COALESCE(SUM(total_freight_amount), 0) as total_freight_value
            FROM {table_name}
        """)
        
        result = db.execute(stats_sql).fetchone()
        
        return {
            "company": company_upper,
            "total_records": result.total_records or 0,
            "delivery_status": {
                "delivered": result.delivered_count or 0,
                "in_transit": result.in_transit_count or 0,
                "pending": result.pending_count or 0
            },
            "totals": {
                "boxes": result.total_boxes or 0,
                "invoice_value": float(result.total_invoice_value or 0),
                "freight_value": float(result.total_freight_value or 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting outward stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get outward statistics: {str(e)}")

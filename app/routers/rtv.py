"""
RTV (Return to Vendor) Router
API endpoints for RTV operations with separate handling for CDPL and CFPL
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Path
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, List
from datetime import datetime
import logging

from app.core.database import get_db
from app.schemas.rtv import (
    RTVCreate, RTVResponse, RTVCreateResponse,
    RTVListResponse, RTVListItem, RTVStatusUpdate,
    RTVBoxValidation, RTVBoxValidationResponse,
    CustomerListResponse, CustomerItem, RTVDeleteResponse
)
from app.models.rtv import CFPLRTVMaster, CFPLRTVItem, CDPLRTVMaster, CDPLRTVItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rtv", tags=["rtv"])


def get_tables(company: str):
    """Get the appropriate table models based on company"""
    company_upper = company.upper()
    if company_upper == "CFPL":
        return {
            'master': CFPLRTVMaster,
            'items': CFPLRTVItem
        }
    elif company_upper == "CDPL":
        return {
            'master': CDPLRTVMaster,
            'items': CDPLRTVItem
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid company. Must be CFPL or CDPL")


def generate_rtv_number() -> str:
    """Generate RTV number in format RTVYYYYMMDDHHMM"""
    now = datetime.now()
    return f"RTV{now.strftime('%Y%m%d%H%M')}"


def check_transaction_exists(db: Session, transaction_no: str, company: str) -> Optional[str]:
    """Check if transaction_no already exists in any RTV (CFPL or CDPL)"""
    # Check CFPL tables
    cfpl_check = db.query(func.count(CFPLRTVItem.item_id)).filter(
        CFPLRTVItem.transaction_no == transaction_no
    ).scalar()
    
    if cfpl_check > 0:
        # Get the RTV number
        rtv_item = db.query(CFPLRTVItem).filter(
            CFPLRTVItem.transaction_no == transaction_no
        ).first()
        return rtv_item.rtv_number
    
    # Check CDPL tables
    cdpl_check = db.query(func.count(CDPLRTVItem.item_id)).filter(
        CDPLRTVItem.transaction_no == transaction_no
    ).scalar()
    
    if cdpl_check > 0:
        # Get the RTV number
        rtv_item = db.query(CDPLRTVItem).filter(
            CDPLRTVItem.transaction_no == transaction_no
        ).first()
        return rtv_item.rtv_number
    
    return None


@router.post("/create", response_model=RTVCreateResponse)
def create_rtv(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    rtv_data: RTVCreate = None,
    db: Session = Depends(get_db)
):
    """
    Create a new RTV (Return to Vendor)
    
    - Generate RTV number automatically
    - Validate that no transaction_no already exists in any RTV
    - Calculate total_value and total_boxes from items
    - Store in company-specific table
    """
    try:
        company_upper = company.upper()
        tables = get_tables(company_upper)
        
        # Validate all items - check if any transaction_no already exists
        for item in rtv_data.items:
            existing_rtv = check_transaction_exists(db, item.transaction_no, company_upper)
            if existing_rtv:
                raise HTTPException(
                    status_code=400,
                    detail=f"Transaction {item.transaction_no} already exists in RTV {existing_rtv}"
                )
        
        # Generate RTV number
        rtv_number = generate_rtv_number()
        
        # Calculate totals
        total_value = sum(item.price for item in rtv_data.items)
        total_boxes = len(rtv_data.items)
        
        # Create RTV master record
        rtv_master = tables['master'](
            rtv_number=rtv_number,
            customer_code=rtv_data.customer_code,
            customer_name=rtv_data.customer_name,
            rtv_type=rtv_data.rtv_type,
            other_reason=rtv_data.other_reason,
            rtv_date=rtv_data.rtv_date,
            invoice_number=rtv_data.invoice_number,
            dc_number=rtv_data.dc_number,
            notes=rtv_data.notes,
            created_by=rtv_data.created_by,
            total_value=total_value,
            total_boxes=total_boxes,
            status="pending",
            company_code=company_upper
        )
        
        db.add(rtv_master)
        db.flush()  # Flush to get the rtv_number
        
        # Create RTV items
        for item in rtv_data.items:
            rtv_item = tables['items'](
                rtv_number=rtv_number,
                transaction_no=item.transaction_no,
                box_number=item.box_number,
                sub_category=item.sub_category,
                item_description=item.item_description,
                net_weight=item.net_weight,
                gross_weight=item.gross_weight,
                price=item.price,
                reason=item.reason,
                qr_data=item.qr_data
            )
            db.add(rtv_item)
        
        db.commit()
        
        logger.info(f"RTV {rtv_number} created successfully for {company_upper}")
        
        return RTVCreateResponse(
            success=True,
            rtv_number=rtv_number,
            message="RTV created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating RTV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create RTV: {str(e)}")


@router.get("/list", response_model=RTVListResponse)
def get_rtv_list(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    status: Optional[str] = Query(None, description="Filter by status"),
    date_from: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get list of RTVs with filters
    
    - Filter by company, status, date range
    - Pagination support
    """
    try:
        company_upper = company.upper()
        tables = get_tables(company_upper)
        
        # Build query
        query = db.query(tables['master'])
        
        # Apply filters
        if status:
            query = query.filter(tables['master'].status == status)
        
        if date_from:
            query = query.filter(tables['master'].rtv_date >= date_from)
        
        if date_to:
            query = query.filter(tables['master'].rtv_date <= date_to)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * limit
        rtv_list = query.order_by(tables['master'].created_at.desc()).offset(offset).limit(limit).all()
        
        # Convert to response format
        data = [
            RTVListItem(
                rtv_number=rtv.rtv_number,
                customer_code=rtv.customer_code,
                customer_name=rtv.customer_name,
                rtv_type=rtv.rtv_type,
                rtv_date=rtv.rtv_date,
                invoice_number=rtv.invoice_number,
                dc_number=rtv.dc_number,
                total_value=rtv.total_value,
                total_boxes=rtv.total_boxes,
                status=rtv.status,
                company_code=rtv.company_code,
                created_at=rtv.created_at,
                updated_at=rtv.updated_at
            )
            for rtv in rtv_list
        ]
        
        return RTVListResponse(
            success=True,
            data=data,
            total=total,
            page=page,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error fetching RTV list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch RTV list: {str(e)}")


@router.get("/{rtv_number}", response_model=RTVResponse)
def get_rtv_details(
    rtv_number: str = Path(..., description="RTV number"),
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific RTV including all items
    """
    try:
        company_upper = company.upper()
        tables = get_tables(company_upper)
        
        rtv = db.query(tables['master']).filter(
            tables['master'].rtv_number == rtv_number
        ).first()
        
        if not rtv:
            raise HTTPException(status_code=404, detail=f"RTV {rtv_number} not found")
        
        return RTVResponse(
            rtv_number=rtv.rtv_number,
            customer_code=rtv.customer_code,
            customer_name=rtv.customer_name,
            rtv_type=rtv.rtv_type,
            other_reason=rtv.other_reason,
            rtv_date=rtv.rtv_date,
            invoice_number=rtv.invoice_number,
            dc_number=rtv.dc_number,
            notes=rtv.notes,
            created_by=rtv.created_by,
            total_value=rtv.total_value,
            total_boxes=rtv.total_boxes,
            status=rtv.status,
            company_code=rtv.company_code,
            created_at=rtv.created_at,
            updated_at=rtv.updated_at,
            items=[item for item in rtv.items]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching RTV details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch RTV details: {str(e)}")


@router.put("/{rtv_number}/status")
def update_rtv_status(
    rtv_number: str = Path(..., description="RTV number"),
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    status_update: RTVStatusUpdate = None,
    db: Session = Depends(get_db)
):
    """
    Update RTV status
    """
    try:
        company_upper = company.upper()
        tables = get_tables(company_upper)
        
        rtv = db.query(tables['master']).filter(
            tables['master'].rtv_number == rtv_number
        ).first()
        
        if not rtv:
            raise HTTPException(status_code=404, detail=f"RTV {rtv_number} not found")
        
        # Update status
        rtv.status = status_update.status
        
        # Update notes if remarks provided
        if status_update.remarks:
            existing_notes = rtv.notes or ""
            new_note = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Status changed to {status_update.status}: {status_update.remarks}"
            rtv.notes = existing_notes + new_note
        
        rtv.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"RTV {rtv_number} status updated to {status_update.status}")
        
        return {
            "success": True,
            "message": f"RTV status updated to {status_update.status}",
            "rtv_number": rtv_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating RTV status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update RTV status: {str(e)}")


@router.delete("/{rtv_number}", response_model=RTVDeleteResponse)
def delete_rtv(
    rtv_number: str = Path(..., description="RTV number"),
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    db: Session = Depends(get_db)
):
    """
    Delete an RTV record and all its associated items
    
    - Deletes RTV master record
    - Cascade deletes all associated items
    """
    try:
        logger.info("=" * 80)
        logger.info(f"DELETE RTV - RTV Number: {rtv_number}, Company: {company}")
        
        company_upper = company.upper()
        tables = get_tables(company_upper)
        
        # Check if RTV exists
        rtv = db.query(tables['master']).filter(
            tables['master'].rtv_number == rtv_number
        ).first()
        
        if not rtv:
            raise HTTPException(status_code=404, detail=f"RTV {rtv_number} not found")
        
        # Log the RTV details before deletion
        logger.info(f"Found RTV: {rtv_number}")
        logger.info(f"Customer: {rtv.customer_name}")
        logger.info(f"Status: {rtv.status}")
        logger.info(f"Total Boxes: {rtv.total_boxes}")
        logger.info(f"Total Value: {rtv.total_value}")
        
        # Delete RTV items first (cascade delete)
        items_deleted = db.query(tables['items']).filter(
            tables['items'].rtv_number == rtv_number
        ).delete()
        
        logger.info(f"Deleted {items_deleted} items")
        
        # Delete RTV master record
        db.query(tables['master']).filter(
            tables['master'].rtv_number == rtv_number
        ).delete()
        
        db.commit()
        
        logger.info(f"✅ RTV {rtv_number} deleted successfully")
        logger.info("=" * 80)
        
        return RTVDeleteResponse(
            success=True,
            message=f"RTV {rtv_number} and all associated items deleted successfully",
            rtv_number=rtv_number
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting RTV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete RTV: {str(e)}")


@router.post("/validate-box", response_model=RTVBoxValidationResponse)
def validate_box(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    validation_data: RTVBoxValidation = None,
    db: Session = Depends(get_db)
):
    """
    Validate if a box can be added to RTV
    
    - Check if transaction_no already exists in any RTV
    - Returns valid: true/false and existing RTV number if found
    """
    try:
        company_upper = company.upper()
        
        existing_rtv = check_transaction_exists(db, validation_data.transaction_no, company_upper)
        
        if existing_rtv:
            return RTVBoxValidationResponse(
                valid=False,
                message=f"Transaction {validation_data.transaction_no} already exists in RTV {existing_rtv}",
                existing_rtv=existing_rtv
            )
        
        return RTVBoxValidationResponse(
            valid=True,
            message=f"Box {validation_data.transaction_no} can be added to RTV"
        )
        
    except Exception as e:
        logger.error(f"Error validating box: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate box: {str(e)}")


@router.get("/customers", response_model=CustomerListResponse)
def get_customers(
    company: str = Query(..., pattern="^(CFPL|CDPL)$")
):
    """
    Get list of customers for dropdown
    
    Returns company-specific customer list
    """
    company_upper = company.upper()
    
    # CDPL Customers
    cdpl_customers = [
        {"value": "CDPL-RR-001", "label": "Reliance Retail Limited"},
        {"value": "CDPL-RF-001", "label": "Reliance Fresh"},
        {"value": "CDPL-BI-001", "label": "Big Bazaar"},
        {"value": "CDPL-DM-001", "label": "DMart"},
        {"value": "CDPL-MT-001", "label": "Metro Cash & Carry"},
        {"value": "CDPL-SP-001", "label": "Spencer's Retail"},
        {"value": "CDPL-FV-001", "label": "Food Bazaar"},
        {"value": "OTHER", "label": "Other (Custom)"}
    ]
    
    # CFPL Customers
    cfpl_customers = [
        {"value": "CFPL-RF-001", "label": "Reliance Fresh"},
        {"value": "CFPL-RR-001", "label": "Reliance Retail Limited"},
        {"value": "CFPL-BI-001", "label": "Big Bazaar"},
        {"value": "CFPL-DM-001", "label": "DMart"},
        {"value": "CFPL-MT-001", "label": "Metro Cash & Carry"},
        {"value": "CFPL-SP-001", "label": "Spencer's Retail"},
        {"value": "CFPL-FV-001", "label": "Food Bazaar"},
        {"value": "OTHER", "label": "Other (Custom)"}
    ]
    
    customers = cdpl_customers if company_upper == "CDPL" else cfpl_customers
    
    return CustomerListResponse(
        success=True,
        data=[CustomerItem(**customer) for customer in customers]
    )


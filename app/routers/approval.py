from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import datetime, date
import logging

from app.core.database import get_db
from app.schemas.approval import (
    ApprovalRecord, ApprovalCreateRequest, ApprovalUpdateRequest,
    ApprovalResponse, ApprovalListResponse, ApprovalDeleteResponse,
    ApprovalWithOutwardResponse
)

router = APIRouter(prefix="/approval", tags=["approval"])
logger = logging.getLogger(__name__)

def table_for_company(company: str) -> str:
    """Map company code to corresponding approval table name"""
    company_upper = company.upper()
    if company_upper == "CFPL":
        return "cfpl_approvals"
    elif company_upper == "CDPL":
        return "cdpl_approvals"
    else:
        raise ValueError(f"Invalid company: {company}. Must be CFPL or CDPL")

def outward_table_for_company(company: str) -> str:
    """Map company code to corresponding outward table name"""
    company_upper = company.upper()
    if company_upper == "CFPL":
        return "cfpl_outward"
    elif company_upper == "CDPL":
        return "cdpl_outward"
    else:
        raise ValueError(f"Invalid company: {company}. Must be CFPL or CDPL")

@router.post("/{company}", response_model=ApprovalResponse)
def create_approval_record(
    company: str,
    request: ApprovalCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new approval record
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    
    **Request Body:**
    - approval_data: Complete approval record data
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table names
        approval_table = table_for_company(company_upper)
        outward_table = outward_table_for_company(company_upper)
        
        # Validate tables exist
        check_approval_table_sql = text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{approval_table}'
            );
        """)
        approval_table_exists = db.execute(check_approval_table_sql).scalar_one()
        
        if not approval_table_exists:
            raise HTTPException(status_code=500, detail=f"Table {approval_table} does not exist")
        
        # Check if consignment exists in outward table
        check_consignment_sql = text(f"""
            SELECT consignment_no FROM {outward_table} 
            WHERE consignment_no = :consignment_no
        """)
        consignment_exists = db.execute(
            check_consignment_sql, 
            {"consignment_no": request.approval_data.consignment_no}
        ).fetchone()
        
        if not consignment_exists:
            raise HTTPException(
                status_code=404, 
                detail=f"Consignment {request.approval_data.consignment_no} not found in outward records"
            )
        
        # Check if approval already exists for this consignment
        check_existing_sql = text(f"""
            SELECT id FROM {approval_table} 
            WHERE consignment_no = :consignment_no
        """)
        existing_approval = db.execute(
            check_existing_sql, 
            {"consignment_no": request.approval_data.consignment_no}
        ).fetchone()
        
        if existing_approval:
            raise HTTPException(
                status_code=409, 
                detail=f"Approval record already exists for consignment {request.approval_data.consignment_no}"
            )
        
        # Insert new approval record
        insert_sql = text(f"""
            INSERT INTO {approval_table} (
                consignment_no, approval_authority, approval_date, quantity, uom,
                gross_weight, net_weight, approval_status, remark, created_at, updated_at
            ) VALUES (
                :consignment_no, :approval_authority, :approval_date, :quantity, :uom,
                :gross_weight, :net_weight, :approval_status, :remark, NOW(), NOW()
            ) RETURNING id, created_at, updated_at
        """)
        
        # Prepare data
        data = request.approval_data.dict()
        
        result = db.execute(insert_sql, data).fetchone()
        db.commit()
        
        # Get the created record
        created_record = get_approval_record_by_id(company, result.id, db)
        
        logger.info(f"Created approval record {result.id} for consignment {request.approval_data.consignment_no}")
        return created_record
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating approval record: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create approval record: {str(e)}")

@router.get("/{company}", response_model=ApprovalListResponse)
def list_approval_records(
    company: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search across all fields"),
    consignment_no: Optional[str] = Query(None, description="Filter by consignment number"),
    approval_authority: Optional[str] = Query(None, description="Filter by approval authority"),
    approval_status: Optional[bool] = Query(None, description="Filter by approval status"),
    from_date: Optional[str] = Query(None, description="Filter from approval date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to approval date (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("approval_date", description="Sort field"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db)
):
    """
    List approval records with filtering and pagination
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    
    **Query Parameters:**
    - page: Page number (default: 1)
    - per_page: Items per page (default: 20, max: 100)
    - search: Search term across all fields
    - consignment_no: Filter by consignment number
    - approval_authority: Filter by approval authority
    - approval_status: Filter by approval status
    - from_date: Filter from approval date
    - to_date: Filter to approval date
    - sort_by: Sort field (default: approval_date)
    - sort_order: Sort order (default: desc)
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table name
        table_name = table_for_company(company_upper)
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        if search:
            where_clauses.append("""
                (LOWER(consignment_no) LIKE :search OR 
                 LOWER(approval_authority) LIKE :search OR 
                 LOWER(remark) LIKE :search)
            """)
            params["search"] = f"%{search.lower()}%"
        
        if consignment_no:
            where_clauses.append("LOWER(consignment_no) LIKE :consignment_no")
            params["consignment_no"] = f"%{consignment_no.lower()}%"
        
        if approval_authority:
            where_clauses.append("LOWER(approval_authority) LIKE :approval_authority")
            params["approval_authority"] = f"%{approval_authority.lower()}%"
        
        if approval_status is not None:
            where_clauses.append("approval_status = :approval_status")
            params["approval_status"] = approval_status
        
        if from_date:
            where_clauses.append("approval_date >= :from_date")
            params["from_date"] = from_date
        
        if to_date:
            where_clauses.append("approval_date <= :to_date")
            params["to_date"] = to_date
        
        where_sql = " AND ".join(where_clauses)
        
        # Validate sort field
        valid_sort_fields = [
            "id", "consignment_no", "approval_authority", "approval_date", 
            "approval_status", "quantity", "gross_weight", "net_weight", "created_at"
        ]
        
        if sort_by not in valid_sort_fields:
            sort_by = "approval_date"
        
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
            
            records.append(ApprovalResponse(**record_dict))
        
        total_pages = (total + per_page - 1) // per_page
        
        logger.info(f"Retrieved {len(records)} approval records for company {company_upper}")
        
        return ApprovalListResponse(
            records=records,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing approval records: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list approval records: {str(e)}")

@router.get("/{company}/{record_id}", response_model=ApprovalResponse)
def get_approval_record(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """
    Get specific approval record by ID
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    - record_id: Record ID
    """
    return get_approval_record_by_id(company, record_id, db)

def get_approval_record_by_id(company: str, record_id: int, db: Session) -> ApprovalResponse:
    """Helper function to get approval record by ID"""
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table name
        table_name = table_for_company(company_upper)
        
        # Get record
        sql = text(f"""
            SELECT *
            FROM {table_name}
            WHERE id = :record_id
        """)
        
        result = db.execute(sql, {"record_id": record_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Approval record {record_id} not found")
        
        # Format record
        record_dict = dict(result._mapping)
        # Convert datetime objects to strings
        for key, value in record_dict.items():
            if isinstance(value, datetime):
                record_dict[key] = value.isoformat()
            elif isinstance(value, date):
                record_dict[key] = value.isoformat()
        
        return ApprovalResponse(**record_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get approval record: {str(e)}")

@router.get("/{company}/consignment/{consignment_no}", response_model=ApprovalWithOutwardResponse)
def get_approval_by_consignment(
    company: str,
    consignment_no: str,
    db: Session = Depends(get_db)
):
    """
    Get approval record by consignment number with outward data
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    - consignment_no: Consignment number
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table names
        approval_table = table_for_company(company_upper)
        outward_table = outward_table_for_company(company_upper)
        
        # Get approval record
        approval_sql = text(f"""
            SELECT *
            FROM {approval_table}
            WHERE consignment_no = :consignment_no
        """)
        
        approval_result = db.execute(approval_sql, {"consignment_no": consignment_no}).fetchone()
        
        if not approval_result:
            raise HTTPException(
                status_code=404, 
                detail=f"Approval record for consignment {consignment_no} not found"
            )
        
        # Get outward record
        outward_sql = text(f"""
            SELECT *
            FROM {outward_table}
            WHERE consignment_no = :consignment_no
        """)
        
        outward_result = db.execute(outward_sql, {"consignment_no": consignment_no}).fetchone()
        
        if not outward_result:
            raise HTTPException(
                status_code=404, 
                detail=f"Outward record for consignment {consignment_no} not found"
            )
        
        # Format approval record
        approval_dict = dict(approval_result._mapping)
        for key, value in approval_dict.items():
            if isinstance(value, datetime):
                approval_dict[key] = value.isoformat()
            elif isinstance(value, date):
                approval_dict[key] = value.isoformat()
        
        # Format outward record
        outward_dict = dict(outward_result._mapping)
        for key, value in outward_dict.items():
            if isinstance(value, datetime):
                outward_dict[key] = value.isoformat()
            elif isinstance(value, date):
                outward_dict[key] = value.isoformat()
        
        return ApprovalWithOutwardResponse(
            approval=ApprovalResponse(**approval_dict),
            outward=outward_dict
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval by consignment {consignment_no}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get approval record: {str(e)}")

@router.put("/{company}/{record_id}", response_model=ApprovalResponse)
def update_approval_record(
    company: str,
    record_id: int,
    request: ApprovalUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update existing approval record
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    - record_id: Record ID to update
    
    **Request Body:**
    - approval_data: Updated approval record data
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table name
        table_name = table_for_company(company_upper)
        
        # Check if record exists
        check_sql = text(f"""
            SELECT id FROM {table_name} WHERE id = :record_id
        """)
        existing_record = db.execute(check_sql, {"record_id": record_id}).fetchone()
        
        if not existing_record:
            raise HTTPException(status_code=404, detail=f"Approval record {record_id} not found")
        
        # Update record
        update_sql = text(f"""
            UPDATE {table_name} SET
                approval_authority = :approval_authority,
                approval_date = :approval_date,
                quantity = :quantity,
                uom = :uom,
                gross_weight = :gross_weight,
                net_weight = :net_weight,
                approval_status = :approval_status,
                remark = :remark,
                updated_at = NOW()
            WHERE id = :record_id
        """)
        
        # Prepare data
        data = request.approval_data.dict()
        data['record_id'] = record_id
        
        db.execute(update_sql, data)
        db.commit()
        
        # Get updated record
        updated_record = get_approval_record_by_id(company, record_id, db)
        
        logger.info(f"Updated approval record {record_id} for company {company_upper}")
        return updated_record
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating approval record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update approval record: {str(e)}")

@router.delete("/{company}/{record_id}", response_model=ApprovalDeleteResponse)
def delete_approval_record(
    company: str,
    record_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete approval record
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    - record_id: Record ID to delete
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table name
        table_name = table_for_company(company_upper)
        
        # Get record details before deletion
        get_sql = text(f"""
            SELECT consignment_no, approval_authority FROM {table_name} WHERE id = :record_id
        """)
        result = db.execute(get_sql, {"record_id": record_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Approval record {record_id} not found")
        
        # Delete record
        delete_sql = text(f"""
            DELETE FROM {table_name} WHERE id = :record_id
        """)
        
        db.execute(delete_sql, {"record_id": record_id})
        db.commit()
        
        logger.info(f"Deleted approval record {record_id} for company {company_upper}")
        
        return ApprovalDeleteResponse(
            id=record_id,
            consignment_no=result.consignment_no,
            approval_authority=result.approval_authority,
            status="deleted",
            message="Approval record deleted successfully",
            deleted_at=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting approval record {record_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete approval record: {str(e)}")

@router.get("/{company}/stats/summary")
def get_approval_stats(
    company: str,
    db: Session = Depends(get_db)
):
    """
    Get approval statistics summary
    
    **Path Parameters:**
    - company: Company code (CFPL or CDPL)
    """
    try:
        # Validate company
        company_upper = company.upper()
        if company_upper not in ("CFPL", "CDPL"):
            raise HTTPException(status_code=400, detail="Company must be CFPL or CDPL")
        
        # Get table name
        table_name = table_for_company(company_upper)
        
        # Get statistics
        stats_sql = text(f"""
            SELECT 
                COUNT(*) as total_records,
                COUNT(CASE WHEN approval_status = true THEN 1 END) as approved_count,
                COUNT(CASE WHEN approval_status = false THEN 1 END) as rejected_count,
                COALESCE(SUM(quantity), 0) as total_quantity,
                COALESCE(SUM(gross_weight), 0) as total_gross_weight,
                COALESCE(SUM(net_weight), 0) as total_net_weight
            FROM {table_name}
        """)
        
        result = db.execute(stats_sql).fetchone()
        
        return {
            "company": company_upper,
            "total_records": result.total_records or 0,
            "approval_status": {
                "approved": result.approved_count or 0,
                "rejected": result.rejected_count or 0
            },
            "totals": {
                "quantity": result.total_quantity or 0,
                "gross_weight": float(result.total_gross_weight or 0),
                "net_weight": float(result.total_net_weight or 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting approval stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get approval statistics: {str(e)}")

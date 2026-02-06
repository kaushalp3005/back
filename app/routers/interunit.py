from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import datetime, date
import logging
import io
import xlsxwriter
import re

from app.core.database import get_db
from app.routers.auth import get_current_user
from app.schemas import interunit as schemas
from app.schemas.interunit import (
    RequestCreate, RequestResponse, RequestWithLines, RequestUpdate,
    TransferCreate, TransferUpdate, TransferHeaderResponse, TransferWithLines,
    TransferListResponse, TransferListItem,
    TransferApproveRequest, TransferApproveResponse,
    BoxCreate, BoxResponse, DeleteResponse, ApprovalAuthorityResponse,
    WarehouseSiteResponse, MaterialTypeResponse, UOMResponse
)

router = APIRouter(prefix="/interunit", tags=["interunit-transfer"])
logger = logging.getLogger(__name__)

# ============================================
# UTILITY FUNCTIONS
# ============================================

def generate_request_no() -> str:
    """Generate request number in format REQ{YYYYMMDD}{timestamp}"""
    return f"REQ{datetime.now().strftime('%Y%m%d%H%M')}"

def generate_challan_no() -> str:
    """Generate challan number in format TRANS{YYYYMMDDHHMMSS}"""
    return f"TRANS{datetime.now().strftime('%Y%m%d%H%M%S')}"

def convert_date_format(date_str: str) -> date:
    """Convert DD-MM-YYYY format to date object"""
    try:
        return datetime.strptime(date_str, '%d-%m-%Y').date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use DD-MM-YYYY")

# ============================================
# DROPDOWN ENDPOINTS
# ============================================

@router.get("/dropdowns/warehouse-sites", response_model=List[WarehouseSiteResponse])
def get_warehouse_sites(
    active_only: bool = Query(True, description="Return only active sites"),
    db: Session = Depends(get_db)
):
    """Get all warehouse sites for dropdown"""
    try:
        where_clause = "WHERE is_active = :active_only" if active_only else ""
        params = {"active_only": True} if active_only else {}
        
        sql = text(f"""
            SELECT id, site_code, site_name, is_active
            FROM warehouse_sites
            {where_clause}
            ORDER BY site_code ASC
        """)
        
        results = db.execute(sql, params).fetchall()
        
        return [
            WarehouseSiteResponse(
                id=row.id,
                site_code=row.site_code,
                site_name=row.site_name,
                is_active=row.is_active
            )
            for row in results
        ]
        
    except Exception as e:
        logger.error(f"Error fetching warehouse sites: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch warehouse sites: {str(e)}")

@router.get("/dropdowns/material-types", response_model=List[MaterialTypeResponse])
def get_material_types(
    active_only: bool = Query(True, description="Return only active types"),
    db: Session = Depends(get_db)
):
    """Get all material types for dropdown"""
    try:
        where_clause = "WHERE is_active = :active_only" if active_only else ""
        params = {"active_only": True} if active_only else {}
        
        sql = text(f"""
            SELECT id, type_code, type_name, description, is_active
            FROM material_types
            {where_clause}
            ORDER BY type_code ASC
        """)
        
        results = db.execute(sql, params).fetchall()
        
        return [
            MaterialTypeResponse(
                id=row.id,
                type_code=row.type_code,
                type_name=row.type_name,
                description=row.description,
                is_active=row.is_active
            )
            for row in results
        ]
        
    except Exception as e:
        logger.error(f"Error fetching material types: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch material types: {str(e)}")

@router.get("/dropdowns/units-of-measurement", response_model=List[UOMResponse])
def get_units_of_measurement(
    active_only: bool = Query(True, description="Return only active UOM"),
    db: Session = Depends(get_db)
):
    """Get all units of measurement for dropdown"""
    try:
        where_clause = "WHERE is_active = :active_only" if active_only else ""
        params = {"active_only": True} if active_only else {}
        
        sql = text(f"""
            SELECT id, uom_code, uom_name, description, is_active
            FROM units_of_measurement
            {where_clause}
            ORDER BY uom_code ASC
        """)
        
        results = db.execute(sql, params).fetchall()
        
        return [
            UOMResponse(
                id=row.id,
                uom_code=row.uom_code,
                uom_name=row.uom_name,
                description=row.description,
                is_active=row.is_active
            )
            for row in results
        ]
        
    except Exception as e:
        logger.error(f"Error fetching units of measurement: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch units of measurement: {str(e)}")

# ============================================
# REQUEST ENDPOINTS (Updated for new JSON structure)
# ============================================

@router.post("/requests", response_model=RequestWithLines, status_code=201)
def create_request(
    request_data: RequestCreate,
    created_by: str = Query("user@example.com", description="User email"),
    db: Session = Depends(get_db)
):
    """
    Create a new transfer request using the updated JSON structure
    
    - **form_data**: Form data with request date, warehouses, and reason
    - **article_data**: Array of article items with material type, quantities, etc.
    - **computed_fields**: Auto-generated fields like request number
    """
    try:
        logger.info("=" * 80)
        logger.info("CREATE REQUEST - Incoming Data")
        logger.info(f"Form Data: {request_data.form_data}")
        logger.info(f"Article Data Count: {len(request_data.article_data)}")
        logger.info(f"Computed Fields: {request_data.computed_fields}")
        logger.info(f"Created By: {created_by}")
        
        # Convert date format from DD-MM-YYYY to date object
        request_date = convert_date_format(request_data.form_data.request_date)
        
        # Use frontend-provided request_no if available, otherwise generate one
        if request_data.computed_fields and request_data.computed_fields.request_no:
            request_no = request_data.computed_fields.request_no
            logger.info(f"✅ Using frontend-provided request_no: {request_no}")
        else:
            request_no = generate_request_no()
            logger.info(f"📝 Generated new request_no: {request_no}")
        
        # Create request header using new structure
        header_sql = text("""
            INSERT INTO interunit_transfer_requests 
            (request_no, request_date, from_site, to_site, reason_code, remarks, status, created_by, created_ts)
            VALUES (:request_no, :request_date, :from_site, :to_site, :reason_code, :remarks, 'Pending', :created_by, :created_ts)
            RETURNING id, request_no, request_date, from_site, to_site, reason_code, remarks, status, 
                      reject_reason, created_by, created_ts, rejected_ts, updated_at
        """)
        
        header_result = db.execute(header_sql, {
            "request_no": request_no,
            "request_date": request_date,
            "from_site": request_data.form_data.from_warehouse,
            "to_site": request_data.form_data.to_warehouse,
            "reason_code": request_data.form_data.reason_description or "General Transfer",
            "remarks": request_data.form_data.reason_description or "No remarks",
            "created_by": created_by,
            "created_ts": datetime.now()
        }).fetchone()
        
        request_id = header_result.id
        
        # Create request lines using new structure
        lines = []
        for line in request_data.article_data:
            # Calculate net_weight and total_weight
            pack_size_float = float(line.pack_size)
            quantity_int = int(line.quantity)
            packaging_type = int(line.package_size) if line.package_size else 1
            
            # Calculate net_weight: pack_size * packaging_type * qty
            calculated_net_weight = pack_size_float * packaging_type * quantity_int
            
            # Calculate total_weight (add 10% for packaging, must be > net_weight)
            calculated_total_weight = calculated_net_weight * 1.1
            
            line_sql = text("""
                INSERT INTO interunit_transfer_request_lines
                (request_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw, 
                 pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number)
                VALUES (:request_id, :material_type, :item_category, :sub_category, :item_desc_raw,
                        :pack_size, :quantity, :uom, :packaging_type, :net_weight, :total_weight, :batch_number, :lot_number)
                RETURNING id, request_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw,
                          pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number,
                          created_at, updated_at
            """)
            
            line_result = db.execute(line_sql, {
                "request_id": request_id,
                "material_type": line.material_type,
                "item_category": line.item_category,
                "sub_category": line.sub_category,
                "item_desc_raw": line.item_description,
                "pack_size": pack_size_float,
                "quantity": quantity_int,
                "uom": line.uom,
                "packaging_type": packaging_type,
                "net_weight": calculated_net_weight,
                "total_weight": calculated_total_weight,
                "batch_number": line.batch_number,
                "lot_number": line.lot_number
            }).fetchone()
            
            lines.append(line_result)
        
        db.commit()
        
        logger.info(f"✅ Request created successfully")
        logger.info(f"Request ID: {request_id}, Request No: {request_no}")
        logger.info(f"Lines Created: {len(lines)}")
        logger.info("=" * 80)
        
        # Return response in new format with NULL handling
        return {
            "id": header_result.id,
            "request_no": header_result.request_no or "N/A",
            "request_date": header_result.request_date.strftime('%d-%m-%Y'),
            "from_warehouse": header_result.from_site or "N/A",
            "to_warehouse": header_result.to_site or "N/A",
            "reason_description": header_result.reason_code or "No description provided",
            "status": header_result.status or "Pending",
            "reject_reason": header_result.reject_reason,
            "created_by": header_result.created_by or "Unknown",
            "created_ts": header_result.created_ts,
            "rejected_ts": header_result.rejected_ts,
            "updated_at": header_result.updated_at,
            "lines": [
                {
                    "id": line.id,
                    "request_id": line.request_id,
                    "material_type": line.rm_pm_fg_type or "N/A",
                    "item_category": line.item_category or "N/A",
                    "sub_category": line.sub_category or "N/A",
                    "item_description": line.item_desc_raw or "No description",
                    "quantity": str(line.qty) if line.qty is not None else "0",
                    "uom": line.uom or "N/A",
                    "pack_size": str(line.pack_size) if line.pack_size is not None else "0",
                    "package_size": str(line.packaging_type) if line.packaging_type else None,
                    "net_weight": str(line.net_weight) if line.net_weight is not None else "0",
                    "batch_number": line.batch_number,
                    "lot_number": line.lot_number,
                    "created_at": line.created_at,
                    "updated_at": line.updated_at
                }
                for line in lines
            ]
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create request: {str(e)}")

@router.get("/requests", response_model=List[RequestWithLines])
def list_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    from_warehouse: Optional[str] = Query(None, description="Filter by from_warehouse"),
    to_warehouse: Optional[str] = Query(None, description="Filter by to_warehouse"),
    created_by: Optional[str] = Query(None, description="Filter by creator"),
    db: Session = Depends(get_db)
):
    """Get all requests with optional filters"""
    try:
        where_clauses = []
        params = {}
        
        if status:
            where_clauses.append("r.status = :status")
            params["status"] = status
        if from_warehouse:
            where_clauses.append("r.from_site = :from_warehouse")
            params["from_warehouse"] = from_warehouse.upper()
        if to_warehouse:
            where_clauses.append("r.to_site = :to_warehouse")
            params["to_warehouse"] = to_warehouse.upper()
        if created_by:
            where_clauses.append("r.created_by = :created_by")
            params["created_by"] = created_by
        
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Get requests
        request_sql = text(f"""
            SELECT r.id, r.request_no, r.request_date, r.from_site, r.to_site, r.reason_code, r.remarks,
                   r.status, r.reject_reason, r.created_by, r.created_ts, r.rejected_ts, r.updated_at
            FROM interunit_transfer_requests r
            {where_clause}
            ORDER BY r.created_ts DESC
        """)
        
        requests = db.execute(request_sql, params).fetchall()
        
        result = []
        for req in requests:
            # Get lines for this request
            lines_sql = text("""
                SELECT id, request_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw,
                       pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number,
                       created_at, updated_at
                FROM interunit_transfer_request_lines
                WHERE request_id = :request_id
                ORDER BY id
            """)
            
            lines = db.execute(lines_sql, {"request_id": req.id}).fetchall()
            
            result.append({
                "id": req.id,
                "request_no": req.request_no,
                "request_date": req.request_date.strftime('%d-%m-%Y'),
                "from_warehouse": req.from_site or "N/A",
                "to_warehouse": req.to_site or "N/A",
                "reason_description": req.reason_code or "No description provided",
                "status": req.status,
                "reject_reason": req.reject_reason,
                "created_by": req.created_by,
                "created_ts": req.created_ts,
                "rejected_ts": req.rejected_ts,
                "updated_at": req.updated_at,
                "lines": [
                    {
                        "id": line.id,
                        "request_id": line.request_id,
                        "material_type": line.rm_pm_fg_type if line.rm_pm_fg_type else "",
                        "item_category": line.item_category if line.item_category else "",
                        "sub_category": line.sub_category if line.sub_category else "",
                        "item_description": line.item_desc_raw if line.item_desc_raw else "",
                        "quantity": str(line.qty) if line.qty is not None else "0",
                        "uom": line.uom if line.uom else "",
                        "pack_size": str(line.pack_size) if line.pack_size is not None else "0",
                        "package_size": str(line.packaging_type) if line.packaging_type else None,
                        "net_weight": str(line.net_weight) if line.net_weight is not None else "0",
                        "batch_number": line.batch_number if line.batch_number else "",
                        "lot_number": line.lot_number if line.lot_number else "",
                        "created_at": line.created_at,
                        "updated_at": line.updated_at
                    }
                    for line in lines
                ]
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing requests: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list requests: {str(e)}")

@router.get("/requests/{request_id}", response_model=RequestWithLines)
def get_request(request_id: int, db: Session = Depends(get_db)):
    """Get single request by ID"""
    try:
        # Get request header
        request_sql = text("""
            SELECT id, request_no, request_date, from_site, to_site, reason_code, remarks,
                   status, reject_reason, created_by, created_ts, rejected_ts, updated_at
            FROM interunit_transfer_requests
            WHERE id = :request_id
        """)
        
        request = db.execute(request_sql, {"request_id": request_id}).fetchone()
        
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Get request lines
        lines_sql = text("""
            SELECT id, request_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw,
                   pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number,
                   created_at, updated_at
            FROM interunit_transfer_request_lines
            WHERE request_id = :request_id
            ORDER BY id
        """)
        
        lines = db.execute(lines_sql, {"request_id": request_id}).fetchall()
        
        return {
            "id": request.id,
            "request_no": request.request_no,
            "request_date": request.request_date.strftime('%d-%m-%Y'),
            "from_warehouse": request.from_site or "N/A",
            "to_warehouse": request.to_site or "N/A",
            "reason_description": request.reason_code or "No description provided",
            "status": request.status,
            "reject_reason": request.reject_reason,
            "created_by": request.created_by,
            "created_ts": request.created_ts,
            "rejected_ts": request.rejected_ts,
            "updated_at": request.updated_at,
            "lines": [
                {
                    "id": line.id,
                    "request_id": line.request_id,
                    "material_type": line.rm_pm_fg_type if line.rm_pm_fg_type else "",
                    "item_category": line.item_category if line.item_category else "",
                    "sub_category": line.sub_category if line.sub_category else "",
                    "item_description": line.item_desc_raw if line.item_desc_raw else "",
                    "quantity": str(line.qty) if line.qty is not None else "0",
                    "uom": line.uom if line.uom else "",
                    "pack_size": str(line.pack_size) if line.pack_size is not None else "0",
                    "package_size": str(line.packaging_type) if line.packaging_type else None,
                    "net_weight": str(line.net_weight) if line.net_weight is not None else "0",
                    "batch_number": line.batch_number if line.batch_number else "",
                    "lot_number": line.lot_number if line.lot_number else "",
                    "created_at": line.created_at,
                    "updated_at": line.updated_at
                }
                for line in lines
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get request: {str(e)}")

@router.patch("/requests/{request_id}", response_model=RequestResponse)
def update_request(
    request_id: int,
    update_data: RequestUpdate,
    db: Session = Depends(get_db)
):
    """
    Update request status (Process/Accept or Reject/Cancel)
    """
    try:
        # Check if request exists
        check_sql = text("SELECT id, status FROM interunit_transfer_requests WHERE id = :request_id")
        existing = db.execute(check_sql, {"request_id": request_id}).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Build update query
        update_fields = []
        params = {"request_id": request_id}
        
        if update_data.status:
            update_fields.append("status = :status")
            params["status"] = update_data.status
        
        if update_data.reject_reason:
            update_fields.append("reject_reason = :reject_reason")
            params["reject_reason"] = update_data.reject_reason.upper()
        
        if update_data.rejected_ts:
            update_fields.append("rejected_ts = :rejected_ts")
            params["rejected_ts"] = update_data.rejected_ts
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_sql = text(f"""
            UPDATE interunit_transfer_requests
            SET {", ".join(update_fields)}
            WHERE id = :request_id
            RETURNING id, request_no, request_date, from_warehouse, to_warehouse, reason_description,
                      status, reject_reason, created_by, created_ts, rejected_ts, updated_at
        """)
        
        result = db.execute(update_sql, params).fetchone()
        db.commit()
        
        return {
            "id": result.id,
            "request_no": result.request_no,
            "request_date": result.request_date.strftime('%d-%m-%Y'),
            "from_warehouse": result.from_warehouse,
            "to_warehouse": result.to_warehouse,
            "reason_description": result.reason_description,
            "status": result.status,
            "reject_reason": result.reject_reason,
            "created_by": result.created_by,
            "created_ts": result.created_ts,
            "rejected_ts": result.rejected_ts,
            "updated_at": result.updated_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update request: {str(e)}")

@router.delete("/requests/{request_id}", response_model=DeleteResponse)
def delete_request(request_id: int, db: Session = Depends(get_db)):
    """Delete a request (lines will be cascade deleted)"""
    try:
        # Check if request exists
        check_sql = text("SELECT id FROM interunit_transfer_requests WHERE id = :request_id")
        existing = db.execute(check_sql, {"request_id": request_id}).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Delete request (lines will be cascade deleted)
        delete_sql = text("DELETE FROM interunit_transfer_requests WHERE id = :request_id")
        db.execute(delete_sql, {"request_id": request_id})
        db.commit()
        
        return {"success": True, "message": "Request deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete request: {str(e)}")

# ============================================
# TRANSFER ENDPOINTS (Updated for new structure)
# ============================================

@router.post("/transfers", response_model=TransferWithLines, status_code=201)
def create_transfer(
    transfer_data: TransferCreate,
    created_by: str = Query("user@example.com", description="User email"),
    db: Session = Depends(get_db)
):
    """
    Create a new transfer using the updated structure
    """
    try:
        logger.info("=" * 80)
        logger.info("CREATE TRANSFER - Incoming Data")
        logger.info(f"Header: {transfer_data.header}")
        logger.info(f"Lines Count: {len(transfer_data.lines)}")
        logger.info(f"Request ID: {transfer_data.request_id}")
        logger.info(f"Created By: {created_by}")
        
        # Use frontend-provided challan_no if available, otherwise generate one
        if transfer_data.header.challan_no:
            challan_no = transfer_data.header.challan_no
            logger.info(f"✅ Using frontend-provided challan_no: {challan_no}")
        else:
            challan_no = generate_challan_no()
            logger.info(f"📝 Generated new challan_no: {challan_no}")
        
        # Create transfer header
        logger.info(f"📝 Creating transfer header with:")
        logger.info(f"  - vehicle_no: {transfer_data.header.vehicle_no}")
        logger.info(f"  - driver_name: {transfer_data.header.driver_name}")
        logger.info(f"  - approved_by: {transfer_data.header.approved_by}")
        logger.info(f"  - remark: {transfer_data.header.remark}")
        
        header_sql = text("""
            INSERT INTO interunit_transfers_header
            (challan_no, stock_trf_date, from_site, to_site, vehicle_no, driver_name, approved_by, remark, reason_code, 
             status, request_id, created_by, created_ts)
            VALUES (:challan_no, :stock_trf_date, :from_site, :to_site, :vehicle_no, :driver_name, :approved_by, :remark, :reason_code,
                    'Pending', :request_id, :created_by, :created_ts)
            RETURNING id, challan_no, stock_trf_date, from_site, to_site, vehicle_no, driver_name, approved_by, remark, reason_code,
                      status, request_id, created_by, created_ts, approved_ts, updated_ts, has_variance
        """)
        
        header_result = db.execute(header_sql, {
            "challan_no": challan_no,
            "stock_trf_date": transfer_data.header.stock_trf_date,
            "from_site": transfer_data.header.from_warehouse,
            "to_site": transfer_data.header.to_warehouse,
            "vehicle_no": transfer_data.header.vehicle_no,
            "driver_name": transfer_data.header.driver_name,
            "approved_by": transfer_data.header.approved_by,
            "remark": transfer_data.header.remark,
            "reason_code": transfer_data.header.reason_code,
            "request_id": transfer_data.request_id,
            "created_by": created_by,
            "created_ts": datetime.now()
        }).fetchone()
        
        header_id = header_result.id
        
        # Create transfer lines
        lines = []
        for line in transfer_data.lines:
            # Calculate net_weight as pack_size * quantity
            pack_size = float(line.pack_size) if line.pack_size else 0
            quantity = int(line.quantity) if line.quantity else 0
            net_weight = pack_size * quantity
            
            line_sql = text("""
                INSERT INTO interunit_transfers_lines
                (header_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw,
                 pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number)
                VALUES (:header_id, :material_type, :item_category, :sub_category, :item_desc_raw,
                        :pack_size, :quantity, :uom, :packaging_type, :net_weight, :total_weight, :batch_number, :lot_number)
                RETURNING id, header_id, rm_pm_fg_type, item_category, sub_category, item_desc_raw,
                          pack_size, qty, uom, packaging_type, net_weight, total_weight, batch_number, lot_number,
                          created_at, updated_at
            """)
            
            line_result = db.execute(line_sql, {
                "header_id": header_id,
                "material_type": line.material_type,
                "item_category": line.item_category,
                "sub_category": line.sub_category,
                "item_desc_raw": line.item_description,
                "pack_size": pack_size,
                "quantity": quantity,
                "uom": line.uom,
                "packaging_type": float(line.package_size) if line.package_size else 0,
                "net_weight": net_weight,
                "total_weight": net_weight,  # Same as net_weight for now
                "batch_number": line.batch_number if line.batch_number else "",
                "lot_number": line.lot_number if line.lot_number else ""
            }).fetchone()
            
            lines.append(line_result)
        
        # Create transfer boxes if provided
        boxes = []
        if transfer_data.boxes:
            logger.info(f"📦 Creating {len(transfer_data.boxes)} boxes...")
            for box in transfer_data.boxes:
                box_sql = text("""
                    INSERT INTO interunit_transfer_boxes
                    (header_id, transfer_line_id, box_number, article, lot_number, batch_number, transaction_no, net_weight, gross_weight)
                    VALUES (:header_id, :transfer_line_id, :box_number, :article, :lot_number, :batch_number, :transaction_no, :net_weight, :gross_weight)
                    RETURNING id, transfer_line_id, header_id, box_number, article, lot_number, batch_number, transaction_no,
                              net_weight, gross_weight, created_at, updated_at
                """)
                
                # For now, link all boxes to the first line (you may need to improve this logic)
                transfer_line_id = lines[0].id if lines else None
                
                box_result = db.execute(box_sql, {
                    "header_id": header_id,
                    "transfer_line_id": transfer_line_id,
                    "box_number": box.box_number,
                    "article": box.article,
                    "lot_number": box.lot_number if box.lot_number else "",
                    "batch_number": box.batch_number if box.batch_number else "",
                    "transaction_no": box.transaction_no if box.transaction_no else "",
                    "net_weight": float(box.net_weight),
                    "gross_weight": float(box.gross_weight)
                }).fetchone()
                
                boxes.append(box_result)
            
            logger.info(f"✅ {len(boxes)} boxes created successfully")
        
        # Update request status to "Transferred" if transfer was created from request
        if transfer_data.request_id:
            logger.info(f"📝 Updating request {transfer_data.request_id} status to 'Transferred'")
            update_request_sql = text("""
                UPDATE interunit_transfer_requests
                SET status = 'Transferred',
                    updated_at = :updated_at
                WHERE id = :request_id
            """)
            db.execute(update_request_sql, {
                "request_id": transfer_data.request_id,
                "updated_at": datetime.now()
            })
            logger.info(f"✅ Request {transfer_data.request_id} status updated to 'Transferred'")
        
        db.commit()
        
        logger.info(f"✅ Transfer created successfully")
        logger.info(f"Transfer ID: {header_id}, Challan No: {challan_no}")
        logger.info(f"Lines Created: {len(lines)}")
        logger.info(f"Boxes Created: {len(boxes)}")
        logger.info("=" * 80)
        
        # Return response
        return {
            "header": {
                "id": header_result.id,
                "challan_no": header_result.challan_no,
                "stock_trf_date": header_result.stock_trf_date,
                "from_warehouse": header_result.from_site,
                "to_warehouse": header_result.to_site,
                "vehicle_no": header_result.vehicle_no,
                "driver_name": header_result.driver_name,
                "remark": header_result.remark,
                "reason_code": header_result.reason_code,
                "status": header_result.status,
                "request_id": header_result.request_id,
                "created_by": header_result.created_by,
                "created_ts": header_result.created_ts,
                "approved_by": header_result.approved_by,
                "approved_ts": header_result.approved_ts,
                "updated_ts": header_result.updated_ts,
                "has_variance": header_result.has_variance
            },
            "lines": [
                {
                    "id": line.id,
                    "header_id": line.header_id,
                    "material_type": line.rm_pm_fg_type,
                    "item_category": line.item_category,
                    "sub_category": line.sub_category,
                    "item_description": line.item_desc_raw,
                    "quantity": str(line.qty),
                    "uom": line.uom,
                    "pack_size": str(line.pack_size),
                    "package_size": str(line.packaging_type) if line.packaging_type else None,
                    "net_weight": str(line.net_weight),
                    "batch_number": line.batch_number,
                    "lot_number": line.lot_number,
                    "created_at": line.created_at,
                    "updated_at": line.updated_at
                }
                for line in lines
            ]
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating transfer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create transfer: {str(e)}")

# ============================================
# APPROVAL AUTHORITIES DROPDOWN ENDPOINTS
# ============================================

@router.get("/dropdowns/approval-authorities", response_model=List[ApprovalAuthorityResponse])
def get_approval_authorities(
    warehouse: Optional[str] = Query(None, description="Filter by warehouse"),
    active_only: bool = Query(True, description="Return only active authorities"),
    db: Session = Depends(get_db)
):
    """
    Get all approval authorities for dropdown
    """
    try:
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        if active_only:
            where_clauses.append("is_active = :active_only")
            params["active_only"] = True
        
        if warehouse:
            where_clauses.append("warehouse = :warehouse")
            params["warehouse"] = warehouse.upper()
        
        where_sql = " AND ".join(where_clauses)
        
        # Query approval authorities
        sql = text(f"""
            SELECT id, authority, contact_number, email, warehouse, is_active
            FROM transfers_approval_authorities
            WHERE {where_sql}
            ORDER BY authority ASC
        """)
        
        results = db.execute(sql, params).fetchall()
        
        # Format response
        authorities = [
            ApprovalAuthorityResponse(
                id=row.id,
                authority=row.authority,
                contact_number=row.contact_number,
                email=row.email,
                warehouse=row.warehouse,
                is_active=row.is_active
            )
            for row in results
        ]
        
        logger.info(f"Retrieved {len(authorities)} approval authorities")
        return authorities
        
    except Exception as e:
        logger.error(f"Error fetching approval authorities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch approval authorities: {str(e)}")

@router.get("/dropdowns/approval-authorities/warehouse/{warehouse}", response_model=List[ApprovalAuthorityResponse])
def get_approval_authorities_by_warehouse(
    warehouse: str,
    active_only: bool = Query(True, description="Return only active authorities"),
    db: Session = Depends(get_db)
):
    """
    Get approval authorities by warehouse for dropdown
    """
    try:
        # Build WHERE clause
        where_clauses = ["warehouse = :warehouse"]
        params = {"warehouse": warehouse.upper()}
        
        if active_only:
            where_clauses.append("is_active = :active_only")
            params["active_only"] = True
        
        where_sql = " AND ".join(where_clauses)
        
        # Query approval authorities for warehouse
        sql = text(f"""
            SELECT id, authority, contact_number, email, warehouse, is_active
            FROM transfers_approval_authorities
            WHERE {where_sql}
            ORDER BY authority ASC
        """)
        
        results = db.execute(sql, params).fetchall()
        
        # Format response
        authorities = [
            ApprovalAuthorityResponse(
                id=row.id,
                authority=row.authority,
                contact_number=row.contact_number,
                email=row.email,
                warehouse=row.warehouse,
                is_active=row.is_active
            )
            for row in results
        ]
        
        logger.info(f"Retrieved {len(authorities)} approval authorities for warehouse {warehouse}")
        return authorities
        
    except Exception as e:
        logger.error(f"Error fetching approval authorities for warehouse {warehouse}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch approval authorities: {str(e)}")

# ============================================
# TRANSFERS LIST ENDPOINT
# ============================================

@router.get("/transfers")
def get_transfers(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    from_site: Optional[str] = Query(None, description="Filter by from site"),
    to_site: Optional[str] = Query(None, description="Filter by to site"),
    from_date: Optional[str] = Query(None, description="Filter by start date (DD-MM-YYYY)"),
    to_date: Optional[str] = Query(None, description="Filter by end date (DD-MM-YYYY)"),
    challan_no: Optional[str] = Query(None, description="Filter by transfer number"),
    sort_by: str = Query("created_ts", description="Sort by field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db)
):
    """
    Get list of transfer records from interunit_transfers_header
    """
    try:
        logger.info("=" * 80)
        logger.info("GET /interunit/transfers called")
        logger.info(f"Params: page={page}, per_page={per_page}, status={status}, from_site={from_site}, to_site={to_site}")
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        if status:
            where_clauses.append("h.status = :status")
            params["status"] = status
        
        if from_site:
            where_clauses.append("h.from_site = :from_site")
            params["from_site"] = from_site
        
        if to_site:
            where_clauses.append("h.to_site = :to_site")
            params["to_site"] = to_site
        
        if from_date:
            from_date_obj = convert_date_format(from_date)
            where_clauses.append("h.stock_trf_date >= :from_date")
            params["from_date"] = from_date_obj
        
        if to_date:
            to_date_obj = convert_date_format(to_date)
            where_clauses.append("h.stock_trf_date <= :to_date")
            params["to_date"] = to_date_obj
        
        if challan_no:
            where_clauses.append("h.challan_no = :challan_no")
            params["challan_no"] = challan_no
        
        where_sql = " AND ".join(where_clauses)
        
        # Build ORDER BY clause
        valid_sort_fields = ["challan_no", "stock_trf_date", "from_site", "to_site", "status", "created_ts"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_ts"
        
        order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        order_sql = f"h.{sort_by} {order_direction}"
        
        # Get total count
        count_sql = text(f"""
            SELECT COUNT(*)
            FROM interunit_transfers_header h
            WHERE {where_sql}
        """)
        
        total = db.execute(count_sql, params).scalar()
        logger.info(f"Total transfers found: {total}")
        
        # Get paginated records with aggregated counts
        offset = (page - 1) * per_page
        params["limit"] = per_page
        params["offset"] = offset
        
        sql = text(f"""
            SELECT 
                h.id,
                h.challan_no,
                h.stock_trf_date,
                h.from_site,
                h.to_site,
                h.vehicle_no,
                h.driver_name,
                h.remark,
                h.reason_code,
                h.status,
                h.request_id,
                h.created_by,
                h.created_ts,
                h.approved_by,
                h.approved_ts,
                h.has_variance,
                r.request_no,
                COUNT(DISTINCT l.id) as items_count,
                COUNT(DISTINCT b.id) as boxes_count,
                COALESCE(SUM(l.qty), 0) as total_qty
            FROM interunit_transfers_header h
            LEFT JOIN interunit_transfer_requests r ON h.request_id = r.id
            LEFT JOIN interunit_transfers_lines l ON h.id = l.header_id
            LEFT JOIN interunit_transfer_boxes b ON h.id = b.header_id
            WHERE {where_sql}
            GROUP BY h.id, r.request_no
            ORDER BY {order_sql}
            LIMIT :limit OFFSET :offset
        """)
        
        results = db.execute(sql, params).fetchall()
        logger.info(f"Retrieved {len(results)} transfer records")
        
        # Format response
        transfers = []
        for row in results:
            # Calculate pending items: total_qty - boxes_count
            # (boxes_count is the actual number of scanned boxes)
            pending_items = max(0, int(row.total_qty or 0) - int(row.boxes_count or 0))
            
            # Format date to DD-MM-YYYY
            transfer_date = row.stock_trf_date.strftime('%d-%m-%Y') if row.stock_trf_date else ""
            created_ts = row.created_ts.strftime('%Y-%m-%dT%H:%M:%SZ') if row.created_ts else ""
            
            transfer = {
                "id": row.id,
                "challan_no": row.challan_no,
                "transfer_no": row.challan_no,  # Alias for frontend compatibility
                "request_no": row.request_no,
                "stock_trf_date": transfer_date,
                "transfer_date": transfer_date,  # Alias for frontend compatibility
                "from_site": row.from_site,
                "from_warehouse": row.from_site,  # Alias for frontend compatibility
                "to_site": row.to_site,
                "to_warehouse": row.to_site,  # Alias for frontend compatibility
                "vehicle_no": row.vehicle_no,
                "vehicle_number": row.vehicle_no,  # Alias for frontend compatibility
                "driver_name": row.driver_name or "N/A",
                "approval_authority": row.approved_by or "N/A",
                "remark": row.remark,
                "reason_code": row.reason_code,
                "status": row.status,
                "request_id": row.request_id,
                "created_by": row.created_by,
                "created_ts": created_ts,
                "approved_by": row.approved_by,
                "approved_ts": row.approved_ts.strftime('%Y-%m-%dT%H:%M:%SZ') if row.approved_ts else None,
                "has_variance": row.has_variance,
                "items_count": row.items_count or 0,
                "boxes_count": row.boxes_count or 0,
                "pending_items": pending_items
            }
            transfers.append(transfer)
        
        # Calculate pagination info
        total_pages = (total + per_page - 1) // per_page
        
        response = {
            "records": transfers,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
        
        logger.info(f"Returning {len(transfers)} transfers, page {page}/{total_pages}")
        logger.info("=" * 80)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transfers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch transfers: {str(e)}")

@router.get("/transfers/{transfer_id}")
def get_transfer_details(
    transfer_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed transfer information including lines and boxes
    """
    try:
        logger.info("=" * 80)
        logger.info(f"GET /interunit/transfers/{transfer_id} called")
        
        # Get transfer header
        header_sql = text("""
            SELECT 
                h.id,
                h.challan_no,
                h.stock_trf_date,
                h.from_site,
                h.to_site,
                h.vehicle_no,
                h.driver_name,
                h.remark,
                h.reason_code,
                h.status,
                h.request_id,
                h.created_by,
                h.created_ts,
                h.approved_by,
                h.approved_ts,
                h.has_variance,
                r.request_no
            FROM interunit_transfers_header h
            LEFT JOIN interunit_transfer_requests r ON h.request_id = r.id
            WHERE h.id = :transfer_id
        """)
        
        header = db.execute(header_sql, {"transfer_id": transfer_id}).fetchone()
        
        if not header:
            raise HTTPException(status_code=404, detail="Transfer not found")
        
        # Get transfer lines
        lines_sql = text("""
            SELECT 
                id,
                header_id,
                rm_pm_fg_type,
                item_category,
                sub_category,
                item_desc_raw,
                item_id,
                hsn_code,
                pack_size,
                packaging_type,
                qty,
                uom,
                net_weight,
                total_weight,
                batch_number,
                lot_number,
                created_at,
                updated_at
            FROM interunit_transfers_lines
            WHERE header_id = :transfer_id
            ORDER BY id
        """)
        
        lines = db.execute(lines_sql, {"transfer_id": transfer_id}).fetchall()
        
        # Get transfer boxes
        boxes_sql = text("""
            SELECT 
                id,
                transfer_line_id,
                header_id,
                box_number,
                article,
                lot_number,
                batch_number,
                transaction_no,
                net_weight,
                gross_weight,
                created_at,
                updated_at
            FROM interunit_transfer_boxes
            WHERE header_id = :transfer_id
            ORDER BY box_number
        """)
        
        boxes = db.execute(boxes_sql, {"transfer_id": transfer_id}).fetchall()
        
        # Format date to DD-MM-YYYY
        transfer_date = header.stock_trf_date.strftime('%d-%m-%Y') if header.stock_trf_date else ""
        created_ts = header.created_ts.strftime('%Y-%m-%dT%H:%M:%SZ') if header.created_ts else ""
        
        # Get driver name and approval authority
        driver_name = header.driver_name or "N/A"
        approval_authority = header.approved_by or "N/A"
        
        # Calculate counts
        items_count = len(lines)
        boxes_count = len(boxes)
        total_qty = sum(line.qty for line in lines) if lines else 0
        pending_items = max(0, total_qty - boxes_count)
        
        # Build response
        response = {
            "id": header.id,
            "challan_no": header.challan_no,
            "request_no": header.request_no,
            "stock_trf_date": transfer_date,
            "transfer_date": transfer_date,
            "from_site": header.from_site,
            "from_warehouse": header.from_site,
            "to_site": header.to_site,
            "to_warehouse": header.to_site,
            "vehicle_no": header.vehicle_no,
            "vehicle_number": header.vehicle_no,
            "driver_name": driver_name,
            "approval_authority": approval_authority,
            "remark": header.remark,
            "total_qty_required": total_qty,
            "boxes_provided": boxes_count,
            "boxes_pending": pending_items,
            "reason_code": header.reason_code,
            "status": header.status,
            "request_id": header.request_id,
            "created_by": header.created_by,
            "created_ts": created_ts,
            "approved_by": header.approved_by,
            "approved_ts": header.approved_ts.strftime('%Y-%m-%dT%H:%M:%SZ') if header.approved_ts else None,
            "has_variance": header.has_variance,
            "items_count": items_count,
            "boxes_count": boxes_count,
            "pending_items": pending_items,
            "lines": [
                {
                    "id": line.id,
                    "header_id": line.header_id,
                    "rm_pm_fg_type": line.rm_pm_fg_type,
                    "item_category": line.item_category,
                    "sub_category": line.sub_category,
                    "item_desc_raw": line.item_desc_raw,
                    "item_id": line.item_id,
                    "hsn_code": line.hsn_code,
                    "pack_size": float(line.pack_size) if line.pack_size else 0,
                    "packaging_type": line.packaging_type,
                    "qty": line.qty,
                    "uom": line.uom,
                    "net_weight": float(line.net_weight) if line.net_weight else 0,
                    "total_weight": float(line.total_weight) if line.total_weight else 0,
                    "batch_number": line.batch_number,
                    "lot_number": line.lot_number,
                    "created_at": line.created_at.strftime('%Y-%m-%dT%H:%M:%SZ') if line.created_at else None,
                    "updated_at": line.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ') if line.updated_at else None
                }
                for line in lines
            ],
            "boxes": [
                {
                    "id": box.id,
                    "transfer_line_id": box.transfer_line_id,
                    "header_id": box.header_id,
                    "box_number": box.box_number,
                    "article": box.article,
                    "lot_number": box.lot_number,
                    "batch_number": box.batch_number,
                    "transaction_no": box.transaction_no,
                    "net_weight": float(box.net_weight) if box.net_weight else 0,
                    "gross_weight": float(box.gross_weight) if box.gross_weight else 0,
                    "created_at": box.created_at.strftime('%Y-%m-%dT%H:%M:%SZ') if box.created_at else None,
                    "updated_at": box.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ') if box.updated_at else None
                }
                for box in boxes
            ]
        }
        
        logger.info(f"Transfer details retrieved: {header.challan_no}")
        logger.info(f"Lines: {items_count}, Boxes: {boxes_count}, Pending: {pending_items}")
        logger.info("=" * 80)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transfer details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch transfer details: {str(e)}")


# ============================================
# CONFIRM TRANSFER RECEIPT (Transfer IN)
# ============================================
@router.put("/transfers/{transfer_id}/confirm")
def confirm_transfer_receipt(transfer_id: int, db: Session = Depends(get_db)):
    """
    Confirm receipt of transfer (Transfer IN)
    Updates status to 'Received' so it appears in All Transfers list
    """
    try:
        logger.info("=" * 80)
        logger.info(f"Confirming transfer receipt for ID: {transfer_id}")
        
        # Get transfer header
        transfer = db.execute(
            text("""
                SELECT id, challan_no, status
                FROM interunit_transfers_header
                WHERE id = :transfer_id
            """),
            {"transfer_id": transfer_id}
        ).fetchone()
        
        if not transfer:
            raise HTTPException(status_code=404, detail="Transfer not found")
        
        # Update status to 'Received'
        db.execute(
            text("""
                UPDATE interunit_transfers_header
                SET status = 'Received',
                    updated_ts = CURRENT_TIMESTAMP
                WHERE id = :transfer_id
            """),
            {"transfer_id": transfer_id}
        )
        
        db.commit()
        
        logger.info(f"✅ Transfer {transfer.challan_no} confirmed as Received")
        logger.info("=" * 80)
        
        return {
            "success": True,
            "message": "Transfer receipt confirmed successfully",
            "transfer_id": transfer_id,
            "challan_no": transfer.challan_no,
            "status": "Received"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error confirming transfer receipt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to confirm transfer receipt: {str(e)}")


# ============================================
# TRANSFER IN ENDPOINTS
# ============================================

@router.post("/transfer-in", status_code=201)
async def create_transfer_in(
    transfer_in_data: schemas.TransferInCreate,
    db: Session = Depends(get_db)
    # current_user: dict = Depends(get_current_user)  # Temporarily disabled for testing
):
    """
    Create a new Transfer IN (GRN) with scanned boxes
    """
    try:
        logger.info("=" * 80)
        logger.info("📥 CREATING TRANSFER IN (GRN)")
        logger.info(f"Transfer OUT ID: {transfer_in_data.transfer_out_id}")
        logger.info(f"GRN Number: {transfer_in_data.grn_number}")
        logger.info(f"Receiving Warehouse: {transfer_in_data.receiving_warehouse}")
        logger.info(f"Received By: {transfer_in_data.received_by}")
        logger.info(f"Box Condition: {transfer_in_data.box_condition}")
        logger.info(f"Scanned Boxes: {len(transfer_in_data.scanned_boxes)}")
        
        # Verify Transfer OUT exists
        transfer_out = db.execute(
            text("SELECT id, challan_no FROM interunit_transfers_header WHERE id = :id"),
            {"id": transfer_in_data.transfer_out_id}
        ).fetchone()
        
        if not transfer_out:
            raise HTTPException(status_code=404, detail="Transfer OUT not found")
        
        logger.info(f"✅ Transfer OUT found: {transfer_out.challan_no}")
        
        # Check if GRN number already exists
        existing_grn = db.execute(
            text("SELECT id FROM interunit_transfer_in_header WHERE grn_number = :grn"),
            {"grn": transfer_in_data.grn_number}
        ).fetchone()
        
        if existing_grn:
            raise HTTPException(status_code=400, detail=f"GRN number {transfer_in_data.grn_number} already exists")
        
        # Insert Transfer IN Header
        header_sql = text("""
            INSERT INTO interunit_transfer_in_header
            (transfer_out_id, transfer_out_no, grn_number, grn_date, receiving_warehouse, 
             received_by, received_at, box_condition, condition_remarks, status)
            VALUES (:transfer_out_id, :transfer_out_no, :grn_number, CURRENT_TIMESTAMP, 
                    :receiving_warehouse, :received_by, CURRENT_TIMESTAMP, :box_condition, 
                    :condition_remarks, 'Received')
            RETURNING id, grn_number, grn_date, receiving_warehouse, received_by, 
                      received_at, box_condition, condition_remarks, status, created_at, updated_at
        """)
        
        header_result = db.execute(header_sql, {
            "transfer_out_id": transfer_in_data.transfer_out_id,
            "transfer_out_no": transfer_out.challan_no,
            "grn_number": transfer_in_data.grn_number,
            "receiving_warehouse": transfer_in_data.receiving_warehouse.upper(),
            "received_by": transfer_in_data.received_by.upper(),
            "box_condition": transfer_in_data.box_condition,
            "condition_remarks": transfer_in_data.condition_remarks if transfer_in_data.condition_remarks else None
        }).fetchone()
        
        header_id = header_result.id
        logger.info(f"✅ Transfer IN Header created with ID: {header_id}")
        
        # Insert scanned boxes
        boxes = []
        for box in transfer_in_data.scanned_boxes:
            box_sql = text("""
                INSERT INTO interunit_transfer_in_boxes
                (header_id, box_number, article, batch_number, lot_number, transaction_no,
                 net_weight, gross_weight, scanned_at, is_matched)
                VALUES (:header_id, :box_number, :article, :batch_number, :lot_number, 
                        :transaction_no, :net_weight, :gross_weight, CURRENT_TIMESTAMP, :is_matched)
                RETURNING id, box_number, article, batch_number, lot_number, transaction_no,
                          net_weight, gross_weight, scanned_at, is_matched
            """)
            
            box_result = db.execute(box_sql, {
                "header_id": header_id,
                "box_number": box.box_number,
                "article": box.article if box.article else None,
                "batch_number": box.batch_number if box.batch_number else None,
                "lot_number": box.lot_number if box.lot_number else None,
                "transaction_no": box.transaction_no if box.transaction_no else None,
                "net_weight": float(box.net_weight) if box.net_weight else None,
                "gross_weight": float(box.gross_weight) if box.gross_weight else None,
                "is_matched": box.is_matched
            }).fetchone()
            
            boxes.append(box_result)
        
        logger.info(f"✅ {len(boxes)} boxes recorded in Transfer IN")
        
        # Update Transfer OUT status to "Received"
        db.execute(
            text("""
                UPDATE interunit_transfers_header
                SET status = 'Received', updated_ts = CURRENT_TIMESTAMP
                WHERE id = :transfer_out_id
            """),
            {"transfer_out_id": transfer_in_data.transfer_out_id}
        )
        
        db.commit()
        
        logger.info("✅ Transfer IN created successfully")
        logger.info("=" * 80)
        
        # Return response
        return {
            "header": {
                "id": header_result.id,
                "transfer_out_id": transfer_in_data.transfer_out_id,
                "transfer_out_no": transfer_out.challan_no,
                "grn_number": header_result.grn_number,
                "grn_date": header_result.grn_date,
                "receiving_warehouse": header_result.receiving_warehouse,
                "received_by": header_result.received_by,
                "received_at": header_result.received_at,
                "box_condition": header_result.box_condition,
                "condition_remarks": header_result.condition_remarks,
                "status": header_result.status,
                "created_at": header_result.created_at,
                "updated_at": header_result.updated_at
            },
            "boxes": [
                {
                    "id": b.id,
                    "box_number": b.box_number,
                    "article": b.article,
                    "batch_number": b.batch_number,
                    "lot_number": b.lot_number,
                    "transaction_no": b.transaction_no,
                    "net_weight": b.net_weight,
                    "gross_weight": b.gross_weight,
                    "scanned_at": b.scanned_at,
                    "is_matched": b.is_matched
                }
                for b in boxes
            ],
            "total_boxes_scanned": len(boxes)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creating Transfer IN: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Transfer IN: {str(e)}")


@router.get("/transfer-in")
async def get_transfer_in_list(
    db: Session = Depends(get_db),
    # current_user: dict = Depends(get_current_user),  # Temporarily disabled
    skip: int = 0,
    limit: int = 100
):
    """
    Get list of all Transfer INs (GRNs)
    """
    try:
        logger.info(f"📥 Fetching Transfer IN list (skip: {skip}, limit: {limit})")
        
        # Get Transfer IN records with box counts
        query = text("""
            SELECT 
                h.id,
                h.transfer_out_id,
                h.transfer_out_no,
                h.grn_number,
                h.grn_date,
                h.receiving_warehouse,
                h.received_by,
                h.received_at,
                h.box_condition,
                h.status,
                COUNT(b.id) as total_boxes_scanned,
                h.created_at
            FROM interunit_transfer_in_header h
            LEFT JOIN interunit_transfer_in_boxes b ON h.id = b.header_id
            GROUP BY h.id
            ORDER BY h.created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        
        results = db.execute(query, {"limit": limit, "skip": skip}).fetchall()
        
        transfer_ins = [
            {
                "id": row.id,
                "transfer_out_id": row.transfer_out_id,
                "transfer_out_no": row.transfer_out_no,
                "grn_number": row.grn_number,
                "grn_date": row.grn_date,
                "receiving_warehouse": row.receiving_warehouse,
                "received_by": row.received_by,
                "received_at": row.received_at,
                "box_condition": row.box_condition,
                "status": row.status,
                "total_boxes_scanned": row.total_boxes_scanned,
                "created_at": row.created_at
            }
            for row in results
        ]
        
        # Get total count
        count_result = db.execute(text("SELECT COUNT(*) as count FROM interunit_transfer_in_header")).fetchone()
        total = count_result.count if count_result else 0
        
        logger.info(f"✅ Found {len(transfer_ins)} Transfer INs (Total: {total})")
        
        return {
            "items": transfer_ins,
            "total": total,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching Transfer IN list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Transfer IN list: {str(e)}")


@router.get("/transfer-in/{transfer_in_id}")
async def get_transfer_in_detail(
    transfer_in_id: int,
    db: Session = Depends(get_db)
    # current_user: dict = Depends(get_current_user)  # Temporarily disabled
):
    """
    Get detailed Transfer IN with all scanned boxes
    """
    try:
        logger.info(f"📥 Fetching Transfer IN detail for ID: {transfer_in_id}")
        
        # Get header
        header_query = text("""
            SELECT id, transfer_out_id, transfer_out_no, grn_number, grn_date,
                   receiving_warehouse, received_by, received_at, box_condition,
                   condition_remarks, status, created_at, updated_at
            FROM interunit_transfer_in_header
            WHERE id = :id
        """)
        
        header = db.execute(header_query, {"id": transfer_in_id}).fetchone()
        
        if not header:
            raise HTTPException(status_code=404, detail="Transfer IN not found")
        
        # Get boxes
        boxes_query = text("""
            SELECT id, box_number, article, batch_number, lot_number, transaction_no,
                   net_weight, gross_weight, scanned_at, is_matched
            FROM interunit_transfer_in_boxes
            WHERE header_id = :header_id
            ORDER BY scanned_at
        """)
        
        boxes = db.execute(boxes_query, {"header_id": transfer_in_id}).fetchall()
        
        logger.info(f"✅ Found Transfer IN with {len(boxes)} boxes")
        
        return {
            "header": {
                "id": header.id,
                "transfer_out_id": header.transfer_out_id,
                "transfer_out_no": header.transfer_out_no,
                "grn_number": header.grn_number,
                "grn_date": header.grn_date,
                "receiving_warehouse": header.receiving_warehouse,
                "received_by": header.received_by,
                "received_at": header.received_at,
                "box_condition": header.box_condition,
                "condition_remarks": header.condition_remarks,
                "status": header.status,
                "created_at": header.created_at,
                "updated_at": header.updated_at
            },
            "boxes": [
                {
                    "id": b.id,
                    "box_number": b.box_number,
                    "article": b.article,
                    "batch_number": b.batch_number,
                    "lot_number": b.lot_number,
                    "transaction_no": b.transaction_no,
                    "net_weight": b.net_weight,
                    "gross_weight": b.gross_weight,
                    "scanned_at": b.scanned_at,
                    "is_matched": b.is_matched
                }
                for b in boxes
            ],
            "total_boxes_scanned": len(boxes)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching Transfer IN detail: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Transfer IN detail: {str(e)}")
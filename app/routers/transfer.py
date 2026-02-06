# File: transfer_router.py
# Path: backend/app/routers/transfer.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transfer import (
    TransferRequest, TransferRequestItem, TransferScannedBox, 
    TransferInfo, WarehouseMaster, generate_request_no, generate_transfer_no,
    get_transfer_with_details, get_warehouse_addresses
)
from app.schemas.transfer import (
    TransferRequestCreate, TransferRequestResponse, TransferRequestListResponse,
    TransferCompleteCreate, TransferCompleteResponse, TransferRequestDetailResponse,
    DCDataResponse, ScannerInput, ScannerResponse, BoxScanData,
    TransferRequestFilter, StandardResponse, WarehouseMasterResponse
)

router = APIRouter(prefix="/transfer", tags=["Transfer Module"])


# ============================================
# WAREHOUSE MASTER ENDPOINTS
# ============================================

@router.get("/warehouses", response_model=List[WarehouseMasterResponse])
async def get_warehouses(
    is_active: bool = Query(True, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """Get all warehouses for dropdowns"""
    warehouses = db.query(WarehouseMaster).filter(
        WarehouseMaster.is_active == is_active
    ).order_by(WarehouseMaster.warehouse_name).all()
    
    return warehouses


# ============================================
# TRANSFER REQUEST ENDPOINTS
# ============================================

@router.post("/request", response_model=StandardResponse)
async def create_transfer_request(
    request_data: TransferRequestCreate,
    db: Session = Depends(get_db)
):
    """Create a new transfer request"""
    try:
        # Use request_no from frontend if provided, otherwise generate one
        request_no = request_data.request_no if hasattr(request_data, 'request_no') and request_data.request_no else generate_request_no(db)
        
        # Create transfer request
        transfer_request = TransferRequest(
            request_no=request_no,
            request_date=request_data.request_date,
            from_warehouse=request_data.from_warehouse,
            to_warehouse=request_data.to_warehouse,
            reason=request_data.reason,
            reason_description=request_data.reason_description,
            status="Pending",
            created_by=request_data.created_by
        )
        
        db.add(transfer_request)
        db.flush()  # Get the ID
        
        # Create transfer request items
        for item_data in request_data.items:
            item = TransferRequestItem(
                transfer_id=transfer_request.id,
                line_number=item_data.line_number,
                material_type=item_data.material_type,
                item_category=item_data.item_category,
                sub_category=item_data.sub_category,
                item_description=item_data.item_description,
                sku_id=item_data.sku_id,
                quantity=item_data.quantity,
                uom=item_data.uom,
                pack_size=item_data.pack_size,
                package_size=item_data.package_size,
                net_weight=item_data.net_weight
            )
            db.add(item)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Transfer request created successfully",
            data={"request_no": request_no, "request_id": transfer_request.id}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating transfer request: {str(e)}"
        )


@router.get("/requests", response_model=TransferRequestListResponse)
async def get_transfer_requests(
    request_status: Optional[str] = Query(None, description="Filter by status", alias="status"),
    from_warehouse: Optional[str] = Query(None, description="Filter by from warehouse"),
    to_warehouse: Optional[str] = Query(None, description="Filter by to warehouse"),
    request_date_from: Optional[date] = Query(None, description="Filter from date"),
    request_date_to: Optional[date] = Query(None, description="Filter to date"),
    from_date: Optional[date] = Query(None, description="Filter from date (alias)"),
    to_date: Optional[date] = Query(None, description="Filter to date (alias)"),
    created_by: Optional[str] = Query(None, description="Filter by creator"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=1000, description="Items per page"),
    db: Session = Depends(get_db)
):
    """Get transfer requests list with filtering and pagination"""
    try:
        # Support both parameter names (from_date/to_date and request_date_from/request_date_to)
        effective_date_from = request_date_from or from_date
        effective_date_to = request_date_to or to_date

        query = db.query(TransferRequest)

        # Apply filters
        if request_status:
            query = query.filter(TransferRequest.status == request_status)
        if from_warehouse:
            query = query.filter(TransferRequest.from_warehouse == from_warehouse)
        if to_warehouse:
            query = query.filter(TransferRequest.to_warehouse == to_warehouse)
        if effective_date_from:
            query = query.filter(TransferRequest.request_date >= effective_date_from)
        if effective_date_to:
            query = query.filter(TransferRequest.request_date <= effective_date_to)
        if created_by:
            query = query.filter(TransferRequest.created_by == created_by)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        requests = query.order_by(TransferRequest.created_at.desc()).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        
        # Get item counts for each request
        request_list = []
        for req in requests:
            item_count = db.query(TransferRequestItem).filter(
                TransferRequestItem.transfer_id == req.id
            ).count()
            
            request_list.append({
                "id": req.id,
                "request_no": req.request_no,
                "transfer_no": req.transfer_no,
                "request_date": req.request_date,
                "from_warehouse": req.from_warehouse,
                "to_warehouse": req.to_warehouse,
                "reason_description": req.reason_description,
                "status": req.status,
                "item_count": item_count,
                "created_by": req.created_by,
                "created_at": req.created_at
            })
        
        return TransferRequestListResponse(
            success=True,
            message="Transfer requests retrieved successfully",
            data=request_list,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving transfer requests: {str(e)}"
        )


@router.get("/requests/{request_id}", response_model=TransferRequestDetailResponse)
async def get_transfer_request_detail(
    request_id: int,
    db: Session = Depends(get_db)
):
    """Get transfer request details by ID (used in transfer form)"""
    try:
        transfer_data = get_transfer_with_details(db, request_id)
        
        if not transfer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transfer request not found"
            )
        
        return TransferRequestDetailResponse(
            success=True,
            message="Transfer request details retrieved successfully",
            data=transfer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving transfer request details: {str(e)}"
        )


# ============================================
# TRANSFER FORM ENDPOINTS
# ============================================

@router.post("/submit", response_model=StandardResponse)
async def submit_transfer(
    transfer_data: TransferCompleteCreate,
    db: Session = Depends(get_db)
):
    """Submit complete transfer with scanned boxes and transport details"""
    try:
        # Find the existing request
        existing_request = db.query(TransferRequest).filter(
            TransferRequest.request_no == transfer_data.request_no
        ).first()
        
        if not existing_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transfer request not found"
            )
        
        # Generate transfer number if not exists
        if not existing_request.transfer_no:
            transfer_no = generate_transfer_no(db)
            existing_request.transfer_no = transfer_no
        
        # Update request status
        existing_request.status = "In Transit"
        
        # Create scanned boxes
        for box_data in transfer_data.scanned_boxes:
            scanned_box = TransferScannedBox(
                transfer_id=existing_request.id,
                box_id=box_data.box_id,
                transaction_no=box_data.transaction_no,
                sku_id=box_data.sku_id,
                box_number_in_array=box_data.box_number_in_array,
                box_number=box_data.box_number,
                item_description=box_data.item_description,
                net_weight=box_data.net_weight,
                gross_weight=box_data.gross_weight,
                qr_data=box_data.qr_data
            )
            db.add(scanned_box)
        
        # Create transport info
        transport_info = TransferInfo(
            transfer_id=existing_request.id,
            vehicle_number=transfer_data.transport_info.vehicle_number,
            vehicle_number_other=transfer_data.transport_info.vehicle_number_other,
            driver_name=transfer_data.transport_info.driver_name,
            driver_name_other=transfer_data.transport_info.driver_name_other,
            driver_phone=transfer_data.transport_info.driver_phone,
            approval_authority=transfer_data.transport_info.approval_authority
        )
        db.add(transport_info)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Transfer submitted successfully",
            data={
                "request_no": existing_request.request_no,
                "transfer_no": existing_request.transfer_no,
                "status": existing_request.status,
                "scanned_boxes_count": len(transfer_data.scanned_boxes)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting transfer: {str(e)}"
        )


# ============================================
# SCANNER ENDPOINTS
# ============================================

@router.post("/scanner/resolve", response_model=ScannerResponse)
async def resolve_scanner_input(
    scanner_input: ScannerInput,
    db: Session = Depends(get_db)
):
    """Resolve scanned box/lot/batch information"""
    try:
        scan_value = scanner_input.scan_value.strip()
        
        # This is a placeholder - in real implementation, you would:
        # 1. Parse the QR code data
        # 2. Look up the transaction in your inward system
        # 3. Return the resolved box/lot/batch information
        
        # For now, return mock data based on scan pattern
        if scan_value.startswith("TX"):
            # Transaction number scan
            box_data = BoxScanData(
                scan_value=scan_value,
                resolved_box=f"BOX{scan_value[-2:]}",
                resolved_lot=f"LOT{scan_value[-4:-2]}",
                resolved_batch=f"BATCH{scan_value[-6:-4]}",
                sku_id="SKU001234",
                sku_name="Wheat Flour 1kg",
                material_type="RM",
                uom="KG",
                available_qty=Decimal("100.000"),
                expiry_date=date(2024, 2, 15),
                fefo_priority=1
            )
            
            return ScannerResponse(
                success=True,
                message="Scan resolved successfully",
                data=box_data.model_dump()
            )
        else:
            return ScannerResponse(
                success=False,
                message="Invalid scan format. Expected transaction number starting with 'TX'",
                data=None
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resolving scan: {str(e)}"
        )


# ============================================
# DC GENERATION ENDPOINTS
# ============================================

@router.get("/{company}/{transfer_no}/dc-data", response_model=DCDataResponse)
async def get_dc_data(
    company: str,
    transfer_no: str,
    db: Session = Depends(get_db)
):
    """Get delivery challan data for DC generation"""
    try:
        # Get transfer request with transfer number
        transfer_request = db.query(TransferRequest).filter(
            TransferRequest.transfer_no == transfer_no
        ).first()
        
        if not transfer_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transfer not found"
            )
        
        # Get warehouse addresses
        warehouse_codes = [transfer_request.from_warehouse, transfer_request.to_warehouse]
        warehouse_addresses = get_warehouse_addresses(db, warehouse_codes)
        
        # Get items
        items = db.query(TransferRequestItem).filter(
            TransferRequestItem.transfer_id == transfer_request.id
        ).order_by(TransferRequestItem.line_number).all()
        
        # Get scanned boxes
        scanned_boxes = db.query(TransferScannedBox).filter(
            TransferScannedBox.transfer_id == transfer_request.id
        ).order_by(TransferScannedBox.box_number_in_array).all()
        
        # Get transport info
        transport_info = db.query(TransferInfo).filter(
            TransferInfo.transfer_id == transfer_request.id
        ).first()
        
        if not transport_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transport information not found"
            )
        
        # Build response
        dc_data = DCDataResponse(
            transfer_no=transfer_request.transfer_no,
            request_no=transfer_request.request_no,
            request_date=transfer_request.request_date,
            from_warehouse=warehouse_addresses[transfer_request.from_warehouse],
            to_warehouse=warehouse_addresses[transfer_request.to_warehouse],
            items=[
                {
                    "line_number": item.line_number,
                    "material_type": item.material_type,
                    "item_category": item.item_category,
                    "sub_category": item.sub_category,
                    "item_description": item.item_description,
                    "sku_id": item.sku_id,
                    "quantity": item.quantity,
                    "uom": item.uom,
                    "pack_size": item.pack_size,
                    "package_size": item.package_size,
                    "net_weight": item.net_weight
                }
                for item in items
            ],
            scanned_boxes=[
                {
                    "box_id": box.box_id,
                    "transaction_no": box.transaction_no,
                    "sku_id": box.sku_id,
                    "box_number": box.box_number,
                    "item_description": box.item_description,
                    "net_weight": box.net_weight,
                    "gross_weight": box.gross_weight
                }
                for box in scanned_boxes
            ],
            transport_info={
                "vehicle_number": transport_info.vehicle_number,
                "vehicle_number_other": transport_info.vehicle_number_other,
                "driver_name": transport_info.driver_name,
                "driver_name_other": transport_info.driver_name_other,
                "driver_phone": transport_info.driver_phone,
                "approval_authority": transport_info.approval_authority
            }
        )
        
        return dc_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving DC data: {str(e)}"
        )


# ============================================
# UTILITY ENDPOINTS
# ============================================

@router.get("/status-options")
async def get_status_options():
    """Get available status options for transfer requests"""
    return {
        "success": True,
        "message": "Status options retrieved successfully",
        "data": [
            {"value": "Pending", "label": "Pending"},
            {"value": "Approved", "label": "Approved"},
            {"value": "Rejected", "label": "Rejected"},
            {"value": "In Transit", "label": "In Transit"},
            {"value": "Completed", "label": "Completed"}
        ]
    }


@router.get("/material-types")
async def get_material_types():
    """Get available material types"""
    return {
        "success": True,
        "message": "Material types retrieved successfully",
        "data": [
            {"value": "RM", "label": "Raw Material"},
            {"value": "PM", "label": "Packaging Material"},
            {"value": "FG", "label": "Finished Good"},
            {"value": "SFG", "label": "Semi-Finished Good"}
        ]
    }


# ============================================
# INTERUNIT COMPATIBILITY ENDPOINTS
# ============================================

@router.get("/interunit/requests/{request_id}", response_model=TransferRequestDetailResponse)
async def get_interunit_request(
    request_id: int,
    db: Session = Depends(get_db)
):
    """Get transfer request for interunit compatibility (used in transfer form)"""
    return await get_transfer_request_detail(request_id, db)


@router.post("/interunit/{company}", response_model=StandardResponse)
async def submit_interunit_transfer(
    company: str,
    transfer_data: TransferCompleteCreate,
    db: Session = Depends(get_db)
):
    """Submit transfer for interunit compatibility"""
    return await submit_transfer(transfer_data, db)

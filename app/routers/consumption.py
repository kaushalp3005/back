# File: consumption_router.py
# Path: backend/app/routers/consumption.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.consumption import (
    BOM, BOMComponent, Config, DailyLedger, FIFOLayer, InventoryMove, 
    JobCard, QCHold, SKU, SalesOrder, User, Warehouse
)
from app.schemas.consumption import (
    BOMComponentResponse, BOMCreate, BOMResponse, ConfigGet, ConsumptionPost, DispatchPost,
    FIFOLayerResponse, InventoryMoveResponse, JobCardCreate, JobCardResponse,
    LedgerFilter, LedgerRow, PaginatedResponse, QCHoldCreate, QCHoldResponse,
    ReceiptPost, StandardResponse, TransferPost
)

router = APIRouter(prefix="/consumption", tags=["Consumption Backend"])


# ============================================
# SKU ENDPOINTS
# ============================================

@router.get("/sku", response_model=PaginatedResponse)
async def get_skus(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    material_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get SKUs with pagination and filtering"""
    query = db.query(SKU).filter(SKU.is_active == True)
    
    if material_type:
        query = query.filter(SKU.material_type == material_type.upper())
    
    if search:
        query = query.filter(
            or_(
                SKU.name.ilike(f"%{search}%"),
                SKU.id.ilike(f"%{search}%"),
                SKU.description.ilike(f"%{search}%")
            )
        )
    
    total = query.count()
    skus = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return PaginatedResponse(
        success=True,
        message="SKUs retrieved successfully",
        data=[{
            "id": sku.id,
            "name": sku.name,
            "material_type": sku.material_type,
            "uom": sku.uom,
            "perishable": sku.perishable,
            "description": sku.description,
            "category": sku.category,
            "sub_category": sku.sub_category,
            "hsn_code": sku.hsn_code,
            "gst_rate": float(sku.gst_rate),
            "is_active": sku.is_active,
            "created_at": sku.created_at.isoformat(),
            "updated_at": sku.updated_at.isoformat()
        } for sku in skus],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


# ============================================
# WAREHOUSE ENDPOINTS
# ============================================

@router.get("/warehouse", response_model=PaginatedResponse)
async def get_warehouses(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    sitecode: Optional[str] = Query(None),
    warehouse_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get warehouses with pagination and filtering"""
    query = db.query(Warehouse).filter(Warehouse.is_active == True)
    
    if sitecode:
        query = query.filter(Warehouse.sitecode == sitecode)
    
    if warehouse_type:
        query = query.filter(Warehouse.warehouse_type == warehouse_type)
    
    total = query.count()
    warehouses = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return PaginatedResponse(
        success=True,
        message="Warehouses retrieved successfully",
        data=[{
            "code": wh.code,
            "name": wh.name,
            "sitecode": wh.sitecode,
            "location": wh.location,
            "warehouse_type": wh.warehouse_type,
            "is_active": wh.is_active,
            "created_at": wh.created_at.isoformat(),
            "updated_at": wh.updated_at.isoformat()
        } for wh in warehouses],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


# ============================================
# BOM ENDPOINTS
# ============================================

@router.post("/bom", response_model=StandardResponse)
async def create_bom(bom_data: BOMCreate, db: Session = Depends(get_db)):
    """Create a new BOM with components"""
    try:
        # Check if BOM already exists
        existing_bom = db.query(BOM).filter(BOM.id == bom_data.id).first()
        if existing_bom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BOM with this ID already exists"
            )
        
        # Create BOM
        bom = BOM(
            id=bom_data.id,
            name=bom_data.name,
            description=bom_data.description,
            version=bom_data.version,
            output_sku_id=bom_data.output_sku_id,
            output_qty=bom_data.output_qty,
            output_uom=bom_data.output_uom,
            is_active=bom_data.is_active,
            created_by=bom_data.created_by
        )
        db.add(bom)
        
        # Create BOM components
        for component_data in bom_data.components:
            component = BOMComponent(
                bom_id=bom_data.id,
                sku_id=component_data.sku_id,
                material_type=component_data.material_type,
                qty_required=component_data.qty_required,
                uom=component_data.uom,
                sequence_order=component_data.sequence_order,
                process_loss_pct=component_data.process_loss_pct,
                extra_giveaway_pct=component_data.extra_giveaway_pct,
                handling_loss_pct=component_data.handling_loss_pct,
                shrinkage_pct=component_data.shrinkage_pct,
                is_active=component_data.is_active
            )
            # Calculate loss percentages
            component.calculate_loss_percentages()
            db.add(component)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="BOM created successfully",
            data={"bom_id": bom_data.id}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating BOM: {str(e)}"
        )


@router.get("/bom/{bom_id}", response_model=BOMResponse)
async def get_bom(bom_id: str, db: Session = Depends(get_db)):
    """Get BOM by ID with components"""
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )
    
    components = db.query(BOMComponent).filter(
        BOMComponent.bom_id == bom_id,
        BOMComponent.is_active == True
    ).order_by(BOMComponent.sequence_order).all()
    
    return BOMResponse(
        id=bom.id,
        name=bom.name,
        description=bom.description,
        version=bom.version,
        output_sku_id=bom.output_sku_id,
        output_qty=bom.output_qty,
        output_uom=bom.output_uom,
        is_active=bom.is_active,
        created_by=bom.created_by,
        created_at=bom.created_at,
        updated_at=bom.updated_at,
        components=[BOMComponentResponse(
            id=comp.id,
            bom_id=comp.bom_id,
            sku_id=comp.sku_id,
            material_type=comp.material_type,
            qty_required=comp.qty_required,
            uom=comp.uom,
            sequence_order=comp.sequence_order,
            process_loss_pct=comp.process_loss_pct,
            extra_giveaway_pct=comp.extra_giveaway_pct,
            handling_loss_pct=comp.handling_loss_pct,
            shrinkage_pct=comp.shrinkage_pct,
            total_loss_pct=comp.total_loss_pct,
            qty_with_loss=comp.qty_with_loss,
            is_active=comp.is_active,
            created_at=comp.created_at,
            updated_at=comp.updated_at
        ) for comp in components]
    )


# ============================================
# JOB CARD ENDPOINTS
# ============================================

@router.post("/job-card", response_model=StandardResponse)
async def create_job_card(job_card_data: JobCardCreate, db: Session = Depends(get_db)):
    """Create a new job card"""
    try:
        # Check if job card already exists
        existing_job_card = db.query(JobCard).filter(
            JobCard.job_card_no == job_card_data.job_card_no
        ).first()
        if existing_job_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job card with this number already exists"
            )
        
        # Verify SKU and BOM exist
        sku = db.query(SKU).filter(SKU.id == job_card_data.sku_id).first()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU not found"
            )
        
        bom = db.query(BOM).filter(BOM.id == job_card_data.bom_id).first()
        if not bom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BOM not found"
            )
        
        # Create job card
        job_card = JobCard(
            job_card_no=job_card_data.job_card_no,
            sku_id=job_card_data.sku_id,
            bom_id=job_card_data.bom_id,
            planned_qty=job_card_data.planned_qty,
            uom=job_card_data.uom,
            status=job_card_data.status,
            priority=job_card_data.priority,
            due_date=job_card_data.due_date,
            start_date=job_card_data.start_date,
            completion_date=job_card_data.completion_date,
            production_line=job_card_data.production_line,
            shift=job_card_data.shift,
            remarks=job_card_data.remarks,
            created_by=job_card_data.created_by
        )
        db.add(job_card)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Job card created successfully",
            data={"job_card_no": job_card_data.job_card_no}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating job card: {str(e)}"
        )


@router.get("/job-card/{job_card_no}", response_model=JobCardResponse)
async def get_job_card(job_card_no: str, db: Session = Depends(get_db)):
    """Get job card by number"""
    job_card = db.query(JobCard).filter(
        JobCard.job_card_no == job_card_no
    ).first()
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
    
    return JobCardResponse(
        job_card_no=job_card.job_card_no,
        sku_id=job_card.sku_id,
        bom_id=job_card.bom_id,
        planned_qty=job_card.planned_qty,
        actual_qty=job_card.actual_qty,
        uom=job_card.uom,
        status=job_card.status,
        priority=job_card.priority,
        due_date=job_card.due_date,
        start_date=job_card.start_date,
        completion_date=job_card.completion_date,
        production_line=job_card.production_line,
        shift=job_card.shift,
        remarks=job_card.remarks,
        created_by=job_card.created_by,
        created_at=job_card.created_at,
        updated_at=job_card.updated_at
    )


# ============================================
# CONSUMPTION ENDPOINTS
# ============================================

@router.post("/consumption", response_model=StandardResponse)
async def post_consumption(consumption_data: ConsumptionPost, db: Session = Depends(get_db)):
    """Post consumption transaction for job card"""
    try:
        # Verify job card exists and is active
        job_card = db.query(JobCard).filter(
            JobCard.job_card_no == consumption_data.job_card_no
        ).first()
        if not job_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job card not found"
            )
        
        if job_card.status not in ['PLANNED', 'IN_PROGRESS']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job card is not in a valid state for consumption"
            )
        
        # Verify warehouse exists
        warehouse = db.query(Warehouse).filter(
            Warehouse.code == consumption_data.warehouse
        ).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse not found"
            )
        
        # Process each consumption line
        inventory_moves = []
        for line in consumption_data.lines:
            # Verify SKU exists
            sku = db.query(SKU).filter(SKU.id == line.sku_id).first()
            if not sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {line.sku_id} not found"
                )
            
            # Create inventory move for consumption
            inventory_move = InventoryMove(
                warehouse=consumption_data.warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="CON",
                job_card_no=consumption_data.job_card_no,
                qty_out=line.qty_issued,
                uom=line.uom,
                unit_cost=0,  # Will be calculated from FIFO layers
                ref_doc=f"CONSUMPTION-{consumption_data.job_card_no}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks=consumption_data.remarks
            )
            db.add(inventory_move)
            inventory_moves.append(inventory_move)
        
        # Update job card status if it was PLANNED
        if job_card.status == "PLANNED":
            job_card.status = "IN_PROGRESS"
            job_card.start_date = datetime.now().date()
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Consumption posted successfully",
            data={
                "job_card_no": consumption_data.job_card_no,
                "lines_processed": len(consumption_data.lines),
                "inventory_moves": [str(move.id) for move in inventory_moves]
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error posting consumption: {str(e)}"
        )


# ============================================
# RECEIPT ENDPOINTS
# ============================================

@router.post("/receipt", response_model=StandardResponse)
async def post_receipt(receipt_data: ReceiptPost, db: Session = Depends(get_db)):
    """Post production receipt for job card"""
    try:
        # Verify job card exists
        job_card = db.query(JobCard).filter(
            JobCard.job_card_no == receipt_data.job_card_no
        ).first()
        if not job_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job card not found"
            )
        
        # Verify destination warehouse exists
        warehouse = db.query(Warehouse).filter(
            Warehouse.code == receipt_data.to_warehouse
        ).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination warehouse not found"
            )
        
        # Process each receipt line
        inventory_moves = []
        for line in receipt_data.lines:
            # Verify SKU exists
            sku = db.query(SKU).filter(SKU.id == line.sku_id).first()
            if not sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {line.sku_id} not found"
                )
            
            # Determine transaction code based on output type
            tx_code = "SFG" if receipt_data.output_type == "SFG" else "FG"
            
            # Create inventory move for receipt
            inventory_move = InventoryMove(
                warehouse=receipt_data.to_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code=tx_code,
                job_card_no=receipt_data.job_card_no,
                qty_in=line.qty_produced,
                uom=line.uom,
                unit_cost=0,  # Will be calculated based on BOM costs
                ref_doc=f"RECEIPT-{receipt_data.job_card_no}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks=f"Production receipt - Yield: {line.yield_pct}%, Scrap: {line.scrap_qty}"
            )
            db.add(inventory_move)
            inventory_moves.append(inventory_move)
        
        # Update job card actual quantity and status
        total_produced = sum(line.qty_produced for line in receipt_data.lines)
        job_card.actual_qty = total_produced
        job_card.status = "COMPLETED"
        job_card.completion_date = datetime.now().date()
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Production receipt posted successfully",
            data={
                "job_card_no": receipt_data.job_card_no,
                "lines_processed": len(receipt_data.lines),
                "total_produced": float(total_produced),
                "inventory_moves": [str(move.id) for move in inventory_moves]
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error posting receipt: {str(e)}"
        )


# ============================================
# TRANSFER ENDPOINTS
# ============================================

@router.post("/transfer", response_model=StandardResponse)
async def post_transfer(transfer_data: TransferPost, db: Session = Depends(get_db)):
    """Post inter-warehouse transfer"""
    try:
        # Verify source and destination warehouses exist
        source_warehouse = db.query(Warehouse).filter(
            Warehouse.code == transfer_data.source_warehouse
        ).first()
        if not source_warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source warehouse not found"
            )
        
        destination_warehouse = db.query(Warehouse).filter(
            Warehouse.code == transfer_data.destination_warehouse
        ).first()
        if not destination_warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination warehouse not found"
            )
        
        # Process each transfer line
        inventory_moves = []
        for line in transfer_data.lines:
            # Verify SKU exists
            sku = db.query(SKU).filter(SKU.id == line.sku_id).first()
            if not sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {line.sku_id} not found"
                )
            
            # Create inventory move for transfer out
            transfer_out_move = InventoryMove(
                warehouse=transfer_data.source_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="TROUT",
                qty_out=line.qty,
                uom=line.uom,
                unit_cost=0,  # Will be calculated from FIFO layers
                ref_doc=f"TRANSFER-{transfer_data.source_warehouse}-{transfer_data.destination_warehouse}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Inter-warehouse transfer out"
            )
            db.add(transfer_out_move)
            inventory_moves.append(transfer_out_move)
            
            # Create inventory move for transfer in
            transfer_in_move = InventoryMove(
                warehouse=transfer_data.destination_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="TRIN",
                qty_in=line.qty,
                uom=line.uom,
                unit_cost=0,  # Will be calculated from FIFO layers
                ref_doc=f"TRANSFER-{transfer_data.source_warehouse}-{transfer_data.destination_warehouse}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Inter-warehouse transfer in"
            )
            db.add(transfer_in_move)
            inventory_moves.append(transfer_in_move)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Transfer posted successfully",
            data={
                "source_warehouse": transfer_data.source_warehouse,
                "destination_warehouse": transfer_data.destination_warehouse,
                "lines_processed": len(transfer_data.lines),
                "inventory_moves": [str(move.id) for move in inventory_moves]
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error posting transfer: {str(e)}"
        )


# ============================================
# DISPATCH ENDPOINTS
# ============================================

@router.post("/dispatch", response_model=StandardResponse)
async def post_dispatch(dispatch_data: DispatchPost, db: Session = Depends(get_db)):
    """Post outward dispatch with FEFO allocation"""
    try:
        # Verify warehouse exists
        warehouse = db.query(Warehouse).filter(
            Warehouse.code == dispatch_data.warehouse
        ).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse not found"
            )
        
        # Verify sales order exists
        sales_order = db.query(SalesOrder).filter(
            SalesOrder.so_no == dispatch_data.so_no
        ).first()
        if not sales_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sales order not found"
            )
        
        # Process each dispatch line
        inventory_moves = []
        for line in dispatch_data.lines:
            # Verify SKU exists
            sku = db.query(SKU).filter(SKU.id == line.sku_id).first()
            if not sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU {line.sku_id} not found"
                )
            
            # Create inventory move for dispatch
            inventory_move = InventoryMove(
                warehouse=dispatch_data.warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="OUT",
                so_no=dispatch_data.so_no,
                qty_out=line.qty,
                uom=line.uom,
                unit_cost=0,  # Will be calculated from FIFO layers
                ref_doc=f"DISPATCH-{dispatch_data.so_no}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Outward dispatch"
            )
            db.add(inventory_move)
            inventory_moves.append(inventory_move)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Dispatch posted successfully",
            data={
                "warehouse": dispatch_data.warehouse,
                "so_no": dispatch_data.so_no,
                "lines_processed": len(dispatch_data.lines),
                "inventory_moves": [str(move.id) for move in inventory_moves]
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error posting dispatch: {str(e)}"
        )


# ============================================
# LEDGER ENDPOINTS
# ============================================

@router.post("/ledger")
async def get_ledger(filter_data: LedgerFilter, db: Session = Depends(get_db)):
    """Get daily ledger data with filtering"""
    try:
        # Use the database function to calculate ledger
        query = text("""
            SELECT * FROM calculate_daily_ledger(
                :p_date, :p_company, :p_warehouse_filter, :p_sku_id_filter
            )
        """)

        result = db.execute(query, {
            "p_date": filter_data.date,
            "p_company": "CFPL",
            "p_warehouse_filter": filter_data.warehouse,
            "p_sku_id_filter": filter_data.sku_id
        })

        ledger_rows = []
        for row in result:
            ledger_row = LedgerRow(
                date=row.date,
                company=row.company,
                warehouse=row.warehouse,
                sku_id=row.sku_id,
                material_type=row.material_type,
                opening_stock=row.opening_stock,
                stock_in_hand=row.opening_stock,  # Stock in hand is the same as opening stock
                transfer_in=row.transfer_in,
                transfer_out=row.transfer_out,
                stock_in=row.stock_in,
                stock_out=row.stock_out,
                closing_stock=row.closing_stock,
                valuation_rate=row.valuation_rate,
                inventory_value_closing=row.inventory_value_closing,
                uom=row.uom
            )
            ledger_rows.append(ledger_row)

        # Return data wrapped in the expected response format
        return {
            "success": True,
            "message": "Ledger data retrieved successfully",
            "data": ledger_rows,
            "total": len(ledger_rows)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving ledger: {str(e)}"
        )


# ============================================
# CONFIGURATION ENDPOINTS
# ============================================

@router.get("/config", response_model=ConfigGet)
async def get_config(db: Session = Depends(get_db)):
    """Get system configuration"""
    try:
        config_items = db.query(Config).filter(Config.is_active == True).all()
        
        config_dict = {}
        for item in config_items:
            config_dict[item.config_key] = item.config_value
        
        return ConfigGet(
            valuation_method=config_dict.get("valuation_method", "FIFO"),
            variance_threshold_pct=Decimal(config_dict.get("variance_threshold_pct", "5.0"))
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving configuration: {str(e)}"
        )


# ============================================
# FIFO LAYERS ENDPOINTS
# ============================================

@router.get("/fifo-layers", response_model=List[FIFOLayerResponse])
async def get_fifo_layers(
    warehouse: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get FIFO layers for cost allocation"""
    try:
        query = db.query(FIFOLayer).filter(FIFOLayer.remaining_qty > 0)
        
        if warehouse:
            query = query.filter(FIFOLayer.warehouse == warehouse)
        
        if item_id:
            query = query.filter(FIFOLayer.item_id == item_id)
        
        fifo_layers = query.order_by(
            FIFOLayer.created_at.asc(),
            FIFOLayer.expiry_date.asc()
        ).all()
        
        return [FIFOLayerResponse(
            id=layer.id,
            company=layer.company,
            warehouse=layer.warehouse,
            item_id=layer.item_id,
            lot=layer.lot,
            batch=layer.batch,
            open_qty=layer.open_qty,
            open_value=layer.open_value,
            remaining_qty=layer.remaining_qty,
            unit_cost=layer.unit_cost,
            expiry_date=layer.expiry_date,
            source_tx_id=layer.source_tx_id,
            created_at=layer.created_at,
            updated_at=layer.updated_at
        ) for layer in fifo_layers]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving FIFO layers: {str(e)}"
        )


# ============================================
# QC HOLDS ENDPOINTS
# ============================================

@router.post("/qc-hold", response_model=StandardResponse)
async def create_qc_hold(qc_hold_data: QCHoldCreate, db: Session = Depends(get_db)):
    """Create QC hold for inventory"""
    try:
        # Verify inventory move exists
        inventory_move = db.query(InventoryMove).filter(
            InventoryMove.id == qc_hold_data.inventory_move_id
        ).first()
        if not inventory_move:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inventory move not found"
            )
        
        # Create QC hold
        qc_hold = QCHold(
            inventory_move_id=qc_hold_data.inventory_move_id,
            warehouse=qc_hold_data.warehouse,
            item_id=qc_hold_data.item_id,
            lot=qc_hold_data.lot,
            batch=qc_hold_data.batch,
            qty=qc_hold_data.qty,
            uom=qc_hold_data.uom,
            hold_reason=qc_hold_data.hold_reason,
            qc_remarks=qc_hold_data.qc_remarks,
            qc_by=qc_hold_data.qc_by,
            status="HOLD"
        )
        db.add(qc_hold)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="QC hold created successfully",
            data={"qc_hold_id": str(qc_hold.id)}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating QC hold: {str(e)}"
        )


@router.get("/qc-holds", response_model=List[QCHoldResponse])
async def get_qc_holds(
    warehouse: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get QC holds with filtering"""
    try:
        query = db.query(QCHold)
        
        if warehouse:
            query = query.filter(QCHold.warehouse == warehouse)
        
        if status:
            query = query.filter(QCHold.status == status.upper())
        
        qc_holds = query.order_by(QCHold.hold_date.desc()).all()
        
        return [QCHoldResponse(
            id=hold.id,
            inventory_move_id=hold.inventory_move_id,
            warehouse=hold.warehouse,
            item_id=hold.item_id,
            lot=hold.lot,
            batch=hold.batch,
            qty=hold.qty,
            uom=hold.uom,
            hold_reason=hold.hold_reason,
            hold_date=hold.hold_date,
            release_date=hold.release_date,
            status=hold.status,
            qc_remarks=hold.qc_remarks,
            qc_by=hold.qc_by,
            created_at=hold.created_at,
            updated_at=hold.updated_at
        ) for hold in qc_holds]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving QC holds: {str(e)}"
        )


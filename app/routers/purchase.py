"""
Router for Purchase Order CRUD operations.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderOut,
    ItemCreate,
    ItemUpdate,
    ItemOut,
    BoxCreate,
    BoxUpdate,
    BoxOut,
)
from app.services import purchase as purchase_service

router = APIRouter(prefix="/v1/purchase", tags=["Purchase Orders"])


# ==================== PURCHASE ORDER (Header) ENDPOINTS ====================

@router.post("/orders", response_model=PurchaseOrderOut, status_code=201)
async def create_purchase_order(
    po_data: PurchaseOrderCreate,
    db: Session = Depends(get_db)
):
    """Create a new purchase order."""
    try:
        result = purchase_service.create_purchase_order(db, po_data)
        return result
    except Exception as e:
        import logging
        logging.error(f"Failed to create purchase order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create purchase order: {str(e)}")


@router.get("/orders", response_model=List[PurchaseOrderOut])
async def get_purchase_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    company_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all purchase orders with optional filtering."""
    return purchase_service.get_purchase_orders(db, skip, limit, company_name)


@router.get("/orders/{po_id}", response_model=PurchaseOrderOut)
async def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db)
):
    """Get a purchase order by ID."""
    po = purchase_service.get_purchase_order(db, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.get("/orders/by-po-number/{po_number:path}", response_model=PurchaseOrderOut)
async def get_purchase_order_by_po_number(
    po_number: str,
    db: Session = Depends(get_db)
):
    """Get a purchase order by PO number with all details.
    
    Note: The po_number parameter supports URL encoding and special characters like '/'.
    Example: CF/PO/2025-26/01477 should be URL encoded as CF%2FPO%2F2025-26%2F01477
    """
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Getting purchase order for PO number: {po_number}")
    
    po = purchase_service.get_purchase_order_by_po_number(db, po_number)
    if not po:
        raise HTTPException(status_code=404, detail=f"Purchase order not found for PO number: {po_number}")
    
    return po


@router.get("/complete/{purchase_number}")
async def get_complete_purchase_data(
    purchase_number: str,
    box_id: Optional[int] = Query(None, description="Optional box ID to filter results to specific box only"),
    db: Session = Depends(get_db)
):
    """
    Get complete purchase data including order, approval, items, and boxes in one API call.
    
    This endpoint returns everything you need:
    - Purchase order details (buyer, supplier, financial summary)
    - Purchase approval information (transporter, customer info)
    - All items with descriptions, weights, financial data
    - All boxes for each item (or just one specific box if box_id provided)
    - Summary statistics
    
    Parameters:
    - purchase_number: Like "PR-20251105155654" (not PO number)
    - box_id: Optional - if provided, filters approval data to show only that specific box and its parent item
    
    Usage Examples:
    - GET /api/v1/purchase/complete/PR-20251105155654  (all data)
    - GET /api/v1/purchase/complete/PR-20251105155654?box_id=123  (specific box only)
    
    Response includes:
    - purchase_order: Complete PO details (always same regardless of box_id)
    - approval: Complete approval data (null if no approval exists, filtered if box_id provided)
    - has_approval: Boolean flag
    - items_count: Total number of items (1 if filtered by box_id)
    - boxes_count: Total number of boxes (1 if filtered by box_id)
    - summary: Quick access to key information including filtering status
    """
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Getting complete purchase data for purchase number: {purchase_number}")
    
    complete_data = purchase_service.get_complete_purchase_data(db, purchase_number, box_id)
    if not complete_data:
        raise HTTPException(status_code=404, detail=f"Purchase order not found for purchase number: {purchase_number}")
    
    filter_info = f", Filtered by box_id={box_id}" if box_id else ""
    logger.info(f"Returning complete data: Purchase={purchase_number}, "
               f"PO={complete_data['summary']['po_number']}, "
               f"Approval={complete_data['has_approval']}, "
               f"Items={complete_data['items_count']}, "
               f"Boxes={complete_data['boxes_count']}{filter_info}")
    
    return complete_data


@router.put("/orders/{po_id}", response_model=PurchaseOrderOut)
async def update_purchase_order(
    po_id: int,
    po_update: PurchaseOrderUpdate,
    db: Session = Depends(get_db)
):
    """Update a purchase order."""
    po = purchase_service.update_purchase_order(db, po_id, po_update)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.delete("/orders/{po_id}", status_code=204)
async def delete_purchase_order(
    po_id: int,
    db: Session = Depends(get_db)
):
    """Delete a purchase order."""
    success = purchase_service.delete_purchase_order(db, po_id)
    if not success:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return None


# ==================== PURCHASE ORDER ITEMS ENDPOINTS ====================

@router.post("/items", response_model=ItemOut, status_code=201)
async def create_po_item(
    item_data: ItemCreate,
    db: Session = Depends(get_db)
):
    """Create a new purchase order item."""
    try:
        result = purchase_service.create_po_item(db, item_data)
        return result
    except ValueError as e:
        # Handle foreign key constraint errors
        import logging
        logging.error(f"Validation error creating PO item: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Failed to create PO item: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create purchase order item: {str(e)}")


@router.get("/items", response_model=List[ItemOut])
async def get_po_items(
    purchase_order_id: int = Query(..., description="Purchase order ID to filter items"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all items for a purchase order."""
    return purchase_service.get_po_items_by_po(db, purchase_order_id, skip, limit)


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_po_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    """Get a purchase order item by ID."""
    item = purchase_service.get_po_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Purchase order item not found")
    return item


@router.put("/items/{item_id}", response_model=ItemOut)
async def update_po_item(
    item_id: int,
    item_update: ItemUpdate,
    db: Session = Depends(get_db)
):
    """Update a purchase order item."""
    item = purchase_service.update_po_item(db, item_id, item_update)
    if not item:
        raise HTTPException(status_code=404, detail="Purchase order item not found")
    return item


@router.delete("/items/{item_id}", status_code=204)
async def delete_po_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    """Delete a purchase order item."""
    success = purchase_service.delete_po_item(db, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Purchase order item not found")
    return None


# ==================== BOX MANAGEMENT ENDPOINTS ====================

@router.post("/boxes", response_model=BoxOut, status_code=201)
async def create_box(
    box_data: BoxCreate,
    db: Session = Depends(get_db)
):
    """Create a new box."""
    return purchase_service.create_box(db, box_data)


@router.get("/boxes", response_model=List[BoxOut])
async def get_boxes(
    po_item_id: int = Query(..., description="PO item ID to filter boxes"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all boxes for a purchase order item."""
    return purchase_service.get_boxes_by_item(db, po_item_id, skip, limit)


@router.get("/boxes/{box_id}", response_model=BoxOut)
async def get_box(
    box_id: int,
    db: Session = Depends(get_db)
):
    """Get a box by ID."""
    box = purchase_service.get_box(db, box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")
    return box


@router.put("/boxes/{box_id}", response_model=BoxOut)
async def update_box(
    box_id: int,
    box_update: BoxUpdate,
    db: Session = Depends(get_db)
):
    """Update a box."""
    box = purchase_service.update_box(db, box_id, box_update)
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")
    return box


@router.delete("/boxes/{box_id}", status_code=204)
async def delete_box(
    box_id: int,
    db: Session = Depends(get_db)
):
    """Delete a box."""
    success = purchase_service.delete_box(db, box_id)
    if not success:
        raise HTTPException(status_code=404, detail="Box not found")
    return None


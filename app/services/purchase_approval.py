"""
Service layer for Purchase Approval CRUD operations.
Updated to prevent blank entries in items and boxes tables with strict validation.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from decimal import Decimal

from app.models.purchase_approval import PurchaseApproval, PurchaseApprovalItem, PurchaseApprovalBox
from app.schemas.purchase_approval import (
    PurchaseApprovalCreate,
    PurchaseApprovalUpdate,
    PurchaseApprovalOut,
    PurchaseApprovalItemOut,
    PurchaseApprovalBoxOut,
    PurchaseApprovalWithItemsOut,
    TransporterInformation,
    CustomerInformation,
    ItemSchema,
    BoxSchema,
)


def _db_approval_to_schema(db_approval: PurchaseApproval) -> PurchaseApprovalOut:
    """Convert database PurchaseApproval to PurchaseApprovalOut schema."""
    return PurchaseApprovalOut(
        id=db_approval.id,
        purchase_order_id=db_approval.purchase_order_id,
        transporter_information=TransporterInformation(
            vehicle_number=db_approval.vehicle_number,
            transporter_name=db_approval.transporter_name,
            lr_number=db_approval.lr_number,
            destination_location=db_approval.destination_location,
        ),
        customer_information=CustomerInformation(
            customer_name=db_approval.customer_name,
            authority=db_approval.authority,
            challan_number=db_approval.challan_number,
            invoice_number=db_approval.invoice_number,
            grn_number=db_approval.grn_number,
            grn_quantity=db_approval.grn_quantity,
            delivery_note_number=db_approval.delivery_note_number,
            service_po_number=db_approval.service_po_number,
        ),
        created_at=db_approval.created_at,
        updated_at=db_approval.updated_at,
    )


# Helper function to safely convert to Decimal
def safe_decimal(value, default=None):
    """Safely convert value to Decimal with 3 decimal places."""
    if value is None or value == '':
        return default
    try:
        return Decimal(str(value)).quantize(Decimal('0.001'))
    except:
        return default


# Helper function to check if an item is valid (not blank)
def is_valid_item(item_data):
    """
    Check if an item has enough meaningful data to warrant database storage.
    Requires at least: description OR (material_type AND quantity)
    """
    import logging
    logger = logging.getLogger(__name__)

    # Check each field carefully
    has_material_type = bool(item_data.material_type and str(item_data.material_type).strip())
    has_description = bool(item_data.item_description and str(item_data.item_description).strip())
    has_quantity = item_data.quantity_units is not None and float(item_data.quantity_units) > 0
    has_net_weight = item_data.net_weight is not None and float(item_data.net_weight) > 0
    has_category = bool(item_data.item_category and str(item_data.item_category).strip())

    # Minimum validation: needs description OR (material AND quantity)
    is_valid = has_description or (has_material_type and has_quantity)

    logger.info(f"Item validation - material={has_material_type}, desc={has_description}, qty={has_quantity}, weight={has_net_weight}, cat={has_category} => VALID={is_valid}")
    logger.debug(f"Item data: material_type='{item_data.material_type}', description='{item_data.item_description}', qty={item_data.quantity_units}")

    return is_valid


# Helper function to check if a box is valid (not blank)
def is_valid_box(box_data):
    """
    Check if a box has enough meaningful data to warrant database storage.
    Requires at least: box_number AND (article_name OR weight)
    """
    has_box_number = bool(box_data.box_number and str(box_data.box_number).strip())
    has_article = bool(box_data.article_name and str(box_data.article_name).strip())
    has_net_weight = box_data.net_weight is not None and float(box_data.net_weight) > 0
    has_gross_weight = box_data.gross_weight is not None and float(box_data.gross_weight) > 0
    has_weight = has_net_weight or has_gross_weight
    
    # Minimum validation: needs box_number AND (article OR weight)
    is_valid = has_box_number and (has_article or has_weight)
    
    print(f"DEBUG: Box validation - number={has_box_number}, article={has_article}, weight={has_weight} => valid={is_valid}")
    
    return is_valid


def create_purchase_approval(db: Session, approval_data: PurchaseApprovalCreate) -> PurchaseApprovalWithItemsOut:
    """Create a new purchase approval with items and boxes."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Creating purchase approval for PO: {approval_data.purchase_order_id}")

        # Create the approval header
        db_approval = PurchaseApproval(
            purchase_order_id=approval_data.purchase_order_id,
            vehicle_number=approval_data.transporter_information.vehicle_number,
            transporter_name=approval_data.transporter_information.transporter_name,
            lr_number=approval_data.transporter_information.lr_number,
            destination_location=approval_data.transporter_information.destination_location,
            customer_name=approval_data.customer_information.customer_name,
            authority=approval_data.customer_information.authority,
            challan_number=approval_data.customer_information.challan_number,
            invoice_number=approval_data.customer_information.invoice_number,
            grn_number=approval_data.customer_information.grn_number,
            grn_quantity=approval_data.customer_information.grn_quantity,
            delivery_note_number=approval_data.customer_information.delivery_note_number,
            service_po_number=approval_data.customer_information.service_po_number,
        )

        db.add(db_approval)
        db.flush()  # Get the ID

        logger.info(f"Created approval header with ID {db_approval.id}")
        logger.info(f"Number of items to process: {len(approval_data.items)}")

        # Create items with their boxes
        items_schemas = []
        valid_items_count = 0

        for idx, item_data in enumerate(approval_data.items):
            logger.info(f"===== Processing item {idx + 1}/{len(approval_data.items)} =====")
            logger.info(f"Item data: material={item_data.material_type}, desc={item_data.item_description}, qty={item_data.quantity_units}, uom={item_data.uom}")

            # Skip blank/empty items
            if not is_valid_item(item_data):
                logger.warning(f"❌ Skipping invalid/blank item {idx + 1}")
                continue

            logger.info(f"✓ Creating valid item {idx + 1}")
            valid_items_count += 1

            db_item = PurchaseApprovalItem(
                approval_id=db_approval.id,
                material_type=item_data.material_type or '',
                item_category=item_data.item_category or '',
                sub_category=item_data.sub_category or '',
                item_description=item_data.item_description or '',
                quantity_units=safe_decimal(item_data.quantity_units),
                pack_size=safe_decimal(item_data.pack_size, Decimal('0')),
                uom=item_data.uom or '',
                net_weight=safe_decimal(item_data.net_weight),
                gross_weight=safe_decimal(item_data.gross_weight),
                lot_number=item_data.lot_number or '',
                mfg_date=item_data.mfg_date,
                exp_date=item_data.exp_date,
                # Article/Item Financial Information (optional)
                hsn_code=item_data.hsn_code,
                price_per_kg=safe_decimal(item_data.price_per_kg),
                taxable_value=safe_decimal(item_data.taxable_value),
                gst_percentage=safe_decimal(item_data.gst_percentage),
            )
            db.add(db_item)
            db.flush()

            logger.info(f"Created item with ID {db_item.id}, processing {len(item_data.boxes)} boxes")

            # Create boxes for this item
            boxes_schemas = []
            valid_boxes_count = 0

            for box_idx, box_data in enumerate(item_data.boxes):
                logger.debug(f"----- Processing box {box_idx + 1} for item {db_item.id} -----")
                logger.debug(f"Box data: number={box_data.box_number}, article={box_data.article_name}, net_weight={box_data.net_weight}")

                # Skip blank/empty boxes
                if not is_valid_box(box_data):
                    logger.debug(f"❌ Skipping invalid/blank box {box_idx + 1}")
                    continue

                logger.debug(f"✓ Creating valid box {box_idx + 1}")
                valid_boxes_count += 1

                db_box = PurchaseApprovalBox(
                    item_id=db_item.id,
                    box_number=box_data.box_number or '',
                    article_name=box_data.article_name or '',
                    lot_number=box_data.lot_number or '',
                    net_weight=safe_decimal(box_data.net_weight),
                    gross_weight=safe_decimal(box_data.gross_weight),
                )
                db.add(db_box)
                db.flush()  # Get the box ID
                boxes_schemas.append(BoxSchema(
                    box_id=db_box.id,  # Include box_id for frontend
                    box_number=box_data.box_number,
                    article_name=box_data.article_name,
                    lot_number=box_data.lot_number,
                    net_weight=box_data.net_weight,
                    gross_weight=box_data.gross_weight,
                ))

            db.flush()  # Ensure boxes are created
            logger.info(f"Created {valid_boxes_count}/{len(item_data.boxes)} valid boxes for item {db_item.id}")

            items_schemas.append(ItemSchema(
                material_type=item_data.material_type,
                item_category=item_data.item_category,
                sub_category=item_data.sub_category,
                item_description=item_data.item_description,
                quantity_units=item_data.quantity_units,
                pack_size=item_data.pack_size,
                uom=item_data.uom,
                net_weight=item_data.net_weight,
                gross_weight=item_data.gross_weight,
                lot_number=item_data.lot_number,
                mfg_date=item_data.mfg_date,
                exp_date=item_data.exp_date,
                # Article/Item Financial Information (optional)
                hsn_code=item_data.hsn_code,
                price_per_kg=item_data.price_per_kg,
                taxable_value=item_data.taxable_value,
                gst_percentage=item_data.gst_percentage,
                boxes=boxes_schemas,
            ))

        db.commit()
        db.refresh(db_approval)

        logger.info(f"===== Successfully created approval {db_approval.id} with {valid_items_count}/{len(approval_data.items)} valid items =====")

        return PurchaseApprovalWithItemsOut(
            id=db_approval.id,
            purchase_order_id=db_approval.purchase_order_id,
            transporter_information=TransporterInformation(
                vehicle_number=db_approval.vehicle_number,
                transporter_name=db_approval.transporter_name,
                lr_number=db_approval.lr_number,
                destination_location=db_approval.destination_location,
            ),
            customer_information=CustomerInformation(
                customer_name=db_approval.customer_name,
                authority=db_approval.authority,
                challan_number=db_approval.challan_number,
                invoice_number=db_approval.invoice_number,
                grn_number=db_approval.grn_number,
                grn_quantity=db_approval.grn_quantity,
                delivery_note_number=db_approval.delivery_note_number,
                service_po_number=db_approval.service_po_number,
            ),
            items=items_schemas,
            created_at=db_approval.created_at,
            updated_at=db_approval.updated_at,
        )
    except Exception as e:
        logger.error(f"Failed to create approval: {str(e)}", exc_info=True)
        db.rollback()
        raise


def get_purchase_approval(db: Session, approval_id: int) -> Optional[PurchaseApprovalWithItemsOut]:
    """Get a purchase approval by ID with all items and boxes."""
    db_approval = db.query(PurchaseApproval).filter(PurchaseApproval.id == approval_id).first()
    if not db_approval:
        return None
    
    # Get items
    db_items = db.query(PurchaseApprovalItem).filter(
        PurchaseApprovalItem.approval_id == approval_id
    ).all()
    
    items_schemas = []
    for db_item in db_items:
        # Get boxes for each item
        db_boxes = db.query(PurchaseApprovalBox).filter(
            PurchaseApprovalBox.item_id == db_item.id
        ).all()
        
        boxes_schemas = [
            BoxSchema(
                box_id=box.id,  # Include box_id for frontend
                box_number=box.box_number,
                article_name=box.article_name,
                lot_number=box.lot_number,
                net_weight=box.net_weight,
                gross_weight=box.gross_weight,
            ) for box in db_boxes
        ]
        
        items_schemas.append(ItemSchema(
            material_type=db_item.material_type,
            item_category=db_item.item_category,
            sub_category=db_item.sub_category,
            item_description=db_item.item_description,
            quantity_units=db_item.quantity_units,
            pack_size=db_item.pack_size,
            uom=db_item.uom,
            net_weight=db_item.net_weight,
            gross_weight=db_item.gross_weight,
            lot_number=db_item.lot_number,
            mfg_date=db_item.mfg_date,
            exp_date=db_item.exp_date,
            # Article/Item Financial Information (optional)
            hsn_code=db_item.hsn_code,
            price_per_kg=db_item.price_per_kg,
            taxable_value=db_item.taxable_value,
            gst_percentage=db_item.gst_percentage,
            boxes=boxes_schemas,
        ))
    
    return PurchaseApprovalWithItemsOut(
        id=db_approval.id,
        purchase_order_id=db_approval.purchase_order_id,
        transporter_information=TransporterInformation(
            vehicle_number=db_approval.vehicle_number,
            transporter_name=db_approval.transporter_name,
            lr_number=db_approval.lr_number,
            destination_location=db_approval.destination_location,
        ),
        customer_information=CustomerInformation(
            customer_name=db_approval.customer_name,
            authority=db_approval.authority,
            challan_number=db_approval.challan_number,
            invoice_number=db_approval.invoice_number,
            grn_number=db_approval.grn_number,
            grn_quantity=db_approval.grn_quantity,
            delivery_note_number=db_approval.delivery_note_number,
            service_po_number=db_approval.service_po_number,
        ),
        items=items_schemas,
        created_at=db_approval.created_at,
        updated_at=db_approval.updated_at,
    )


def get_purchase_approval_by_purchase_number(db: Session, purchase_number: str) -> Optional[PurchaseApprovalWithItemsOut]:
    """Get a purchase approval by purchase number/order ID with all items and boxes."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Query by purchase_order_id field which contains the purchase number
    db_approval = db.query(PurchaseApproval).filter(PurchaseApproval.purchase_order_id == purchase_number).first()
    if not db_approval:
        logger.warning(f"No purchase approval found for purchase number: {purchase_number}")
        return None
    
    logger.info(f"Found purchase approval ID {db_approval.id} for purchase number {purchase_number}")
    
    # Get items for this approval
    db_items = db.query(PurchaseApprovalItem).filter(
        PurchaseApprovalItem.approval_id == db_approval.id
    ).all()
    
    items_schemas = []
    for db_item in db_items:
        # Get boxes for each item
        db_boxes = db.query(PurchaseApprovalBox).filter(
            PurchaseApprovalBox.item_id == db_item.id
        ).all()
        
        boxes_schemas = [
            BoxSchema(
                box_id=box.id,  # Include box_id for frontend
                box_number=box.box_number,
                article_name=box.article_name,
                lot_number=box.lot_number,
                net_weight=box.net_weight,
                gross_weight=box.gross_weight,
            ) for box in db_boxes
        ]
        
        items_schemas.append(ItemSchema(
            material_type=db_item.material_type,
            item_category=db_item.item_category,
            sub_category=db_item.sub_category,
            item_description=db_item.item_description,
            quantity_units=db_item.quantity_units,
            pack_size=db_item.pack_size,
            uom=db_item.uom,
            net_weight=db_item.net_weight,
            gross_weight=db_item.gross_weight,
            lot_number=db_item.lot_number,
            mfg_date=db_item.mfg_date,
            exp_date=db_item.exp_date,
            # Article/Item Financial Information
            hsn_code=db_item.hsn_code,
            price_per_kg=db_item.price_per_kg,
            taxable_value=db_item.taxable_value,
            gst_percentage=db_item.gst_percentage,
            boxes=boxes_schemas,
        ))
    
    logger.info(f"Returning approval data with {len(items_schemas)} items")
    
    return PurchaseApprovalWithItemsOut(
        id=db_approval.id,
        purchase_order_id=db_approval.purchase_order_id,
        transporter_information=TransporterInformation(
            vehicle_number=db_approval.vehicle_number,
            transporter_name=db_approval.transporter_name,
            lr_number=db_approval.lr_number,
            destination_location=db_approval.destination_location,
        ),
        customer_information=CustomerInformation(
            customer_name=db_approval.customer_name,
            authority=db_approval.authority,
            challan_number=db_approval.challan_number,
            invoice_number=db_approval.invoice_number,
            grn_number=db_approval.grn_number,
            grn_quantity=db_approval.grn_quantity,
            delivery_note_number=db_approval.delivery_note_number,
            service_po_number=db_approval.service_po_number,
        ),
        items=items_schemas,
        created_at=db_approval.created_at,
        updated_at=db_approval.updated_at,
    )


def get_purchase_approvals(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    purchase_order_id: Optional[str] = None
) -> List[PurchaseApprovalOut]:
    """Get all purchase approvals with optional filtering."""
    query = db.query(PurchaseApproval)
    
    if purchase_order_id:
        query = query.filter(PurchaseApproval.purchase_order_id == purchase_order_id)
    
    db_approvals = query.order_by(desc(PurchaseApproval.created_at)).offset(skip).limit(limit).all()
    return [_db_approval_to_schema(db_approval) for db_approval in db_approvals]


def update_purchase_approval(
    db: Session,
    approval_id: int,
    approval_update: PurchaseApprovalUpdate
) -> Optional[PurchaseApprovalWithItemsOut]:
    """Update a purchase approval."""
    try:
        db_approval = db.query(PurchaseApproval).filter(PurchaseApproval.id == approval_id).first()
        if not db_approval:
            print(f"DEBUG: No approval found with ID {approval_id}")
            return None
        
        print(f"\nDEBUG: ===== UPDATE APPROVAL {approval_id} =====")
        print(f"DEBUG: Found approval, PO: {db_approval.purchase_order_id}")
        print(f"DEBUG: Update data received: {approval_update.model_dump(exclude_none=True)}")
        
        # Update purchase_order_id if provided
        if approval_update.purchase_order_id:
            db_approval.purchase_order_id = approval_update.purchase_order_id
        
        # Update transporter information
        if approval_update.transporter_information:
            trans = approval_update.transporter_information
            if trans.vehicle_number is not None:
                db_approval.vehicle_number = trans.vehicle_number
            if trans.transporter_name is not None:
                db_approval.transporter_name = trans.transporter_name
            if trans.lr_number is not None:
                db_approval.lr_number = trans.lr_number
            if trans.destination_location is not None:
                db_approval.destination_location = trans.destination_location
        
        # Update customer information
        if approval_update.customer_information:
            cust = approval_update.customer_information
            if cust.customer_name is not None:
                db_approval.customer_name = cust.customer_name
            if cust.authority is not None:
                db_approval.authority = cust.authority
            if cust.challan_number is not None:
                db_approval.challan_number = cust.challan_number
            if cust.invoice_number is not None:
                db_approval.invoice_number = cust.invoice_number
            if cust.grn_number is not None:
                db_approval.grn_number = cust.grn_number
            if cust.grn_quantity is not None:
                db_approval.grn_quantity = cust.grn_quantity
            if cust.delivery_note_number is not None:
                db_approval.delivery_note_number = cust.delivery_note_number
            if cust.service_po_number is not None:
                db_approval.service_po_number = cust.service_po_number
        
        # Update items if provided
        if approval_update.items is not None:
            print(f"\nDEBUG: Updating items - received {len(approval_update.items)} items")

            # Check if any items are valid before deleting existing items
            valid_items_to_add = [item for item in approval_update.items if is_valid_item(item)]

            # Only proceed with item update if there are valid items OR the array is explicitly empty
            if len(valid_items_to_add) > 0 or len(approval_update.items) == 0:
                # Delete existing items and their boxes (cascade)
                deleted_count = db.query(PurchaseApprovalItem).filter(
                    PurchaseApprovalItem.approval_id == approval_id
                ).delete()
                print(f"DEBUG: Deleted {deleted_count} existing items (with their boxes)")

                # Add new valid items with their boxes
                valid_items_count = 0
                total_valid_boxes = 0

                for idx, item_data in enumerate(approval_update.items):
                    print(f"\nDEBUG: ===== Processing item {idx + 1} =====")
                    print(f"DEBUG: Item data: material={item_data.material_type}, desc={item_data.item_description}, qty={item_data.quantity_units}, uom={item_data.uom}")

                    # Skip blank/empty items
                    if not is_valid_item(item_data):
                        print(f"DEBUG: ❌ Skipping invalid/blank item {idx + 1} during update")
                        continue

                    print(f"DEBUG: ✓ Creating valid item {idx + 1}")
                    valid_items_count += 1

                    db_item = PurchaseApprovalItem(
                        approval_id=approval_id,
                        material_type=item_data.material_type or '',
                        item_category=item_data.item_category or '',
                        sub_category=item_data.sub_category or '',
                        item_description=item_data.item_description or '',
                        quantity_units=safe_decimal(item_data.quantity_units),
                        pack_size=safe_decimal(item_data.pack_size, Decimal('0')),
                        uom=item_data.uom or '',
                        net_weight=safe_decimal(item_data.net_weight),
                        gross_weight=safe_decimal(item_data.gross_weight),
                        lot_number=item_data.lot_number or '',
                        mfg_date=item_data.mfg_date,
                        exp_date=item_data.exp_date,
                        # Article/Item Financial Information (optional)
                        hsn_code=item_data.hsn_code,
                        price_per_kg=safe_decimal(item_data.price_per_kg),
                        taxable_value=safe_decimal(item_data.taxable_value),
                        gst_percentage=safe_decimal(item_data.gst_percentage),
                    )
                    db.add(db_item)
                    db.flush()
                    print(f"DEBUG: Added item with ID {db_item.id}, has {len(item_data.boxes)} boxes to process")

                    # Create boxes for this item
                    valid_boxes_count = 0
                    for box_idx, box_data in enumerate(item_data.boxes):
                        print(f"\nDEBUG: ----- Processing box {box_idx + 1} for item {db_item.id} -----")
                        print(f"DEBUG: Box data: number={box_data.box_number}, article={box_data.article_name}, net_weight={box_data.net_weight}")

                        # Skip blank/empty boxes
                        if not is_valid_box(box_data):
                            print(f"DEBUG: ❌ Skipping invalid/blank box {box_idx + 1} during update")
                            continue

                        print(f"DEBUG: ✓ Creating valid box {box_idx + 1}")
                        valid_boxes_count += 1

                        db_box = PurchaseApprovalBox(
                            item_id=db_item.id,
                            box_number=box_data.box_number or '',
                            article_name=box_data.article_name or '',
                            lot_number=box_data.lot_number or '',
                            net_weight=safe_decimal(box_data.net_weight),
                            gross_weight=safe_decimal(box_data.gross_weight),
                        )
                        db.add(db_box)

                    print(f"DEBUG: ===== Added {valid_boxes_count}/{len(item_data.boxes)} valid boxes for item {db_item.id} =====")
                    total_valid_boxes += valid_boxes_count

                print(f"\nDEBUG: ===== Update summary: {valid_items_count}/{len(approval_update.items)} valid items, {total_valid_boxes} total valid boxes =====")
            else:
                print(f"DEBUG: ⚠️ No valid items provided - skipping item update to preserve existing items")
        
        db.commit()
        db.refresh(db_approval)
        print(f"DEBUG: Successfully updated approval {approval_id}\n")
        
        return get_purchase_approval(db, approval_id)
    
    except Exception as e:
        print(f"ERROR: Failed to update approval {approval_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise e


def get_purchase_approval_box(db: Session, box_id: int) -> Optional[dict]:
    """Get a specific purchase approval box by ID with related item and approval info."""
    db_box = db.query(PurchaseApprovalBox).filter(PurchaseApprovalBox.id == box_id).first()
    if not db_box:
        return None

    # Get related item and approval info
    db_item = db.query(PurchaseApprovalItem).filter(PurchaseApprovalItem.id == db_box.item_id).first()
    db_approval = db.query(PurchaseApproval).filter(PurchaseApproval.id == db_item.approval_id).first()

    # Return structure matching frontend BoxDetailResponse interface
    return {
        "box_id": db_box.id,
        "box_number": db_box.box_number,
        "article_name": db_box.article_name,
        "lot_number": db_box.lot_number,
        "net_weight": db_box.net_weight,
        "gross_weight": db_box.gross_weight,
        "created_at": db_box.created_at,
        # Item details (renamed from item_info to item for frontend)
        "item": {
            "item_description": db_item.item_description,
            "material_type": db_item.material_type,
            "item_category": db_item.item_category,
            "sub_category": db_item.sub_category,
        },
        # Full approval details (renamed from approval_info to approval for frontend)
        "approval": {
            "id": db_approval.id,
            "purchase_order_id": db_approval.purchase_order_id,
            "created_at": db_approval.created_at,
            "transporter_information": {
                "vehicle_number": db_approval.vehicle_number,
                "transporter_name": db_approval.transporter_name,
                "lr_number": db_approval.lr_number,
                "destination_location": db_approval.destination_location,
            },
            "customer_information": {
                "customer_name": db_approval.customer_name,
                "authority": db_approval.authority,
                "challan_number": db_approval.challan_number,
                "invoice_number": db_approval.invoice_number,
                "grn_number": db_approval.grn_number,
                "grn_quantity": db_approval.grn_quantity,
            },
        },
    }


def delete_purchase_approval(db: Session, approval_id: int) -> bool:
    """Delete a purchase approval (cascade deletes items and boxes)."""
    db_approval = db.query(PurchaseApproval).filter(PurchaseApproval.id == approval_id).first()
    if not db_approval:
        return False
    
    db.delete(db_approval)
    db.commit()
    return True


def delete_purchase_approval_by_purchase_number(db: Session, purchase_number: str) -> bool:
    """Delete a purchase approval by purchase number (cascade deletes items and boxes)."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Find approval by purchase_order_id field
    db_approval = db.query(PurchaseApproval).filter(
        PurchaseApproval.purchase_order_id == purchase_number
    ).first()
    
    if not db_approval:
        logger.warning(f"No purchase approval found for deletion with purchase number: {purchase_number}")
        return False
    
    logger.info(f"Found purchase approval ID {db_approval.id} for purchase number {purchase_number}, proceeding with deletion")
    
    # Delete the approval (cascade will handle items and boxes)
    db.delete(db_approval)
    db.commit()
    
    logger.info(f"Successfully deleted purchase approval for purchase number: {purchase_number}")
    return True


def get_approvals_by_po_id(db: Session, po_id: str) -> List[PurchaseApprovalWithItemsOut]:
    """Get all purchase approvals by purchase order ID with complete details."""
    # Get all approvals for this PO
    db_approvals = db.query(PurchaseApproval).filter(
        PurchaseApproval.purchase_order_id == po_id
    ).order_by(desc(PurchaseApproval.created_at)).all()
    
    result = []
    for db_approval in db_approvals:
        # Get items for this approval
        db_items = db.query(PurchaseApprovalItem).filter(
            PurchaseApprovalItem.approval_id == db_approval.id
        ).all()
        
        items_schemas = []
        for db_item in db_items:
            # Get boxes for each item
            db_boxes = db.query(PurchaseApprovalBox).filter(
                PurchaseApprovalBox.item_id == db_item.id
            ).all()
            
            boxes_schemas = [
                BoxSchema(
                    box_id=box.id,  # Include box_id for frontend
                    box_number=box.box_number,
                    article_name=box.article_name,
                    lot_number=box.lot_number,
                    net_weight=box.net_weight,
                    gross_weight=box.gross_weight,
                ) for box in db_boxes
            ]
            
            items_schemas.append(ItemSchema(
                material_type=db_item.material_type,
                item_category=db_item.item_category,
                sub_category=db_item.sub_category,
                item_description=db_item.item_description,
                quantity_units=db_item.quantity_units,
                pack_size=db_item.pack_size,
                uom=db_item.uom,
                net_weight=db_item.net_weight,
                gross_weight=db_item.gross_weight,
                lot_number=db_item.lot_number,
                mfg_date=db_item.mfg_date,
                exp_date=db_item.exp_date,
                # Article/Item Financial Information (optional)
                hsn_code=db_item.hsn_code,
                price_per_kg=db_item.price_per_kg,
                taxable_value=db_item.taxable_value,
                gst_percentage=db_item.gst_percentage,
                boxes=boxes_schemas,
            ))
        
        result.append(PurchaseApprovalWithItemsOut(
            id=db_approval.id,
            purchase_order_id=db_approval.purchase_order_id,
            transporter_information=TransporterInformation(
                vehicle_number=db_approval.vehicle_number,
                transporter_name=db_approval.transporter_name,
                lr_number=db_approval.lr_number,
                destination_location=db_approval.destination_location,
            ),
            customer_information=CustomerInformation(
                customer_name=db_approval.customer_name,
                authority=db_approval.authority,
                challan_number=db_approval.challan_number,
                invoice_number=db_approval.invoice_number,
                grn_number=db_approval.grn_number,
                grn_quantity=db_approval.grn_quantity,
                delivery_note_number=db_approval.delivery_note_number,
                service_po_number=db_approval.service_po_number,
            ),
            items=items_schemas,
            created_at=db_approval.created_at,
            updated_at=db_approval.updated_at,
        ))
    
    return result
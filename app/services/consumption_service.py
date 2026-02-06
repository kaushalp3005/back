# File: consumption_service.py
# Path: backend/app/services/consumption_service.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.models.consumption import (
    BOM, BOMComponent, Config, DailyLedger, FIFOLayer, InventoryMove, 
    JobCard, QCHold, SKU, Warehouse
)
from app.schemas.consumption import ConsumptionLine, ReceiptLine, TransferLine


class ConsumptionService:
    """Service class for consumption backend business logic"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ============================================
    # FIFO ALLOCATION METHODS
    # ============================================
    
    def allocate_fifo_for_consumption(
        self, 
        warehouse: str, 
        item_id: str, 
        qty_required: Decimal,
        uom: str,
        lot_no: Optional[str] = None,
        batch_no: Optional[str] = None
    ) -> List[Tuple[FIFOLayer, Decimal]]:
        """
        Allocate FIFO layers for consumption with FEFO support for perishable items
        Returns list of (layer, qty_allocated) tuples
        """
        # Get FIFO layers ordered by FEFO (FIFO + Expiry) for perishable items
        query = self.db.query(FIFOLayer).filter(
            and_(
                FIFOLayer.warehouse == warehouse,
                FIFOLayer.item_id == item_id,
                FIFOLayer.remaining_qty > 0
            )
        )
        
        # Apply lot/batch filtering if specified
        if lot_no:
            query = query.filter(FIFOLayer.lot == lot_no)
        if batch_no:
            query = query.filter(FIFOLayer.batch == batch_no)
        
        # Check if item is perishable for FEFO ordering
        sku = self.db.query(SKU).filter(SKU.id == item_id).first()
        if sku and sku.perishable:
            # FEFO: First Expiry First Out
            query = query.order_by(
                FIFOLayer.expiry_date.asc().nulls_last(),
                FIFOLayer.created_at.asc()
            )
        else:
            # FIFO: First In First Out
            query = query.order_by(FIFOLayer.created_at.asc())
        
        layers = query.all()
        
        allocations = []
        remaining_qty = qty_required
        
        for layer in layers:
            if remaining_qty <= 0:
                break
            
            # Allocate from this layer
            qty_to_allocate = min(remaining_qty, layer.remaining_qty)
            allocations.append((layer, qty_to_allocate))
            remaining_qty -= qty_to_allocate
        
        if remaining_qty > 0:
            raise ValueError(f"Insufficient stock. Required: {qty_required}, Available: {qty_required - remaining_qty}")
        
        return allocations
    
    def update_fifo_layers_after_consumption(
        self, 
        allocations: List[Tuple[FIFOLayer, Decimal]]
    ) -> None:
        """Update FIFO layers after consumption allocation"""
        for layer, qty_allocated in allocations:
            layer.remaining_qty -= qty_allocated
            if layer.remaining_qty < 0:
                layer.remaining_qty = Decimal('0')
            self.db.add(layer)
    
    def create_fifo_layer_from_receipt(
        self,
        warehouse: str,
        item_id: str,
        lot: str,
        batch: str,
        qty: Decimal,
        unit_cost: Decimal,
        source_tx_id: UUID,
        expiry_date: Optional[date] = None
    ) -> FIFOLayer:
        """Create new FIFO layer from receipt transaction"""
        fifo_layer = FIFOLayer(
            warehouse=warehouse,
            item_id=item_id,
            lot=lot,
            batch=batch,
            open_qty=qty,
            open_value=qty * unit_cost,
            remaining_qty=qty,
            unit_cost=unit_cost,
            source_tx_id=source_tx_id,
            expiry_date=expiry_date
        )
        self.db.add(fifo_layer)
        return fifo_layer
    
    # ============================================
    # LEDGER CALCULATION METHODS
    # ============================================
    
    def calculate_daily_ledger(
        self,
        ledger_date: date,
        company: str = "CFPL",
        warehouse: Optional[str] = None,
        sku_id: Optional[str] = None
    ) -> List[DailyLedger]:
        """Calculate daily ledger for specified date and filters"""
        
        # Get all inventory moves for the date
        moves_query = self.db.query(InventoryMove).filter(
            and_(
                func.date(InventoryMove.ts) == ledger_date,
                InventoryMove.company == company
            )
        )
        
        if warehouse:
            moves_query = moves_query.filter(InventoryMove.warehouse == warehouse)
        if sku_id:
            moves_query = moves_query.filter(InventoryMove.item_id == sku_id)
        
        moves = moves_query.all()
        
        # Group moves by warehouse and SKU
        grouped_moves = {}
        for move in moves:
            key = (move.warehouse, move.item_id)
            if key not in grouped_moves:
                grouped_moves[key] = {
                    'warehouse': move.warehouse,
                    'item_id': move.item_id,
                    'uom': move.uom,
                    'transfer_in': Decimal('0'),
                    'transfer_out': Decimal('0'),
                    'stock_in': Decimal('0'),
                    'stock_out': Decimal('0'),
                    'total_value_in': Decimal('0'),
                    'total_value_out': Decimal('0'),
                    'total_qty_in': Decimal('0'),
                    'total_qty_out': Decimal('0')
                }
            
            group = grouped_moves[key]
            
            # Categorize transactions
            if move.tx_code == 'TRIN':
                group['transfer_in'] += move.qty_in
            elif move.tx_code == 'TROUT':
                group['transfer_out'] += move.qty_out
            elif move.tx_code in ['GRN', 'SFG', 'FG', 'ADJ+', 'RETIN', 'OPENING']:
                group['stock_in'] += move.qty_in
                group['total_value_in'] += move.value_in
                group['total_qty_in'] += move.qty_in
            elif move.tx_code in ['CON', 'OUT', 'ADJ-', 'SCRAP', 'RTV']:
                group['stock_out'] += move.qty_out
                group['total_value_out'] += move.value_out
                group['total_qty_out'] += move.qty_out
        
        # Calculate ledger entries
        ledger_entries = []
        for key, group in grouped_moves.items():
            warehouse_code, item_id = key
            
            # Get SKU details
            sku = self.db.query(SKU).filter(SKU.id == item_id).first()
            if not sku:
                continue
            
            # Get previous day's closing stock
            prev_day_ledger = self.db.query(DailyLedger).filter(
                and_(
                    DailyLedger.date == ledger_date - datetime.timedelta(days=1),
                    DailyLedger.company == company,
                    DailyLedger.warehouse == warehouse_code,
                    DailyLedger.sku_id == item_id
                )
            ).first()
            
            opening_stock = prev_day_ledger.closing_stock if prev_day_ledger else Decimal('0')
            
            # Calculate closing stock
            closing_stock = (
                opening_stock + 
                group['transfer_in'] + 
                group['stock_in'] - 
                group['transfer_out'] - 
                group['stock_out']
            )
            
            # Calculate valuation rate (weighted average)
            valuation_rate = Decimal('0')
            if group['total_qty_in'] > 0:
                valuation_rate = group['total_value_in'] / group['total_qty_in']
            elif prev_day_ledger:
                valuation_rate = prev_day_ledger.valuation_rate
            
            # Calculate inventory value
            inventory_value_closing = closing_stock * valuation_rate
            
            # Create or update ledger entry
            ledger_entry = DailyLedger(
                date=ledger_date,
                company=company,
                warehouse=warehouse_code,
                sku_id=item_id,
                material_type=sku.material_type,
                opening_stock=opening_stock,
                transfer_in=group['transfer_in'],
                transfer_out=group['transfer_out'],
                stock_in=group['stock_in'],
                stock_out=group['stock_out'],
                closing_stock=closing_stock,
                valuation_rate=valuation_rate,
                inventory_value_closing=inventory_value_closing,
                uom=sku.uom
            )
            
            # Check if entry already exists and update or insert
            existing_entry = self.db.query(DailyLedger).filter(
                and_(
                    DailyLedger.date == ledger_date,
                    DailyLedger.company == company,
                    DailyLedger.warehouse == warehouse_code,
                    DailyLedger.sku_id == item_id
                )
            ).first()
            
            if existing_entry:
                # Update existing entry
                existing_entry.opening_stock = opening_stock
                existing_entry.transfer_in = group['transfer_in']
                existing_entry.transfer_out = group['transfer_out']
                existing_entry.stock_in = group['stock_in']
                existing_entry.stock_out = group['stock_out']
                existing_entry.closing_stock = closing_stock
                existing_entry.valuation_rate = valuation_rate
                existing_entry.inventory_value_closing = inventory_value_closing
                self.db.add(existing_entry)
                ledger_entries.append(existing_entry)
            else:
                # Insert new entry
                self.db.add(ledger_entry)
                ledger_entries.append(ledger_entry)
        
        self.db.commit()
        return ledger_entries
    
    # ============================================
    # BOM CALCULATION METHODS
    # ============================================
    
    def calculate_bom_requirements(
        self,
        bom_id: str,
        planned_qty: Decimal
    ) -> List[Tuple[str, Decimal, str, Decimal]]:
        """
        Calculate material requirements from BOM
        Returns list of (sku_id, qty_required, uom, qty_with_loss) tuples
        """
        bom_components = self.db.query(BOMComponent).filter(
            and_(
                BOMComponent.bom_id == bom_id,
                BOMComponent.is_active == True
            )
        ).all()
        
        requirements = []
        for component in bom_components:
            # Use pre-calculated quantity with loss
            qty_with_loss = component.qty_with_loss * planned_qty  # Scale by planned quantity
            
            requirements.append((
                component.sku_id,
                qty_with_loss,
                component.uom,
                component.qty_required * planned_qty
            ))
        
        return requirements
    
    def check_material_availability(
        self,
        warehouse: str,
        requirements: List[Tuple[str, Decimal, str, Decimal]]
    ) -> Tuple[bool, List[str]]:
        """
        Check material availability for BOM requirements
        Returns (is_available, list_of_shortages)
        """
        shortages = []
        
        for sku_id, qty_required, uom, _ in requirements:
            # Get current stock from FIFO layers
            total_available = self.db.query(func.sum(FIFOLayer.remaining_qty)).filter(
                and_(
                    FIFOLayer.warehouse == warehouse,
                    FIFOLayer.item_id == sku_id,
                    FIFOLayer.remaining_qty > 0
                )
            ).scalar() or Decimal('0')
            
            if total_available < qty_required:
                shortage_qty = qty_required - total_available
                shortages.append(f"{sku_id}: Short by {shortage_qty} {uom}")
        
        return len(shortages) == 0, shortages
    
    # ============================================
    # TRANSACTION PROCESSING METHODS
    # ============================================
    
    def process_consumption_transaction(
        self,
        job_card_no: str,
        warehouse: str,
        consumption_lines: List[ConsumptionLine]
    ) -> List[InventoryMove]:
        """Process consumption transaction with FIFO allocation"""
        inventory_moves = []
        
        for line in consumption_lines:
            # Allocate FIFO layers
            allocations = self.allocate_fifo_for_consumption(
                warehouse=warehouse,
                item_id=line.sku_id,
                qty_required=line.qty_issued,
                uom=line.uom,
                lot_no=line.lot_no,
                batch_no=line.batch_no
            )
            
            # Calculate weighted average cost
            total_cost = Decimal('0')
            total_qty = Decimal('0')
            for layer, qty_allocated in allocations:
                total_cost += layer.unit_cost * qty_allocated
                total_qty += qty_allocated
            
            avg_unit_cost = total_cost / total_qty if total_qty > 0 else Decimal('0')
            
            # Create inventory move
            inventory_move = InventoryMove(
                warehouse=warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="CON",
                job_card_no=job_card_no,
                qty_out=line.qty_issued,
                uom=line.uom,
                unit_cost=avg_unit_cost,
                value_out=total_cost,
                ref_doc=f"CONSUMPTION-{job_card_no}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Material consumption"
            )
            
            self.db.add(inventory_move)
            inventory_moves.append(inventory_move)
            
            # Update FIFO layers
            self.update_fifo_layers_after_consumption(allocations)
        
        return inventory_moves
    
    def process_receipt_transaction(
        self,
        job_card_no: str,
        warehouse: str,
        receipt_lines: List[ReceiptLine],
        output_type: str
    ) -> List[InventoryMove]:
        """Process production receipt transaction"""
        inventory_moves = []
        
        for line in receipt_lines:
            # Calculate unit cost from BOM (simplified - in real scenario, 
            # this would be calculated from consumed materials)
            unit_cost = Decimal('0')  # Placeholder - should be calculated from BOM costs
            
            # Create inventory move
            tx_code = "SFG" if output_type == "SFG" else "FG"
            inventory_move = InventoryMove(
                warehouse=warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code=tx_code,
                job_card_no=job_card_no,
                qty_in=line.qty_produced,
                uom=line.uom,
                unit_cost=unit_cost,
                value_in=line.qty_produced * unit_cost,
                ref_doc=f"RECEIPT-{job_card_no}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks=f"Production receipt - Yield: {line.yield_pct}%, Scrap: {line.scrap_qty}"
            )
            
            self.db.add(inventory_move)
            inventory_moves.append(inventory_move)
            
            # Create FIFO layer
            self.create_fifo_layer_from_receipt(
                warehouse=warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                qty=line.qty_produced,
                unit_cost=unit_cost,
                source_tx_id=inventory_move.id
            )
        
        return inventory_moves
    
    def process_transfer_transaction(
        self,
        source_warehouse: str,
        destination_warehouse: str,
        transfer_lines: List[TransferLine]
    ) -> List[InventoryMove]:
        """Process inter-warehouse transfer transaction"""
        inventory_moves = []
        
        for line in transfer_lines:
            # Allocate FIFO layers from source warehouse
            allocations = self.allocate_fifo_for_consumption(
                warehouse=source_warehouse,
                item_id=line.sku_id,
                qty_required=line.qty,
                uom=line.uom,
                lot_no=line.lot_no,
                batch_no=line.batch_no
            )
            
            # Calculate weighted average cost
            total_cost = Decimal('0')
            total_qty = Decimal('0')
            for layer, qty_allocated in allocations:
                total_cost += layer.unit_cost * qty_allocated
                total_qty += qty_allocated
            
            avg_unit_cost = total_cost / total_qty if total_qty > 0 else Decimal('0')
            
            # Create transfer out move
            transfer_out_move = InventoryMove(
                warehouse=source_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="TROUT",
                qty_out=line.qty,
                uom=line.uom,
                unit_cost=avg_unit_cost,
                value_out=total_cost,
                ref_doc=f"TRANSFER-{source_warehouse}-{destination_warehouse}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Inter-warehouse transfer out"
            )
            
            self.db.add(transfer_out_move)
            inventory_moves.append(transfer_out_move)
            
            # Create transfer in move
            transfer_in_move = InventoryMove(
                warehouse=destination_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                tx_code="TRIN",
                qty_in=line.qty,
                uom=line.uom,
                unit_cost=avg_unit_cost,
                value_in=total_cost,
                ref_doc=f"TRANSFER-{source_warehouse}-{destination_warehouse}",
                ref_line=f"LINE-{line.sku_id}",
                created_by="system",
                remarks="Inter-warehouse transfer in"
            )
            
            self.db.add(transfer_in_move)
            inventory_moves.append(transfer_in_move)
            
            # Update FIFO layers
            self.update_fifo_layers_after_consumption(allocations)
            
            # Create FIFO layer in destination warehouse
            self.create_fifo_layer_from_receipt(
                warehouse=destination_warehouse,
                item_id=line.sku_id,
                lot=line.lot_no,
                batch=line.batch_no,
                qty=line.qty,
                unit_cost=avg_unit_cost,
                source_tx_id=transfer_in_move.id
            )
        
        return inventory_moves
    
    # ============================================
    # UTILITY METHODS
    # ============================================
    
    def get_current_stock(
        self,
        warehouse: str,
        item_id: str,
        lot: Optional[str] = None,
        batch: Optional[str] = None
    ) -> Decimal:
        """Get current stock level for item in warehouse"""
        query = self.db.query(func.sum(FIFOLayer.remaining_qty)).filter(
            and_(
                FIFOLayer.warehouse == warehouse,
                FIFOLayer.item_id == item_id,
                FIFOLayer.remaining_qty > 0
            )
        )
        
        if lot:
            query = query.filter(FIFOLayer.lot == lot)
        if batch:
            query = query.filter(FIFOLayer.batch == batch)
        
        return query.scalar() or Decimal('0')
    
    def get_valuation_method(self) -> str:
        """Get current valuation method from configuration"""
        config = self.db.query(Config).filter(
            and_(
                Config.config_key == "valuation_method",
                Config.is_active == True
            )
        ).first()
        
        return config.config_value if config else "FIFO"
    
    def get_variance_threshold(self) -> Decimal:
        """Get variance threshold from configuration"""
        config = self.db.query(Config).filter(
            and_(
                Config.config_key == "variance_threshold_pct",
                Config.is_active == True
            )
        ).first()
        
        return Decimal(config.config_value) if config else Decimal('5.0')


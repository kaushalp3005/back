# File: consumption_schemas.py
# Path: backend/app/schemas/consumption.py

from datetime import date as Date, datetime
from decimal import Decimal
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================
# BASE MODELS
# ============================================

class SKUBase(BaseModel):
    id: str = Field(..., description="SKU ID")
    name: str = Field(..., description="SKU Name")
    material_type: str = Field(..., description="Material Type: RM, PM, SFG, FG")
    uom: str = Field(..., description="Unit of Measure")
    perishable: bool = Field(default=False, description="Is perishable")
    description: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_rate: Decimal = Field(default=0, description="GST Rate")
    is_active: bool = Field(default=True)

    @field_validator('material_type')
    @classmethod
    def validate_material_type(cls, v):
        if v not in ['RM', 'PM', 'SFG', 'FG']:
            raise ValueError('Material type must be RM, PM, SFG, or FG')
        return v.upper()


class WarehouseBase(BaseModel):
    code: str = Field(..., description="Warehouse Code")
    name: str = Field(..., description="Warehouse Name")
    sitecode: str = Field(..., description="Site Code")
    location: Optional[str] = None
    warehouse_type: str = Field(default="STORAGE", description="Warehouse Type")
    is_active: bool = Field(default=True)


class UserBase(BaseModel):
    email: str = Field(..., description="User Email")
    role: str = Field(..., description="User Role")
    full_name: Optional[str] = None
    department: Optional[str] = None
    is_active: bool = Field(default=True)


# ============================================
# BOM MODELS
# ============================================

class BOMComponentBase(BaseModel):
    sku_id: str = Field(..., description="SKU ID")
    material_type: str = Field(..., description="Material Type: RM, PM")
    qty_required: Decimal = Field(..., description="Quantity Required")
    uom: str = Field(..., description="Unit of Measure")
    sequence_order: int = Field(default=1, description="Sequence Order")
    
    # Loss tracking fields
    process_loss_pct: Decimal = Field(default=0, description="Process Loss Percentage")
    extra_giveaway_pct: Decimal = Field(default=0, description="Extra Giveaway Percentage")
    handling_loss_pct: Decimal = Field(default=0, description="Handling Loss Percentage")
    shrinkage_pct: Decimal = Field(default=0, description="Shrinkage Percentage")
    
    is_active: bool = Field(default=True)

    @field_validator('material_type')
    @classmethod
    def validate_material_type(cls, v):
        if v not in ['RM', 'PM']:
            raise ValueError('Material type must be RM or PM')
        return v.upper()


class BOMComponentCreate(BOMComponentBase):
    pass


class BOMComponentResponse(BOMComponentBase):
    id: int
    bom_id: str
    total_loss_pct: Decimal
    qty_with_loss: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BOMBase(BaseModel):
    id: str = Field(..., description="BOM ID")
    name: str = Field(..., description="BOM Name")
    description: Optional[str] = None
    version: str = Field(default="1.0", description="BOM Version")
    output_sku_id: str = Field(..., description="Output SKU ID")
    output_qty: Decimal = Field(default=1, description="Output Quantity")
    output_uom: str = Field(..., description="Output UOM")
    is_active: bool = Field(default=True)
    created_by: Optional[str] = None


class BOMCreate(BOMBase):
    components: List[BOMComponentCreate] = Field(default=[], description="BOM Components")


class BOMResponse(BOMBase):
    created_at: datetime
    updated_at: datetime
    components: List[BOMComponentResponse] = []

    class Config:
        from_attributes = True


# ============================================
# JOB CARD MODELS
# ============================================

class JobCardBase(BaseModel):
    job_card_no: str = Field(..., description="Job Card Number")
    sku_id: str = Field(..., description="SKU ID")
    bom_id: str = Field(..., description="BOM ID")
    planned_qty: Decimal = Field(..., description="Planned Quantity")
    uom: str = Field(..., description="Unit of Measure")
    status: str = Field(default="PLANNED", description="Job Card Status")
    priority: str = Field(default="NORMAL", description="Priority")
    due_date: Optional[Date] = None
    start_date: Optional[Date] = None
    completion_date: Optional[Date] = None
    production_line: Optional[str] = None
    shift: Optional[str] = None
    remarks: Optional[str] = None
    created_by: Optional[str] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        valid_statuses = ['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of {valid_statuses}')
        return v.upper()

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        valid_priorities = ['HIGH', 'NORMAL', 'LOW']
        if v not in valid_priorities:
            raise ValueError(f'Priority must be one of {valid_priorities}')
        return v.upper()


class JobCardCreate(JobCardBase):
    pass


class JobCardResponse(JobCardBase):
    actual_qty: Decimal = Field(default=0, description="Actual Quantity")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================
# INVENTORY MOVES MODELS
# ============================================

class InventoryMoveBase(BaseModel):
    warehouse: str = Field(..., description="Warehouse Code")
    item_id: str = Field(..., description="SKU ID")
    lot: Optional[str] = None
    batch: Optional[str] = None
    tx_code: str = Field(..., description="Transaction Code")
    job_card_no: Optional[str] = None
    so_no: Optional[str] = None
    qty_in: Decimal = Field(default=0, description="Quantity In")
    qty_out: Decimal = Field(default=0, description="Quantity Out")
    uom: str = Field(..., description="Unit of Measure")
    unit_cost: Decimal = Field(default=0, description="Unit Cost")
    ref_doc: Optional[str] = None
    ref_line: Optional[str] = None
    created_by: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator('tx_code')
    @classmethod
    def validate_tx_code(cls, v):
        valid_codes = [
            'GRN', 'CON', 'SFG', 'FG', 'TRIN', 'TROUT', 'OUT', 'ADJ+', 'ADJ-',
            'RETIN', 'OPENING', 'SCRAP', 'RTV', 'QC_HOLD', 'QC_RELEASE'
        ]
        if v not in valid_codes:
            raise ValueError(f'Transaction code must be one of {valid_codes}')
        return v.upper()


class InventoryMoveCreate(InventoryMoveBase):
    pass


class InventoryMoveResponse(InventoryMoveBase):
    id: UUID
    ts: datetime
    company: str
    value_in: Decimal
    value_out: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# LEDGER MODELS
# ============================================

class LedgerFilter(BaseModel):
    date: Date = Field(..., description="Date in YYYY-MM-DD format")
    warehouse: Optional[str] = None
    sku_id: Optional[str] = None
    material_type: Optional[str] = None

    @field_validator('material_type')
    @classmethod
    def validate_material_type(cls, v):
        if v is not None and v not in ['RM', 'PM', 'SFG', 'FG']:
            raise ValueError('Material type must be RM, PM, SFG, or FG')
        return v.upper() if v else v


class LedgerRow(BaseModel):
    date: Date = Field(..., description="Date in YYYY-MM-DD format")
    company: str = Field(..., description="Company Code")
    warehouse: str = Field(..., description="Warehouse Code")
    sku_id: str = Field(..., description="SKU ID")
    material_type: str = Field(..., description="Material Type")
    opening_stock: Decimal = Field(..., description="Opening Stock")
    stock_in_hand: Decimal = Field(..., description="Stock In Hand (same as opening stock)")
    transfer_in: Decimal = Field(..., description="Transfer In")
    transfer_out: Decimal = Field(..., description="Transfer Out")
    stock_in: Decimal = Field(..., description="Stock In")
    stock_out: Decimal = Field(..., description="Stock Out")
    closing_stock: Decimal = Field(..., description="Closing Stock")
    valuation_rate: Decimal = Field(..., description="Valuation Rate")
    inventory_value_closing: Decimal = Field(..., description="Inventory Value Closing")
    uom: str = Field(..., description="Unit of Measure")

    class Config:
        from_attributes = True


# ============================================
# CONSUMPTION MODELS
# ============================================

class ConsumptionLine(BaseModel):
    sku_id: str = Field(..., description="SKU ID")
    material_type: str = Field(..., description="Material Type: RM, PM")
    uom: str = Field(..., description="Unit of Measure")
    qty_issued: Decimal = Field(..., description="Quantity Issued")
    lot_no: str = Field(..., description="Lot Number")
    batch_no: str = Field(..., description="Batch Number")

    @field_validator('material_type')
    @classmethod
    def validate_material_type(cls, v):
        if v not in ['RM', 'PM']:
            raise ValueError('Material type must be RM or PM')
        return v.upper()


class ConsumptionPost(BaseModel):
    job_card_no: str = Field(..., description="Job Card Number")
    warehouse: str = Field(..., description="Warehouse Code")
    lines: List[ConsumptionLine] = Field(..., description="Consumption Lines")
    remarks: Optional[str] = None


# ============================================
# RECEIPT MODELS
# ============================================

class ReceiptLine(BaseModel):
    sku_id: str = Field(..., description="SKU ID")
    uom: str = Field(..., description="Unit of Measure")
    qty_produced: Decimal = Field(..., description="Quantity Produced")
    batch_no: str = Field(..., description="Batch Number")
    lot_no: str = Field(..., description="Lot Number")
    yield_pct: Optional[Decimal] = None
    scrap_qty: Optional[Decimal] = None


class ReceiptPost(BaseModel):
    job_card_no: str = Field(..., description="Job Card Number")
    output_type: str = Field(..., description="Output Type: SFG, FG")
    to_warehouse: str = Field(..., description="Destination Warehouse")
    qc_required: bool = Field(default=True, description="QC Required")
    lines: List[ReceiptLine] = Field(..., description="Receipt Lines")

    @field_validator('output_type')
    @classmethod
    def validate_output_type(cls, v):
        if v not in ['SFG', 'FG']:
            raise ValueError('Output type must be SFG or FG')
        return v.upper()


# ============================================
# TRANSFER MODELS
# ============================================

class TransferLine(BaseModel):
    sku_id: str = Field(..., description="SKU ID")
    uom: str = Field(..., description="Unit of Measure")
    qty: Decimal = Field(..., description="Quantity")
    lot_no: str = Field(..., description="Lot Number")
    batch_no: str = Field(..., description="Batch Number")


class TransferPost(BaseModel):
    source_warehouse: str = Field(..., description="Source Warehouse")
    destination_warehouse: str = Field(..., description="Destination Warehouse")
    lines: List[TransferLine] = Field(..., description="Transfer Lines")


# ============================================
# DISPATCH MODELS
# ============================================

class DispatchLine(BaseModel):
    sku_id: str = Field(..., description="SKU ID")
    uom: str = Field(..., description="Unit of Measure")
    qty: Decimal = Field(..., description="Quantity")
    lot_no: Optional[str] = None
    batch_no: Optional[str] = None


class DispatchPost(BaseModel):
    warehouse: str = Field(..., description="Warehouse Code")
    so_no: str = Field(..., description="Sales Order Number")
    lines: List[DispatchLine] = Field(..., description="Dispatch Lines")


# ============================================
# CONFIGURATION MODELS
# ============================================

class ConfigGet(BaseModel):
    valuation_method: str = Field(..., description="Valuation Method: FIFO, WAVG")
    variance_threshold_pct: Decimal = Field(..., description="Variance Threshold Percentage")

    @field_validator('valuation_method')
    @classmethod
    def validate_valuation_method(cls, v):
        if v not in ['FIFO', 'WAVG']:
            raise ValueError('Valuation method must be FIFO or WAVG')
        return v.upper()


# ============================================
# FIFO LAYERS MODELS
# ============================================

class FIFOLayerBase(BaseModel):
    warehouse: str = Field(..., description="Warehouse Code")
    item_id: str = Field(..., description="SKU ID")
    lot: Optional[str] = None
    batch: Optional[str] = None
    open_qty: Decimal = Field(..., description="Open Quantity")
    open_value: Decimal = Field(..., description="Open Value")
    remaining_qty: Decimal = Field(..., description="Remaining Quantity")
    unit_cost: Decimal = Field(..., description="Unit Cost")
    expiry_date: Optional[Date] = None


class FIFOLayerResponse(FIFOLayerBase):
    id: UUID
    company: str
    source_tx_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================
# QC HOLDS MODELS
# ============================================

class QCHoldBase(BaseModel):
    inventory_move_id: UUID = Field(..., description="Inventory Move ID")
    warehouse: str = Field(..., description="Warehouse Code")
    item_id: str = Field(..., description="SKU ID")
    lot: Optional[str] = None
    batch: Optional[str] = None
    qty: Decimal = Field(..., description="Quantity")
    uom: str = Field(..., description="Unit of Measure")
    hold_reason: str = Field(..., description="Hold Reason")
    qc_remarks: Optional[str] = None
    qc_by: Optional[str] = None


class QCHoldCreate(QCHoldBase):
    pass


class QCHoldResponse(QCHoldBase):
    id: UUID
    hold_date: datetime
    release_date: Optional[datetime] = None
    status: str = Field(default="HOLD", description="Status: HOLD, RELEASE, REJECT")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================
# RESPONSE MODELS
# ============================================

class StandardResponse(BaseModel):
    success: bool = Field(..., description="Success status")
    message: str = Field(..., description="Response message")
    data: Optional[Union[dict, list]] = None


class PaginatedResponse(BaseModel):
    success: bool = Field(..., description="Success status")
    message: str = Field(..., description="Response message")
    data: List[dict] = Field(..., description="Response data")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    per_page: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total pages")


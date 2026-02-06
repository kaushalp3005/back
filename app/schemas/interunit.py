from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List, Literal
from datetime import date, datetime
from decimal import Decimal
import re

# ============================================
# ENUMS FOR VALIDATION (as per JSON requirements)
# ============================================

WarehouseOptions = Literal["W202", "A185", "A101", "A68", "F53", "Savla", "Rishi"]
MaterialTypeOptions = Literal["RM", "PM", "FG", "RTV"]
UOMOptions = Literal["KG", "PCS", "BOX", "CARTON"]

# ============================================
# FORM DATA SCHEMAS (as per JSON structure)
# ============================================

class FormDataBase(BaseModel):
    """Base form data schema matching JSON structure"""
    request_date: str = Field(..., description="Request date in DD-MM-YYYY format")
    from_warehouse: WarehouseOptions = Field(..., description="Requesting warehouse site code")
    to_warehouse: WarehouseOptions = Field(..., description="Supplying warehouse site code")
    reason_description: str = Field(..., description="Reason description for the transfer request")

    @validator('request_date')
    def validate_date_format(cls, v):
        """Validate DD-MM-YYYY format"""
        if not re.match(r'^\d{2}-\d{2}-\d{4}$', v):
            raise ValueError('Date must be in DD-MM-YYYY format')
        return v

    @validator('reason_description')
    def uppercase_reason_description(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @model_validator(mode='after')
    def validate_warehouses_different(self):
        """Ensure from_warehouse != to_warehouse"""
        if self.from_warehouse and self.to_warehouse and self.from_warehouse == self.to_warehouse:
            raise ValueError('From warehouse and to warehouse must be different')
        return self

# ============================================
# ARTICLE DATA SCHEMAS (as per JSON structure)
# ============================================

class ArticleDataBase(BaseModel):
    """Base article data schema matching JSON structure"""
    material_type: MaterialTypeOptions = Field(..., description="Type of material")
    item_category: str = Field(..., description="Item category from API or fallback data")
    sub_category: str = Field(..., description="Sub category dependent on item category")
    item_description: str = Field(..., description="Item description dependent on category and sub category")
    quantity: str = Field(default="0", description="Quantity in units")
    uom: UOMOptions = Field(..., description="Unit of measurement")
    pack_size: str = Field(default="0.00", description="Pack size in Kg (for RM/PM/RTV) or gm (for FG)")
    package_size: Optional[str] = Field(default="0", description="Package size in gm (only for FG material type)")
    net_weight: Optional[str] = Field(default=None, description="Auto-calculated net weight")

    @validator('material_type', 'uom')
    def uppercase_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @validator('item_category', 'sub_category', 'item_description')
    def uppercase_text_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @validator('package_size')
    def validate_package_size_conditional(cls, v, values):
        """Package size is required only when materialType === 'FG'"""
        material_type = values.get('material_type')
        if material_type == 'FG' and (not v or v == "0"):
            raise ValueError('Package size is required when material type is FG')
        return v

    @model_validator(mode='after')
    def calculate_net_weight(self):
        """Auto-calculate net weight based on material type"""
        quantity = float(self.quantity)
        pack_size = float(self.pack_size)
        package_size = float(self.package_size) if self.package_size else 0

        if self.material_type == 'FG':
            # For FG: (packageSize * packSize) * quantity
            net_weight = (package_size * pack_size) * quantity
        else:
            # For RM/PM/RTV: quantity * packSize
            net_weight = quantity * pack_size

        self.net_weight = str(net_weight)
        return self

# ============================================
# COMPUTED FIELDS SCHEMAS (as per JSON structure)
# ============================================

class ComputedFields(BaseModel):
    """Computed fields schema matching JSON structure"""
    request_no: Optional[str] = Field(None, description="Auto-generated request number in format REQ{YYYYMMDD}{timestamp}")

# ============================================
# VALIDATION RULES SCHEMAS (as per JSON structure)
# ============================================

class ValidationRules(BaseModel):
    """Validation rules schema matching JSON structure"""
    from_warehouse_required: bool = Field(True, description="From warehouse is required")
    from_warehouse_not_equal_to_warehouse: bool = Field(True, description="From warehouse must not equal to warehouse")
    to_warehouse_required: bool = Field(True, description="To warehouse is required")
    to_warehouse_not_equal_from_warehouse: bool = Field(True, description="To warehouse must not equal from warehouse")
    material_type_required: bool = Field(True, description="Material type is required")
    material_type_enum: List[str] = Field(default=["RM", "PM", "FG", "RTV"], description="Valid material types")
    package_size_required: bool = Field(True, description="Package size is required")
    package_size_conditional: str = Field("Only when materialType === 'FG'", description="Package size conditional requirement")

# ============================================
# UPDATED REQUEST LINE SCHEMAS
# ============================================

class RequestLineCreate(BaseModel):
    """Request line creation schema matching JSON structure"""
    material_type: MaterialTypeOptions = Field(..., description="Type of material")
    item_category: str = Field(..., description="Item category from API or fallback data")
    sub_category: str = Field(..., description="Sub category dependent on item category")
    item_description: str = Field(..., description="Item description dependent on category and sub category")
    quantity: str = Field(default="0", description="Quantity in units")
    uom: UOMOptions = Field(..., description="Unit of measurement")
    pack_size: str = Field(default="0.00", description="Pack size in Kg (for RM/PM/RTV) or gm (for FG)")
    package_size: Optional[str] = Field(default="0", description="Package size in gm (only for FG material type)")
    batch_number: Optional[str] = Field(None, description="Batch number")
    lot_number: Optional[str] = Field(None, description="Lot number")

    @validator('material_type', 'uom')
    def uppercase_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @validator('item_category', 'sub_category', 'item_description', 'batch_number', 'lot_number')
    def uppercase_text_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @validator('package_size')
    def validate_package_size_conditional(cls, v, values):
        """Package size is required only when materialType === 'FG'"""
        material_type = values.get('material_type')
        if material_type == 'FG' and (not v or v == "0"):
            raise ValueError('Package size is required when material type is FG')
        return v

class RequestLineResponse(BaseModel):
    """Request line response schema"""
    id: int
    request_id: int
    material_type: str
    item_category: str
    sub_category: str
    item_description: str
    quantity: str
    uom: str
    pack_size: str
    package_size: Optional[str] = None
    net_weight: str
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ============================================
# UPDATED REQUEST SCHEMAS
# ============================================

class RequestCreate(BaseModel):
    """Request creation schema matching JSON structure"""
    form_data: FormDataBase = Field(..., description="Form data for the transfer request")
    article_data: List[RequestLineCreate] = Field(..., min_items=1, description="Article data (minimum 1 item required)")
    computed_fields: Optional[ComputedFields] = Field(None, description="Computed fields")
    validation_rules: Optional[ValidationRules] = Field(None, description="Validation rules")

class RequestUpdate(BaseModel):
    """Request update schema"""
    status: Optional[str] = None
    reject_reason: Optional[str] = None
    rejected_ts: Optional[datetime] = None

    @validator('reject_reason')
    def uppercase_reject_reason(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

class RequestResponse(BaseModel):
    """Request response schema"""
    id: int
    request_no: str
    request_date: str
    from_warehouse: str
    to_warehouse: str
    reason_description: str
    status: str
    reject_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_ts: datetime
    rejected_ts: Optional[datetime] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True

class RequestWithLines(RequestResponse):
    """Request with lines response"""
    lines: List[RequestLineResponse]

# ============================================
# DROPDOWN SCHEMAS
# ============================================

class WarehouseSiteResponse(BaseModel):
    """Warehouse site response for dropdowns"""
    id: int
    site_code: str
    site_name: str
    is_active: bool
    
    class Config:
        from_attributes = True

class MaterialTypeResponse(BaseModel):
    """Material type response for dropdowns"""
    id: int
    type_code: str
    type_name: str
    description: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True

class UOMResponse(BaseModel):
    """UOM response for dropdowns"""
    id: int
    uom_code: str
    uom_name: str
    description: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True

# ============================================
# TRANSFER SCHEMAS (Updated to match new structure)
# ============================================

class TransferLineCreate(BaseModel):
    """Transfer line creation schema matching JSON structure"""
    material_type: MaterialTypeOptions = Field(..., description="Type of material")
    item_category: str = Field(..., description="Item category from API or fallback data")
    sub_category: str = Field(..., description="Sub category dependent on item category")
    item_description: str = Field(..., description="Item description dependent on category and sub category")
    quantity: str = Field(default="0", description="Quantity in units")
    uom: UOMOptions = Field(..., description="Unit of measurement")
    pack_size: str = Field(default="0.00", description="Pack size in Kg (for RM/PM/RTV) or gm (for FG)")
    package_size: Optional[str] = Field(default="0", description="Package size in gm (only for FG material type)")
    batch_number: Optional[str] = Field(None, description="Batch number")
    lot_number: Optional[str] = Field(None, description="Lot number")

    @validator('material_type', 'uom')
    def uppercase_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @validator('item_category', 'sub_category', 'item_description', 'batch_number', 'lot_number')
    def uppercase_text_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

class TransferHeaderBase(BaseModel):
    """Base transfer header schema"""
    challan_no: Optional[str] = Field(None, description="Transfer challan number (auto-generated if not provided)")
    stock_trf_date: date = Field(..., description="Transfer date")
    from_warehouse: WarehouseOptions = Field(..., description="Source warehouse")
    to_warehouse: WarehouseOptions = Field(..., description="Destination warehouse")
    vehicle_no: str = Field(..., description="Vehicle number")
    driver_name: Optional[str] = Field(None, description="Driver name")
    approved_by: Optional[str] = Field(None, description="Approval authority name")
    remark: str = Field(..., min_length=1, description="Remark")
    reason_code: str = Field(..., description="Reason code")

    @validator('vehicle_no', 'remark', 'reason_code', 'driver_name', 'approved_by')
    def uppercase_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

    @model_validator(mode='after')
    def validate_warehouses_different(self):
        """Ensure from_warehouse != to_warehouse"""
        if self.from_warehouse and self.to_warehouse and self.from_warehouse == self.to_warehouse:
            raise ValueError('From warehouse and to warehouse must be different')
        return self

class TransferCreate(BaseModel):
    """Transfer creation schema"""
    header: TransferHeaderBase
    lines: List[TransferLineCreate] = Field(..., min_items=1, description="Transfer lines (minimum 1)")
    boxes: Optional[List['BoxCreate']] = Field(default=[], description="Scanned boxes (optional)")
    request_id: Optional[int] = Field(None, description="Request ID if created from request")

class TransferUpdate(BaseModel):
    """Transfer update schema"""
    header: TransferHeaderBase
    lines: List[TransferLineCreate] = Field(..., min_items=1)

class TransferLineResponse(BaseModel):
    """Transfer line response schema"""
    id: int
    header_id: int
    material_type: str
    item_category: str
    sub_category: str
    item_description: str
    quantity: str
    uom: str
    pack_size: str
    package_size: Optional[str] = None
    net_weight: str
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class TransferHeaderResponse(TransferHeaderBase):
    """Transfer header response schema"""
    id: int
    challan_no: str
    status: str
    request_id: Optional[int] = None
    created_by: Optional[str] = None
    created_ts: datetime
    approved_by: Optional[str] = None
    approved_ts: Optional[datetime] = None
    updated_ts: datetime
    has_variance: bool = False
    
    class Config:
        from_attributes = True

class TransferWithLines(BaseModel):
    """Transfer with lines response"""
    header: TransferHeaderResponse
    lines: List[TransferLineResponse]

# ============================================
# BOX SCHEMAS (Updated)
# ============================================

class BoxCreate(BaseModel):
    """Box creation schema"""
    box_number: int = Field(..., description="Box number (sequential)")
    article: str = Field(..., description="Article name")
    lot_number: Optional[str] = Field(None, description="Lot number")
    batch_number: Optional[str] = Field(None, description="Batch number")
    transaction_no: Optional[str] = Field(None, description="Transaction number")
    net_weight: Decimal = Field(0, ge=0, description="Net weight")
    gross_weight: Decimal = Field(0, ge=0, description="Gross weight")

    @validator('article', 'lot_number', 'batch_number', 'transaction_no')
    def uppercase_text_fields(cls, v):
        """Convert to uppercase as per user preference"""
        return v.upper() if v else v

class BoxResponse(BaseModel):
    """Box response schema"""
    id: int
    transfer_line_id: int
    header_id: int
    box_number: int
    article: str
    lot_number: Optional[str] = None
    net_weight: Decimal
    gross_weight: Decimal
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ============================================
# LIST & FILTER SCHEMAS (Updated)
# ============================================

class TransferListItem(BaseModel):
    """Transfer list item (summary)"""
    id: int
    stock_trf_date: date
    from_warehouse: str
    to_warehouse: str
    status: str
    challan_no: str
    lines_count: int
    qty_total: Decimal
    vehicle_no: str
    reason_code: str
    created_by: Optional[str] = None
    has_variance: bool = False

class TransferListResponse(BaseModel):
    """Transfer list response with pagination"""
    items: List[TransferListItem]
    total: int
    pages: int

# ============================================
# APPROVAL SCHEMAS
# ============================================

class TransferApproveRequest(BaseModel):
    """Transfer approval request"""
    transfer_id: int

class TransferApproveResponse(BaseModel):
    """Transfer approval response"""
    header: TransferHeaderResponse
    lines: List[TransferLineResponse]

# ============================================
# DELETE RESPONSE SCHEMAS
# ============================================

class DeleteResponse(BaseModel):
    """Generic delete response"""
    success: bool
    message: str

# ============================================
# APPROVAL AUTHORITY SCHEMAS
# ============================================

class ApprovalAuthorityResponse(BaseModel):
    """Approval authority response schema for dropdowns"""
    id: int
    authority: str = Field(..., description="Authority name")
    contact_number: Optional[str] = Field(None, description="Contact number")
    email: Optional[str] = Field(None, description="Email address")
    warehouse: str = Field(..., description="Warehouse code")
    is_active: bool = Field(True, description="Whether the authority is active")
    
    class Config:
        from_attributes = True

# ============================================
# TRANSFER IN SCHEMAS
# ============================================

class TransferInBoxScanned(BaseModel):
    """Scanned box data for Transfer IN"""
    box_number: str
    article: Optional[str] = None
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    transaction_no: Optional[str] = None
    net_weight: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    is_matched: bool = True

class TransferInCreate(BaseModel):
    """Transfer IN creation request"""
    transfer_out_id: int
    grn_number: str
    receiving_warehouse: str
    received_by: str
    box_condition: Optional[str] = "Good"
    condition_remarks: Optional[str] = None
    scanned_boxes: List[TransferInBoxScanned]

    @validator('box_condition')
    def validate_box_condition(cls, v):
        """Validate box condition values"""
        allowed = ['Good', 'Damaged', 'Partial']
        if v and v not in allowed:
            raise ValueError(f'Box condition must be one of: {", ".join(allowed)}')
        return v

class TransferInBoxResponse(BaseModel):
    """Transfer IN box response"""
    id: int
    box_number: str
    article: Optional[str]
    batch_number: Optional[str]
    lot_number: Optional[str]
    transaction_no: Optional[str]
    net_weight: Optional[Decimal]
    gross_weight: Optional[Decimal]
    scanned_at: datetime
    is_matched: bool

class TransferInHeaderResponse(BaseModel):
    """Transfer IN header response"""
    id: int
    transfer_out_id: int
    transfer_out_no: str
    grn_number: str
    grn_date: datetime
    receiving_warehouse: str
    received_by: str
    received_at: datetime
    box_condition: Optional[str]
    condition_remarks: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

class TransferInDetailResponse(BaseModel):
    """Transfer IN detail response with boxes"""
    header: TransferInHeaderResponse
    boxes: List[TransferInBoxResponse]
    total_boxes_scanned: int

# Resolve forward references
TransferCreate.model_rebuild()

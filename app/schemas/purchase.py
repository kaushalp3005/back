from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, field_serializer
from decimal import Decimal

# --------------------------
# Shared small value objects
# --------------------------
Currency = Literal["INR"]

class PurchaseOrderInfo(BaseModel):
    po_number: str
    po_date: date
    po_validity: Optional[date] = None
    currency: Currency = "INR"

class Party(BaseModel):
    name: str
    address: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None

class FinancialSummary(BaseModel):
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    sub_total: Decimal = Field(..., max_digits=14, decimal_places=2)
    igst: Decimal = Field(default=Decimal('0'), max_digits=14, decimal_places=2)
    other_charges_non_gst: Decimal = Field(default=Decimal('0'), max_digits=14, decimal_places=2)
    grand_total: Decimal = Field(..., max_digits=14, decimal_places=2)

    @field_serializer('sub_total', 'igst', 'other_charges_non_gst', 'grand_total', when_used='always')
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)

# --------------------------
# PURCHASE ORDER (Header)
# --------------------------
class PurchaseOrderCreate(BaseModel):
    """Create a PO header only (no items)."""
    company_name: str
    purchase_number: str

    purchase_order: PurchaseOrderInfo
    buyer: Party
    supplier: Party
    ship_to: Party

    # Additional info
    freight_by: Optional[str] = None
    dispatch_by: Optional[str] = None
    indentor: Optional[str] = None

    # Financial snapshot
    financial_summary: FinancialSummary


class PurchaseOrderUpdate(BaseModel):
    """Partial update (PATCH) of PO header."""
    # Typically id comes from path; include here if you prefer body-based validation
    id: Optional[int] = None

    company_name: Optional[str] = None
    purchase_number: Optional[str] = None

    # Nested parts are optional, and their inner fields are also optional
    purchase_order: Optional[PurchaseOrderInfo] = None
    buyer: Optional[Party] = None
    supplier: Optional[Party] = None
    ship_to: Optional[Party] = None

    freight_by: Optional[str] = None
    dispatch_by: Optional[str] = None
    indentor: Optional[str] = None

    financial_summary: Optional[FinancialSummary] = None


class PurchaseOrderOut(BaseModel):
    id: int
    company_name: str
    purchase_number: str

    purchase_order: PurchaseOrderInfo
    buyer: Party
    supplier: Party
    ship_to: Party

    freight_by: Optional[str] = None
    dispatch_by: Optional[str] = None
    indentor: Optional[str] = None

    financial_summary: FinancialSummary

    created_at: datetime
    updated_at: datetime


# --------------------------
# PO ITEMS (separate ops)
# --------------------------
class ItemCreate(BaseModel):
    """Create a single item under a PO."""
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    purchase_order_id: int
    sr_no: int
    material_type: str
    item_category: str
    sub_category: Optional[str] = None
    item_description: str
    hsn_code: Optional[str] = None
    net_weight_kg: Decimal = Field(..., max_digits=12, decimal_places=3)
    price_per_kg: Decimal = Field(..., max_digits=12, decimal_places=2)
    taxable_value: Decimal = Field(..., max_digits=14, decimal_places=2)
    gst_percentage: Decimal = Field(..., max_digits=5, decimal_places=2)

    @field_validator("gst_percentage")
    @classmethod
    def gst_in_range(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 28:
            raise ValueError("gst_percentage must be between 0 and 28")
        return v

    @field_serializer('net_weight_kg', 'price_per_kg', 'taxable_value', 'gst_percentage', when_used='always')
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)


class ItemUpdate(BaseModel):
    """Partial update (PATCH) of an item."""
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    sr_no: Optional[int] = None
    material_type: Optional[str] = None
    item_category: Optional[str] = None
    sub_category: Optional[str] = None
    item_description: Optional[str] = None
    hsn_code: Optional[str] = None
    net_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    price_per_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=2)
    taxable_value: Optional[Decimal] = Field(None, max_digits=14, decimal_places=2)
    gst_percentage: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)

    @field_validator("gst_percentage")
    @classmethod
    def gst_in_range(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return v
        if v < 0 or v > 28:
            raise ValueError("gst_percentage must be between 0 and 28")
        return v

    @field_serializer('net_weight_kg', 'price_per_kg', 'taxable_value', 'gst_percentage', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class ItemOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    purchase_order_id: int
    sr_no: int
    material_type: str
    item_category: str
    sub_category: Optional[str] = None
    item_description: str
    hsn_code: Optional[str] = None
    net_weight_kg: Decimal = Field(..., max_digits=12, decimal_places=3)
    price_per_kg: Decimal = Field(..., max_digits=12, decimal_places=2)
    taxable_value: Decimal = Field(..., max_digits=14, decimal_places=2)
    gst_percentage: Decimal = Field(..., max_digits=5, decimal_places=2)
    created_at: datetime
    updated_at: datetime

    @field_serializer('net_weight_kg', 'price_per_kg', 'taxable_value', 'gst_percentage', when_used='always')
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)


# --------------------------
# BOXES (separate ops)
# --------------------------
class BoxCreate(BaseModel):
    """Create a single box under an item."""
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    po_item_id: int
    box_no: Optional[str] = None
    qty_units: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    net_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    gross_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    remarks: Optional[str] = None

    @field_serializer('qty_units', 'net_weight_kg', 'gross_weight_kg', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class BoxUpdate(BaseModel):
    """Partial update (PATCH) of a box."""
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    id: Optional[int] = None
    po_item_id: Optional[int] = None
    box_no: Optional[str] = None
    qty_units: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    net_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    gross_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    remarks: Optional[str] = None

    @field_serializer('qty_units', 'net_weight_kg', 'gross_weight_kg', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class BoxOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    po_item_id: int
    box_no: Optional[str] = None
    qty_units: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    net_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    gross_weight_kg: Optional[Decimal] = Field(None, max_digits=12, decimal_places=3)
    remarks: Optional[str] = None
    created_at: datetime

    @field_serializer('qty_units', 'net_weight_kg', 'gross_weight_kg', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


# --------------------------
# Combined response schema
# --------------------------
class CompletePurchaseDataOut(BaseModel):
    """Complete purchase data including order, approval, items, and boxes."""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )
    
    # Purchase Order Information
    purchase_order: PurchaseOrderOut
    
    # Purchase Approval Information (optional - may not exist)
    approval: Optional[dict] = None  # Will contain PurchaseApprovalWithItemsOut data
    
    # Quick access fields
    has_approval: bool = False
    items_count: int = 0
    boxes_count: int = 0
    
    # Summary information with filtering details
    summary: dict = Field(default_factory=dict)


class CompletePurchaseDataSummary(BaseModel):
    """Summary information for complete purchase data response."""
    purchase_number: str
    po_number: str
    po_id: Optional[int] = None
    approval_id: Optional[int] = None
    company_name: Optional[str] = None
    supplier_name: Optional[str] = None
    buyer_name: Optional[str] = None
    grn_number: Optional[str] = None
    total_items: int
    total_boxes: int
    filtered_by_box_id: Optional[int] = None
    is_filtered: bool = False


# --------------------------
# Optional delete request body (if you want one)
# --------------------------
class DeleteRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Optional audit note for deletion")

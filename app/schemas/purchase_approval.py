"""
Schemas for Purchase Approval (Receipt) management.
"""

from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, field_serializer
from decimal import Decimal


# Enums - All are optional (nullable)
DestinationLocation = Optional[Literal["W202", "A185", "A68", "A101", "F53", "SAVLA", "RISHI"]]
MaterialType = Optional[str]  # Allow any string value including empty
UOM = Optional[Literal["BOX", "BAG"]]


# --------------------------
# Nested Value Objects
# --------------------------

class TransporterInformation(BaseModel):
    """Transporter information - all fields are optional."""
    vehicle_number: Optional[str] = Field(default=None, description="Vehicle number (optional)")
    transporter_name: Optional[str] = Field(default=None, description="Transporter name (optional)")
    lr_number: Optional[str] = Field(default=None, description="LR number (optional)")
    destination_location: Optional[DestinationLocation] = Field(default=None, description="Destination location (optional)")


class CustomerInformation(BaseModel):
    customer_name: Optional[str] = None
    authority: Optional[str] = None
    challan_number: Optional[str] = None
    invoice_number: Optional[str] = None
    grn_number: Optional[str] = None
    grn_quantity: Optional[str] = None
    delivery_note_number: Optional[str] = None
    service_po_number: Optional[str] = None


class BoxSchema(BaseModel):
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    box_id: Optional[int] = None  # Added box_id for frontend reference
    box_number: Optional[str] = None
    article_name: Optional[str] = None
    lot_number: Optional[str] = None
    net_weight: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None

    @field_serializer('net_weight', 'gross_weight', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class ItemSchema(BaseModel):
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    material_type: Optional[str] = None  # Allow any string value including empty
    item_category: Optional[str] = None
    sub_category: Optional[str] = None
    item_description: Optional[str] = None  # Allow any string value including empty
    quantity_units: Optional[Decimal] = None
    pack_size: Optional[Decimal] = None
    uom: Optional[str] = None  # Allow any string value including empty
    net_weight: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    lot_number: Optional[str] = None
    mfg_date: Optional[date] = None
    exp_date: Optional[date] = None
    # Article/Item Financial Information (optional - not displayed in approval form)
    hsn_code: Optional[int] = None
    price_per_kg: Optional[Decimal] = None
    taxable_value: Optional[Decimal] = None
    gst_percentage: Optional[Decimal] = None
    boxes: List[BoxSchema] = []

    @field_serializer('quantity_units', 'pack_size', 'net_weight', 'gross_weight', 'price_per_kg', 'taxable_value', 'gst_percentage', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


# --------------------------
# Create Request Schema
# --------------------------

class PurchaseApprovalCreate(BaseModel):
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )

    purchase_order_id: str
    transporter_information: TransporterInformation
    customer_information: CustomerInformation
    items: List[ItemSchema]


# --------------------------
# Update Request Schema
# --------------------------

class PurchaseApprovalUpdate(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # Allow both camelCase and snake_case
        json_encoders={Decimal: str}
    )
    
    purchase_order_id: Optional[str] = Field(None, alias="purchaseOrderId")
    transporter_information: Optional[TransporterInformation] = Field(None, alias="transporterInformation")
    customer_information: Optional[CustomerInformation] = Field(None, alias="customerInformation")
    items: Optional[List[ItemSchema]] = None


# --------------------------
# Response Schema
# --------------------------

class PurchaseApprovalOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    purchase_order_id: str
    transporter_information: TransporterInformation
    customer_information: CustomerInformation
    created_at: datetime
    updated_at: datetime


class PurchaseApprovalItemOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    approval_id: int
    material_type: str
    item_category: Optional[str] = None
    sub_category: Optional[str] = None
    item_description: str
    quantity_units: Optional[Decimal] = None
    pack_size: Optional[Decimal] = None
    uom: Optional[str] = None
    net_weight: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    lot_number: Optional[str] = None
    mfg_date: Optional[date] = None
    exp_date: Optional[date] = None
    # Article/Item Financial Information (optional - not displayed in approval form)
    hsn_code: Optional[int] = None
    price_per_kg: Optional[Decimal] = None
    taxable_value: Optional[Decimal] = None
    gst_percentage: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('quantity_units', 'pack_size', 'net_weight', 'gross_weight', 'price_per_kg', 'taxable_value', 'gst_percentage', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class PurchaseApprovalBoxOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    item_id: int
    box_number: Optional[str] = None
    article_name: Optional[str] = None
    lot_number: Optional[str] = None
    net_weight: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    created_at: datetime

    @field_serializer('net_weight', 'gross_weight', when_used='always')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class PurchaseApprovalWithItemsOut(BaseModel):
    """Complete approval with nested items and boxes."""
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

    id: int
    purchase_order_id: str
    transporter_information: TransporterInformation
    customer_information: CustomerInformation
    items: List[ItemSchema]
    created_at: datetime
    updated_at: datetime


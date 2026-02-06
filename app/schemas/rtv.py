"""
RTV (Return to Vendor) Schemas
Request and Response models for RTV operations
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal


# RTV Type Enum
class RTVType(str):
    QUALITY_ISSUE = "quality_issue"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    EXCESS_QUANTITY = "excess_quantity"
    WRONG_ITEM = "wrong_item"
    OTHER = "other"


# RTV Status Enum
class RTVStatus(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


# RTV Item Schema
class RTVItemCreate(BaseModel):
    transaction_no: str = Field(..., description="CONS or TR number from QR code")
    box_number: int = Field(..., description="Box number from QR code")
    sub_category: Optional[str] = Field(None, description="Sub category of the item")
    item_description: str = Field(..., description="Item description/name")
    net_weight: Decimal = Field(..., description="Net weight in grams")
    gross_weight: Decimal = Field(..., description="Gross weight in grams")
    price: Decimal = Field(..., description="Price/value of the item")
    reason: Optional[str] = Field(None, description="Reason for returning this specific item")
    qr_data: Optional[Dict[str, Any]] = Field(None, description="Complete QR code data")
    
    @validator('net_weight', 'gross_weight', 'price', pre=True)
    def convert_to_decimal(cls, v):
        if isinstance(v, str):
            return Decimal(v)
        return v


class RTVItemResponse(BaseModel):
    item_id: int
    rtv_number: str
    transaction_no: str
    box_number: int
    sub_category: Optional[str]
    item_description: str
    net_weight: Decimal
    gross_weight: Decimal
    price: Decimal
    reason: Optional[str]
    qr_data: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


# RTV Create Schema
class RTVCreate(BaseModel):
    customer_code: str = Field(..., description="Customer code from company-specific list")
    customer_name: str = Field(..., description="Customer name")
    rtv_type: str = Field(..., description="Reason for RTV")
    other_reason: Optional[str] = Field(None, description="Custom reason when rtv_type is 'other'")
    rtv_date: str = Field(..., description="RTV creation date (YYYY-MM-DD)")
    invoice_number: Optional[str] = Field(None, description="Invoice number for the return")
    dc_number: Optional[str] = Field(None, description="Delivery challan number")
    notes: Optional[str] = Field(None, description="Additional remarks/notes")
    created_by: str = Field(..., description="User who created the RTV")
    items: List[RTVItemCreate] = Field(..., min_items=1, description="Array of scanned boxes/items")
    
    @validator('rtv_type')
    def validate_rtv_type(cls, v):
        valid_types = ["quality_issue", "damaged", "expired", "excess_quantity", "wrong_item", "other"]
        if v not in valid_types:
            raise ValueError(f"rtv_type must be one of: {valid_types}")
        return v
    
    @validator('rtv_date')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("rtv_date must be in YYYY-MM-DD format")
        return v


# RTV Response Schema
class RTVResponse(BaseModel):
    rtv_number: str
    customer_code: str
    customer_name: str
    rtv_type: str
    other_reason: Optional[str]
    rtv_date: str
    invoice_number: Optional[str]
    dc_number: Optional[str]
    notes: Optional[str]
    created_by: str
    total_value: Decimal
    total_boxes: int
    status: str
    company_code: str
    created_at: datetime
    updated_at: datetime
    items: List[RTVItemResponse]
    
    class Config:
        from_attributes = True


# RTV List Response Schema
class RTVListItem(BaseModel):
    rtv_number: str
    customer_code: str
    customer_name: str
    rtv_type: str
    rtv_date: str
    invoice_number: Optional[str]
    dc_number: Optional[str]
    total_value: Decimal
    total_boxes: int
    status: str
    company_code: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RTVListResponse(BaseModel):
    success: bool
    data: List[RTVListItem]
    total: int
    page: int
    limit: int


# RTV Status Update Schema
class RTVStatusUpdate(BaseModel):
    status: str = Field(..., description="New status")
    remarks: Optional[str] = Field(None, description="Remarks for status change")
    
    @validator('status')
    def validate_status(cls, v):
        valid_statuses = ["pending", "approved", "rejected", "completed"]
        if v not in valid_statuses:
            raise ValueError(f"status must be one of: {valid_statuses}")
        return v


# RTV Box Validation Schema
class RTVBoxValidation(BaseModel):
    transaction_no: str = Field(..., description="Transaction number to validate")


class RTVBoxValidationResponse(BaseModel):
    valid: bool
    message: str
    existing_rtv: Optional[str] = None


# RTV Create Response Schema
class RTVCreateResponse(BaseModel):
    success: bool
    rtv_number: str
    message: str


# Customer Schema
class CustomerItem(BaseModel):
    value: str
    label: str


class CustomerListResponse(BaseModel):
    success: bool
    data: List[CustomerItem]


# RTV Delete Response Schema
class RTVDeleteResponse(BaseModel):
    success: bool
    message: str
    rtv_number: str

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, time
from decimal import Decimal

# ============================================
# ARTICLE SCHEMAS
# ============================================

class ArticleBase(BaseModel):
    """Base article schema"""
    material_type: str = Field(..., description="Material type: RM, PM, FG")
    item_category: str = Field(..., description="Item category")
    sub_category: str = Field(..., description="Sub category")
    item_description: str = Field(..., description="Item description")
    sku_id: Optional[str] = Field(None, description="SKU ID")
    quantity_units: float = Field(..., ge=0, description="Quantity in units")
    uom: str = Field(..., description="Unit of measure: KG, PCS, BOX, CARTON")
    pack_size_gm: float = Field(0, ge=0, description="Pack size in grams")
    no_of_packets: int = Field(0, ge=0, description="Number of packets")
    net_weight_gm: float = Field(..., ge=0, description="Net weight in grams (calculated in frontend)")
    gross_weight_gm: float = Field(..., ge=0, description="Gross weight in grams")
    batch_number: str = Field(..., description="Batch number (generated in frontend)")
    unit_rate: float = Field(0, ge=0, description="Unit rate")

class ArticleCreate(ArticleBase):
    """Article creation schema"""
    pass

class ArticleUpdate(ArticleBase):
    """Article update schema"""
    pass

class ArticleResponse(ArticleBase):
    """Article response schema"""
    id: int
    outward_id: int
    company_name: str
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True

# ============================================
# BOX SCHEMAS
# ============================================

class BoxBase(BaseModel):
    """Base box schema"""
    box_number: int = Field(..., description="Box number")
    article_name: Optional[str] = Field(None, description="Article name")
    lot_number: Optional[str] = Field(None, description="Lot number")
    net_weight_gm: float = Field(0, ge=0, description="Net weight in grams (auto-calculated)")
    gross_weight_gm: float = Field(0, ge=0, description="Gross weight in grams")

class BoxCreate(BoxBase):
    """Box creation schema"""
    pass

class BoxUpdate(BaseModel):
    """Box update schema"""
    lot_number: Optional[str] = None
    gross_weight_gm: Optional[float] = Field(None, ge=0)

class BoxResponse(BoxBase):
    """Box response schema"""
    id: int
    article_id: int
    outward_id: int
    company_name: str
    qr_code_generated: bool
    qr_code_data: Optional[str]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True

# ============================================
# APPROVAL SCHEMAS
# ============================================

class ApprovalBase(BaseModel):
    """Base approval schema"""
    approval_status: str = Field("PENDING", description="Approval status: APPROVE, REJECT, PENDING")
    approval_authority: Optional[str] = Field(None, description="Approval authority")
    approval_date: Optional[date] = Field(None, description="Approval date")
    remarks: Optional[str] = Field(None, description="Remarks")

class ApprovalCreate(ApprovalBase):
    """Approval creation schema"""
    pass

class ApprovalUpdate(ApprovalBase):
    """Approval update schema"""
    pass

class ArticleForApproval(BaseModel):
    """Article schema for approval submission (includes frontend ID)"""
    id: Optional[str] = None  # Frontend-generated ID for mapping
    material_type: str
    item_category: str
    sub_category: str
    item_description: str
    sku_id: Optional[int] = None  # Can be integer or string
    quantity_units: float
    uom: str
    pack_size_gm: float
    no_of_packets: int
    net_weight_gm: float
    gross_weight_gm: float
    batch_number: str
    unit_rate: float

class BoxForApproval(BaseModel):
    """Box schema for approval submission"""
    box_number: int
    article_name: str
    lot_number: Optional[str] = None
    net_weight_gm: float
    gross_weight_gm: float

class ApprovalWithArticlesBoxes(BaseModel):
    """Approval request with articles and boxes"""
    consignment_id: int
    approval_authority: str
    approval_date: date
    approval_status: str = "approved"
    approval_remark: Optional[str] = None
    articles: List[ArticleForApproval]
    boxes: List[BoxForApproval]

class ApprovalResponse(ApprovalBase):
    """Approval response schema"""
    id: int
    outward_id: int
    company_name: str
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True

# ============================================
# OUTWARD SCHEMAS
# ============================================

class OutwardRecord(BaseModel):
    """Outward record schema"""
    consignment_no: str = Field(..., description="Consignment number (uppercase)")
    invoice_no: str = Field(..., description="Invoice number (uppercase)")
    customer_name: str = Field(..., description="Customer name (uppercase)")
    delivery_status: str = Field("PENDING", description="Delivery status")
    location: Optional[str] = Field(None, description="Location (uppercase)")
    po_no: Optional[str] = Field(None, description="Purchase order number (uppercase)")
    boxes: int = Field(0, ge=0, description="Total boxes (auto-calculated)")
    net_weight: Optional[str] = Field(None, description="Net weight (auto-calculated)")
    gross_weight: Optional[str] = Field(None, description="Gross weight (auto-calculated)")
    
    # Business Head Information
    business_head: Optional[str] = Field(None, description="Business head")
    business_head_name: Optional[str] = Field(None, description="Business head name (when Other)")
    business_head_email: Optional[str] = Field(None, description="Business head email")
    
    # Appointment & Site Details
    appt_date: Optional[date] = Field(None, description="Appointment date")
    appt_time: Optional[time] = Field(None, description="Appointment time")
    sitecode: Optional[str] = Field(None, description="Site code (uppercase)")
    asn_id: int = Field(0, ge=0, description="ASN ID")
    
    # Transport Details
    transporter_name: Optional[str] = Field(None, description="Transporter name (uppercase)")
    vehicle_no: Optional[str] = Field(None, description="Vehicle number (uppercase)")
    lr_no: Optional[str] = Field(None, description="LR number")
    
    # Delivery Information
    dispatch_date: Optional[date] = Field(None, description="Dispatch date")
    estimated_delivery_date: Optional[date] = Field(None, description="Estimated delivery date")
    actual_delivery_date: Optional[date] = Field(None, description="Actual delivery date")
    
    # Financial Details
    invoice_amount: float = Field(0, ge=0, description="Invoice amount")
    invoice_gst_amount: float = Field(0, ge=0, description="Invoice GST amount")
    total_invoice_amount: float = Field(0, ge=0, description="Total invoice amount (auto-calculated)")
    freight_amount: float = Field(0, ge=0, description="Freight amount")
    freight_gst_amount: float = Field(0, ge=0, description="Freight GST amount")
    total_freight_amount: float = Field(0, ge=0, description="Total freight amount (auto-calculated)")
    
    # Address Details
    billing_address: Optional[str] = Field(None, description="Billing address (uppercase)")
    shipping_address: Optional[str] = Field(None, description="Shipping address (uppercase)")
    pincode: Optional[int] = Field(None, ge=0, description="Pincode")
    
    # File paths
    invoice_files: Optional[List[str]] = Field(None, description="Invoice file paths")
    pod_files: Optional[List[str]] = Field(None, description="POD file paths")
    
    @validator('lr_no', pre=True)
    def coerce_lr_no_to_str(cls, v):
        """Coerce lr_no to string if it's an integer"""
        if v is not None and not isinstance(v, str):
            return str(v)
        return v

    @validator('business_head_email')
    def set_business_head_email(cls, v, values):
        """Auto-set email based on business head selection"""
        if v:
            return v.upper()

        business_head = values.get('business_head')
        if business_head:
            email_mapping = {
                'Rakesh Ratra': 'rakesh@candorfoods.in',
                'Prashant Pal': 'prashant.pal@candorfoods.in',
                'Yash Gawdi': 'yash@candorfoods.in',
                'Ajay Bajaj': 'ajay@candorfoods.in'
            }
            return email_mapping.get(business_head)
        return v

class OutwardCreateRequest(BaseModel):
    """Request to create outward record from consignment form"""
    company_name: Optional[str] = None
    consignment_no: str
    invoice_no: str
    customer_name: str
    location: Optional[str] = None
    po_no: Optional[str] = None
    boxes: int = 0
    gross_weight: Optional[str] = None
    net_weight: Optional[str] = None
    appt_date: Optional[date] = None
    appt_time: Optional[time] = None
    sitecode: Optional[str] = None
    asn_id: int = 0
    transporter_name: Optional[str] = None
    vehicle_no: Optional[str] = None
    lr_no: Optional[str] = None
    dispatch_date: Optional[date] = None
    estimated_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    delivery_status: str = "PENDING"
    invoice_amount: float = 0
    invoice_gst_amount: float = 0
    total_invoice_amount: float = 0
    freight_amount: float = 0
    freight_gst_amount: float = 0
    total_freight_amount: float = 0
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    pincode: Optional[int] = None
    business_head: Optional[str] = None
    business_head_name: Optional[str] = None
    business_head_email: Optional[str] = None
    invoice_files: Optional[List[str]] = None
    pod_files: Optional[List[str]] = None

class OutwardUpdateRequest(BaseModel):
    """Request to update outward record"""
    outward_data: OutwardRecord

class OutwardResponse(BaseModel):
    """Response for outward record"""
    id: int
    company_name: str
    consignment_no: str
    invoice_no: str
    customer_name: str
    delivery_status: str
    location: Optional[str]
    po_no: Optional[str]
    boxes: int
    net_weight: Optional[str]
    gross_weight: Optional[str]

    # Business Head
    business_head: Optional[str]
    business_head_name: Optional[str]
    business_head_email: Optional[str]

    # Appointment & Site
    appt_date: Optional[date]
    appt_time: Optional[time]
    sitecode: Optional[str]
    asn_id: int

    # Transport
    transporter_name: Optional[str]
    vehicle_no: Optional[str]
    lr_no: Optional[str]

    # Delivery
    dispatch_date: Optional[date]
    estimated_delivery_date: Optional[date]
    actual_delivery_date: Optional[date]

    # Financial
    invoice_amount: float
    invoice_gst_amount: float
    total_invoice_amount: float
    freight_amount: float
    freight_gst_amount: float
    total_freight_amount: float

    # Address
    billing_address: Optional[str]
    shipping_address: Optional[str]
    pincode: Optional[int]

    # Files
    invoice_files: Optional[List[str]]
    pod_files: Optional[List[str]]

    # Timestamps
    created_at: str
    updated_at: str

    @validator('lr_no', pre=True)
    def coerce_lr_no_to_str(cls, v):
        """Coerce lr_no to string if it's an integer"""
        if v is not None and not isinstance(v, str):
            return str(v)
        return v

    class Config:
        from_attributes = True

class OutwardWithDetails(OutwardResponse):
    """Outward response with articles, boxes, and approval"""
    articles: List[ArticleResponse] = []
    box_details: List[BoxResponse] = []  # Renamed from 'boxes' to avoid conflict with OutwardResponse.boxes (int)
    approval: Optional[ApprovalResponse] = None

class OutwardListResponse(BaseModel):
    """Response for outward records list"""
    records: List[OutwardResponse]
    total: int
    page: int
    per_page: int
    total_pages: int

class OutwardDeleteResponse(BaseModel):
    """Response for outward record deletion"""
    id: int
    consignment_no: str
    status: str
    message: str
    deleted_at: str

# ============================================
# DROPDOWN SCHEMAS
# ============================================

class SitecodeResponse(BaseModel):
    """Sitecode dropdown response"""
    id: int
    sitecode: str
    is_active: bool
    
    class Config:
        from_attributes = True

class TransporterResponse(BaseModel):
    """Transporter dropdown response"""
    id: int
    transporter_name: str
    contact_no: Optional[str]
    email: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

class SitecodeCreate(BaseModel):
    """Create sitecode"""
    sitecode: str

class TransporterCreate(BaseModel):
    """Create transporter"""
    transporter_name: str
    contact_no: Optional[str] = None
    email: Optional[str] = None

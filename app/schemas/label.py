from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class LabelFormat(str, Enum):
    """Supported label formats"""
    BMP = "bmp"
    PNG = "png"
    JPEG = "jpeg"
    JPG = "jpg"

class LabelStatus(str, Enum):
    """Label processing status"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class BoxManagementPayload(BaseModel):
    """Payload structure for box management reference"""
    company: str
    transaction_no: str
    box_number: int
    article_description: str
    sku_id: int
    net_weight: float
    gross_weight: float
    batch_number: str
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    vendor_name: Optional[str] = None
    customer_name: Optional[str] = None
    entry_date: str
    quality_grade: Optional[str] = None
    uom: Optional[str] = None
    packaging_type: Optional[str] = None
    lot_number: Optional[str] = None
    currency: Optional[str] = None
    unit_rate: Optional[float] = None
    total_amount: Optional[float] = None

    @field_validator('entry_date', 'manufacturing_date', 'expiry_date', mode='before')
    @classmethod
    def validate_dates(cls, v):
        """Convert date objects to strings"""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, str):
            return v
        return str(v)

class LabelUploadRequest(BaseModel):
    """Request model for label upload"""
    company: str
    transaction_no: str
    box_number: int
    label_format: LabelFormat
    description: Optional[str] = None

class LabelUploadResponse(BaseModel):
    """Response model for label upload"""
    label_id: str
    status: LabelStatus
    message: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
    box_management_payload: BoxManagementPayload

class LabelInfo(BaseModel):
    """Label information model"""
    label_id: str
    company: str
    transaction_no: str
    box_number: int
    file_name: str
    file_path: str
    file_size: int
    label_format: LabelFormat
    status: LabelStatus
    description: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    box_management_payload: BoxManagementPayload

class LabelListResponse(BaseModel):
    """Response model for label listing"""
    labels: List[LabelInfo]
    total: int
    page: int
    per_page: int
    total_pages: int

class LabelDeleteResponse(BaseModel):
    """Response model for label deletion"""
    label_id: str
    status: str
    message: str
    deleted_at: datetime

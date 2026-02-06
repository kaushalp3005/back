# File: alerts_recipients_schemas.py
# Path: backend/app/schemas/alerts_recipients.py

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, validator


# ============================================
# BASE SCHEMAS
# ============================================

class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class PaginatedResponse(BaseModel):
    success: bool
    message: str
    data: List[Dict[str, Any]]
    total: int
    page: int
    per_page: int
    pages: int


# ============================================
# ALERT RECIPIENTS SCHEMAS
# ============================================

class AlertRecipientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    phone_number: Optional[str] = Field(None, max_length=20)
    module: str = Field(..., min_length=1, max_length=100)
    company_code: str = Field("CFPL", max_length=10)

    @validator('module')
    def validate_module(cls, v):
        allowed_modules = ['CONSUMPTION', 'TRANSFER', 'OUTWARD', 'INWARD', 'APPROVAL', 'LABEL', 'SKU']
        if v.upper() not in allowed_modules:
            raise ValueError(f'Module must be one of: {", ".join(allowed_modules)}')
        return v.upper()


class AlertRecipientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    phone_number: Optional[str] = Field(None, max_length=20)
    module: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    company_code: Optional[str] = Field(None, max_length=10)

    @validator('module')
    def validate_module(cls, v):
        if v is not None:
            allowed_modules = ['CONSUMPTION', 'TRANSFER', 'OUTWARD', 'INWARD', 'APPROVAL', 'LABEL', 'SKU']
            if v.upper() not in allowed_modules:
                raise ValueError(f'Module must be one of: {", ".join(allowed_modules)}')
            return v.upper()
        return v


class AlertRecipientResponse(BaseModel):
    id: int
    name: str
    email: str
    phone_number: Optional[str]
    module: str
    is_active: bool
    company_code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================
# FILTER SCHEMAS
# ============================================

class AlertRecipientFilter(BaseModel):
    module: Optional[str] = None
    company_code: Optional[str] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None  # Search in name or email


# ============================================
# BULK OPERATION SCHEMAS
# ============================================

class BulkRecipientCreate(BaseModel):
    recipients: List[AlertRecipientCreate]


class BulkRecipientUpdate(BaseModel):
    recipient_ids: List[int]
    update_data: AlertRecipientUpdate


class BulkRecipientDelete(BaseModel):
    recipient_ids: List[int]


# ============================================
# EMAIL SENDING SCHEMAS (for frontend use)
# ============================================

class EmailSendRequest(BaseModel):
    recipients: List[str] = Field(..., description="List of email addresses")
    subject: str = Field(..., min_length=1, max_length=500)
    message: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1, max_length=100)
    source_id: Optional[str] = Field(None, max_length=255)


class EmailSendResponse(BaseModel):
    success: bool
    message: str
    recipients_sent: int
    recipients_failed: int
    failed_recipients: List[str]


# ============================================
# STATISTICS SCHEMAS
# ============================================

class RecipientsStats(BaseModel):
    total_recipients: int
    active_recipients: int
    inactive_recipients: int
    recipients_by_module: Dict[str, int]
    recipients_by_company: Dict[str, int]

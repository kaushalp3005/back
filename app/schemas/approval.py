from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class ApprovalRecord(BaseModel):
    """Approval record schema"""
    consignment_no: str = Field(..., description="Consignment number (links to outward)")
    approval_authority: str = Field(..., description="Approval authority name")
    approval_date: date = Field(..., description="Approval date")
    quantity: int = Field(..., description="Approved quantity")
    uom: str = Field(..., description="Unit of measure")
    gross_weight: float = Field(..., description="Gross weight")
    net_weight: float = Field(..., description="Net weight")
    approval_status: bool = Field(..., description="Approval status (true=approved, false=rejected)")
    remark: str = Field(..., description="Approval remarks")

class ApprovalCreateRequest(BaseModel):
    """Request to create approval record"""
    approval_data: ApprovalRecord

class ApprovalUpdateRequest(BaseModel):
    """Request to update approval record"""
    approval_data: ApprovalRecord

class ApprovalResponse(BaseModel):
    """Response for approval record"""
    id: int
    consignment_no: str
    approval_authority: str
    approval_date: date
    quantity: int
    uom: str
    gross_weight: float
    net_weight: float
    approval_status: bool
    remark: str
    created_at: str
    updated_at: str

class ApprovalListResponse(BaseModel):
    """Response for approval records list"""
    records: list[ApprovalResponse]
    total: int
    page: int
    per_page: int
    total_pages: int

class ApprovalDeleteResponse(BaseModel):
    """Response for approval record deletion"""
    id: int
    consignment_no: str
    approval_authority: str
    status: str
    message: str
    deleted_at: str

class ApprovalWithOutwardResponse(BaseModel):
    """Response combining approval and outward data"""
    approval: ApprovalResponse
    outward: dict  # Outward record data

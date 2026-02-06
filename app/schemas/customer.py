from pydantic import BaseModel, Field
from typing import Optional, List

class CustomerDropdownQuery(BaseModel):
    """Query parameters for customer dropdown"""
    search: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class CustomerOption(BaseModel):
    """Single customer option"""
    id: int
    customer_name: str

class CustomerDropdownResponse(BaseModel):
    """Response for customer dropdown"""
    customers: List[CustomerOption]
    meta: dict

class CustomerMeta(BaseModel):
    """Metadata for customer dropdown"""
    total_customers: int
    limit: int
    offset: int
    search: Optional[str] = None


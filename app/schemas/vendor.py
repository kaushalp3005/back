from pydantic import BaseModel, Field
from typing import Optional, List

class VendorDropdownQuery(BaseModel):
    """Query parameters for vendor dropdown"""
    vendor_name: Optional[str] = None
    location: Optional[str] = None
    search: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class SelectedVendorState(BaseModel):
    """Currently selected vendor state"""
    vendor_name: Optional[str] = None
    location: Optional[str] = None

class ResolvedFromVendor(BaseModel):
    """Auto-resolved location from vendor_name selection"""
    location: Optional[str] = None

class ResolvedFromLocation(BaseModel):
    """Vendors available for selected location"""
    vendor_names: List[str] = []

class VendorAutoSelection(BaseModel):
    """Auto-selection results"""
    resolved_from_vendor: ResolvedFromVendor
    resolved_from_location: ResolvedFromLocation

class VendorOptions(BaseModel):
    """Available options for dropdowns"""
    vendor_names: List[str]
    locations: List[str]
    vendor_ids: List[int]

class VendorMeta(BaseModel):
    """Metadata for vendor dropdown"""
    total_vendors: int
    total_locations: int
    limit: int
    offset: int
    search: Optional[str] = None

class VendorDropdownResponse(BaseModel):
    """Complete response for vendor dropdown"""
    selected: SelectedVendorState
    auto_selection: VendorAutoSelection
    options: VendorOptions
    meta: VendorMeta


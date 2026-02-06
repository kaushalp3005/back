"""
Pydantic schemas for Item Catalog API.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class ItemCatalogBase(BaseModel):
    """Base schema for item catalog."""
    MATERIAL_TYPE: Optional[str] = None
    ITEM_CATEGORY: Optional[str] = None
    SUB_CATEGORY: Optional[str] = None
    ITEM_DESCRIPTION: Optional[str] = None


class ItemDetailsResponse(BaseModel):
    """Response schema for complete item details."""
    MATERIAL_TYPE: str
    ITEM_CATEGORY: str
    SUB_CATEGORY: Optional[str] = None
    ITEM_DESCRIPTION: str

    class Config:
        from_attributes = True


class DropdownValuesResponse(BaseModel):
    """Response schema for dropdown values."""
    values: List[str] = Field(
        default_factory=list,
        description="List of unique values for the dropdown"
    )
    count: int = Field(
        description="Total count of unique values"
    )


class CascadingDropdownRequest(BaseModel):
    """Request schema for cascading dropdown endpoint."""
    MATERIAL_TYPE: Optional[str] = Field(
        None,
        description="Filter by material type"
    )
    ITEM_CATEGORY: Optional[str] = Field(
        None,
        description="Filter by item category"
    )
    SUB_CATEGORY: Optional[str] = Field(
        None,
        description="Filter by sub category"
    )
    field: str = Field(
        ...,
        description="Field to get values for: MATERIAL_TYPE, ITEM_CATEGORY, SUB_CATEGORY, or ITEM_DESCRIPTION"
    )

    @field_validator('field')
    @classmethod
    def validate_field(cls, v: str) -> str:
        """Validate that field is one of the allowed values."""
        allowed_fields = ['MATERIAL_TYPE', 'ITEM_CATEGORY', 'SUB_CATEGORY', 'ITEM_DESCRIPTION']
        if v not in allowed_fields:
            raise ValueError(f"field must be one of {allowed_fields}")
        return v


class AutoFillRequest(BaseModel):
    """Request schema for auto-fill endpoint."""
    ITEM_DESCRIPTION: str = Field(
        ...,
        description="Item description to search for",
        min_length=1
    )


class GlobalSearchRequest(BaseModel):
    """Request schema for global search endpoint."""
    search_term: str = Field(
        ...,
        description="Search term to find in ITEM_DESCRIPTION",
        min_length=1
    )
    limit: Optional[int] = Field(
        default=None,
        description="Optional maximum number of results to return (no limit if not specified)",
        ge=1
    )


class GlobalSearchResponse(BaseModel):
    """Response schema for global search."""
    results: List[ItemDetailsResponse]
    count: int
    search_term: str

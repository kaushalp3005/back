"""
Pydantic schemas for PDF extraction operations.
"""

from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field


class ItemExtraction(BaseModel):
    """Schema for individual item extracted from PDF."""
    ITEM_DESCRIPTION: str = Field(
        ...,
        description="Description of the item"
    )
    HSN_CODE: Optional[int] = Field(
        None,
        description="HSN code as big integer"
    )
    QUANTITY: Optional[float] = Field(
        None,
        description="Quantity of the item"
    )
    PRICE_PER_KG: Optional[float] = Field(
        None,
        description="Price per kilogram"
    )
    TAXABLE_VALUE: Optional[float] = Field(
        None,
        description="Taxable value of the item"
    )
    GST_PERCENTAGE: Optional[float] = Field(
        None,
        description="GST percentage applicable"
    )


class PDFExtractionResponse(BaseModel):
    """Response schema for PDF extraction."""
    PO_NUMBER: Optional[str] = Field(
        None,
        description="Purchase Order number"
    )
    PO_DATE: Optional[date] = Field(
        None,
        description="Purchase Order date in ISO format"
    )
    PO_VALIDITY: Optional[date] = Field(
        None,
        description="Purchase Order validity date in ISO format"
    )
    BUYER_NAME: Optional[str] = Field(
        None,
        description="Name of the buyer"
    )
    BUYER_ADDRESS: Optional[str] = Field(
        None,
        description="Address of the buyer"
    )
    BUYER_GSTIN: Optional[str] = Field(
        None,
        description="GSTIN of the buyer"
    )
    BUYER_STATE: Optional[str] = Field(
        None,
        description="State of the buyer"
    )
    SUPPLIER_NAME: Optional[str] = Field(
        None,
        description="Name of the supplier"
    )
    SUPPLIER_ADDRESS: Optional[str] = Field(
        None,
        description="Address of the supplier"
    )
    SUPPLIER_GSTIN: Optional[str] = Field(
        None,
        description="GSTIN of the supplier"
    )
    SUPPLIER_STATE: Optional[str] = Field(
        None,
        description="State of the supplier"
    )
    SHIP_TO_NAME: Optional[str] = Field(
        None,
        description="Ship to name"
    )
    SHIP_TO_ADDRESS: Optional[str] = Field(
        None,
        description="Ship to address"
    )
    SHIP_TO_STATE: Optional[str] = Field(
        None,
        description="Ship to state"
    )
    FREIGHT_BY: Optional[str] = Field(
        None,
        description="Freight handled by"
    )
    DISPATCH_BY: Optional[str] = Field(
        None,
        description="Dispatch handled by"
    )
    INDENTOR: Optional[str] = Field(
        None,
        description="Indentor information"
    )
    ITEMS: List[ItemExtraction] = Field(
        default_factory=list,
        description="List of items from the purchase order"
    )

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class PDFExtractionErrorResponse(BaseModel):
    """Error response schema for PDF extraction."""
    error: str = Field(
        ...,
        description="Error message"
    )
    details: Optional[str] = Field(
        None,
        description="Additional error details"
    )
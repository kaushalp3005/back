"""
Database models for Purchase Order management.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Date, Numeric, DateTime, Text, 
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base, engine


class PurchaseOrder(Base):
    """Purchase Order Header model."""
    __tablename__ = "purchase_orders"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    company_name = Column(Text, nullable=False)
    purchase_number = Column(Text, nullable=False)
    po_number = Column(Text, nullable=False)
    po_date = Column(Date, nullable=False)
    po_validity = Column(Date, nullable=True)
    currency = Column(Text, nullable=False, default="INR")
    
    # Buyer
    buyer_name = Column(Text, nullable=False)
    buyer_address = Column(Text, nullable=True)
    buyer_gstin = Column(Text, nullable=True)
    buyer_state = Column(Text, nullable=True)
    
    # Supplier
    supplier_name = Column(Text, nullable=False)
    supplier_address = Column(Text, nullable=True)
    supplier_gstin = Column(Text, nullable=True)
    supplier_state = Column(Text, nullable=True)
    
    # Ship-to
    ship_to_name = Column(Text, nullable=False)
    ship_to_address = Column(Text, nullable=True)
    ship_to_state = Column(Text, nullable=True)
    
    # Additional info
    freight_by = Column(Text, nullable=True)
    dispatch_by = Column(Text, nullable=True)
    indentor = Column(Text, nullable=True)
    
    # Financial summary
    sub_total = Column(Numeric(14, 2), nullable=False)
    igst = Column(Numeric(14, 2), nullable=False, default=0)
    other_charges_non_gst = Column(Numeric(14, 2), nullable=False, default=0)
    grand_total = Column(Numeric(14, 2), nullable=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    items = relationship("POItem", back_populates="purchase_order", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_po_company_date", "company_name", "po_date"),
    )


class POItem(Base):
    """Purchase Order Item model."""
    __tablename__ = "po_items"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    purchase_order_id = Column(BIGINT, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    sr_no = Column(Integer, nullable=False)
    material_type = Column(Text, nullable=False)
    item_category = Column(Text, nullable=False)
    sub_category = Column(Text, nullable=True)
    item_description = Column(Text, nullable=False)
    hsn_code = Column(Text, nullable=True)
    net_weight_kg = Column(Numeric(12, 3), nullable=False)
    price_per_kg = Column(Numeric(12, 2), nullable=False)
    taxable_value = Column(Numeric(14, 2), nullable=False)
    gst_percentage = Column(Numeric(5, 2), nullable=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="items")
    boxes = relationship("POItemBox", back_populates="po_item", cascade="all, delete-orphan")
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "sr_no", name="uq_po_item_sr_no"),
        Index("idx_items_po", "purchase_order_id"),
    )


class POItemBox(Base):
    """Box management model."""
    __tablename__ = "po_item_boxes"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    po_item_id = Column(BIGINT, ForeignKey("po_items.id", ondelete="CASCADE"), nullable=False)
    box_no = Column(Text, nullable=True)
    qty_units = Column(Numeric(12, 3), nullable=True)
    net_weight_kg = Column(Numeric(12, 3), nullable=True)
    gross_weight_kg = Column(Numeric(12, 3), nullable=True)
    remarks = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    po_item = relationship("POItem", back_populates="boxes")
    
    # Indexes
    __table_args__ = (
        Index("idx_boxes_item", "po_item_id"),
    )


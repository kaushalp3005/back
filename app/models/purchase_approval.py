"""
Database models for Purchase Approval (Receipt) management.
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Date, Numeric, DateTime, Text, 
    ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class DestinationLocation(enum.Enum):
    """Destination location enum."""
    W202 = "W202"
    A185 = "A185"
    A68 = "A68"
    A101 = "A101"
    F53 = "F53"
    SAVLA = "SAVLA"
    RISHI = "RISHI"


class MaterialType(enum.Enum):
    """Material type enum."""
    RAW_MATERIAL = "Raw Material"
    PACKAGING = "Packaging"
    FINISHED_GOODS = "Finished Goods"
    OTHERS = "Others"


class UOM(enum.Enum):
    """Unit of measurement enum."""
    BOX = "BOX"
    BAG = "BAG"


class PurchaseApproval(Base):
    """Purchase Approval (Receipt) Header model."""
    __tablename__ = "purchase_approvals"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Text, nullable=False)  # Reference to original PO
    
    # Transporter Information
    vehicle_number = Column(Text, nullable=True)
    transporter_name = Column(Text, nullable=True)
    lr_number = Column(Text, nullable=True)
    destination_location = Column(String(20), nullable=True)
    
    # Customer Information
    customer_name = Column(Text, nullable=True)
    authority = Column(Text, nullable=True)
    challan_number = Column(Text, nullable=True)
    invoice_number = Column(Text, nullable=True)
    grn_number = Column(Text, nullable=True)
    grn_quantity = Column(Text, nullable=True)
    delivery_note_number = Column(Text, nullable=True)
    service_po_number = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    items = relationship("PurchaseApprovalItem", back_populates="approval", cascade="all, delete-orphan")


class PurchaseApprovalItem(Base):
    """Purchase Approval Item model."""
    __tablename__ = "purchase_approval_items"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    approval_id = Column(BIGINT, ForeignKey("purchase_approvals.id", ondelete="CASCADE"), nullable=False)
    
    # Item Information
    material_type = Column(Text, nullable=True)
    item_category = Column(Text, nullable=True)
    sub_category = Column(Text, nullable=True)
    item_description = Column(Text, nullable=True)
    
    # Quantity and Weight Information
    quantity_units = Column(Numeric(12, 3), nullable=True)
    pack_size = Column(Numeric(12, 3), nullable=True)
    uom = Column(String(10), nullable=True)
    net_weight = Column(Numeric(12, 3), nullable=True)
    gross_weight = Column(Numeric(12, 3), nullable=True)
    
    # Lot and Date Information
    lot_number = Column(Text, nullable=True)
    mfg_date = Column(Date, nullable=True)
    exp_date = Column(Date, nullable=True)

    # Article/Item Financial Information (optional - not displayed in approval form)
    hsn_code = Column(BIGINT, nullable=True)
    price_per_kg = Column(Numeric(10, 2), nullable=True)
    taxable_value = Column(Numeric(12, 2), nullable=True)
    gst_percentage = Column(Numeric(5, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    approval = relationship("PurchaseApproval", back_populates="items")
    boxes = relationship("PurchaseApprovalBox", back_populates="item", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_approval_items", "approval_id"),
    )


class PurchaseApprovalBox(Base):
    """Purchase Approval Box model."""
    __tablename__ = "purchase_approval_boxes"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    item_id = Column(BIGINT, ForeignKey("purchase_approval_items.id", ondelete="CASCADE"), nullable=False)
    
    box_number = Column(Text, nullable=True)
    article_name = Column(Text, nullable=True)
    lot_number = Column(Text, nullable=True)
    net_weight = Column(Numeric(12, 3), nullable=True)
    gross_weight = Column(Numeric(12, 3), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    item = relationship("PurchaseApprovalItem", back_populates="boxes")
    
    # Indexes
    __table_args__ = (
        Index("idx_boxes_item", "item_id"),
    )


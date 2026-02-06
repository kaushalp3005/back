"""
RTV (Return to Vendor) Models
Separate tables for CDPL and CFPL companies
"""

from sqlalchemy import Column, String, Integer, Numeric, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import logging

Base = declarative_base()

logger = logging.getLogger(__name__)


# CFPL RTV Master Table
class CFPLRTVMaster(Base):
    __tablename__ = "cfplrtv_master"
    
    rtv_number = Column(String(50), primary_key=True, index=True)
    customer_code = Column(String(100), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    rtv_type = Column(String(50), nullable=False)
    other_reason = Column(Text, nullable=True)
    rtv_date = Column(String(10), nullable=False)  # YYYY-MM-DD format
    invoice_number = Column(String(100), nullable=True)
    dc_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(200), nullable=False)
    total_value = Column(Numeric(10, 2), nullable=False)
    total_boxes = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    company_code = Column(String(10), nullable=False, default="CFPL", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship to items
    items = relationship("CFPLRTVItem", back_populates="rtv_master", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_cfpl_rtv_date', 'rtv_date'),
        Index('idx_cfpl_rtv_status', 'status'),
        Index('idx_cfpl_rtv_company', 'company_code'),
    )


# CFPL RTV Items Table
class CFPLRTVItem(Base):
    __tablename__ = "cfplrtv_items"
    
    item_id = Column(Integer, primary_key=True, autoincrement=True)
    rtv_number = Column(String(50), ForeignKey("cfplrtv_master.rtv_number", ondelete="CASCADE"), nullable=False, index=True)
    transaction_no = Column(String(100), nullable=False, index=True)
    box_number = Column(Integer, nullable=False)
    sub_category = Column(String(200), nullable=True)
    item_description = Column(String(500), nullable=False)
    net_weight = Column(Numeric(10, 2), nullable=False)
    gross_weight = Column(Numeric(10, 2), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    reason = Column(Text, nullable=True)
    qr_data = Column(JSONB, nullable=True)  # Store complete QR data as JSON
    
    # Relationship to master
    rtv_master = relationship("CFPLRTVMaster", back_populates="items")
    
    __table_args__ = (
        Index('idx_cfpl_transaction_no', 'transaction_no'),
        Index('idx_cfpl_rtv_transaction', 'rtv_number', 'transaction_no'),
    )


# CDPL RTV Master Table
class CDPLRTVMaster(Base):
    __tablename__ = "cdplrtv_master"
    
    rtv_number = Column(String(50), primary_key=True, index=True)
    customer_code = Column(String(100), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    rtv_type = Column(String(50), nullable=False)
    other_reason = Column(Text, nullable=True)
    rtv_date = Column(String(10), nullable=False)  # YYYY-MM-DD format
    invoice_number = Column(String(100), nullable=True)
    dc_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(200), nullable=False)
    total_value = Column(Numeric(10, 2), nullable=False)
    total_boxes = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    company_code = Column(String(10), nullable=False, default="CDPL", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship to items
    items = relationship("CDPLRTVItem", back_populates="rtv_master", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_cdpl_rtv_date', 'rtv_date'),
        Index('idx_cdpl_rtv_status', 'status'),
        Index('idx_cdpl_rtv_company', 'company_code'),
    )


# CDPL RTV Items Table
class CDPLRTVItem(Base):
    __tablename__ = "cdplrtv_items"
    
    item_id = Column(Integer, primary_key=True, autoincrement=True)
    rtv_number = Column(String(50), ForeignKey("cdplrtv_master.rtv_number", ondelete="CASCADE"), nullable=False, index=True)
    transaction_no = Column(String(100), nullable=False, index=True)
    box_number = Column(Integer, nullable=False)
    sub_category = Column(String(200), nullable=True)
    item_description = Column(String(500), nullable=False)
    net_weight = Column(Numeric(10, 2), nullable=False)
    gross_weight = Column(Numeric(10, 2), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    reason = Column(Text, nullable=True)
    qr_data = Column(JSONB, nullable=True)  # Store complete QR data as JSON
    
    # Relationship to master
    rtv_master = relationship("CDPLRTVMaster", back_populates="items")
    
    __table_args__ = (
        Index('idx_cdpl_transaction_no', 'transaction_no'),
        Index('idx_cdpl_rtv_transaction', 'rtv_number', 'transaction_no'),
    )


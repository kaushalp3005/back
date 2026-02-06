# File: transfer_models.py
# Path: backend/app/models/transfer.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, 
    Numeric, String, Text, UniqueConstraint, CheckConstraint, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================
# WAREHOUSE MASTER MODEL
# ============================================

class WarehouseMaster(Base):
    __tablename__ = "warehouse_master"

    id = Column(Integer, primary_key=True)
    warehouse_code = Column(String(50), unique=True, nullable=False)
    warehouse_name = Column(String(200), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100))
    state = Column(String(100))
    pincode = Column(String(10))
    gstin = Column(String(15))
    contact_person = Column(String(100))
    contact_phone = Column(String(15))
    contact_email = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    transfer_requests_from = relationship("TransferRequest", foreign_keys="TransferRequest.from_warehouse", back_populates="from_warehouse_rel")
    transfer_requests_to = relationship("TransferRequest", foreign_keys="TransferRequest.to_warehouse", back_populates="to_warehouse_rel")

    __table_args__ = (
        Index("idx_warehouse_master_code", "warehouse_code"),
        Index("idx_warehouse_master_active", "is_active"),
    )


# ============================================
# TRANSFER REQUEST MODEL
# ============================================

class TransferRequest(Base):
    __tablename__ = "transfer_requests"

    id = Column(Integer, primary_key=True)
    request_no = Column(String(50), unique=True, nullable=False)
    transfer_no = Column(String(50), unique=True)
    request_date = Column(Date, nullable=False)
    from_warehouse = Column(String(100), ForeignKey("warehouse_master.warehouse_code"), nullable=False)
    to_warehouse = Column(String(100), ForeignKey("warehouse_master.warehouse_code"), nullable=False)
    reason = Column(String(100))
    reason_description = Column(Text, nullable=False)
    status = Column(String(50), default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))

    # Relationships
    from_warehouse_rel = relationship("WarehouseMaster", foreign_keys=[from_warehouse], back_populates="transfer_requests_from")
    to_warehouse_rel = relationship("WarehouseMaster", foreign_keys=[to_warehouse], back_populates="transfer_requests_to")
    items = relationship("TransferRequestItem", back_populates="transfer_request", cascade="all, delete-orphan")
    scanned_boxes = relationship("TransferScannedBox", back_populates="transfer_request", cascade="all, delete-orphan")
    transfer_info = relationship("TransferInfo", back_populates="transfer_request", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Approved', 'Rejected', 'In Transit', 'Completed')", name="ck_transfer_status"),
        Index("idx_transfer_requests_request_no", "request_no"),
        Index("idx_transfer_requests_transfer_no", "transfer_no"),
        Index("idx_transfer_requests_status", "status"),
        Index("idx_transfer_requests_date", "request_date"),
        Index("idx_transfer_requests_from_warehouse", "from_warehouse"),
        Index("idx_transfer_requests_to_warehouse", "to_warehouse"),
    )


# ============================================
# TRANSFER REQUEST ITEMS MODEL
# ============================================

class TransferRequestItem(Base):
    __tablename__ = "transfer_request_items"

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("transfer_requests.id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    material_type = Column(String(50))
    item_category = Column(String(100), nullable=False)
    sub_category = Column(String(100))
    item_description = Column(String(500), nullable=False)
    sku_id = Column(String(100))
    quantity = Column(Numeric(15, 3), nullable=False)
    uom = Column(String(20), nullable=False)
    pack_size = Column(Numeric(10, 2), default=0)
    package_size = Column(String(50))
    net_weight = Column(Numeric(10, 3), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    transfer_request = relationship("TransferRequest", back_populates="items")

    __table_args__ = (
        CheckConstraint("material_type IN ('RM', 'PM', 'FG', 'SFG')", name="ck_item_material_type"),
        UniqueConstraint("transfer_id", "line_number", name="uq_transfer_item_line"),
        Index("idx_transfer_items_transfer_id", "transfer_id"),
        Index("idx_transfer_items_material_type", "material_type"),
        Index("idx_transfer_items_sku", "sku_id"),
    )


# ============================================
# TRANSFER SCANNED BOXES MODEL
# ============================================

class TransferScannedBox(Base):
    __tablename__ = "transfer_scanned_boxes"

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("transfer_requests.id", ondelete="CASCADE"), nullable=False)
    box_id = Column(Integer, nullable=False)
    transaction_no = Column(String(100), nullable=False)
    sku_id = Column(String(100), nullable=False)
    box_number_in_array = Column(Integer, nullable=False)
    box_number = Column(Integer, nullable=False)
    item_description = Column(String(500))
    net_weight = Column(Numeric(10, 3), default=0)
    gross_weight = Column(Numeric(10, 3), default=0)
    scan_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    qr_data = Column(JSON)

    # Relationships
    transfer_request = relationship("TransferRequest", back_populates="scanned_boxes")

    __table_args__ = (
        UniqueConstraint("transfer_id", "transaction_no", "sku_id", "box_number_in_array", name="uq_scanned_box"),
        Index("idx_scanned_boxes_transfer_id", "transfer_id"),
        Index("idx_scanned_boxes_transaction_no", "transaction_no"),
        Index("idx_scanned_boxes_sku", "sku_id"),
        Index("idx_scanned_boxes_scan_timestamp", "scan_timestamp"),
    )


# ============================================
# TRANSFER INFO MODEL (Transport Details)
# ============================================

class TransferInfo(Base):
    __tablename__ = "transfer_info"

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("transfer_requests.id", ondelete="CASCADE"), nullable=False, unique=True)
    vehicle_number = Column(String(50), nullable=False)
    vehicle_number_other = Column(String(50))
    driver_name = Column(String(100), nullable=False)
    driver_name_other = Column(String(100))
    driver_phone = Column(String(15))
    approval_authority = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    transfer_request = relationship("TransferRequest", back_populates="transfer_info")

    __table_args__ = (
        Index("idx_transfer_info_transfer_id", "transfer_id"),
        Index("idx_transfer_info_vehicle", "vehicle_number"),
        Index("idx_transfer_info_driver", "driver_name"),
    )


# ============================================
# UTILITY FUNCTIONS
# ============================================

def generate_request_no(session) -> str:
    """Generate request number in format REQYYYYMMDDXXX"""
    from sqlalchemy import text
    
    result = session.execute(text("""
        SELECT 'REQ' || TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || 
               LPAD(COALESCE(MAX(CAST(SUBSTRING(request_no FROM 12) AS INTEGER)), 0) + 1, 3, '0')
        FROM transfer_requests
        WHERE request_no LIKE 'REQ' || TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || '%'
    """))
    
    return result.scalar()


def generate_transfer_no(session) -> str:
    """Generate transfer number in format TRANSYYYYMMDDXXX"""
    from sqlalchemy import text
    
    result = session.execute(text("""
        SELECT 'TRANS' || TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || 
               LPAD(COALESCE(MAX(CAST(SUBSTRING(transfer_no FROM 10) AS INTEGER)), 0) + 1, 3, '0')
        FROM transfer_requests
        WHERE transfer_no LIKE 'TRANS' || TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || '%'
    """))
    
    return result.scalar()


# ============================================
# HELPER FUNCTIONS FOR DATA RETRIEVAL
# ============================================

def get_transfer_with_details(session, transfer_id: int) -> Optional[Dict[str, Any]]:
    """Get transfer request with all related details"""
    from sqlalchemy import text
    
    query = text("""
        SELECT 
            tr.id,
            tr.request_no,
            tr.transfer_no,
            tr.request_date,
            tr.from_warehouse,
            tr.to_warehouse,
            tr.reason,
            tr.reason_description,
            tr.status,
            tr.created_by,
            tr.created_at,
            tr.updated_at,
            -- Items
            COALESCE(
                json_agg(
                    json_build_object(
                        'id', tri.id,
                        'line_number', tri.line_number,
                        'material_type', tri.material_type,
                        'item_category', tri.item_category,
                        'sub_category', tri.sub_category,
                        'item_description', tri.item_description,
                        'sku_id', tri.sku_id,
                        'quantity', tri.quantity,
                        'uom', tri.uom,
                        'pack_size', tri.pack_size,
                        'package_size', tri.package_size,
                        'net_weight', tri.net_weight
                    ) ORDER BY tri.line_number
                ) FILTER (WHERE tri.id IS NOT NULL), 
                '[]'::json
            ) as items,
            -- Scanned boxes
            COALESCE(
                json_agg(
                    json_build_object(
                        'id', tsb.id,
                        'box_id', tsb.box_id,
                        'transaction_no', tsb.transaction_no,
                        'sku_id', tsb.sku_id,
                        'box_number_in_array', tsb.box_number_in_array,
                        'box_number', tsb.box_number,
                        'item_description', tsb.item_description,
                        'net_weight', tsb.net_weight,
                        'gross_weight', tsb.gross_weight,
                        'scan_timestamp', tsb.scan_timestamp,
                        'qr_data', tsb.qr_data
                    ) ORDER BY tsb.box_number_in_array
                ) FILTER (WHERE tsb.id IS NOT NULL), 
                '[]'::json
            ) as scanned_boxes,
            -- Transport info
            CASE 
                WHEN ti.id IS NOT NULL THEN
                    json_build_object(
                        'id', ti.id,
                        'vehicle_number', ti.vehicle_number,
                        'vehicle_number_other', ti.vehicle_number_other,
                        'driver_name', ti.driver_name,
                        'driver_name_other', ti.driver_name_other,
                        'driver_phone', ti.driver_phone,
                        'approval_authority', ti.approval_authority,
                        'created_at', ti.created_at
                    )
                ELSE NULL
            END as transport_info
        FROM transfer_requests tr
        LEFT JOIN transfer_request_items tri ON tr.id = tri.transfer_id
        LEFT JOIN transfer_scanned_boxes tsb ON tr.id = tsb.transfer_id
        LEFT JOIN transfer_info ti ON tr.id = ti.transfer_id
        WHERE tr.id = :transfer_id
        GROUP BY tr.id, ti.id, ti.vehicle_number, ti.vehicle_number_other, 
                 ti.driver_name, ti.driver_name_other, ti.driver_phone, 
                 ti.approval_authority, ti.created_at
    """)
    
    result = session.execute(query, {"transfer_id": transfer_id}).fetchone()
    
    if result:
        return {
            "id": result.id,
            "request_no": result.request_no,
            "transfer_no": result.transfer_no,
            "request_date": result.request_date,
            "from_warehouse": result.from_warehouse,
            "to_warehouse": result.to_warehouse,
            "reason": result.reason,
            "reason_description": result.reason_description,
            "status": result.status,
            "created_by": result.created_by,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "items": result.items,
            "scanned_boxes": result.scanned_boxes,
            "transport_info": result.transfer_info
        }
    
    return None


def get_warehouse_addresses(session, warehouse_codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Get warehouse addresses for DC generation"""
    warehouses = session.query(WarehouseMaster).filter(
        WarehouseMaster.warehouse_code.in_(warehouse_codes)
    ).all()
    
    return {
        wh.warehouse_code: {
            "code": wh.warehouse_code,
            "name": wh.warehouse_name,
            "address": wh.address,
            "city": wh.city,
            "state": wh.state,
            "pincode": wh.pincode,
            "gstin": wh.gstin,
            "contact_person": wh.contact_person,
            "contact_phone": wh.contact_phone,
            "contact_email": wh.contact_email
        }
        for wh in warehouses
    }

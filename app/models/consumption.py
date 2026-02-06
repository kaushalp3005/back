# File: consumption_models.py
# Path: backend/app/models/consumption.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, 
    Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================
# BASE MODELS
# ============================================

class SKU(Base):
    __tablename__ = "sku"

    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    material_type = Column(String(10), nullable=False)
    uom = Column(String(20), nullable=False)
    perishable = Column(Boolean, default=False)
    description = Column(Text)
    category = Column(String(100))
    sub_category = Column(String(100))
    hsn_code = Column(String(20))
    gst_rate = Column(Numeric(5, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    bom_outputs = relationship("BOM", back_populates="output_sku")
    bom_components = relationship("BOMComponent", back_populates="sku")
    job_cards = relationship("JobCard", back_populates="sku")
    inventory_moves = relationship("InventoryMove", back_populates="sku")
    fifo_layers = relationship("FIFOLayer", back_populates="sku")
    daily_ledger = relationship("DailyLedger", back_populates="sku")
    qc_holds = relationship("QCHold", back_populates="sku")

    __table_args__ = (
        CheckConstraint("material_type IN ('RM', 'PM', 'SFG', 'FG')", name="ck_sku_material_type"),
        Index("idx_sku_material_type", "material_type"),
        Index("idx_sku_perishable", "perishable"),
        Index("idx_sku_active", "is_active"),
    )


class Warehouse(Base):
    __tablename__ = "warehouse"

    code = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    sitecode = Column(String(100), nullable=False)
    location = Column(String(255))
    warehouse_type = Column(String(50), default="STORAGE")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    inventory_moves = relationship("InventoryMove", back_populates="warehouse_rel")
    fifo_layers = relationship("FIFOLayer", back_populates="warehouse_rel")
    daily_ledger = relationship("DailyLedger", back_populates="warehouse_rel")
    qc_holds = relationship("QCHold", back_populates="warehouse_rel")

    __table_args__ = (
        Index("idx_warehouse_sitecode", "sitecode"),
        Index("idx_warehouse_type", "warehouse_type"),
        Index("idx_warehouse_active", "is_active"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    full_name = Column(String(255))
    department = Column(String(100))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_active", "is_active"),
    )


# ============================================
# BOM MODELS
# ============================================

class BOM(Base):
    __tablename__ = "bom"

    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    version = Column(String(20), default="1.0")
    output_sku_id = Column(String(100), ForeignKey("sku.id"))
    output_qty = Column(Numeric(15, 4), nullable=False, default=1)
    output_uom = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    output_sku = relationship("SKU", back_populates="bom_outputs")
    components = relationship("BOMComponent", back_populates="bom", cascade="all, delete-orphan")
    job_cards = relationship("JobCard", back_populates="bom")

    __table_args__ = (
        Index("idx_bom_output_sku", "output_sku_id"),
        Index("idx_bom_active", "is_active"),
    )


class BOMComponent(Base):
    __tablename__ = "bom_components"

    id = Column(Integer, primary_key=True)
    bom_id = Column(String(100), ForeignKey("bom.id", ondelete="CASCADE"))
    sku_id = Column(String(100), ForeignKey("sku.id"))
    material_type = Column(String(10), nullable=False)
    qty_required = Column(Numeric(15, 4), nullable=False)
    uom = Column(String(20), nullable=False)
    sequence_order = Column(Integer, default=1)
    
    # Loss tracking fields
    process_loss_pct = Column(Numeric(5, 2), default=0)
    extra_giveaway_pct = Column(Numeric(5, 2), default=0)
    handling_loss_pct = Column(Numeric(5, 2), default=0)
    shrinkage_pct = Column(Numeric(5, 2), default=0)
    
    # Calculated fields (computed in application layer)
    total_loss_pct = Column(Numeric(5, 2), default=0)
    qty_with_loss = Column(Numeric(15, 4), default=0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    bom = relationship("BOM", back_populates="components")
    sku = relationship("SKU", back_populates="bom_components")

    def calculate_loss_percentages(self):
        """Calculate total loss percentage and quantity with loss"""
        self.total_loss_pct = (
            self.process_loss_pct + 
            self.extra_giveaway_pct + 
            self.handling_loss_pct + 
            self.shrinkage_pct
        )
        self.qty_with_loss = self.qty_required * (1 + (self.total_loss_pct / 100))

    __table_args__ = (
        CheckConstraint("material_type IN ('RM', 'PM')", name="ck_bom_component_material_type"),
        Index("idx_bom_components_bom", "bom_id"),
        Index("idx_bom_components_sku", "sku_id"),
        Index("idx_bom_components_material_type", "material_type"),
    )


# ============================================
# JOB CARD MODELS
# ============================================

class JobCard(Base):
    __tablename__ = "job_card"

    job_card_no = Column(String(100), primary_key=True)
    sku_id = Column(String(100), ForeignKey("sku.id"))
    bom_id = Column(String(100), ForeignKey("bom.id"))
    planned_qty = Column(Numeric(15, 4), nullable=False)
    actual_qty = Column(Numeric(15, 4), default=0)
    uom = Column(String(20), nullable=False)
    status = Column(String(50), default="PLANNED")
    priority = Column(String(20), default="NORMAL")
    due_date = Column(Date)
    start_date = Column(Date)
    completion_date = Column(Date)
    production_line = Column(String(100))
    shift = Column(String(20))
    remarks = Column(Text)
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sku = relationship("SKU", back_populates="job_cards")
    bom = relationship("BOM", back_populates="job_cards")
    inventory_moves = relationship("InventoryMove", back_populates="job_card")

    __table_args__ = (
        CheckConstraint("status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_job_card_status"),
        CheckConstraint("priority IN ('HIGH', 'NORMAL', 'LOW')", name="ck_job_card_priority"),
        Index("idx_job_card_sku", "sku_id"),
        Index("idx_job_card_bom", "bom_id"),
        Index("idx_job_card_status", "status"),
        Index("idx_job_card_due_date", "due_date"),
    )


# ============================================
# INVENTORY MOVES MODELS
# ============================================

class InventoryMove(Base):
    __tablename__ = "inventory_moves"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    company = Column(String(10), nullable=False, default="CFPL")
    warehouse = Column(String(100), ForeignKey("warehouse.code"))
    item_id = Column(String(100), ForeignKey("sku.id"))
    lot = Column(String(100))
    batch = Column(String(100))
    tx_code = Column(String(20), nullable=False)
    job_card_no = Column(String(100), ForeignKey("job_card.job_card_no"))
    so_no = Column(String(100))
    qty_in = Column(Numeric(15, 4), default=0)
    qty_out = Column(Numeric(15, 4), default=0)
    uom = Column(String(20), nullable=False)
    unit_cost = Column(Numeric(15, 4), default=0)
    value_in = Column(Numeric(15, 2), default=0)
    value_out = Column(Numeric(15, 2), default=0)
    ref_doc = Column(String(255))
    ref_line = Column(String(100))
    created_by = Column(String(255))
    remarks = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    warehouse_rel = relationship("Warehouse", back_populates="inventory_moves")
    sku = relationship("SKU", back_populates="inventory_moves")
    job_card = relationship("JobCard", back_populates="inventory_moves")
    fifo_layers = relationship("FIFOLayer", back_populates="source_transaction")
    qc_holds = relationship("QCHold", back_populates="inventory_move")

    __table_args__ = (
        CheckConstraint("tx_code IN ('GRN', 'CON', 'SFG', 'FG', 'TRIN', 'TROUT', 'OUT', 'ADJ+', 'ADJ-', 'RETIN', 'OPENING', 'SCRAP', 'RTV', 'QC_HOLD', 'QC_RELEASE')", name="ck_inventory_moves_tx_code"),
        Index("idx_inventory_moves_ts", "ts"),
        Index("idx_inventory_moves_company", "company"),
        Index("idx_inventory_moves_warehouse", "warehouse"),
        Index("idx_inventory_moves_item", "item_id"),
        Index("idx_inventory_moves_tx_code", "tx_code"),
        Index("idx_inventory_moves_job_card", "job_card_no"),
        Index("idx_inventory_moves_lot_batch", "lot", "batch"),
    )


# ============================================
# FIFO LAYERS MODELS
# ============================================

class FIFOLayer(Base):
    __tablename__ = "fifo_layers"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    company = Column(String(10), nullable=False, default="CFPL")
    warehouse = Column(String(100), ForeignKey("warehouse.code"))
    item_id = Column(String(100), ForeignKey("sku.id"))
    lot = Column(String(100))
    batch = Column(String(100))
    open_qty = Column(Numeric(15, 4), nullable=False)
    open_value = Column(Numeric(15, 2), nullable=False)
    remaining_qty = Column(Numeric(15, 4), nullable=False)
    unit_cost = Column(Numeric(15, 4), nullable=False)
    source_tx_id = Column(PostgresUUID(as_uuid=True), ForeignKey("inventory_moves.id"))
    expiry_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    warehouse_rel = relationship("Warehouse", back_populates="fifo_layers")
    sku = relationship("SKU", back_populates="fifo_layers")
    source_transaction = relationship("InventoryMove", back_populates="fifo_layers")

    __table_args__ = (
        Index("idx_fifo_layers_company", "company"),
        Index("idx_fifo_layers_warehouse", "warehouse"),
        Index("idx_fifo_layers_item", "item_id"),
        Index("idx_fifo_layers_lot_batch", "lot", "batch"),
        Index("idx_fifo_layers_expiry", "expiry_date"),
        Index("idx_fifo_layers_remaining_qty", "remaining_qty"),
    )


# ============================================
# DAILY LEDGER MODELS
# ============================================

class DailyLedger(Base):
    __tablename__ = "daily_ledger"

    date = Column(Date, nullable=False)
    company = Column(String(10), nullable=False, default="CFPL")
    warehouse = Column(String(100), ForeignKey("warehouse.code"))
    sku_id = Column(String(100), ForeignKey("sku.id"))
    material_type = Column(String(10), nullable=False)
    opening_stock = Column(Numeric(15, 4), default=0)
    transfer_in = Column(Numeric(15, 4), default=0)
    transfer_out = Column(Numeric(15, 4), default=0)
    stock_in = Column(Numeric(15, 4), default=0)
    stock_out = Column(Numeric(15, 4), default=0)
    closing_stock = Column(Numeric(15, 4), default=0)
    valuation_rate = Column(Numeric(15, 4), default=0)
    inventory_value_closing = Column(Numeric(15, 2), default=0)
    uom = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    warehouse_rel = relationship("Warehouse", back_populates="daily_ledger")
    sku = relationship("SKU", back_populates="daily_ledger")

    __table_args__ = (
        CheckConstraint("material_type IN ('RM', 'PM', 'SFG', 'FG')", name="ck_daily_ledger_material_type"),
        PrimaryKeyConstraint("date", "company", "warehouse", "sku_id"),
        Index("idx_daily_ledger_date", "date"),
        Index("idx_daily_ledger_company", "company"),
        Index("idx_daily_ledger_warehouse", "warehouse"),
        Index("idx_daily_ledger_sku", "sku_id"),
        Index("idx_daily_ledger_material_type", "material_type"),
    )


# ============================================
# CONFIGURATION MODELS
# ============================================

class Config(Base):
    __tablename__ = "config"

    id = Column(Integer, primary_key=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(Text, nullable=False)
    description = Column(Text)
    data_type = Column(String(20), default="STRING")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_config_key", "config_key"),
        Index("idx_config_active", "is_active"),
    )


# ============================================
# SALES ORDERS MODELS
# ============================================

class SalesOrder(Base):
    __tablename__ = "sales_orders"

    so_no = Column(String(100), primary_key=True)
    customer_name = Column(String(255), nullable=False)
    customer_code = Column(String(100))
    order_date = Column(Date, nullable=False)
    delivery_date = Column(Date)
    status = Column(String(50), default="PENDING")
    total_amount = Column(Numeric(15, 2), default=0)
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'DISPATCHED', 'DELIVERED')", name="ck_sales_order_status"),
        Index("idx_sales_orders_customer", "customer_name"),
        Index("idx_sales_orders_status", "status"),
        Index("idx_sales_orders_order_date", "order_date"),
    )


# ============================================
# QC HOLDS MODELS
# ============================================

class QCHold(Base):
    __tablename__ = "qc_holds"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    inventory_move_id = Column(PostgresUUID(as_uuid=True), ForeignKey("inventory_moves.id"))
    warehouse = Column(String(100), ForeignKey("warehouse.code"))
    item_id = Column(String(100), ForeignKey("sku.id"))
    lot = Column(String(100))
    batch = Column(String(100))
    qty = Column(Numeric(15, 4), nullable=False)
    uom = Column(String(20), nullable=False)
    hold_reason = Column(String(255))
    hold_date = Column(DateTime(timezone=True), server_default=func.now())
    release_date = Column(DateTime(timezone=True))
    status = Column(String(20), default="HOLD")
    qc_remarks = Column(Text)
    qc_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    inventory_move = relationship("InventoryMove", back_populates="qc_holds")
    warehouse_rel = relationship("Warehouse", back_populates="qc_holds")
    sku = relationship("SKU", back_populates="qc_holds")

    __table_args__ = (
        CheckConstraint("status IN ('HOLD', 'RELEASE', 'REJECT')", name="ck_qc_hold_status"),
        Index("idx_qc_holds_inventory_move", "inventory_move_id"),
        Index("idx_qc_holds_warehouse", "warehouse"),
        Index("idx_qc_holds_item", "item_id"),
        Index("idx_qc_holds_status", "status"),
    )


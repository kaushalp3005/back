# File: alerts_recipients_models.py
# Path: backend/app/models/alerts_recipients.py

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Index, Integer, String
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================
# ALERTS RECIPIENTS MODEL
# ============================================

class AlertRecipient(Base):
    __tablename__ = "alert_recipients"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone_number = Column(String(20))
    module = Column(String(100), nullable=False)  # CONSUMPTION, TRANSFER, OUTWARD, etc.
    is_active = Column(Boolean, default=True)
    company_code = Column(String(10), default="CFPL")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_alert_recipients_email", "email"),
        Index("idx_alert_recipients_module", "module"),
        Index("idx_alert_recipients_active", "is_active"),
        Index("idx_alert_recipients_company", "company_code"),
    )

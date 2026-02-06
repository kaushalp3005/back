"""
Database models for Item Catalog (CFPL and CDPL items).
"""

from sqlalchemy import Column, Integer, String, Text
from app.core.database import Base


class CFPLItem(Base):
    """CFPL Items catalog model."""
    __tablename__ = "cfplitems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    MATERIAL_TYPE = Column(String(255), nullable=True, index=True)
    ITEM_CATEGORY = Column(String(255), nullable=True, index=True)
    SUB_CATEGORY = Column(String(255), nullable=True, index=True)
    ITEM_DESCRIPTION = Column(Text, nullable=True, index=True)


class CDPLItem(Base):
    """CDPL Items catalog model."""
    __tablename__ = "cdplitems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    MATERIAL_TYPE = Column(String(255), nullable=True, index=True)
    ITEM_CATEGORY = Column(String(255), nullable=True, index=True)
    SUB_CATEGORY = Column(String(255), nullable=True, index=True)
    ITEM_DESCRIPTION = Column(Text, nullable=True, index=True)

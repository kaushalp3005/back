"""
Schema models for WhatsApp integration.
"""

from typing import Optional
from pydantic import BaseModel, Field


class WhatsAppWebhookRequest(BaseModel):
    """WhatsApp webhook request model."""
    MessageSid: str
    From: str
    To: str
    Body: Optional[str] = None
    NumMedia: int = 0
    MediaUrl0: Optional[str] = None
    MediaContentType0: Optional[str] = None


class WhatsAppMessageResponse(BaseModel):
    """WhatsApp message response model."""
    status: str
    message_sid: Optional[str] = None
    message: str


class PDFProcessingRequest(BaseModel):
    """PDF processing request from WhatsApp."""
    phone_number: str
    pdf_url: str
    message_sid: str


class PDFProcessingResponse(BaseModel):
    """PDF processing response."""
    success: bool
    message: str
    purchase_order_id: Optional[int] = None
    purchase_approval_id: Optional[int] = None
    error: Optional[str] = None

"""
WhatsApp webhook router for Twilio integration.
"""

import logging
import os
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.whatsapp import get_whatsapp_service, WhatsAppService
from app.schemas.whatsapp import (
    WhatsAppMessageResponse,
    PDFProcessingRequest,
    PDFProcessingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


@router.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for receiving WhatsApp messages from Twilio.

    This endpoint automatically processes PDF files and creates database entries.
    """
    try:
        logger.info(f"Received WhatsApp message from {From}")
        logger.info(f"Message SID: {MessageSid}, NumMedia: {NumMedia}, Body: {Body}")

        service = get_whatsapp_service()

        # Check if message contains a PDF file
        if NumMedia > 0 and MediaContentType0 == "application/pdf":
            logger.info(f"Received PDF file: {MediaUrl0}")

            try:
                # Send processing message
                service.send_message(From, "Processing your PDF...")

                # Download PDF into memory (BytesIO)
                pdf_file = await service.download_pdf_from_url(MediaUrl0)

                # Process PDF and create entries automatically
                result = service.process_pdf_and_create_entries(
                    db=db,
                    pdf_file=pdf_file,
                    phone_number=From
                )

                # Send simple success message with PO number (plain text, no formatting)
                success_msg = f"Created entry for {result['po_number']}"
                service.send_message(From, success_msg)

                # Return empty response (message already sent)
                return ""

            except Exception as e:
                logger.error(f"Error processing PDF: {str(e)}", exc_info=True)

                # Send error message (truncated to avoid WhatsApp limit)
                error_text = str(e)
                # Keep error message under 200 characters to stay well under WhatsApp's 1600 limit
                if len(error_text) > 200:
                    error_text = error_text[:200] + "..."

                error_msg = f"Error processing PDF: {error_text}\n\nPlease try again or contact support."
                service.send_message(From, error_msg)

                # Return empty response (message already sent)
                return ""

        # Handle other messages
        elif Body:
            welcome_msg = "Welcome to Candor Foods Purchase Order System!\n\nSend a PDF file of the purchase order and I'll automatically process it and create entries in the system."
            service.send_message(From, welcome_msg)
            return ""

        # Unknown message type
        else:
            service.send_message(From, "Please send a PDF file of the purchase order.")
            return ""

    except Exception as e:
        logger.error(f"Error in WhatsApp webhook: {str(e)}", exc_info=True)
        try:
            service = get_whatsapp_service()
            # Send short error message
            service.send_message(From, "An error occurred processing your request. Please try again later or contact support.")
        except Exception as msg_error:
            logger.error(f"Failed to send error message: {str(msg_error)}")
        return ""


@router.get("/status")
async def whatsapp_status():
    """
    Check WhatsApp service status.
    """
    try:
        service = get_whatsapp_service()
        return {
            "status": "active",
            "whatsapp_number": service.whatsapp_number,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WhatsApp service error: {str(e)}")


@router.post("/send-message")
async def send_message(
    to_number: str,
    message: str,
):
    """
    Send a message via WhatsApp (for testing/admin use).
    """
    try:
        service = get_whatsapp_service()
        message_sid = service.send_message(to_number, message)

        return WhatsAppMessageResponse(
            status="sent",
            message_sid=message_sid,
            message="Message sent successfully"
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



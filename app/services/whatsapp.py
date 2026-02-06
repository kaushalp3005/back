"""
Service for WhatsApp integration using Twilio.
"""

import os
import logging
import httpx
import tempfile
from typing import Optional, BinaryIO
from datetime import datetime
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from app.core.config import settings
from app.services.pdf_extraction import PDFExtractionService
from app.services.purchase import create_purchase_order
from app.services.purchase_approval import create_purchase_approval
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderInfo,
    Party,
    FinancialSummary,
)
from app.schemas.purchase_approval import (
    PurchaseApprovalCreate,
    TransporterInformation,
    CustomerInformation,
    ItemSchema,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Service for handling WhatsApp messages via Twilio."""

    def __init__(self):
        """Initialize the WhatsApp service with Twilio client."""
        self.account_sid = settings.twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = settings.twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.whatsapp_number = settings.twilio_whatsapp_number

        if not self.account_sid or not self.auth_token:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")

        self.client = Client(self.account_sid, self.auth_token)
        self.pdf_service = PDFExtractionService()
        logger.info("Initialized WhatsApp service with Twilio")

    def send_message(self, to_number: str, message: str) -> str:
        """
        Send a simple text message via WhatsApp.

        Args:
            to_number: Recipient phone number (with country code)
            message: Message text to send

        Returns:
            Message SID
        """
        try:
            # Ensure the number has the whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            message = self.client.messages.create(
                from_=self.whatsapp_number,
                body=message,
                to=to_number
            )

            logger.info(f"Message sent to {to_number}: {message.sid}")
            return message.sid

        except Exception as e:
            logger.error(f"Failed to send message to {to_number}: {str(e)}")
            raise

    def send_interactive_buttons(self, to_number: str, message: str, pdf_url: str, message_sid: str) -> str:
        """
        Send a message with interactive buttons for Extract/Cancel using Twilio's Interactive Messages.

        Args:
            to_number: Recipient phone number
            message: Message text
            pdf_url: URL of the PDF file
            message_sid: Original message SID for tracking

        Returns:
            Message SID
        """
        try:
            # Ensure the number has the whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            # Create interactive message with buttons
            interactive_message = {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "PDF Processing"
                },
                "body": {
                    "text": f"{message}\n\nFile reference: {message_sid[-8:]}"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": f"extract_{message_sid}",
                                "title": "✅ Extract"
                            }
                        },
                        {
                            "type": "reply", 
                            "reply": {
                                "id": f"cancel_{message_sid}",
                                "title": "❌ Cancel"
                            }
                        }
                    ]
                }
            }

            message = self.client.messages.create(
                from_=self.whatsapp_number,
                to=to_number,
                content_sid=None,  # Use custom content
                messaging_service_sid=None,
                body=None,  # Don't use body when using interactive content
                persistent_action=["extract", "cancel"],  # Make buttons persistent
                content_variables={
                    "1": message,
                    "2": message_sid[-8:]
                }
            )

            logger.info(f"Interactive buttons sent to {to_number}: {message.sid}")
            return message.sid

        except Exception as e:
            logger.error(f"Failed to send interactive buttons: {str(e)}")
            # Fallback to regular message with text instructions
            logger.info("Falling back to text-based interaction")
            
            button_message = f"""{message}

Please reply with:
- *EXTRACT* to process the PDF  
- *CANCEL* to cancel

Your file reference: {message_sid[-8:]}"""

            fallback_message = self.client.messages.create(
                from_=self.whatsapp_number,
                body=button_message,
                to=to_number
            )

            logger.info(f"Fallback message sent to {to_number}: {fallback_message.sid}")
            return fallback_message.sid

    async def download_pdf_from_url(self, url: str, auth_header: Optional[str] = None) -> BinaryIO:
        """
        Download PDF file from URL directly into memory (no temp file).

        Args:
            url: URL to download from
            auth_header: Optional authentication header (for Twilio URLs)

        Returns:
            BytesIO object containing the PDF data
        """
        try:
            from io import BytesIO

            headers = {}
            if auth_header:
                headers["Authorization"] = auth_header
            else:
                # Use basic auth for Twilio media URLs
                import base64
                credentials = base64.b64encode(
                    f"{self.account_sid}:{self.auth_token}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {credentials}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()

                # Create BytesIO object in memory
                pdf_bytes = BytesIO(response.content)
                pdf_bytes.seek(0)

            logger.info(f"Downloaded PDF from {url} into memory ({len(response.content)} bytes)")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to download PDF from {url}: {str(e)}")
            raise

    def _map_buyer_to_company(self, buyer_name: str) -> str:
        """
        Map buyer name to company code.

        Args:
            buyer_name: Buyer name from PDF

        Returns:
            Company code (CFPL or CDPL)
        """
        if not buyer_name:
            return "CFPL"  # Default

        buyer_upper = buyer_name.upper().strip()

        if "CANDOR FOODS PRIVATE LIMITED" in buyer_upper:
            return "CFPL"
        elif "CANDOR DATES PRIVATE LIMITED" in buyer_upper:
            return "CDPL"
        else:
            return "CFPL"  # Default to CFPL

    def _get_item_details_from_catalog(self, db: Session, company: str, item_description: str) -> dict:
        """
        Get item details from catalog based on description.

        Args:
            db: Database session
            company: Company code (CFPL or CDPL)
            item_description: Item description from PDF

        Returns:
            Dictionary with item details
        """
        try:
            from app.services.item_catalog import ItemCatalogService
            from app.schemas.item_catalog import AutoFillRequest

            request = AutoFillRequest(ITEM_DESCRIPTION=item_description)
            item_details = ItemCatalogService.auto_fill_from_description(db, company, request)

            if item_details:
                return {
                    "material_type": item_details.MATERIAL_TYPE,
                    "item_category": item_details.ITEM_CATEGORY,
                    "sub_category": item_details.SUB_CATEGORY,
                    "item_description": item_details.ITEM_DESCRIPTION,
                }
            else:
                # If not found in catalog, use extracted description as-is
                logger.warning(f"Item not found in catalog for description: {item_description}")
                return {
                    "material_type": "",
                    "item_category": "",
                    "sub_category": None,
                    "item_description": item_description,
                }

        except Exception as e:
            logger.error(f"Error fetching item from catalog: {str(e)}")
            # Fallback to extracted description
            return {
                "material_type": "",
                "item_category": "",
                "sub_category": None,
                "item_description": item_description,
            }

    def process_pdf_and_create_entries(
        self,
        db: Session,
        pdf_file: BinaryIO,
        phone_number: str
    ) -> dict:
        """
        Process PDF and automatically create purchase order and purchase approval entries.

        Args:
            db: Database session
            pdf_file: PDF file object
            phone_number: WhatsApp number of sender

        Returns:
            Dictionary with created IDs and status
        """
        try:
            logger.info(f"Processing PDF for {phone_number}")

            # Step 1: Extract data from PDF
            logger.info("Extracting data from PDF...")
            extracted_data = self.pdf_service.process_pdf(pdf_file)

            # Step 2: Determine company based on buyer name
            company = self._map_buyer_to_company(extracted_data.BUYER_NAME)
            logger.info(f"Mapped buyer '{extracted_data.BUYER_NAME}' to company: {company}")

            # Step 3: Generate purchase number in PR-YYYYMMDDHHMMSS format
            purchase_number = f"PR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info(f"Generated purchase number: {purchase_number}")

            # Step 4: Get PO number from PDF
            po_number = extracted_data.PO_NUMBER or purchase_number

            # Step 5: Create Purchase Order
            logger.info("Creating purchase order...")

            po_create = PurchaseOrderCreate(
                company_name=company,
                purchase_number=purchase_number,
                purchase_order=PurchaseOrderInfo(
                    po_number=po_number,
                    po_date=extracted_data.PO_DATE or datetime.now().date(),
                    po_validity=extracted_data.PO_VALIDITY,
                    currency="INR",
                ),
                buyer=Party(
                    name=extracted_data.BUYER_NAME or "Unknown Buyer",
                    address=extracted_data.BUYER_ADDRESS,
                    gstin=extracted_data.BUYER_GSTIN,
                    state=extracted_data.BUYER_STATE,
                ),
                supplier=Party(
                    name=extracted_data.SUPPLIER_NAME or "Unknown Supplier",
                    address=extracted_data.SUPPLIER_ADDRESS,
                    gstin=extracted_data.SUPPLIER_GSTIN,
                    state=extracted_data.SUPPLIER_STATE,
                ),
                ship_to=Party(
                    name=extracted_data.SHIP_TO_NAME or "Unknown",
                    address=extracted_data.SHIP_TO_ADDRESS,
                    gstin=None,
                    state=extracted_data.SHIP_TO_STATE,
                ),
                freight_by=extracted_data.FREIGHT_BY,
                dispatch_by=extracted_data.DISPATCH_BY,
                indentor=extracted_data.INDENTOR,
                financial_summary=FinancialSummary(
                    sub_total=0.0,
                    igst=0.0,
                    other_charges_non_gst=0.0,
                    grand_total=0.0,
                ),
            )

            created_po = create_purchase_order(db, po_create)
            logger.info(f"Created purchase order with ID: {created_po.id}")

            # Step 6: Create Purchase Approval with Items
            logger.info("Creating purchase approval...")

            # Convert extracted items to ItemSchema using catalog lookup
            items = []
            for idx, item in enumerate(extracted_data.ITEMS or [], start=1):
                # Get item details from catalog
                catalog_item = self._get_item_details_from_catalog(
                    db,
                    company,
                    item.ITEM_DESCRIPTION
                )

                item_schema = ItemSchema(
                    material_type=catalog_item["material_type"],
                    item_category=catalog_item["item_category"],
                    sub_category=catalog_item["sub_category"],
                    item_description=catalog_item["item_description"],
                    quantity_units=0.000,  # Set to 0 as per requirement
                    pack_size=None,
                    uom="",  # Keep blank as per requirement
                    net_weight=item.QUANTITY,  # Set to extracted quantity
                    gross_weight=None,
                    lot_number=None,
                    mfg_date=None,
                    exp_date=None,
                    hsn_code=item.HSN_CODE,
                    price_per_kg=item.PRICE_PER_KG,
                    taxable_value=item.TAXABLE_VALUE,
                    gst_percentage=item.GST_PERCENTAGE,
                    boxes=[],  # No boxes initially
                )
                items.append(item_schema)

            approval_create = PurchaseApprovalCreate(
                purchase_order_id=po_number,  # Use PO number from PDF
                transporter_information=TransporterInformation(
                    vehicle_number=None,
                    transporter_name=None,
                    lr_number=None,
                    destination_location=None,  # Keep null as per requirement
                ),
                customer_information=CustomerInformation(
                    customer_name="",  # Keep blank string instead of null
                    authority=None,
                    challan_number=None,
                    invoice_number=None,
                    grn_number=None,
                    grn_quantity=None,
                    delivery_note_number=None,
                    service_po_number=None,
                ),
                items=items,
            )

            created_approval = create_purchase_approval(db, approval_create)
            logger.info(f"Created purchase approval with ID: {created_approval.id}")

            return {
                "success": True,
                "purchase_order_id": created_po.id,
                "purchase_number": purchase_number,
                "po_number": po_number,  # Return PO number for message
                "purchase_approval_id": created_approval.id,
                "items_count": len(items),
                "company": company,
            }

        except Exception as e:
            logger.error(f"Failed to process PDF and create entries: {str(e)}", exc_info=True)
            raise

    def create_twiml_response(self, message: str) -> str:
        """
        Create a TwiML response for webhook.

        Args:
            message: Message to send back

        Returns:
            TwiML XML string
        """
        response = MessagingResponse()
        response.message(message)
        return str(response)

    def create_twiml_interactive_response(self, message: str, message_sid: str) -> str:
        """
        Create a TwiML response with interactive-style formatting for webhook.
        
        Since Twilio's WhatsApp interactive buttons require pre-approved templates,
        we'll format the message to look like interactive buttons using emojis and formatting.

        Args:
            message: Message to send back
            message_sid: Message SID for button identification

        Returns:
            TwiML XML string with button-style formatting
        """
        try:
            response = MessagingResponse()
            
            # Create a visually appealing message that mimics interactive buttons
            button_formatted_message = f"""📋 {message}

┌─────────────────────┐
│  📤 *EXTRACT*       │
│  Process the PDF    │
└─────────────────────┘

┌─────────────────────┐  
│  ❌ *CANCEL*        │
│  Cancel processing  │
└─────────────────────┘

💬 Reply with *EXTRACT* or *CANCEL*

📋 Reference: {message_sid[-8:]}"""
            
            msg = response.message()
            msg.body(button_formatted_message)
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Failed to create interactive TwiML: {str(e)}")
            # Fallback to regular response
            fallback_msg = f"""{message}

Please reply with:
• EXTRACT - to process the PDF
• CANCEL - to cancel

Reference: {message_sid[-8:]}"""
            
            return self.create_twiml_response(fallback_msg)

    def send_confirmation_buttons(self, to_number: str, message: str, action_id: str) -> str:
        """
        Send a message with confirmation-style buttons (Confirm/Cancel).
        
        This creates the visual style similar to the screenshot you showed.

        Args:
            to_number: Recipient phone number
            message: Message text
            action_id: Unique ID for tracking this action

        Returns:
            Message SID
        """
        try:
            # Ensure the number has the whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            confirmation_message = f"""📄 {message}

┌─────────────────────┐
│  ✅ *CONFIRM*       │
│  Proceed with task  │
└─────────────────────┘

┌─────────────────────┐
│  ❌ *CANCEL*        │
│  Cancel operation   │
└─────────────────────┘

� Reply with *CONFIRM* or *CANCEL*

🔖 Action ID: {action_id}"""

            message = self.client.messages.create(
                from_=self.whatsapp_number,
                body=confirmation_message,
                to=to_number
            )

            logger.info(f"Confirmation buttons sent to {to_number}: {message.sid}")
            return message.sid

        except Exception as e:
            logger.error(f"Failed to send confirmation buttons: {str(e)}")
            raise


# Global instance
whatsapp_service = None


def get_whatsapp_service() -> WhatsAppService:
    """Get or create WhatsApp service instance."""
    global whatsapp_service
    if whatsapp_service is None:
        whatsapp_service = WhatsAppService()
    return whatsapp_service

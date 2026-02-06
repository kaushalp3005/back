"""
Service for extracting structured data from PDF files using Claude Sonnet 4.5.
"""

import os
import json
import logging
from typing import BinaryIO, Optional
from datetime import datetime
import pdfplumber
import anthropic

from app.core.config import settings
from app.schemas.pdf_extraction import PDFExtractionResponse, ItemExtraction

logger = logging.getLogger(__name__)

# Claude Sonnet 4.5 model configuration
CLAUDE_SONNET_4_5_MODEL = "claude-sonnet-4-5-20250929"


class PDFExtractionService:
    """Service for extracting structured data from PDF files using Claude AI."""

    def __init__(self):
        """Initialize the service with Claude API client."""
        self.api_key = settings.claude_api_key or os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY environment variable is required")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        logger.info(f"Initialized PDF extraction service with Claude model: {CLAUDE_SONNET_4_5_MODEL}")

    def extract_text_from_pdf(self, pdf_file: BinaryIO) -> str:
        """
        Extract text content from PDF file.

        Args:
            pdf_file: Binary file object of the PDF

        Returns:
            Extracted text content from the PDF

        Raises:
            Exception: If PDF processing fails
        """
        try:
            pdf_file.seek(0)  # Reset file pointer
            
            text_content = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text_content += f"--- Page {page_num} ---\n{page_text}\n\n"
                    
                    # Also extract tables if present
                    tables = page.extract_tables()
                    for table_num, table in enumerate(tables, 1):
                        text_content += f"--- Table {table_num} on Page {page_num} ---\n"
                        for row in table:
                            text_content += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
                        text_content += "\n"

            if not text_content.strip():
                raise Exception("No text could be extracted from the PDF")

            return text_content

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise Exception(f"Failed to extract text from PDF: {str(e)}")

    def extract_structured_data(self, text_content: str) -> PDFExtractionResponse:
        """
        Extract structured data from text using Claude Sonnet 4.5.

        Args:
            text_content: Raw text extracted from PDF

        Returns:
            PDFExtractionResponse with extracted structured data

        Raises:
            Exception: If Claude API call fails or parsing fails
        """
        try:
            logger.info(f"Using Claude model: {CLAUDE_SONNET_4_5_MODEL} for PDF extraction")
            
            prompt = f"""
You are an expert at extracting structured data from purchase order documents. 

Extract the following information from this purchase order text and return it as a valid JSON object with the exact field names specified:

REQUIRED FIELDS:
- PO_NUMBER: string (Purchase Order number)
- PO_DATE: string (Purchase Order date in ISO format YYYY-MM-DD, if found)
- PO_VALIDITY: string (Purchase Order validity date in ISO format YYYY-MM-DD, if found)
- BUYER_NAME: string (Name of the buyer/customer)
- BUYER_ADDRESS: string (Complete address of the buyer)
- BUYER_GSTIN: string (GSTIN of the buyer)
- BUYER_STATE: string (State of the buyer)
- SUPPLIER_NAME: string (Name of the supplier/vendor)
- SUPPLIER_ADDRESS: string (Complete address of the supplier)
- SUPPLIER_GSTIN: string (GSTIN of the supplier)
- SUPPLIER_STATE: string (State of the supplier)
- SHIP_TO_NAME: string (Ship to name/company)
- SHIP_TO_ADDRESS: string (Ship to address)
- SHIP_TO_STATE: string (Ship to state)
- FREIGHT_BY: string (Who handles freight)
- DISPATCH_BY: string (Who handles dispatch)
- INDENTOR: string (Indentor information)
- ITEMS: array of objects, each containing:
  - ITEM_DESCRIPTION: string (Description of the item)
  - HSN_CODE: integer (HSN code if available)
  - QUANTITY: number (Quantity if available)
  - PRICE_PER_KG: number (Price per kg if available)
  - TAXABLE_VALUE: number (Taxable value if available)
  - GST_PERCENTAGE: number (GST percentage if available)

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no additional text or explanations
2. Use null for fields that are not found or cannot be determined
3. Convert all string fields to CAPITAL CASE before returning
4. For dates, convert to ISO format (YYYY-MM-DD) if you can parse them
5. For the ITEMS array, extract ALL items found in the document
6. Be careful with HSN codes - they should be integers
7. Numbers should be parsed as floats/integers, not strings
8. If multiple items exist, include them all in the ITEMS array
9. CRITICAL: For ITEM_DESCRIPTION, extract ONLY the main item name from the first line in the Description column. 
   Ignore any additional lines below the item name that contain brand names, variants, or other details.
   For example: If the description shows "Desi Ghee" on the first line and "Amul Ghee" on the second line, 
   extract only "DESI GHEE" as the ITEM_DESCRIPTION, not "Amul Ghee" or any combination.

Here is the purchase order text to analyze:

{text_content}

Return the extracted data as JSON:
"""

            response = self.client.messages.create(
                model=CLAUDE_SONNET_4_5_MODEL,  # Claude Sonnet 4.5 - Latest version
                max_tokens=4000,
                temperature=0.1,  # Low temperature for consistent extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Extract the response content
            response_content = response.content[0].text.strip()
            
            # Remove any potential markdown formatting
            if response_content.startswith("```json"):
                response_content = response_content[7:]
            if response_content.startswith("```"):
                response_content = response_content[3:]
            if response_content.endswith("```"):
                response_content = response_content[:-3]
            
            response_content = response_content.strip()

            # Parse the JSON response
            try:
                extracted_data = json.loads(response_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude response as JSON: {response_content}")
                raise Exception(f"Claude returned invalid JSON: {str(e)}")

            # Convert to Pydantic model for validation
            return self._convert_to_response_model(extracted_data)

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {str(e)}")
            raise Exception(f"Claude API error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in Claude extraction: {str(e)}")
            raise Exception(f"Failed to extract structured data: {str(e)}")

    def _convert_to_response_model(self, data: dict) -> PDFExtractionResponse:
        """
        Convert Claude response to Pydantic model with proper validation.

        Args:
            data: Raw dictionary from Claude response

        Returns:
            Validated PDFExtractionResponse object
        """
        try:
            # Handle date parsing
            for date_field in ["PO_DATE", "PO_VALIDITY"]:
                if data.get(date_field) and data[date_field] != "null":
                    try:
                        # Try to parse the date string
                        date_str = str(data[date_field])
                        if date_str and date_str != "null":
                            # Parse ISO format or common formats
                            try:
                                parsed_date = datetime.fromisoformat(date_str).date()
                                data[date_field] = parsed_date
                            except ValueError:
                                # Try other common date formats
                                for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]:
                                    try:
                                        parsed_date = datetime.strptime(date_str, fmt).date()
                                        data[date_field] = parsed_date
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    # If no format worked, set to None
                                    data[date_field] = None
                    except Exception:
                        data[date_field] = None

            # Handle items conversion
            items = []
            if data.get("ITEMS") and isinstance(data["ITEMS"], list):
                for item_data in data["ITEMS"]:
                    if isinstance(item_data, dict):
                        # Ensure HSN_CODE is an integer if present
                        if item_data.get("HSN_CODE") and item_data["HSN_CODE"] != "null":
                            try:
                                item_data["HSN_CODE"] = int(float(str(item_data["HSN_CODE"])))
                            except (ValueError, TypeError):
                                item_data["HSN_CODE"] = None

                        # Ensure numeric fields are proper numbers
                        for numeric_field in ["QUANTITY", "PRICE_PER_KG", "TAXABLE_VALUE", "GST_PERCENTAGE"]:
                            if item_data.get(numeric_field) and item_data[numeric_field] != "null":
                                try:
                                    item_data[numeric_field] = float(item_data[numeric_field])
                                except (ValueError, TypeError):
                                    item_data[numeric_field] = None

                        items.append(ItemExtraction(**item_data))

            data["ITEMS"] = items

            return PDFExtractionResponse(**data)

        except Exception as e:
            logger.error(f"Error converting to response model: {str(e)}")
            raise Exception(f"Failed to validate extracted data: {str(e)}")

    def process_pdf(self, pdf_file: BinaryIO) -> PDFExtractionResponse:
        """
        Complete PDF processing pipeline: extract text and structured data.

        Args:
            pdf_file: Binary file object of the PDF

        Returns:
            PDFExtractionResponse with extracted structured data

        Raises:
            Exception: If any step of the process fails
        """
        try:
            # Step 1: Extract text from PDF
            logger.info("Extracting text from PDF...")
            text_content = self.extract_text_from_pdf(pdf_file)
            
            # Step 2: Extract structured data using Claude
            logger.info("Extracting structured data using Claude Sonnet 4.5...")
            structured_data = self.extract_structured_data(text_content)
            
            logger.info("PDF processing completed successfully")
            return structured_data

        except Exception as e:
            logger.error(f"PDF processing failed: {str(e)}")
            raise
"""
Invoice Extraction Service
Extracts invoice data from various file formats using OpenAI GPT-4o Vision API
Enhanced to scan all PDF pages and improve amount extraction
"""

import os
import json
import base64
import logging
from typing import Dict, Optional, Tuple, List
import fitz  # PyMuPDF
from PIL import Image
from io import BytesIO
from openai import OpenAI
import httpx

logger = logging.getLogger(__name__)


class InvoiceExtractionService:
    """Service for extracting invoice data from PDF and image files using AI"""
    
    # Supported file formats
    SUPPORTED_FORMATS = {
        'pdf': ['pdf'],
        'image': ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'tif']
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the invoice extraction service
        
        Args:
            api_key: OpenAI API key
        """
        # Import settings here to avoid circular imports
        from app.core.config import settings
        
        # Use provided api_key, or fall back to settings, or environment variable
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY in your .env file or pass api_key parameter."
            )

        # Initialize OpenAI client
        # Create httpx client explicitly without proxies to avoid deployment issues
        # This prevents the 'proxies' argument error in EC2/Netlify environments
        try:
            # Create a custom httpx client that explicitly disables proxies
            http_client = httpx.Client(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
            
            # Initialize OpenAI client with the custom httpx client
            self.client = OpenAI(
                api_key=self.api_key,
                http_client=http_client
            )
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> Dict:
        """
        Extract invoice data from file bytes (PDF or image)
        
        Args:
            file_bytes: File content as bytes
            filename: Original filename (used to determine file type)
            
        Returns:
            dict: Extracted invoice data
            
        Raises:
            Exception: If extraction fails
        """
        try:
            # Detect file type
            file_type, file_ext = self._detect_file_type(filename)
            
            # Convert to base64 images based on file type
            if file_type == 'pdf':
                images_base64 = self._pdf_to_base64_images(file_bytes)
            elif file_type == 'image':
                img_base64 = self._image_to_base64(file_bytes, file_ext)
                images_base64 = [img_base64]
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
            
            # Extract data using OpenAI
            invoice_data = self._extract_with_openai(images_base64)
            
            # Validate and clean data
            cleaned_data = self._clean_extracted_data(invoice_data)
            
            logger.info(f"Successfully extracted invoice data from {file_type} file ({len(images_base64)} page(s))")
            return cleaned_data
            
        except Exception as e:
            logger.error(f"Error extracting invoice data: {e}")
            raise Exception(f"Failed to extract invoice data: {str(e)}")
    
    def _detect_file_type(self, filename: str) -> Tuple[str, str]:
        """
        Detect file type from filename
        
        Args:
            filename: Original filename
            
        Returns:
            tuple: (file_type, file_extension)
            
        Raises:
            ValueError: If file type is not supported
        """
        file_ext = filename.lower().split('.')[-1]
        
        if file_ext in self.SUPPORTED_FORMATS['pdf']:
            return 'pdf', file_ext
        elif file_ext in self.SUPPORTED_FORMATS['image']:
            return 'image', file_ext
        else:
            supported = ', '.join(
                self.SUPPORTED_FORMATS['pdf'] + self.SUPPORTED_FORMATS['image']
            )
            raise ValueError(f"Unsupported file format: .{file_ext}. Supported formats: {supported}")
    
    def _pdf_to_base64_images(self, pdf_bytes: bytes, max_pages: int = 10) -> List[str]:
        """
        Convert all pages of PDF to base64-encoded PNG images
        
        Args:
            pdf_bytes: PDF file content as bytes
            max_pages: Maximum number of pages to process (default: 10)
            
        Returns:
            list: List of base64-encoded PNG images (one per page)
        """
        try:
            # Open PDF from bytes
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if pdf_document.page_count == 0:
                raise ValueError("PDF has no pages")
            
            images_base64 = []
            pages_to_process = min(pdf_document.page_count, max_pages)
            
            logger.info(f"Processing {pages_to_process} page(s) from PDF")
            
            # Process each page
            for page_num in range(pages_to_process):
                page = pdf_document[page_num]
                
                # Render page to high-resolution image (2x scaling for better OCR)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                
                # Convert to PNG bytes
                img_bytes = pix.tobytes("png")
                
                # Encode to base64
                img_base64 = base64.b64encode(img_bytes).decode()
                images_base64.append(img_base64)
            
            pdf_document.close()
            
            return images_base64
            
        except Exception as e:
            raise Exception(f"Failed to convert PDF to images: {str(e)}")
    
    def _image_to_base64(self, img_bytes: bytes, file_ext: str) -> str:
        """
        Convert image bytes to base64-encoded PNG image
        
        Args:
            img_bytes: Image file content as bytes
            file_ext: File extension
            
        Returns:
            str: Base64-encoded PNG image
        """
        try:
            # Open image
            image = Image.open(BytesIO(img_bytes))
            
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if too large (max 2048px on longest side for better API performance)
            max_size = 2048
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to PNG bytes
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_bytes_png = buffered.getvalue()
            
            # Encode to base64
            img_base64 = base64.b64encode(img_bytes_png).decode()
            
            return img_base64
            
        except Exception as e:
            raise Exception(f"Failed to process image: {str(e)}")
    
    def _extract_with_openai(self, images_base64: List[str]) -> Dict:
        """
        Extract invoice data using OpenAI Vision API (supports multiple pages)
        
        Args:
            images_base64: List of base64-encoded images
            
        Returns:
            dict: Extracted invoice data
        """
        try:
            prompt = self._get_extraction_prompt()
            
            # Build content array with text prompt and all images
            content = [{"type": "text", "text": prompt}]
            
            # Add all pages as images
            for idx, img_base64 in enumerate(images_base64):
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}",
                        "detail": "high"  # High detail for better text extraction
                    }
                })
            
            # Call OpenAI Vision API with increased token limit
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Using gpt-4o for better accuracy
                messages=[
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                max_tokens=4096,  # Increased from 1500 to handle multi-page documents
                temperature=0  # Deterministic output
            )
            
            # Get response content
            result = response.choices[0].message.content.strip()
            
            # Clean markdown code blocks if present
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
                result = result.strip()
            
            # Parse JSON
            invoice_data = json.loads(result)
            
            return invoice_data
            
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse AI response as JSON: {e}\nResponse: {result}")
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _get_extraction_prompt(self) -> str:
        """
        Get the extraction prompt for OpenAI
        
        Returns:
            str: Extraction prompt
        """
        return """You are analyzing an invoice document that may span multiple pages. Extract the following information and return ONLY a valid JSON object.

IMPORTANT: If multiple pages are provided, scan ALL pages thoroughly to find the required information.

Required fields:
{
    "invoice_number": "string or null",
    "po_number": "string or null",
    "customer_name": "string or null",
    "dispatch_date": "YYYY-MM-DD format or null",
    "total_invoice_amount": number or null,
    "total_gst_amount": number or null,
    "billing_address": "string or null",
    "shipping_address": "string or null",
    "pincode": "string or null",
    "articles": ["array of article/item names as strings"]
}

CRITICAL INSTRUCTIONS FOR AMOUNTS:

⚠️ MOST IMPORTANT - READ CAREFULLY:

"total_invoice_amount" = TAXABLE AMOUNT ONLY (BEFORE TAX/GST IS ADDED)
- This is the BASE amount, SUBTOTAL, or TAXABLE VALUE
- This amount DOES NOT include GST/tax
- Look for labels like:
  * "Taxable Value" (most common in Indian invoices)
  * "Taxable Amount"
  * "Sub Total" / "Subtotal"
  * "Amount Before Tax"
  * In the tax summary table, find the "Taxable Value" row
- DO NOT use "Total", "Grand Total", "Net Payable", "Amount Payable" - these include tax!

"total_gst_amount" = TAX AMOUNT ONLY
- Look for:
  * "IGST" / "CGST + SGST" / "GST Amount"
  * "Total Tax" / "Tax Amount"
  * In tax summary table, the GST/Tax column
- If CGST and SGST shown separately, add them together

AMOUNT EXTRACTION EXAMPLES:

Invoice shows:
  Taxable Value: ₹93,558.64
  IGST @ 12%: ₹11,227.04
  Grand Total: ₹1,04,786.00

CORRECT:
  "total_invoice_amount": 93558.64  ← The taxable value (before GST)
  "total_gst_amount": 11227.04      ← The GST amount

WRONG (Do not do this):
  "total_invoice_amount": 104786.00  ← This is WRONG! This is Grand Total (includes GST)

WHERE TO FIND THESE VALUES:
1. Look for a "Tax Summary" or "HSN/SAC" table (usually on last page)
2. In this table, find columns like "Taxable Value" and "GST/Tax Amount"
3. The "Taxable Value" column = total_invoice_amount
4. The "GST Amount" or "Tax Amount" column = total_gst_amount

FOR INVOICE NUMBER:
- Look for labels: "Invoice No", "Invoice Number", "Invoice #", "Bill No", "INV No", "Tax Invoice No"
- Usually found in the header of the first page
- Extract the complete alphanumeric code

FOR PO NUMBER:
- Look for labels: "PO Number", "P.O. Number", "Purchase Order", "PO No", "P.O. No", "PO#", "Order No", "Order Number", "Ref No", "Reference No", "Buyer's Order No"
- Search CAREFULLY across ALL pages in header, footer, and table sections
- Extract the complete alphanumeric code
- Common locations: near invoice number, in header, in order details section, in terms section
- This field is CRITICAL - search thoroughly before returning null

NUMBER FORMAT RULES:
- Extract as PURE NUMBERS ONLY
- Remove ALL currency symbols: ₹, Rs, INR, Rs., ₹., $
- Remove ALL commas: 1,00,000 → 100000
- Remove ALL spaces
- Keep decimals: 59000.50
- Example conversions:
  * "₹ 93,558.64" → 93558.64
  * "Rs. 1,25,000/-" → 125000
  * "INR 2,47,500.00" → 247500.00

FOR CUSTOMER NAME:
- Look for: "Bill To", "Customer Name", "Party Name", "Sold To", "Buyer", "Customer", "Billed To"
- Usually in the top section of first page
- Extract full company/person name
- Convert to UPPERCASE

FOR DATES:
- Look for: "Date", "Invoice Date", "Dispatch Date", "Bill Date", "Doc Date", "Dated"
- Convert to YYYY-MM-DD format
- Common formats to convert:
  * DD/MM/YYYY → YYYY-MM-DD
  * DD-MM-YYYY → YYYY-MM-DD
  * DD.MM.YYYY → YYYY-MM-DD
  * DD-MMM-YY → YYYY-MM-DD (e.g., 31-Aug-25 → 2025-08-31)

FOR ADDRESSES:
- "billing_address": Look for "Bill To", "Billing Address", "Buyer Address", "Customer Address", "Buyer (Bill to)"
- "shipping_address": Look for "Ship To", "Shipping Address", "Delivery Address", "Consignee", "Dispatch To", "Consignee (Ship to)"
- Include complete address with street, city, state
- Convert to UPPERCASE
- If shipping address not found separately, it may be same as billing address

FOR PINCODE:
- Extract 6-digit Indian postal code
- Look near addresses or separately labeled as "PIN", "Pincode", "Postal Code", "Pin Code"
- Format: XXXXXX (6 digits)

FOR ARTICLES (ITEMS):
- Look for item/product tables in the invoice
- Common table headers: "Description", "Item Description", "Product Name", "Article", "Particulars", "Items", "Product Details"
- Extract ALL item/article names from the invoice
- Convert each article name to UPPERCASE
- Return as an array of strings: ["ITEM 1", "ITEM 2", "ITEM 3"]
- If multiple quantities of same item, list it only once
- Include full product description/name
- Examples:
  * "Premium Wheat Flour 1kg" → "PREMIUM WHEAT FLOUR 1KG"
  * "Sugar White Refined 25kg" → "SUGAR WHITE REFINED 25KG"
  * "Cooking Oil Sunflower 1L" → "COOKING OIL SUNFLOWER 1L"
- If no items found, return empty array: []

MULTI-PAGE HANDLING:
- Page 1 usually contains: Invoice number, dates, addresses, customer details, item details
- Last page usually contains: Tax summary table with Taxable Value, final totals, grand total
- Scan ALL pages for complete information
- The tax summary table with "Taxable Value" is usually on the last page

VALIDATION:
- taxable_value + gst_amount ≈ grand_total
- Typical GST rates: 5%, 12%, 18%, 28%
- total_invoice_amount should be LESS than grand total
- total_gst_amount should be LESS than total_invoice_amount

IMPORTANT RULES:
- Scan ALL provided pages thoroughly
- Focus on finding the "Taxable Value" in tax summary tables
- Return ONLY the JSON object, no explanations
- If a field is not found after thorough search across all pages, return null

Example 1 (Standard GST Invoice):
Document shows:
Items:
  1. Premium Wheat Flour 1kg - Qty: 100
  2. Sugar White Refined 25kg - Qty: 50
HSN/SAC Table:
  Taxable Value: 50,000
  CGST @ 9%: 4,500
  SGST @ 9%: 4,500
  Total Tax: 9,000
Grand Total: 59,000

Output:
{
    "invoice_number": "INV-2025-001",
    "po_number": "PO-123456",
    "customer_name": "ABC ENTERPRISES",
    "dispatch_date": "2025-10-10",
    "total_invoice_amount": 50000.00,
    "total_gst_amount": 9000.00,
    "billing_address": "123 MAIN STREET, MUMBAI, MAHARASHTRA",
    "shipping_address": "456 DELIVERY AVENUE, MUMBAI, MAHARASHTRA",
    "pincode": "400001",
    "articles": ["PREMIUM WHEAT FLOUR 1KG", "SUGAR WHITE REFINED 25KG"]
}

Example 2 (IGST Invoice):
Document shows:
Items:
  1. Fresh Apples Red Delicious 10kg
  2. Green Grapes Premium 5kg
Tax Summary:
  HSN: 08041020
  Taxable Value: 93,558.64
  IGST Rate: 12%
  IGST Amount: 11,227.04
Total: 1,04,786.00

Output:
{
    "invoice_number": "CND/25-26/4981",
    "po_number": "5110917314",
    "customer_name": "RELIANCE RETAIL LIMITED",
    "dispatch_date": "2025-08-31",
    "total_invoice_amount": 93558.64,
    "total_gst_amount": 11227.04,
    "billing_address": "NO. 62/2, RIL BUILDING, RICHMOND ROAD, BANGALORE 560025, KARNATAKA",
    "shipping_address": "SY NO 14/2 15/4, ADAKAMARANAHALLI VILLAGE, BANGALORE, KARNATAKA - 562123",
    "pincode": "562123",
    "articles": ["FRESH APPLES RED DELICIOUS 10KG", "GREEN GRAPES PREMIUM 5KG"]
}

Example 3 (Simple Invoice):
Document shows:
Items:
  - Laptop Dell Inspiron 15 3000 Series
  - Wireless Mouse Logitech M185
  - Laptop Bag Targus Classic 15.6"
  Subtotal: Rs 2,00,000.00
  IGST @ 18%: Rs 36,000.00
  Invoice Total: Rs 2,36,000.00

Output:
{
    "invoice_number": "TAX-INV-2025-003",
    "po_number": "PO/2025/789",
    "customer_name": "PQR SOLUTIONS PRIVATE LIMITED",
    "dispatch_date": "2025-10-08",
    "total_invoice_amount": 200000.00,
    "total_gst_amount": 36000.00,
    "billing_address": "TOWER A, CYBER CITY, GURUGRAM, HARYANA",
    "shipping_address": "WAREHOUSE 12, SECTOR 15, NOIDA, UP",
    "pincode": "201301",
    "articles": ["LAPTOP DELL INSPIRON 15 3000 SERIES", "WIRELESS MOUSE LOGITECH M185", "LAPTOP BAG TARGUS CLASSIC 15.6\""]
}"""
    
    def _clean_extracted_data(self, data: Dict) -> Dict:
        """
        Clean and validate extracted data
        
        Args:
            data: Raw extracted data
            
        Returns:
            dict: Cleaned data
        """
        cleaned = {}
        
        # String fields - convert to uppercase if not None
        string_fields = [
            "invoice_number", "po_number", "customer_name",
            "billing_address", "shipping_address", "pincode"
        ]
        
        for field in string_fields:
            value = data.get(field)
            if value and isinstance(value, str):
                cleaned[field] = value.strip().upper()
            else:
                cleaned[field] = None
        
        # Date field
        dispatch_date = data.get("dispatch_date")
        if dispatch_date and isinstance(dispatch_date, str):
            cleaned["dispatch_date"] = dispatch_date.strip()
        else:
            cleaned["dispatch_date"] = None
        
        # Numeric fields - handle various formats
        numeric_fields = ["total_invoice_amount", "total_gst_amount"]
        
        for field in numeric_fields:
            value = data.get(field)
            if value is not None:
                try:
                    # If already a number, use it
                    if isinstance(value, (int, float)):
                        cleaned[field] = float(value)
                    # If string, clean and convert
                    elif isinstance(value, str):
                        # Remove currency symbols, spaces, and commas
                        cleaned_value = value.strip()
                        # Remove common currency symbols and text
                        for symbol in ['₹', 'Rs', 'INR', 'Rs.', '₹.', '$', '/-']:
                            cleaned_value = cleaned_value.replace(symbol, '')
                        cleaned_value = cleaned_value.replace(',', '').replace(' ', '')
                        # Remove any remaining non-numeric characters except decimal point
                        cleaned_value = ''.join(c for c in cleaned_value if c.isdigit() or c == '.')
                        if cleaned_value:
                            cleaned[field] = float(cleaned_value)
                        else:
                            cleaned[field] = None
                    else:
                        cleaned[field] = None
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to convert {field} value '{value}': {e}")
                    cleaned[field] = None
            else:
                cleaned[field] = None
        
        # Articles array - ensure uppercase
        articles = data.get("articles")
        if articles and isinstance(articles, list):
            cleaned_articles = []
            for article in articles:
                if article and isinstance(article, str):
                    cleaned_articles.append(article.strip().upper())
            cleaned["articles"] = cleaned_articles
        else:
            cleaned["articles"] = []
        
        # Validation: total_invoice_amount should be less than grand total
        if (cleaned.get("total_invoice_amount") is not None and 
            cleaned.get("total_gst_amount") is not None):
            if cleaned["total_invoice_amount"] < cleaned["total_gst_amount"]:
                logger.warning(
                    f"Validation warning: total_invoice_amount ({cleaned['total_invoice_amount']}) "
                    f"is less than total_gst_amount ({cleaned['total_gst_amount']}). "
                    "This may indicate incorrect extraction."
                )
            
            # Calculate expected grand total
            expected_grand_total = cleaned["total_invoice_amount"] + cleaned["total_gst_amount"]
            logger.info(
                f"Invoice breakdown - Taxable: {cleaned['total_invoice_amount']}, "
                f"GST: {cleaned['total_gst_amount']}, "
                f"Expected Grand Total: {expected_grand_total}"
            )
        
        # Log articles count
        if cleaned.get("articles"):
            logger.info(f"Extracted {len(cleaned['articles'])} article(s): {cleaned['articles']}")
        
        return cleaned


# Singleton instance
_service_instance: Optional[InvoiceExtractionService] = None


def get_invoice_extraction_service(api_key: Optional[str] = None) -> InvoiceExtractionService:
    """
    Get singleton instance of InvoiceExtractionService
    
    Args:
        api_key: OpenAI API key (optional)
        
    Returns:
        InvoiceExtractionService: Service instance
    """
    global _service_instance
    
    if _service_instance is None or api_key:
        _service_instance = InvoiceExtractionService(api_key)
    
    return _service_instance
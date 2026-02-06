"""
API Router for PDF extraction operations using Claude Sonnet 4.5.
Extracts structured purchase order data from PDF files.
"""

import logging
from typing import Union
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.services.pdf_extraction import PDFExtractionService
from app.schemas.pdf_extraction import PDFExtractionResponse, PDFExtractionErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pdf-extraction",
    tags=["PDF Extraction"]
)


@router.post(
    "/extract-purchase-order",
    response_model=PDFExtractionResponse,
    summary="Extract structured data from PDF purchase order",
    description="""
    Upload a PDF purchase order document and extract structured data using Claude Sonnet 4.5.

    **Extracts the following information:**
    - Purchase Order details (number, dates, validity)
    - Buyer information (name, address, GSTIN, state)
    - Supplier information (name, address, GSTIN, state)
    - Shipping information (ship to name, address, state)
    - Logistics information (freight by, dispatch by, indentor)
    - Items list with descriptions, HSN codes, quantities, prices, and tax details

    **File Requirements:**
    - Must be a PDF file
    - Maximum file size: 10MB
    - File should contain purchase order information in readable format

    **Response:**
    - All text fields are returned in CAPITAL CASE
    - Dates are returned in ISO format (YYYY-MM-DD)
    - Items are returned as an array with all found items
    - Missing fields are returned as null

    **Example Usage:**
    ```bash
    curl -X POST "http://localhost:8000/api/pdf-extraction/extract-purchase-order" \\
         -H "Content-Type: multipart/form-data" \\
         -F "file=@purchase_order.pdf"
    ```
    """,
    responses={
        200: {
            "description": "Successfully extracted structured data from PDF",
            "model": PDFExtractionResponse
        },
        400: {
            "description": "Invalid file or request",
            "model": PDFExtractionErrorResponse
        },
        422: {
            "description": "File processing error",
            "model": PDFExtractionErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": PDFExtractionErrorResponse
        }
    }
)
async def extract_purchase_order(
    file: UploadFile = File(
        ...,
        description="PDF file containing purchase order to extract data from"
    )
) -> Union[PDFExtractionResponse, JSONResponse]:
    """
    Extract structured purchase order data from uploaded PDF file.

    Args:
        file: Uploaded PDF file containing purchase order

    Returns:
        PDFExtractionResponse with extracted structured data

    Raises:
        HTTPException: For various error conditions
    """
    
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        logger.warning(f"Invalid file type uploaded: {file.filename}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Invalid file type",
                "details": "Only PDF files are supported"
            }
        )

    # Validate file size (10MB limit)
    max_size = 10 * 1024 * 1024  # 10MB
    if file.size and file.size > max_size:
        logger.warning(f"File too large: {file.size} bytes")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "File too large",
                "details": f"Maximum file size is {max_size // (1024*1024)}MB"
            }
        )

    # Validate file has content
    if not file.size or file.size == 0:
        logger.warning("Empty file uploaded")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Empty file",
                "details": "Uploaded file is empty"
            }
        )

    try:
        logger.info(f"Processing PDF extraction for file: {file.filename}")
        
        # Initialize PDF extraction service
        try:
            extraction_service = PDFExtractionService()
        except ValueError as e:
            logger.error(f"Service initialization failed: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Service configuration error",
                    "details": "Claude API key not configured properly"
                }
            )

        # Process the PDF file
        try:
            extracted_data = extraction_service.process_pdf(file.file)
            logger.info(f"Successfully extracted data from {file.filename}")
            return extracted_data

        except Exception as e:
            logger.error(f"PDF processing failed for {file.filename}: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": "PDF processing failed",
                    "details": str(e)
                }
            )

    except Exception as e:
        logger.error(f"Unexpected error processing {file.filename}: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "details": "An unexpected error occurred while processing the file"
            }
        )

    finally:
        # Ensure file is closed
        try:
            await file.close()
        except Exception:
            pass


@router.get(
    "/health",
    summary="Check PDF extraction service health",
    description="Check if the PDF extraction service is properly configured and ready to use.",
    responses={
        200: {"description": "Service is healthy and ready"},
        500: {"description": "Service configuration error"}
    }
)
async def health_check() -> JSONResponse:
    """
    Check if PDF extraction service is properly configured.

    Returns:
        JSONResponse indicating service health status
    """
    try:
        # Try to initialize the service to check configuration
        PDFExtractionService()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "service": "PDF Extraction Service",
                "message": "Claude Sonnet 4.5 API is configured and ready"
            }
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "unhealthy",
                "service": "PDF Extraction Service",
                "error": str(e)
            }
        )
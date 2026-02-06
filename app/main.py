from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    sku,
    inward,
    outward,
    approval,
    auth,
    openfga,
    permissions,
    label,
    dropdown,
    interunit,
    consumption,
    transfer,
    alerts_recipients,
    rtv,
    complaints,
    purchase,
    purchase_approval,
    item_catalog,
    pdf_extraction,
    whatsapp,
)
import uvicorn
# Import all models so they're registered with Base
from app.models import (
    PurchaseOrder,
    POItem,
    POItemBox,
    PurchaseApproval,
    PurchaseApprovalItem,
    PurchaseApprovalBox,
    CFPLItem,
    CDPLItem,
)

app = FastAPI(title="Inventory Management API", version="1.0.0")

# CORS Configuration
if settings.API_CORS_ORIGINS and settings.API_CORS_ORIGINS.strip() == "*":
    # Allow all origins (credentials must be False)
    origins = ["*"]
    allow_credentials = False
else:
    # Specific origins (credentials can be True)
    origins = [
        "http://localhost:3000",
        "http://localhost:4000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4000",
    ]
    
    if settings.API_CORS_ORIGINS:
        additional_origins = [o.strip() for o in settings.API_CORS_ORIGINS.split(",") if o.strip()]
        origins.extend(additional_origins)
    
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Inventory Management API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Inventory Management API is running"}

# Include routers
app.include_router(auth.router)
app.include_router(permissions.router)
app.include_router(sku.router)
app.include_router(inward.router)
app.include_router(outward.router)  # Outward management
app.include_router(approval.router)  # Approval management
# app.include_router(qr.router)  # QR endpoints removed - not in use
app.include_router(openfga.router)
app.include_router(label.router)
app.include_router(dropdown.router)  # Customer & Vendor dropdowns
app.include_router(interunit.router)  # Interunit transfer management
app.include_router(consumption.router)  # Consumption backend management
app.include_router(transfer.router)  # Transfer module management
app.include_router(alerts_recipients.router)  # Alerts recipients management
app.include_router(rtv.router)  # RTV (Return to Vendor) management
app.include_router(complaints.router)  # Complaints (QA) management
app.include_router(purchase.router)  # Purchase Orders management
app.include_router(purchase_approval.router)  # Purchase Approval management
app.include_router(item_catalog.router)  # Item Catalog management
app.include_router(pdf_extraction.router)  # PDF Extraction service
app.include_router(whatsapp.router)  # WhatsApp integration


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
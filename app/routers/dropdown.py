from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from app.core.database import get_db
from app.schemas.customer import (
    CustomerDropdownQuery, CustomerDropdownResponse,
    CustomerOption, CustomerMeta
)
from app.schemas.vendor import (
    VendorDropdownQuery, VendorDropdownResponse,
    SelectedVendorState, VendorAutoSelection,
    ResolvedFromVendor, ResolvedFromLocation,
    VendorOptions, VendorMeta
)

router = APIRouter(prefix="/api/dropdown", tags=["dropdown"])
logger = logging.getLogger(__name__)

# ==================== CUSTOMER DROPDOWN ====================

@router.get("/customers", response_model=CustomerDropdownResponse)
def get_customers_dropdown(
    search: str | None = Query(None, description="Search customer names"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Get customers dropdown list with optional search and pagination
    
    **Query Parameters:**
    - search: Optional search term to filter customer names
    - limit: Maximum number of results (default: 100, max: 1000)
    - offset: Pagination offset (default: 0)
    
    **Response:**
    - customers: List of customer objects with id and customer_name
    - meta: Metadata including total count and pagination info
    """
    try:
        # Normalize search term
        search_term = search.strip() if search else None
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        if search_term:
            where_clauses.append("LOWER(customer_name) LIKE :search")
            params["search"] = f"%{search_term.lower()}%"
        
        where_sql = " AND ".join(where_clauses)
        
        # Count total customers
        count_sql = text(f"""
            SELECT COUNT(*)
            FROM customers
            WHERE {where_sql}
        """)
        total_customers = db.execute(count_sql, params).scalar_one()
        
        # Get paginated customers
        customers_sql = text(f"""
            SELECT id, customer_name
            FROM customers
            WHERE {where_sql}
            ORDER BY customer_name ASC
            LIMIT :limit OFFSET :offset
        """)
        
        results = db.execute(
            customers_sql, 
            {**params, "limit": limit, "offset": offset}
        ).fetchall()
        
        # Format response
        customers = [
            CustomerOption(id=row[0], customer_name=row[1])
            for row in results
        ]
        
        meta = {
            "total_customers": total_customers,
            "limit": limit,
            "offset": offset,
            "search": search_term
        }
        
        logger.info(f"Retrieved {len(customers)} customers (total: {total_customers})")
        
        return CustomerDropdownResponse(
            customers=customers,
            meta=meta
        )
        
    except Exception as e:
        logger.error(f"Error fetching customers dropdown: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch customers: {str(e)}")


@router.get("/customers/{customer_id}")
def get_customer_by_id(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """Get specific customer by ID"""
    try:
        sql = text("""
            SELECT id, customer_name
            FROM customers
            WHERE id = :customer_id
        """)
        
        result = db.execute(sql, {"customer_id": customer_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Customer with id {customer_id} not found")
        
        return {
            "id": result[0],
            "customer_name": result[1]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch customer: {str(e)}")


# ==================== VENDOR DROPDOWN ====================

@router.get("/vendors", response_model=VendorDropdownResponse)
def get_vendors_dropdown(
    vendor_name: str | None = Query(None, description="Selected vendor name (auto-fills location)"),
    location: str | None = Query(None, description="Selected location (filters vendors)"),
    search: str | None = Query(None, description="Search term for vendors"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Get vendors dropdown with auto-selection logic
    
    **Auto-Selection Logic:**
    1. When vendor_name is selected → location is auto-filled
    2. When location is selected → list of vendors for that location is shown
    
    **Query Parameters:**
    - vendor_name: Selected vendor (will auto-fill location)
    - location: Selected location (will filter vendors)
    - search: Search term to filter vendor names
    - limit: Maximum results (default: 100, max: 1000)
    - offset: Pagination offset (default: 0)
    
    **Response Structure:**
    - selected: Current selections (vendor_name, location)
    - auto_selection: Auto-filled values based on selections
    - options: Available dropdown options (vendor_names, locations)
    - meta: Metadata (counts, pagination)
    """
    try:
        # Normalize inputs
        vendor_name = vendor_name.strip() if vendor_name else None
        location = location.strip() if location else None
        search_term = search.strip() if search else None
        
        # Get all unique locations (for dropdown)
        locations_sql = text("""
            SELECT DISTINCT location
            FROM vendors
            WHERE location IS NOT NULL
            ORDER BY location ASC
        """)
        all_locations = db.execute(locations_sql).scalars().all()
        
        # Get vendor names and IDs based on filters
        vendor_where_clauses = ["1=1"]
        vendor_params = {}
        
        if location:
            vendor_where_clauses.append("location = :location")
            vendor_params["location"] = location
        
        if search_term:
            vendor_where_clauses.append("LOWER(vendor_name) LIKE :search")
            vendor_params["search"] = f"%{search_term.lower()}%"
        
        vendor_where_sql = " AND ".join(vendor_where_clauses)
        
        # Count total vendors
        count_sql = text(f"""
            SELECT COUNT(DISTINCT vendor_name)
            FROM vendors
            WHERE {vendor_where_sql}
        """)
        total_vendors = db.execute(count_sql, vendor_params).scalar_one()
        
        # Get paginated vendor names
        vendors_sql = text(f"""
            SELECT DISTINCT id, vendor_name, location
            FROM vendors
            WHERE {vendor_where_sql}
            ORDER BY vendor_name ASC
            LIMIT :limit OFFSET :offset
        """)
        
        vendor_results = db.execute(
            vendors_sql,
            {**vendor_params, "limit": limit, "offset": offset}
        ).fetchall()
        
        vendor_names = [row[1] for row in vendor_results]
        vendor_ids = [row[0] for row in vendor_results]
        
        # Auto-selection logic: Resolve location from vendor_name
        resolved_from_vendor = ResolvedFromVendor()
        if vendor_name:
            try:
                resolve_sql = text("""
                    SELECT location
                    FROM vendors
                    WHERE vendor_name = :vendor_name
                    LIMIT 1
                """)
                result = db.execute(resolve_sql, {"vendor_name": vendor_name}).fetchone()
                
                if result:
                    resolved_from_vendor.location = result[0]
                    logger.info(f"Auto-resolved location '{result[0]}' for vendor '{vendor_name}'")
                    
            except Exception as e:
                logger.warning(f"Error resolving location from vendor: {e}")
        
        # Auto-selection logic: Get vendors for selected location
        resolved_from_location = ResolvedFromLocation()
        if location:
            try:
                location_vendors_sql = text("""
                    SELECT DISTINCT vendor_name
                    FROM vendors
                    WHERE location = :location
                    ORDER BY vendor_name ASC
                """)
                location_vendor_results = db.execute(
                    location_vendors_sql, 
                    {"location": location}
                ).scalars().all()
                
                resolved_from_location.vendor_names = list(location_vendor_results)
                logger.info(f"Found {len(resolved_from_location.vendor_names)} vendors for location '{location}'")
                
            except Exception as e:
                logger.warning(f"Error resolving vendors from location: {e}")
        
        # Build response
        selected = SelectedVendorState(
            vendor_name=vendor_name,
            location=location
        )
        
        auto_selection = VendorAutoSelection(
            resolved_from_vendor=resolved_from_vendor,
            resolved_from_location=resolved_from_location
        )
        
        options = VendorOptions(
            vendor_names=vendor_names,
            locations=list(all_locations),
            vendor_ids=vendor_ids
        )
        
        meta = VendorMeta(
            total_vendors=total_vendors,
            total_locations=len(all_locations),
            limit=limit,
            offset=offset,
            search=search_term
        )
        
        logger.info(f"Retrieved vendors dropdown: {len(vendor_names)} vendors, {len(all_locations)} locations")
        
        return VendorDropdownResponse(
            selected=selected,
            auto_selection=auto_selection,
            options=options,
            meta=meta
        )
        
    except Exception as e:
        logger.error(f"Error fetching vendors dropdown: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch vendors: {str(e)}")


@router.get("/vendors/{vendor_id}")
def get_vendor_by_id(
    vendor_id: int,
    db: Session = Depends(get_db)
):
    """Get specific vendor by ID"""
    try:
        sql = text("""
            SELECT id, vendor_name, location
            FROM vendors
            WHERE id = :vendor_id
        """)
        
        result = db.execute(sql, {"vendor_id": vendor_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found")
        
        return {
            "id": result[0],
            "vendor_name": result[1],
            "location": result[2]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vendor {vendor_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch vendor: {str(e)}")


# ==================== DEBUG ENDPOINTS ====================

@router.get("/debug/customers/count")
def debug_customer_count(db: Session = Depends(get_db)):
    """Debug endpoint to check customer table"""
    try:
        count_sql = text("SELECT COUNT(*) FROM customers")
        count = db.execute(count_sql).scalar_one()
        
        sample_sql = text("SELECT id, customer_name FROM customers LIMIT 5")
        samples = db.execute(sample_sql).fetchall()
        
        return {
            "total_customers": count,
            "sample_customers": [
                {"id": row[0], "customer_name": row[1]}
                for row in samples
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug query failed: {str(e)}")


@router.get("/debug/vendors/count")
def debug_vendor_count(db: Session = Depends(get_db)):
    """Debug endpoint to check vendor table"""
    try:
        count_sql = text("SELECT COUNT(*) FROM vendors")
        count = db.execute(count_sql).scalar_one()
        
        locations_sql = text("SELECT DISTINCT location FROM vendors")
        locations = db.execute(locations_sql).scalars().all()
        
        sample_sql = text("SELECT id, vendor_name, location FROM vendors LIMIT 5")
        samples = db.execute(sample_sql).fetchall()
        
        return {
            "total_vendors": count,
            "total_locations": len(locations),
            "locations": list(locations),
            "sample_vendors": [
                {"id": row[0], "vendor_name": row[1], "location": row[2]}
                for row in samples
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug query failed: {str(e)}")


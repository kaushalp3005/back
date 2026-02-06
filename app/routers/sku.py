from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from app.core.database import get_db
from app.schemas.dropdown import (
    DropdownQuery, DropdownResponse,
    SelectedState, AutoSelection,
    ResolvedFromItem, ResolvedFromMaterialType, ResolvedFromCategorySub,
    Options, Meta
)

router = APIRouter(prefix="/sku", tags=["sku"])

def table_for_company(company: str) -> str:
    """Map company code to corresponding table name with validation"""
    company_upper = company.upper()
    if company_upper == "CFPL":
        return "cfplsku"
    elif company_upper == "CDPL":
        return "cdplsku"
    else:
        raise ValueError(f"Invalid company: {company}. Must be CFPL or CDPL")

@router.get("/dropdown", response_model=DropdownResponse)
def get_dropdown(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    material_type: str | None = None,
    item_description: str | None = None,
    item_category: str | None = None,
    sub_category: str | None = None,
    search: str | None = None,
    sort: str = "alpha",
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    # --- Normalize & validate company, trim inputs ---
    company = (company or "").upper()
    if company not in ("CFPL", "CDPL"):
        raise HTTPException(status_code=400, detail="company must be CFPL or CDPL")

    material_type = material_type.strip() if material_type else None
    item_description = item_description.strip() if item_description else None
    item_category = item_category.strip() if item_category else None
    sub_category = sub_category.strip() if sub_category else None
    search = search.strip() if search else None

    tbl = table_for_company(company)
    
    # Validate table name to prevent SQL injection
    valid_tables = {"cfplsku", "cdplsku"}
    if tbl not in valid_tables:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {tbl}")
    
    # Log the table being queried for debugging
    logging.info(f"Querying dropdown for company: {company} -> table: {tbl}")
    logging.info(f"Parameters: material_type={material_type}, item_category={item_category}, sub_category={sub_category}, search={search}")

    # --- Build base WHERE clause for company filtering ---
    base_where_clauses = ["1=1"]
    base_params = {}
    
    # Always add company filter if company column exists
    try:
        check_company_col_sql = text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{tbl}' AND column_name = 'company'
        """)
        has_company_col = db.execute(check_company_col_sql).fetchone()
        
        if has_company_col:
            base_where_clauses.append("company = :company")
            base_params["company"] = company
            logging.info(f"Added company filter: {company}")
    except Exception as e:
        logging.warning(f"Error checking company column: {e}")

    base_where_sql = " AND ".join(base_where_clauses)

    # --- Get all material types (only filtered by company) ---
    material_types_sql = text(f"""
        SELECT DISTINCT material_type
        FROM {tbl}
        WHERE {base_where_sql}
        ORDER BY material_type ASC
    """)
    material_types = db.execute(material_types_sql, base_params).scalars().all()

    # --- Get item categories (filtered by company and material_type if provided) ---
    item_categories = []
    if material_type:
        cat_where_clauses = base_where_clauses.copy()
        cat_params = base_params.copy()
        cat_where_clauses.append("UPPER(material_type) = UPPER(:material_type)")
        cat_params["material_type"] = material_type
        
        cat_where_sql = " AND ".join(cat_where_clauses)
        
        cats_sql = text(f"""
            SELECT DISTINCT item_category
            FROM {tbl}
            WHERE {cat_where_sql}
            ORDER BY item_category ASC
        """)
        item_categories = db.execute(cats_sql, cat_params).scalars().all()

    # --- Get sub categories (filtered by company, material_type, and item_category if provided) ---
    sub_categories = []
    if material_type and item_category:
        sub_where_clauses = base_where_clauses.copy()
        sub_params = base_params.copy()
        sub_where_clauses.append("UPPER(material_type) = UPPER(:material_type)")
        sub_where_clauses.append("UPPER(item_category) = UPPER(:item_cat)")
        sub_params["material_type"] = material_type
        sub_params["item_cat"] = item_category
        
        sub_where_sql = " AND ".join(sub_where_clauses)
        
        subs_sql = text(f"""
            SELECT DISTINCT sub_category
            FROM {tbl}
            WHERE {sub_where_sql}
            ORDER BY sub_category ASC
        """)
        sub_categories = db.execute(subs_sql, sub_params).scalars().all()

    # --- Get item descriptions (filtered by company, material_type, item_category, and sub_category if provided) ---
    item_descriptions = []
    item_ids = []
    total_item_descriptions = 0
    
    if material_type and item_category and sub_category:
        desc_where_clauses = base_where_clauses.copy()
        desc_params = base_params.copy()
        desc_where_clauses.append("UPPER(material_type) = UPPER(:material_type)")
        desc_where_clauses.append("UPPER(item_category) = UPPER(:item_cat)")
        desc_where_clauses.append("UPPER(sub_category) = UPPER(:sub_cat)")
        desc_params["material_type"] = material_type
        desc_params["item_cat"] = item_category
        desc_params["sub_cat"] = sub_category
        
        if search:
            desc_where_clauses.append("LOWER(item_description) LIKE :search")
            desc_params["search"] = f"%{search.lower()}%"
        
        desc_where_sql = " AND ".join(desc_where_clauses)
        
        # Count total descriptions
        total_desc_sql = text(f"""
            SELECT COUNT(DISTINCT item_description)
            FROM {tbl}
            WHERE {desc_where_sql}
        """)
        total_item_descriptions = db.execute(total_desc_sql, desc_params).scalar_one()

        # Get paginated descriptions with IDs and material_type
        desc_sql = text(f"""
            SELECT DISTINCT id, item_description, material_type
            FROM {tbl}
            WHERE {desc_where_sql}
            ORDER BY item_description ASC
            LIMIT :limit OFFSET :offset
        """)
        desc_rows = db.execute(
            desc_sql, {**desc_params, "limit": limit, "offset": offset}
        ).fetchall()

        item_descriptions = [row[1] for row in desc_rows]
        item_ids = [row[0] for row in desc_rows]
        material_types = [row[2] for row in desc_rows]

    # --- Resolve from item_description (auto-fill category & sub-category & material_type) ---
    resolved_from_item = ResolvedFromItem()
    if item_description:
        try:
            resolve_where_clauses = base_where_clauses.copy()
            resolve_params = base_params.copy()
            resolve_where_clauses.append("item_description = :desc")
            resolve_params["desc"] = item_description

            resolve_where_sql = " AND ".join(resolve_where_clauses)

            sql = text(f"""
                SELECT item_category, sub_category, material_type
                FROM {tbl}
                WHERE {resolve_where_sql}
                LIMIT 1
            """)
            row = db.execute(sql, resolve_params).fetchone()

            if row:
                resolved_from_item.material_type = row[2]
                resolved_from_item.item_category = row[0]
                resolved_from_item.sub_category = row[1]
        except Exception as e:
            logging.warning(f"Error resolving from item: {e}")

    total_material_types = len(material_types)
    total_categories = len(item_categories)
    total_sub_categories = len(sub_categories)

    # Get item categories for the selected material type
    resolved_from_material_type = ResolvedFromMaterialType(item_categories=item_categories)
    resolved_from_category_sub = ResolvedFromCategorySub(item_descriptions=item_descriptions)

    selected = SelectedState(
        material_type=material_type,
        item_description=item_description,
        item_category=item_category,
        sub_category=sub_category,
    )

    options = Options(
        material_types=material_types,
        item_descriptions=item_descriptions,
        item_categories=item_categories,
        sub_categories=sub_categories,
        item_ids=item_ids,
    )

    meta = Meta(
        total_material_types=total_material_types,
        total_item_descriptions=total_item_descriptions,
        total_categories=total_categories,
        total_sub_categories=total_sub_categories,
        limit=limit,
        offset=offset,
        sort="alpha",
        search=search,
    )

    return DropdownResponse(
        company=company,
        selected=selected,
        auto_selection=AutoSelection(
            resolved_from_item=resolved_from_item,
            resolved_from_material_type=resolved_from_material_type,
            resolved_from_category_sub=resolved_from_category_sub
        ),
        options=options,
        meta=meta
    )

@router.get("/global-search", response_model=dict)
def get_global_item_search(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    search: str | None = Query(None, description="Search term for item descriptions"),
    limit: int = Query(200, ge=1, le=10000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Global item description search - bypasses hierarchy
    
    **Purpose:**
    - Search across ALL item descriptions regardless of category/sub-category
    - When an item is selected, automatically provides category and sub-category
    - Perfect for quick item lookup without navigating hierarchy
    
    **Query Parameters:**
    - company: Company code (CFPL or CDPL)
    - search: Optional search term (partial match on item descriptions)
    - limit: Maximum results (default: 200, max: 10000)
    - offset: Pagination offset (default: 0)
    
    **Response:**
    - items: List of all item descriptions with full details
    - meta: Pagination and search metadata
    """
    try:
        # Normalize inputs
        company_upper = company.upper()
        search_term = search.strip() if search else None
        
        # Get table name
        tbl = table_for_company(company_upper)
        
        # Validate table name
        valid_tables = {"cfplsku", "cdplsku"}
        if tbl not in valid_tables:
            raise HTTPException(status_code=400, detail=f"Invalid table name: {tbl}")
        
        logging.info(f"Global search for company: {company_upper} -> table: {tbl}")
        if search_term:
            logging.info(f"Search term: '{search_term}'")
        
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = {}
        
        # Add company filter if company column exists
        try:
            check_company_col_sql = text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{tbl}' AND column_name = 'company'
            """)
            has_company_col = db.execute(check_company_col_sql).fetchone()
            
            if has_company_col:
                where_clauses.append("company = :company")
                params["company"] = company_upper
                logging.info(f"Added company filter: {company_upper}")
        except Exception as e:
            logging.warning(f"Error checking company column: {e}")
        
        # Add search filter if provided
        if search_term:
            where_clauses.append("LOWER(item_description) LIKE :search")
            params["search"] = f"%{search_term.lower()}%"
        
        where_sql = " AND ".join(where_clauses)
        
        # Count total items
        count_sql = text(f"""
            SELECT COUNT(DISTINCT item_description)
            FROM {tbl}
            WHERE {where_sql}
        """)
        total_items = db.execute(count_sql, params).scalar_one()
        
        # Get paginated items with full details
        items_sql = text(f"""
            SELECT DISTINCT id, item_description, material_type, item_category, sub_category
            FROM {tbl}
            WHERE {where_sql}
            ORDER BY item_description ASC
            LIMIT :limit OFFSET :offset
        """)

        items_rows = db.execute(
            items_sql, {**params, "limit": limit, "offset": offset}
        ).fetchall()

        # Format items
        items = []
        for row in items_rows:
            items.append({
                "id": row[0],
                "item_description": row[1],
                "material_type": row[2],
                "group": row[3],
                "sub_group": row[4]
            })
        
        # Build response
        response = {
            "company": company_upper,
            "items": items,
            "meta": {
                "total_items": total_items,
                "limit": limit,
                "offset": offset,
                "search": search_term,
                "has_more": (offset + limit) < total_items
            }
        }
        
        logging.info(f"Global search returned {len(items)} items (total: {total_items})")
        
        return response
        
    except Exception as e:
        logging.error(f"Error in global item search: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch items: {str(e)}")


@router.get("/test-filtering")
def test_filtering(company: str = Query(..., pattern="^(CFPL|CDPL)$")):
    """Test endpoint to verify company filtering logic without database"""
    company_upper = company.upper()
    tbl = table_for_company(company_upper)
    
    return {
        "message": f"Company filtering test for {company_upper}",
        "company": company_upper,
        "table": tbl,
        "status": "Filtering logic working correctly"
    }

@router.get("/debug/tables")
def debug_tables(db: Session = Depends(get_db)):
    """Debug endpoint to check data integrity between tables"""
    try:
        # Check CFPL table
        cfpl_count_sql = text("SELECT COUNT(*) FROM cfplsku")
        cfpl_count = db.execute(cfpl_count_sql).scalar_one()
        
        # Check CDPL table  
        cdpl_count_sql = text("SELECT COUNT(*) FROM cdplsku")
        cdpl_count = db.execute(cdpl_count_sql).scalar_one()
        
        # Get sample data from both tables
        cfpl_sample_sql = text("SELECT DISTINCT item_description FROM cfplsku LIMIT 5")
        cfpl_sample = db.execute(cfpl_sample_sql).scalars().all()
        
        cdpl_sample_sql = text("SELECT DISTINCT item_description FROM cdplsku LIMIT 5")
        cdpl_sample = db.execute(cdpl_sample_sql).scalars().all()
        
        # Check for data contamination - look for CFPL data in CDPL table and vice versa
        contamination_check = {}
        
        # Check if tables have company column
        cfpl_has_company_sql = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cfplsku' AND column_name = 'company'
        """)
        cfpl_has_company = db.execute(cfpl_has_company_sql).fetchone()
        
        cdpl_has_company_sql = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cdplsku' AND column_name = 'company'
        """)
        cdpl_has_company = db.execute(cdpl_has_company_sql).fetchone()
        
        if cfpl_has_company:
            # Check for CDPL data in CFPL table
            cfpl_cdpl_data_sql = text("SELECT COUNT(*) FROM cfplsku WHERE company = 'CDPL'")
            cfpl_cdpl_count = db.execute(cfpl_cdpl_data_sql).scalar_one()
            contamination_check["cfpl_table_has_cdpl_data"] = cfpl_cdpl_count
            
        if cdpl_has_company:
            # Check for CFPL data in CDPL table
            cdpl_cfpl_data_sql = text("SELECT COUNT(*) FROM cdplsku WHERE company = 'CFPL'")
            cdpl_cfpl_count = db.execute(cdpl_cfpl_data_sql).scalar_one()
            contamination_check["cdpl_table_has_cfpl_data"] = cdpl_cfpl_count
        
        # Get unique categories from both tables to check for overlap
        cfpl_categories_sql = text("SELECT DISTINCT item_category FROM cfplsku LIMIT 10")
        cfpl_categories = db.execute(cfpl_categories_sql).scalars().all()
        
        cdpl_categories_sql = text("SELECT DISTINCT item_category FROM cdplsku LIMIT 10")
        cdpl_categories = db.execute(cdpl_categories_sql).scalars().all()
        
        return {
            "cfpl_table": {
                "count": cfpl_count,
                "sample_descriptions": cfpl_sample,
                "sample_categories": cfpl_categories,
                "has_company_column": bool(cfpl_has_company)
            },
            "cdpl_table": {
                "count": cdpl_count, 
                "sample_descriptions": cdpl_sample,
                "sample_categories": cdpl_categories,
                "has_company_column": bool(cdpl_has_company)
            },
            "contamination_check": contamination_check,
            "analysis": {
                "cfpl_categories": cfpl_categories,
                "cdpl_categories": cdpl_categories,
                "category_overlap": list(set(cfpl_categories) & set(cdpl_categories))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug query failed: {str(e)}")

@router.get("/id")
def get_sku_id(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    item_description: str = Query(..., description="Item description to search for"),
    item_category: str | None = Query(None, description="Item category filter"),
    sub_category: str | None = Query(None, description="Sub category filter"),
    material_type: str | None = Query(None, description="Material type filter"),
    db: Session = Depends(get_db),
):
    """Get SKU ID for a specific item description"""
    # Normalize company
    company = company.upper()
    if company not in ("CFPL", "CDPL"):
        raise HTTPException(status_code=400, detail="company must be CFPL or CDPL")
    
    tbl = table_for_company(company)
    
    # Validate table name
    valid_tables = {"cfplsku", "cdplsku"}
    if tbl not in valid_tables:
        raise HTTPException(status_code=400, detail=f"Invalid table name: {tbl}")
    
    logging.info(f"Getting SKU ID for: company={company}, item_description={item_description}, material_type={material_type}")

    # Handle "other" in any dropdown field - return placeholder since there's no real SKU
    fields_to_check = [item_description, item_category, sub_category, material_type]
    if any(f and f.strip().lower() == "other" for f in fields_to_check):
        return {
            "sku_id": None,
            "id": None,
            "item_description": item_description,
            "material_type": material_type,
            "group": item_category,
            "sub_group": sub_category,
            "item_category": item_category,
            "sub_category": sub_category,
            "company": company
        }

    # Build where clause with case-insensitive matching
    where_clauses = ["UPPER(item_description) = UPPER(:desc)"]
    params = {"desc": item_description}
    
    # Add optional filters with case-insensitive matching
    if material_type:
        where_clauses.append("UPPER(material_type) = UPPER(:material_type)")
        params["material_type"] = material_type
    
    if item_category:
        where_clauses.append("UPPER(item_category) = UPPER(:cat)")
        params["cat"] = item_category
    
    if sub_category:
        where_clauses.append("UPPER(sub_category) = UPPER(:sub_category)")
        params["sub_category"] = sub_category
    
    # Check if table has company column and filter by company
    try:
        check_company_col_sql = text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{tbl}' AND column_name = 'company'
        """)
        has_company_col = db.execute(check_company_col_sql).fetchone()
        
        if has_company_col:
            where_clauses.append("company = :company")
            params["company"] = company
            logging.info(f"Added company filter: {company}")
    except Exception as e:
        logging.warning(f"Error checking company column: {e}")
    
    where_sql = " AND ".join(where_clauses)
    
    # Query for the SKU ID
    sql = text(f"""
        SELECT id, item_description, material_type, item_category, sub_category
        FROM {tbl}
        WHERE {where_sql}
        LIMIT 1
    """)

    try:
        logging.info(f"Executing SQL: {sql} with params: {params}")
        result = db.execute(sql, params).fetchone()
        if not result:
            logging.warning(f"SKU not found for item_description: {item_description}")
            raise HTTPException(
                status_code=404,
                detail=f"SKU not found for item_description: {item_description}"
            )

        response = {
            "sku_id": result[0],  # Frontend expects 'sku_id'
            "id": result[0],
            "item_description": result[1],
            "material_type": result[2],
            "group": result[3],
            "sub_group": result[4],
            "item_category": result[3],  # Alias for group
            "sub_category": result[4],   # Alias for sub_group
            "company": company
        }
        
        logging.info(f"Found SKU: {response}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error querying SKU ID: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
# File: inward.py
# Path: backend/app/routers/inward.py

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, conint, condecimal, ValidationError
from typing import List, Literal, Optional
from sqlalchemy import text, bindparam, or_, and_
from sqlalchemy.orm import Session
from app.core.database import get_db
import logging
import re
from datetime import datetime, date

router = APIRouter(prefix="/inward", tags=["inward"])

Company = Literal["CFPL", "CDPL"]

# ---------- Pydantic Schemas ----------
class TransactionIn(BaseModel):
    transaction_no: str
    entry_date: str
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    lr_number: Optional[str] = None
    vendor_supplier_name: Optional[str] = None
    customer_party_name: Optional[str] = None
    source_location: Optional[str] = None
    destination_location: Optional[str] = None
    challan_number: Optional[str] = None
    invoice_number: Optional[str] = None
    po_number: Optional[str] = None
    grn_number: Optional[str] = None
    grn_quantity: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    system_grn_date: Optional[str] = None
    purchase_by: Optional[str] = None
    service_invoice_number: Optional[str] = None
    dn_number: Optional[str] = None
    approval_authority: Optional[str] = None
    total_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    tax_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    discount_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    received_quantity: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    remark: Optional[str] = None
    currency: Optional[str] = "INR"

class ArticleIn(BaseModel):
    transaction_no: str
    sku_id: Optional[int] = None
    item_description: str
    item_category: Optional[str] = None
    sub_category: Optional[str] = None
    item_code: Optional[str] = None
    hsn_code: Optional[str] = None
    quality_grade: Optional[str] = None
    uom: Optional[str] = None
    packaging_type: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    quantity_units: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    net_weight: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    total_weight: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    import_date: Optional[str] = None
    unit_rate: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    total_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    tax_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    discount_amount: Optional[condecimal(max_digits=18, decimal_places=2)] = None
    currency: Optional[str] = "INR"
    # New fields for issuance tracking
    issuance_date: Optional[str] = None
    job_card_no: Optional[str] = None
    issuance_quantity: Optional[condecimal(max_digits=18, decimal_places=3)] = None

class BoxIn(BaseModel):
    transaction_no: str
    article_description: str
    box_number: conint(strict=True, ge=1)
    net_weight: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    gross_weight: Optional[condecimal(max_digits=18, decimal_places=3)] = None
    lot_number: Optional[str] = None
    count: Optional[conint(strict=True, ge=0)] = None

class InwardPayloadFlexible(BaseModel):
    """Flexible payload to handle both frontend and backend formats"""
    company: Company
    transaction: TransactionIn
    
    # Legacy format fields
    articles: Optional[List[ArticleIn]] = None
    boxes: Optional[List[BoxIn]] = None
    
    # New frontend format fields
    article_details: Optional[dict] = None
    ledger_details: Optional[dict] = None
    
    def model_post_init(self, __context) -> None:
        """Transform frontend format to backend format after model creation"""
        if self.article_details is not None and self.ledger_details is not None:
            if self.articles is None and self.boxes is None:
                # Transform to legacy format
                self.articles, self.boxes = self.create_articles_and_boxes()
        
        # Validate required fields
        if not self.articles or not self.boxes:
            raise ValueError("articles and boxes are required")

    def create_articles_and_boxes(self) -> tuple[List[ArticleIn], List[BoxIn]]:
        """Transform frontend article_details and ledger_details into legacy articles and boxes"""
        if not (self.article_details and self.ledger_details):
            raise ValueError("article_details and ledger_details are required")

        # Use provided SKU ID - None is allowed for "other" items
        sku_id = self.article_details.get("sku_id")

        # NOTE: item_description is NOT auto-filled from AI extraction payload
        # It must be provided explicitly by the user in the form
        item_description = self.article_details.get("item_description")
        if not item_description:
            raise ValueError("item_description is required and must be provided by the user")

        article = ArticleIn(
            transaction_no=self.transaction.transaction_no,
            sku_id=sku_id,
            item_description=item_description,
            item_category=self.article_details.get("item_category"),
            sub_category=self.article_details.get("sub_group_cd"),
            quantity_units=self.ledger_details.get("received_quantity"),
            net_weight=self.ledger_details.get("net_weight"),
            total_weight=self.ledger_details.get("gross_weight"),
            batch_number=self.ledger_details.get("batch_number"),
            lot_number=self.ledger_details.get("lot_number"),
            manufacturing_date=self.ledger_details.get("manufacturing_date"),
            expiry_date=self.ledger_details.get("expiry_date"),
            unit_rate=self.ledger_details.get("supplier_rate") or self.ledger_details.get("inward_rate"),
            total_amount=0.0,
            tax_amount=0.0,
            discount_amount=0.0,
            currency=self.transaction.currency or "INR"
        )

        box = BoxIn(
            transaction_no=self.transaction.transaction_no,
            article_description=item_description,
            box_number=1,
            net_weight=self.ledger_details.get("net_weight"),
            gross_weight=self.ledger_details.get("gross_weight"),
            lot_number=self.ledger_details.get("lot_number"),
            count=self.ledger_details.get("count")
        )

        return [article], [box]



# Legacy class for backward compatibility  
class InwardPayload(BaseModel):
    company: Company
    transaction: TransactionIn
    articles: List[ArticleIn]
    boxes: List[BoxIn]

# Response models for listing
class InwardListItem(BaseModel):
    transaction_id: str
    batch_number: Optional[str] = None
    entry_date: str
    invoice_number: Optional[str] = None
    po_number: Optional[str] = None
    item_descriptions: List[str]
    quantities_and_uoms: List[str]

class InwardListResponse(BaseModel):
    records: List[InwardListItem]
    total: int
    page: int
    per_page: int

# ---------- Helpers ----------
def table_names(company: Company):
    prefix = "cfpl" if company == "CFPL" else "cdpl"
    return {
        "tx": f"{prefix}_transactions",
        "art": f"{prefix}_articles",
        "box": f"{prefix}_boxes",
        "sku": f"{prefix}sku",
    }

def get_sku_name_column(db: Session, table_name: str) -> str:
    """Detect the correct column name for SKU item name"""
    try:
        check_sql = text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name IN ('item_name', 'name', 'sku_name', 'description', 'item_description')
            LIMIT 1
        """)
        result = db.execute(check_sql, {"table_name": table_name}).fetchone()
        if result:
            column_name = result[0]
            logging.info(f"Detected SKU name column: {column_name}")
            return column_name
    except Exception as e:
        logging.warning(f"Could not detect SKU column name: {e}")
    
    # Default fallback
    logging.info("Using default SKU column name: 'name'")
    return 'name'

def clean_date_fields(data: dict) -> dict:
    """Convert empty strings to None for date fields"""
    date_fields = ['system_grn_date', 'manufacturing_date', 'expiry_date', 'import_date']
    cleaned_data = data.copy()
    for field in date_fields:
        if field in cleaned_data and cleaned_data[field] == '':
            cleaned_data[field] = None
    return cleaned_data

def format_date_for_frontend(date_value) -> Optional[str]:
    """Format date values for frontend consumption"""
    if date_value is None:
        return None
    
    try:
        from datetime import datetime
        
        # Handle different date types
        if isinstance(date_value, str):
            cleaned_date = date_value.strip()
            
            # Special handling for your exact format "2025-09-23 23:56:55+00"
            # Check if matches: YYYY-MM-DD HH:MM:SS+XX
            if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{2}', cleaned_date):
                try:
                    # Extract just the date part (before first space)
                    date_part = cleaned_date.split(' ')[0]
                    dt = datetime.strptime(date_part, '%Y-%m-%d')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass
            
            # Try parsing as timestamp with timezone offset
            try:
                # Handle "+00" timezone format by converting to standard offset
                if '+' in cleaned_date and len(cleaned_date.split('+')[1]) == 2:
                    # "2025-09-23 23:56:55+00" → "2025-09-23 23:56:55+0000"
                    cleaned_date = cleaned_date.replace('+00', '+0000', 1)
                
                # Handle "-00" timezone format
                if '-' in cleaned_date and '(' not in cleaned_date and len(cleaned_date.split('-')[-1]) == 2:
                    # Only if it looks like timezone format at end
                    last_part = cleaned_date.split('-')[-1]
                    if len(cleaned_date.split('-')[-1]) == 2 and not any(c in last_part for c in [' ', '+']):
                        cleaned_date = cleaned_date.replace(last_part, '00' + last_part[-2:])
                
                # Try various timestamp formats
                timestamp_formats = [
                    '%Y-%m-%d %H:%M:%S%z',     # "2025-09-23 23:56:55+0000"
                    '%Y-%m-%d %H:%M:%S',       # "2025-09-23 23:56:55"
                    '%Y-%m-%dT%H:%M:%S%z',     # "2025-09-23T23:56:55+0000"
                    '%Y-%m-%dT%H:%M:%S',       # "2025-09-23T23:56:55"
                    '%Y-%m-%dT%H:%M:%SZ',     # "2025-09-23T23:56:55Z"
                ]
                
                for fmt in timestamp_formats:
                    try:
                        parsed_date = datetime.strptime(cleaned_date, fmt)
                        return parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
            except Exception:
                pass
            
            # Simple date extraction fallback
            if ' ' in cleaned_date and re.match(r'\d{4}-\d{2}-\d{2}', cleaned_date):
                # Extract date part before first space: "2025-09-23 23:56:55+00" → "2025-09-23"
                date_part = cleaned_date.split(' ')[0]
                return date_part
            
            return cleaned_date
            
        elif hasattr(date_value, 'strftime'):
            # Handle datetime objects directly
            return date_value.strftime('%Y-%m-%d')
        else:
            # Convert to string and retry
            return format_date_for_frontend(str(date_value))
            
    except Exception as e:
        logging.debug(f"Date formatting fallback for {date_value}: {e}")
        # Final fallback: extract date part if it's a timestamp string
        if isinstance(date_value, str) and ' ' in date_value:
            try:
                return date_value.split(' ')[0]
            except:
                pass
        return str(date_value) if date_value else None

def format_record_dates(record_dict: dict) -> dict:
    """Format all date fields in a record for frontend consumption"""
    date_fields = [
        'entry_date', 'system_grn_date', 'manufacturing_date', 
        'expiry_date', 'import_date'
    ]
    
    formatted_record = record_dict.copy()
    for field in date_fields:
        if field in formatted_record:
            formatted_record[field] = format_date_for_frontend(formatted_record[field])
    
    return formatted_record

def validate_and_normalize_dates(from_date: Optional[str], to_date: Optional[str]):
    """Validate and normalize date inputs, ensuring correct order"""
    if not from_date and not to_date:
        return None, None
    
    try:
        # Convert string dates to date objects for comparison
        from_dt = None
        to_dt = None
        
        if from_date:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
        
        if to_date:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        # If both dates are provided, ensure correct order
        if from_dt and to_dt and from_dt > to_dt:
            # Swap dates
            from_dt, to_dt = to_dt, from_dt
        
        # Convert back to string format
        normalized_from = from_dt.strftime('%Y-%m-%d') if from_dt else None
        normalized_to = to_dt.strftime('%Y-%m-%d') if to_dt else None
        
        return normalized_from, normalized_to
        
    except ValueError as e:
        logging.error(f"Date validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use YYYY-MM-DD format.")

def build_search_conditions(tables: dict, search: Optional[str], from_date: Optional[str], to_date: Optional[str]):
    """Build comprehensive search conditions for all transaction fields"""
    where_clauses = ["1=1"]
    params = {}
    
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        
        # Build comprehensive search across all transaction fields
        search_fields = [
            # Transaction table fields
            "t.transaction_no",
            "t.vehicle_number", 
            "t.transporter_name",
            "t.lr_number",
            "t.vendor_supplier_name",
            "t.customer_party_name", 
            "t.source_location",
            "t.destination_location",
            "t.challan_number",
            "t.invoice_number",
            "t.po_number", 
            "t.grn_number",
            "t.purchase_by",
            "t.service_invoice_number",
            "t.dn_number", 
            "t.approval_authority",
            "t.remark",
            # Article table fields
            "a.item_description",
            "a.item_category",
            "a.sub_category", 
            "a.item_code",
            "a.hsn_code",
            "a.quality_grade",
            "a.uom",
            "a.packaging_type",
            "a.batch_number",
            "a.lot_number",
            "a.currency",
            # Box table fields  
            "b.article_description",
            "b.lot_number"
        ]
        
        # Create ILIKE conditions for all searchable fields
        search_conditions = []
        for field in search_fields:
            search_conditions.append(f"COALESCE({field}, '') ILIKE :search")
        
        # Also search numeric fields converted to text
        numeric_search_conditions = [
            "CAST(COALESCE(t.grn_quantity, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(t.total_amount, 0) AS TEXT) ILIKE :search", 
            "CAST(COALESCE(t.tax_amount, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(t.received_quantity, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(a.sku_id, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(a.quantity_units, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(a.net_weight, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(a.total_weight, 0) AS TEXT) ILIKE :search", 
            "CAST(COALESCE(a.unit_rate, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(a.total_amount, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(b.box_number, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(b.net_weight, 0) AS TEXT) ILIKE :search",
            "CAST(COALESCE(b.gross_weight, 0) AS TEXT) ILIKE :search"
        ]
        
        all_search_conditions = search_conditions + numeric_search_conditions
        where_clauses.append(f"({' OR '.join(all_search_conditions)})")
        params["search"] = search_term
    
    # FIXED: PostgreSQL timestamp with timezone date filtering
    if from_date or to_date:
        date_conditions = []
        
        if from_date and to_date:
            if from_date == to_date:
                # Same date - match any time on that specific date
                date_conditions.append("""
                    (
                        (t.entry_date IS NOT NULL AND DATE(t.entry_date AT TIME ZONE 'UTC') = :target_date)
                        OR 
                        (t.entry_date IS NULL AND t.system_grn_date IS NOT NULL AND DATE(t.system_grn_date AT TIME ZONE 'UTC') = :target_date)
                    )
                """)
                params["target_date"] = from_date
                logging.info(f"Single date search: {from_date}")
            else:
                # Date range - match any time within the date range
                date_conditions.append("""
                    (
                        (t.entry_date IS NOT NULL AND DATE(t.entry_date AT TIME ZONE 'UTC') BETWEEN :from_date AND :to_date)
                        OR 
                        (t.entry_date IS NULL AND t.system_grn_date IS NOT NULL AND DATE(t.system_grn_date AT TIME ZONE 'UTC') BETWEEN :from_date AND :to_date)
                    )
                """)
                params["from_date"] = from_date
                params["to_date"] = to_date
                logging.info(f"Date range search: {from_date} to {to_date}")
        elif from_date:
            # From date only
            date_conditions.append("""
                (
                    (t.entry_date IS NOT NULL AND DATE(t.entry_date AT TIME ZONE 'UTC') >= :from_date)
                    OR 
                    (t.entry_date IS NULL AND t.system_grn_date IS NOT NULL AND DATE(t.system_grn_date AT TIME ZONE 'UTC') >= :from_date)
                )
            """)
            params["from_date"] = from_date
            logging.info(f"From date search: >= {from_date}")
        elif to_date:
            # To date only  
            date_conditions.append("""
                (
                    (t.entry_date IS NOT NULL AND DATE(t.entry_date AT TIME ZONE 'UTC') <= :to_date)
                    OR 
                    (t.entry_date IS NULL AND t.system_grn_date IS NOT NULL AND DATE(t.system_grn_date AT TIME ZONE 'UTC') <= :to_date)
                )
            """)
            params["to_date"] = to_date
            logging.info(f"To date search: <= {to_date}")
        
        if date_conditions:
            where_clauses.extend(date_conditions)
    
    final_where = " AND ".join(where_clauses)
    logging.info(f"Final WHERE clause: {final_where}")
    logging.info(f"Query parameters: {params}")
    
    return final_where, params

# ---------- Routes ----------

# Backwards compatibility: Accept company as query parameter
@router.get("", response_model=InwardListResponse)
def list_inward_records_query(
    company: Company = Query(..., description="Company code"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
    search: Optional[str] = Query(None, description="Search across all transaction fields"),
    from_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("entry_date", description="Sort field"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db)
):
    """List inward records with company as query parameter"""
    # Convert skip/limit to page/per_page
    if skip > 0 or limit != 1000:
        page = (skip // limit) + 1 if limit > 0 else 1
        per_page = min(limit, 100)
    
    return list_inward_records(
        company=company,
        page=page,
        per_page=per_page,
        search=search,
        from_date=from_date,
        to_date=to_date,
        sort_by=sort_by,
        sort_order=sort_order,
        db=db
    )

@router.get("/{company}", response_model=InwardListResponse)
def list_inward_records(
    company: Company,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000),
    search: Optional[str] = Query(None, description="Search across all transaction fields"),
    from_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("entry_date", description="Sort field (entry_date, transaction_no, invoice_number)"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db)
):
    """List inward records with comprehensive search and date filtering"""
    tables = table_names(company)
    
    # Validate and normalize dates
    try:
        normalized_from_date, normalized_to_date = validate_and_normalize_dates(from_date, to_date)
    except HTTPException:
        raise
    
    # Build search conditions
    where_sql, params = build_search_conditions(
        tables, search, normalized_from_date, normalized_to_date
    )
    
    # Validate sort parameters
    valid_sort_fields = ["entry_date", "transaction_no", "invoice_number", "po_number"]
    valid_sort_orders = ["asc", "desc"]
    
    if sort_by and sort_by not in valid_sort_fields:
        raise HTTPException(status_code=400, detail=f"Invalid sort field. Allowed: {valid_sort_fields}")
    
    if sort_order and sort_order not in valid_sort_orders:
        raise HTTPException(status_code=400, detail=f"Invalid sort order. Allowed: {valid_sort_orders}")
    
    # Build sort clause
    if sort_by == "entry_date":
        sort_field = "COALESCE(entry_date, system_grn_date)"
    else:
        sort_field = sort_by or "COALESCE(entry_date, system_grn_date)"
    
    sort_direction = sort_order or "desc"
    
    # Debug: First check if ANY records exist without filters
    debug_count_sql = text(f"""
        SELECT COUNT(*) FROM {tables['tx']}
    """)
    
    total_all_records = db.execute(debug_count_sql).scalar_one()
    logging.info(f"Total records in {tables['tx']} table: {total_all_records}")
    
    # Debug: Check sample records
    if total_all_records > 0:
        sample_sql = text(f"""
            SELECT transaction_no, entry_date, system_grn_date FROM {tables['tx']} 
            ORDER BY entry_date DESC LIMIT 3
        """)
        try:
            sample_records = db.execute(sample_sql).fetchall()
            logging.info(f"Sample records from {tables['tx']}:")
            for record in sample_records:
                logging.info(f"  {record.transaction_no}: entry_date={record.entry_date}, system_grn_date={record.system_grn_date}")
        except Exception as e:
            logging.warning(f"Could not fetch sample records: {e}")
    
    # Debug: Date filtering issue analysis
    if from_date or to_date:
        logging.info(f"🔍 DATE FILTERING DEBUG:")
        logging.info(f"   - from_date: {from_date}")
        logging.info(f"   - to_date: {to_date}")
        logging.info(f"   - normalized_from_date: {normalized_from_date}")
        logging.info(f"   - normalized_to_date: {normalized_to_date}")
        
        # Check if any records exist in the date range without other filters
        if normalized_from_date:
            date_only_sql = text(f"""
                SELECT COUNT(*) FROM {tables['tx']} 
                WHERE (DATE(entry_date) >= :check_date OR (entry_date IS NULL AND DATE(system_grn_date) >= :check_date))
            """)
            try:
                date_records = db.execute(date_only_sql, {"check_date": normalized_from_date}).scalar_one()
                logging.info(f"   - Records matching date filter: {date_records}")
            except Exception as e:
                logging.info(f"   - Date filter check failed: {e}")
    else:
        logging.info(f"🔍 NO DATE FILTERING applied")
    
    # Count total matching records
    count_sql = text(f"""
        SELECT COUNT(DISTINCT t.transaction_no)
        FROM {tables['tx']} t
        LEFT JOIN {tables['art']} a ON t.transaction_no = a.transaction_no
        LEFT JOIN {tables['box']} b ON t.transaction_no = b.transaction_no
        WHERE {where_sql}
    """)
    
    try:
        total = db.execute(count_sql, params).scalar_one()
        logging.info(f"Found {total} matching records for company {company}")
        logging.info(f"Count query used: {count_sql}")
        logging.info(f"Count query params: {params}")
    except Exception as e:
        logging.error(f"Count query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search query failed: {str(e)}")
    
    # Calculate offset
    offset = (page - 1) * per_page
    
    # Enhanced list query with comprehensive search
    order_clause = f"{sort_field} {sort_direction.upper()} NULLS LAST, transaction_no DESC"
    list_sql = text(f"""
        WITH filtered_transactions AS (
            SELECT DISTINCT t.transaction_no
            FROM {tables['tx']} t
            LEFT JOIN {tables['art']} a ON t.transaction_no = a.transaction_no
            LEFT JOIN {tables['box']} b ON t.transaction_no = b.transaction_no
            WHERE {where_sql}
        ),
        transaction_data AS (
            SELECT 
                t.transaction_no,
                t.entry_date,
                t.system_grn_date,
                t.invoice_number,
                t.po_number,
                MIN(a.batch_number) as batch_number,
                STRING_AGG(DISTINCT a.item_description, ', ' ORDER BY a.item_description) as article_descriptions,
                STRING_AGG(DISTINCT 
                    CASE 
                        WHEN a.quantity_units IS NOT NULL AND a.uom IS NOT NULL 
                        THEN CONCAT(a.quantity_units::text, ' ', a.uom)
                        WHEN a.quantity_units IS NOT NULL 
                        THEN a.quantity_units::text
                        ELSE NULL
                    END, ', '
                    ORDER BY CASE 
                        WHEN a.quantity_units IS NOT NULL AND a.uom IS NOT NULL 
                        THEN CONCAT(a.quantity_units::text, ' ', a.uom)
                        WHEN a.quantity_units IS NOT NULL 
                        THEN a.quantity_units::text
                        ELSE NULL
                    END
                ) FILTER (WHERE a.quantity_units IS NOT NULL) as article_quantities,
                COUNT(DISTINCT b.box_number) as box_count,
                STRING_AGG(DISTINCT b.article_description, ', ' ORDER BY b.article_description) as box_descriptions
            FROM {tables['tx']} t
            INNER JOIN filtered_transactions ft ON t.transaction_no = ft.transaction_no
            LEFT JOIN {tables['art']} a ON t.transaction_no = a.transaction_no
            LEFT JOIN {tables['box']} b ON t.transaction_no = b.transaction_no
            GROUP BY t.transaction_no, t.entry_date, t.system_grn_date, t.invoice_number, t.po_number
        )
        SELECT 
            transaction_no,
            batch_number,
            COALESCE(entry_date, system_grn_date) as entry_date,
            invoice_number,
            po_number,
            COALESCE(article_descriptions, box_descriptions) as item_descriptions_text,
            CASE 
                WHEN article_quantities IS NOT NULL THEN article_quantities
                WHEN box_count > 0 THEN CONCAT(box_count::text, ' BOX')
                ELSE NULL
            END as quantities_and_uoms_text
        FROM transaction_data
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
    """)
    
    try:
        logging.info(f"Executing list query with offset {offset}, limit {per_page}")
        logging.info(f"SQL Query: {list_sql}")
        logging.info(f"Query parameters: {dict(**params, limit=per_page, offset=offset)}")
        
        records = db.execute(list_sql, {**params, "limit": per_page, "offset": offset}).fetchall()
        logging.info(f"Retrieved {len(records)} records from database")
        
        # Debug: Log first record if any
        if records:
            logging.info(f"Sample record: {records[0]}")
        else:
            logging.warning("No records found in query result")
            
    except Exception as e:
        logging.error(f"List query failed: {e}")
        logging.error(f"SQL: {list_sql}")
        logging.error(f"Params: {dict(**params, limit=per_page, offset=offset)}")
        raise HTTPException(status_code=500, detail=f"Search query failed: {str(e)}")
    
    # Format the response
    formatted_records = []
    logging.info(f"Processing {len(records)} raw records...")
    
    for i, record in enumerate(records):
        logging.info(f"Processing record {i+1}: {record}")
        
        # Convert string aggregations back to lists
        item_descriptions = []
        if record.item_descriptions_text and record.item_descriptions_text.strip():
            item_descriptions = [desc.strip() for desc in record.item_descriptions_text.split(',') if desc.strip()]
        
        quantities_and_uoms = []
        if record.quantities_and_uoms_text and record.quantities_and_uoms_text.strip():
            quantities_and_uoms = [qty.strip() for qty in record.quantities_and_uoms_text.split(',') if qty.strip()]
        
        # Handle null/None values and format dates properly
        entry_date_str = format_date_for_frontend(record.entry_date) or ""
        
        formatted_item = InwardListItem(
            transaction_id=record.transaction_no or "",
            batch_number=record.batch_number,
            entry_date=entry_date_str,
            invoice_number=record.invoice_number,
            po_number=record.po_number,
            item_descriptions=item_descriptions,
            quantities_and_uoms=quantities_and_uoms
        )
        
        logging.info(f"Formatted record {i+1}: {formatted_item}")
        formatted_records.append(formatted_item)
    
    # Log search results for debugging
    logging.info(f"Search completed: {len(formatted_records)} records returned for page {page}")
    if search:
        logging.info(f"Search term: '{search}'")
    if normalized_from_date or normalized_to_date:
        logging.info(f"Date range: {normalized_from_date} to {normalized_to_date}")
    
    response = InwardListResponse(
        records=formatted_records,
        total=total,
        page=page,
        per_page=per_page
    )
    
    # Debug: Verify count matches expected and check for potential null issues
    logging.info(f"Final response count: {len(formatted_records)} records, total: {total}")
    
    # Additional validation: ensure response structure is correct
    if hasattr(response, 'records') and len(response.records) == 0:
        logging.warning(f"No records in final response object")
        # Don't fail - just return empty response gracefully
    else:
        logging.info(f"Response has valid records: {len(response.records)}")
    
    logging.info(f"🔍 FINAL DEBUG: returning {len(formatted_records)} records, total: {total}")
    return response

@router.post("", status_code=201)
async def create_inward(request: Request, db: Session = Depends(get_db)):
    try:
        # Get raw request body for debugging
        body = await request.body()
        logging.info(f"Received inward request body: {body.decode('utf-8')}")
        
        # Parse JSON manually to catch validation errors
        import json
        data = json.loads(body)
        
        # Validate payload
        payload = InwardPayloadFlexible(**data)
        logging.info(f"Successfully validated payload for company: {payload.company}")
        
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {str(e)}")
    except ValidationError as e:
        logging.error(f"Validation error: {e}")
        raise HTTPException(status_code=422, detail=f"Validation error: {e.errors()}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=422, detail=f"Request processing error: {str(e)}")
    
    t = payload.transaction
    tables = table_names(payload.company)

    if not t.transaction_no:
        logging.error(f"Missing transaction_no. Transaction data: {t.model_dump()}")
        raise HTTPException(400, "transaction.transaction_no is required")

    txno = t.transaction_no

    # Ensure all child rows carry the same transaction_no
    for a in payload.articles:
        if a.transaction_no != txno:
            raise HTTPException(400, f"Article '{a.item_description}' has mismatched transaction_no")
    for b in payload.boxes:
        if b.transaction_no != txno:
            raise HTTPException(400, f"Box {b.box_number} has mismatched transaction_no")

    # Ensure boxes.article_description exists in articles list
    article_names = {a.item_description for a in payload.articles}
    unknown_refs = {b.article_description for b in payload.boxes if b.article_description not in article_names}
    if unknown_refs:
        raise HTTPException(400, f"Boxes reference unknown article(s): {sorted(list(unknown_refs))}")

    # Ensure SKU existence - create missing SKUs automatically (skip None for "other" items)
    if payload.articles:
        sku_ids = {a.sku_id for a in payload.articles if a.sku_id is not None}
        if sku_ids:
            sku_sql = (
                text(f"SELECT id FROM {tables['sku']} WHERE id IN :ids")
                .bindparams(bindparam("ids", expanding=True))
            )
            found = {row[0] for row in db.execute(sku_sql, {"ids": list(sku_ids)})}
            missing = sku_ids - found

            # Create missing SKUs automatically
            if missing:
                # Detect the correct column name for SKU table
                name_column = get_sku_name_column(db, tables['sku'])

                for missing_sku_id in missing:
                    # Find the article with this SKU ID
                    article = next(a for a in payload.articles if a.sku_id == missing_sku_id)

                    # Create the SKU (use minimal columns that exist)
                    sku_insert = text(f"""
                        INSERT INTO {tables['sku']} (id, item_description, item_category, sub_category)
                        VALUES (:id, :item_description, :item_category, :sub_category)
                        ON CONFLICT (id) DO UPDATE SET
                            item_description = EXCLUDED.item_description,
                            item_category = EXCLUDED.item_category,
                            sub_category = EXCLUDED.sub_category
                    """)

                    db.execute(sku_insert, {
                        "id": missing_sku_id,
                        "item_description": article.item_description,
                        "item_category": article.item_category or "",
                        "sub_category": article.sub_category or ""
                    })
                    logging.info(f"Auto-created SKU {missing_sku_id} for item: {article.item_description}")

    try:
        # 1) Insert transaction (409 if duplicate)
        # Prepare transaction data with proper null handling for date fields
        tx_data = clean_date_fields(t.model_dump())
        
        insert_tx = text(f"""
            INSERT INTO {tables['tx']} (
                transaction_no, entry_date, vehicle_number, transporter_name, lr_number,
                vendor_supplier_name, customer_party_name, source_location, destination_location,
                challan_number, invoice_number, po_number, grn_number, grn_quantity, system_grn_date,
                purchase_by, service_invoice_number, dn_number, approval_authority,
                total_amount, tax_amount, discount_amount, received_quantity, remark, currency
            ) VALUES (
                :transaction_no, :entry_date, :vehicle_number, :transporter_name, :lr_number,
                :vendor_supplier_name, :customer_party_name, :source_location, :destination_location,
                :challan_number, :invoice_number, :po_number, :grn_number, :grn_quantity, :system_grn_date,
                :purchase_by, :service_invoice_number, :dn_number, :approval_authority,
                :total_amount, :tax_amount, :discount_amount, :received_quantity, :remark, :currency
            )
            ON CONFLICT (transaction_no) DO NOTHING
        """)
        result = db.execute(insert_tx, tx_data)
        if result.rowcount == 0:
            raise HTTPException(status_code=409, detail=f"transaction_no '{txno}' already exists")

        # 2) Bulk insert articles
        if payload.articles:
            # Clean date fields for articles
            articles_data = [clean_date_fields(a.model_dump()) for a in payload.articles]
            
            insert_articles = text(f"""
                INSERT INTO {tables['art']} (
                  transaction_no, sku_id, item_description, item_category, sub_category, item_code, hsn_code,
                  quality_grade, uom, packaging_type, quantity_units, net_weight, total_weight,
                  batch_number, lot_number, manufacturing_date, expiry_date, import_date,
                  unit_rate, total_amount, tax_amount, discount_amount, currency,
                  issuance_date, job_card_no, issuance_quantity
                )
                VALUES (
                  :transaction_no, :sku_id, :item_description, :item_category, :sub_category, :item_code, :hsn_code,
                  :quality_grade, :uom, :packaging_type, :quantity_units, :net_weight, :total_weight,
                  :batch_number, :lot_number, :manufacturing_date, :expiry_date, :import_date,
                  :unit_rate, :total_amount, :tax_amount, :discount_amount, :currency,
                  :issuance_date, :job_card_no, :issuance_quantity
                )
                ON CONFLICT (transaction_no, item_description) DO NOTHING
            """)
            db.execute(insert_articles, articles_data)

        # 3) Bulk insert boxes
        if payload.boxes:
            insert_boxes = text(f"""
                INSERT INTO {tables['box']} (
                  transaction_no, article_description, box_number, net_weight, gross_weight, lot_number, count
                )
                VALUES (
                  :transaction_no, :article_description, :box_number, :net_weight, :gross_weight, :lot_number, :count
                )
                ON CONFLICT (transaction_no, article_description, box_number) DO NOTHING
            """)
            db.execute(insert_boxes, [b.model_dump() for b in payload.boxes])

        db.commit()
        return {"status": "ok", "transaction_no": txno, "company": payload.company}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"Database insert failed: {e}")
        raise HTTPException(500, f"Insert failed: {str(e)}")


@router.get("/{company}/{transaction_no}")
def get_inward(company: Company, transaction_no: str, db: Session = Depends(get_db)):
    tables = table_names(company)

    # 1) Transaction
    tx_res = db.execute(
        text(f"SELECT * FROM {tables['tx']} WHERE transaction_no = :txno"),
        {"txno": transaction_no},
    ).fetchone()
    if not tx_res:
        raise HTTPException(status_code=404, detail=f"transaction_no '{transaction_no}' not found for {company}")

    # Format transaction dates for frontend
    transaction = format_record_dates(dict(tx_res._mapping))

    # 2) Articles with material_type from SKU table
    arts = db.execute(
        text(f"""
            SELECT a.*, s.material_type
            FROM {tables['art']} a
            LEFT JOIN {tables['sku']} s ON a.sku_id = s.id
            WHERE a.transaction_no = :txno
            ORDER BY a.id ASC
        """),
        {"txno": transaction_no},
    ).fetchall()
    # Format article dates for frontend and include material_type
    articles = [format_record_dates(dict(r._mapping)) for r in arts]

    # 3) Boxes
    boxes_res = db.execute(
        text(f"""
            SELECT *
            FROM {tables['box']}
            WHERE transaction_no = :txno
            ORDER BY article_description ASC, box_number ASC
        """),
        {"txno": transaction_no},
    ).fetchall()
    # Boxes don't have date fields, but format for consistency
    boxes = [dict(r._mapping) for r in boxes_res]

    # 4) If no articles but boxes exist, create articles from boxes
    if not articles and boxes:
        # Group boxes by article description to create articles
        article_groups = {}
        for box in boxes:
            article_desc = box['article_description']
            if article_desc not in article_groups:
                article_groups[article_desc] = {
                    'transaction_no': transaction_no,
                    'sku_id': 0,  # Default SKU ID
                    'item_description': article_desc,
                    'item_category': None,
                    'sub_category': None,
                    'material_type': None,  # Added material_type
                    'item_code': None,
                    'hsn_code': None,
                    'quality_grade': None,
                    'uom': 'BOX',  # Default UOM
                    'packaging_type': None,
                    'quantity_units': 0,
                    'net_weight': 0,
                    'total_weight': 0,
                    'batch_number': None,
                    'lot_number': None,
                    'manufacturing_date': None,
                    'expiry_date': None,
                    'import_date': None,
                    'unit_rate': 0,
                    'total_amount': 0,
                    'tax_amount': 0,
                    'discount_amount': 0,
                    'currency': 'INR',
                    'box_count': 0,
                    'total_net_weight': 0,
                    'total_gross_weight': 0
                }

            # Aggregate box data
            article_groups[article_desc]['box_count'] += 1
            if box['net_weight']:
                article_groups[article_desc]['total_net_weight'] += float(box['net_weight'])
            if box['gross_weight']:
                article_groups[article_desc]['total_gross_weight'] += float(box['gross_weight'])

        # Convert to articles list
        articles = list(article_groups.values())
        # Set quantity_units to box count
        for article in articles:
            article['quantity_units'] = article['box_count']
            article['net_weight'] = article['total_net_weight']
            article['total_weight'] = article['total_gross_weight']

    return {
        "company": company,
        "transaction": transaction,
        "articles": articles,
        "boxes": boxes,
    }

@router.put("/{company}/{transaction_no}", status_code=200)
async def update_inward(
    company: Company,
    transaction_no: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an existing inward record"""
    try:
        # Parse request body
        body = await request.body()
        logging.info(f"Received update request for {company}/{transaction_no}")
        
        import json
        data = json.loads(body)
        
        # Validate payload structure
        payload = InwardPayloadFlexible(**data)
        
        # Ensure transaction_no matches URL parameter
        if payload.transaction.transaction_no != transaction_no:
            raise HTTPException(400, "Transaction number in payload must match URL parameter")
        
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        raise HTTPException(422, f"Invalid JSON: {str(e)}")
    except ValidationError as e:
        logging.error(f"Validation error: {e}")
        raise HTTPException(422, f"Validation error: {e.errors()}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(422, f"Request processing error: {str(e)}")

    tables = table_names(company)
    
    try:
        # Check if transaction exists
        check_sql = text(f"SELECT transaction_no FROM {tables['tx']} WHERE transaction_no = :txno")
        existing = db.execute(check_sql, {"txno": transaction_no}).fetchone()
        
        if not existing:
            raise HTTPException(404, f"Transaction '{transaction_no}' not found")

        # 1. Update transaction
        tx_data = clean_date_fields(payload.transaction.model_dump())
        
        # Build dynamic UPDATE query for transaction
        tx_update_fields = []
        tx_params = {"txno": transaction_no}
        
        for field, value in tx_data.items():
            if field != "transaction_no":  # Skip primary key
                tx_update_fields.append(f"{field} = :{field}")
                tx_params[field] = value
        
        if tx_update_fields:
            update_tx_sql = text(f"""
                UPDATE {tables['tx']} 
                SET {', '.join(tx_update_fields)}
                WHERE transaction_no = :txno
            """)
            db.execute(update_tx_sql, tx_params)

        # 2. Handle articles - delete existing and insert new ones
        # Delete existing articles
        delete_articles_sql = text(f"DELETE FROM {tables['art']} WHERE transaction_no = :txno")
        db.execute(delete_articles_sql, {"txno": transaction_no})
        
        # Insert updated articles
        if payload.articles:
            # Ensure SKU existence - create missing SKUs automatically (skip None for "other" items)
            sku_ids = {a.sku_id for a in payload.articles if a.sku_id is not None}
            if sku_ids:
                sku_sql = (
                    text(f"SELECT id FROM {tables['sku']} WHERE id IN :ids")
                    .bindparams(bindparam("ids", expanding=True))
                )
                found = {row[0] for row in db.execute(sku_sql, {"ids": list(sku_ids)})}
                missing = sku_ids - found

                # Create missing SKUs automatically
                for missing_sku_id in missing:
                    # Find the article with this SKU ID
                    article = next(a for a in payload.articles if a.sku_id == missing_sku_id)

                    # Create the SKU (use minimal columns that exist)
                    sku_insert = text(f"""
                        INSERT INTO {tables['sku']} (id, item_description, item_category, sub_category)
                        VALUES (:id, :item_description, :item_category, :sub_category)
                        ON CONFLICT (id) DO UPDATE SET
                            item_description = EXCLUDED.item_description,
                            item_category = EXCLUDED.item_category,
                            sub_category = EXCLUDED.sub_category
                    """)

                    db.execute(sku_insert, {
                        "id": missing_sku_id,
                        "item_description": article.item_description,
                        "item_category": article.item_category or "",
                        "sub_category": article.sub_category or ""
                    })
                    logging.info(f"Auto-created SKU {missing_sku_id} for item: {article.item_description}")
            
            articles_data = [clean_date_fields(a.model_dump()) for a in payload.articles]
            
            insert_articles_sql = text(f"""
                INSERT INTO {tables['art']} (
                    transaction_no, sku_id, item_description, item_category, sub_category, 
                    item_code, hsn_code, quality_grade, uom, packaging_type, quantity_units, 
                    net_weight, total_weight, batch_number, lot_number, manufacturing_date, 
                    expiry_date, import_date, unit_rate, total_amount, tax_amount, 
                    discount_amount, currency, issuance_date, job_card_no, issuance_quantity
                ) VALUES (
                    :transaction_no, :sku_id, :item_description, :item_category, :sub_category,
                    :item_code, :hsn_code, :quality_grade, :uom, :packaging_type, :quantity_units,
                    :net_weight, :total_weight, :batch_number, :lot_number, :manufacturing_date,
                    :expiry_date, :import_date, :unit_rate, :total_amount, :tax_amount,
                    :discount_amount, :currency, :issuance_date, :job_card_no, :issuance_quantity
                )
            """)
            db.execute(insert_articles_sql, articles_data)

        # 3. Handle boxes - delete existing and insert new ones
        # Delete existing boxes
        delete_boxes_sql = text(f"DELETE FROM {tables['box']} WHERE transaction_no = :txno")
        db.execute(delete_boxes_sql, {"txno": transaction_no})
        
        # Insert updated boxes
        if payload.boxes:
            insert_boxes_sql = text(f"""
                INSERT INTO {tables['box']} (
                    transaction_no, article_description, box_number, net_weight, gross_weight, lot_number, count
                ) VALUES (
                    :transaction_no, :article_description, :box_number, :net_weight, :gross_weight, :lot_number, :count
                )
            """)
            db.execute(insert_boxes_sql, [b.model_dump() for b in payload.boxes])

        db.commit()
        
        logging.info(f"Successfully updated transaction {transaction_no} for {company}")
        
        return {
            "status": "updated", 
            "transaction_no": transaction_no, 
            "company": company,
            "articles_count": len(payload.articles),
            "boxes_count": len(payload.boxes)
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"Database update failed: {e}")
        raise HTTPException(500, f"Update failed: {str(e)}")

@router.delete("/{company}/{transaction_no}", status_code=200)
async def delete_inward(
    company: Company,
    transaction_no: str,
    db: Session = Depends(get_db)
):
    """Delete an inward record and all its associated data"""
    tables = table_names(company)
    
    try:
        # Check if transaction exists
        check_sql = text(f"SELECT transaction_no FROM {tables['tx']} WHERE transaction_no = :txno")
        existing = db.execute(check_sql, {"txno": transaction_no}).fetchone()
        
        if not existing:
            raise HTTPException(404, f"Transaction '{transaction_no}' not found")

        # Delete in proper order to respect foreign key constraints
        # 1. Delete boxes first (child table)
        delete_boxes_sql = text(f"DELETE FROM {tables['box']} WHERE transaction_no = :txno")
        boxes_deleted = db.execute(delete_boxes_sql, {"txno": transaction_no}).rowcount
        
        # 2. Delete articles (child table) 
        delete_articles_sql = text(f"DELETE FROM {tables['art']} WHERE transaction_no = :txno")
        articles_deleted = db.execute(delete_articles_sql, {"txno": transaction_no}).rowcount
        
        # 3. Delete transaction (parent table)
        delete_transaction_sql = text(f"DELETE FROM {tables['tx']} WHERE transaction_no = :txno")
        transaction_deleted = db.execute(delete_transaction_sql, {"txno": transaction_no}).rowcount
        
        # Commit all deletions
        db.commit()
        
        logging.info(f"Successfully deleted transaction {transaction_no} for {company}: "
                    f"{transaction_deleted} transaction, {articles_deleted} articles, {boxes_deleted} boxes")
        
        return {
            "status": "deleted",
            "transaction_no": transaction_no,
            "company": company,
            "deleted_counts": {
                "transaction": transaction_deleted,
                "articles": articles_deleted,
                "boxes": boxes_deleted
            }
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"Database deletion failed: {e}")
        raise HTTPException(500, f"Delete failed: {str(e)}")

@router.post("/debug")
async def debug_inward(request: Request):
    """Debug endpoint to see what data is being sent"""
    try:
        body = await request.body()
        logging.info(f"Debug - Raw request body: {body.decode('utf-8')}")
        
        import json
        data = json.loads(body)
        logging.info(f"Debug - Parsed JSON: {data}")
        
        return {
            "status": "debug_success",
            "raw_body": body.decode('utf-8'),
            "parsed_data": data,
            "data_keys": list(data.keys()) if isinstance(data, dict) else "Not a dict"
        }
    except Exception as e:
        logging.error(f"Debug error: {e}")
        return {
            "status": "debug_error",
            "error": str(e)
        }

# Add this debug endpoint to test the timestamp conversion:
@router.get("/debug/timestamp-test/{company}")
def debug_timestamp_test(
    company: Company,
    test_date: str = Query("2024-12-20", description="Date to test (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Test timestamp date conversion"""
    
    tables = table_names(company)
    
    # Test different ways to extract date from timestamp
    test_queries = [
        {
            "name": "Raw timestamp values",
            "query": f"""
                SELECT transaction_no, entry_date, system_grn_date
                FROM {tables['tx']} 
                WHERE entry_date IS NOT NULL OR system_grn_date IS NOT NULL
                LIMIT 5
            """
        },
        {
            "name": "DATE() extraction",
            "query": f"""
                SELECT 
                    transaction_no,
                    entry_date,
                    DATE(entry_date AT TIME ZONE 'UTC') as entry_date_only,
                    system_grn_date,
                    DATE(system_grn_date AT TIME ZONE 'UTC') as grn_date_only
                FROM {tables['tx']} 
                WHERE entry_date IS NOT NULL OR system_grn_date IS NOT NULL
                LIMIT 5
            """
        },
        {
            "name": "Count for test date",
            "query": f"""
                SELECT COUNT(*) as count
                FROM {tables['tx']} 
                WHERE DATE(entry_date AT TIME ZONE 'UTC') = :test_date
                   OR DATE(system_grn_date AT TIME ZONE 'UTC') = :test_date
            """
        },
        {
            "name": "All dates in December 2024",
            "query": f"""
                SELECT COUNT(*) as count
                FROM {tables['tx']} 
                WHERE (entry_date AT TIME ZONE 'UTC') >= '2024-12-01'::date
                  AND (entry_date AT TIME ZONE 'UTC') < '2025-01-01'::date
            """
        }
    ]
    
    results = {
        "test_date": test_date,
        "database_table": tables['tx'],
        "results": []
    }
    
    for test in test_queries:
        try:
            if ":test_date" in test["query"]:
                query_result = db.execute(text(test["query"]), {"test_date": test_date}).fetchall()
            else:
                query_result = db.execute(text(test["query"])).fetchall()
            
            # Convert result to serializable format
            serializable_result = []
            for row in query_result:
                row_dict = {}
                for key, value in row._mapping.items():
                    if value is not None:
                        row_dict[key] = str(value)
                    else:
                        row_dict[key] = None
                serializable_result.append(row_dict)
            
            results["results"].append({
                "name": test["name"],
                "data": serializable_result,
                "count": len(serializable_result),
                "success": True
            })
            
        except Exception as e:
            results["results"].append({
                "name": test["name"],
                "error": str(e),
                "success": False
            })
    
    return results

# Add this debug endpoint to test date formatting:
@router.get("/debug/date-format-test/{company}")
def debug_date_format_test(
    company: Company,
    transaction_no: str = Query(None, description="Transaction number to test"),
    db: Session = Depends(get_db)
):
    """Test date formatting for a specific transaction"""
    
    tables = table_names(company)
    
    if transaction_no:
        # Test specific transaction
        tx_res = db.execute(
            text(f"SELECT * FROM {tables['tx']} WHERE transaction_no = :txno"),
            {"txno": transaction_no},
        ).fetchone()
        
        if not tx_res:
            return {"error": f"Transaction {transaction_no} not found"}
        
        raw_transaction = dict(tx_res._mapping)
        formatted_transaction = format_record_dates(raw_transaction)
        
        # Get articles too
        arts = db.execute(
            text(f"SELECT * FROM {tables['art']} WHERE transaction_no = :txno"),
            {"txno": transaction_no},
        ).fetchall()
        
        raw_articles = [dict(r._mapping) for r in arts]
        formatted_articles = [format_record_dates(art) for art in raw_articles]
        
        return {
            "transaction_no": transaction_no,
            "raw_transaction": raw_transaction,
            "formatted_transaction": formatted_transaction,
            "raw_articles": raw_articles,
            "formatted_articles": formatted_articles,
            "date_fields_compared": {
                "entry_date": {
                    "raw": raw_transaction.get('entry_date'),
                    "formatted": formatted_transaction.get('entry_date')
                },
                "system_grn_date": {
                    "raw": raw_transaction.get('system_grn_date'),
                    "formatted": formatted_transaction.get('system_grn_date')
                }
            }
        }
    else:
        # Test with sample records
        sample_tx = db.execute(
            text(f"SELECT transaction_no, entry_date, system_grn_date FROM {tables['tx']} LIMIT 3")
        ).fetchall()
        
        results = []
        for record in sample_tx:
            raw_data = dict(record._mapping)
            formatted_data = format_record_dates(raw_data)
            results.append({
                "transaction_no": raw_data['transaction_no'],
                "raw": raw_data,
                "formatted": formatted_data
            })
        
        return {
            "message": "Sample date formatting test",
            "results": results,
            "test_format": 'Testing "2025-09-23 23:56:55+00" format',
            "test_result": format_date_for_frontend("2025-09-23 23:56:55+00")
        }
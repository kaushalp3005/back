"""
Service layer for Item Catalog operations.
Handles cascading dropdowns, auto-fill, and search functionality.
"""

from typing import List, Optional, Type, Union
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.item_catalog import CFPLItem, CDPLItem
from app.schemas.item_catalog import (
    ItemDetailsResponse,
    DropdownValuesResponse,
    CascadingDropdownRequest,
    AutoFillRequest,
    GlobalSearchRequest,
    GlobalSearchResponse
)


class ItemCatalogService:
    """Service class for item catalog operations."""

    @staticmethod
    def get_model_for_company(company: str) -> Type[Union[CFPLItem, CDPLItem]]:
        """
        Get the appropriate model based on company name.

        Args:
            company: Company name (CFPL or CDPL)

        Returns:
            Model class for the company

        Raises:
            ValueError: If company is not supported
        """
        company_upper = company.upper().strip()

        if company_upper == "CFPL":
            return CFPLItem
        elif company_upper == "CDPL":
            return CDPLItem
        else:
            raise ValueError(
                f"Unsupported company: {company}. Must be 'CFPL' or 'CDPL'"
            )

    @staticmethod
    def get_cascading_dropdown_values(
        db: Session,
        company: str,
        request: CascadingDropdownRequest
    ) -> DropdownValuesResponse:
        """
        Get dropdown values based on previous selections (cascading).

        Args:
            db: Database session
            company: Company name (CFPL or CDPL)
            request: Request with filters and target field

        Returns:
            DropdownValuesResponse with unique values
        """
        Model = ItemCatalogService.get_model_for_company(company)

        # Start building query
        query = db.query(Model)

        # Apply filters based on previous selections
        if request.MATERIAL_TYPE:
            query = query.filter(Model.MATERIAL_TYPE == request.MATERIAL_TYPE)

        if request.ITEM_CATEGORY:
            query = query.filter(Model.ITEM_CATEGORY == request.ITEM_CATEGORY)

        if request.SUB_CATEGORY:
            query = query.filter(Model.SUB_CATEGORY == request.SUB_CATEGORY)

        # Get the target field
        field_attr = getattr(Model, request.field)

        # Query for distinct values, excluding None/empty
        values_query = query.with_entities(field_attr).filter(
            field_attr.isnot(None),
            field_attr != ''
        ).distinct().order_by(field_attr)

        # Execute query and extract values
        results = values_query.all()
        values = [str(result[0]) for result in results if result[0]]

        return DropdownValuesResponse(
            values=values,
            count=len(values)
        )

    @staticmethod
    def auto_fill_from_description(
        db: Session,
        company: str,
        request: AutoFillRequest
    ) -> Optional[ItemDetailsResponse]:
        """
        Auto-fill MATERIAL_TYPE, ITEM_CATEGORY, SUB_CATEGORY based on ITEM_DESCRIPTION.

        Args:
            db: Database session
            company: Company name (CFPL or CDPL)
            request: Request with ITEM_DESCRIPTION

        Returns:
            ItemDetailsResponse with all fields or None if not found
        """
        Model = ItemCatalogService.get_model_for_company(company)

        # Search for exact match first
        item = db.query(Model).filter(
            Model.ITEM_DESCRIPTION == request.ITEM_DESCRIPTION
        ).first()

        if not item:
            return None

        return ItemDetailsResponse(
            MATERIAL_TYPE=item.MATERIAL_TYPE or "",
            ITEM_CATEGORY=item.ITEM_CATEGORY or "",
            SUB_CATEGORY=item.SUB_CATEGORY,
            ITEM_DESCRIPTION=item.ITEM_DESCRIPTION or ""
        )

    @staticmethod
    def global_search(
        db: Session,
        company: str,
        request: GlobalSearchRequest
    ) -> GlobalSearchResponse:
        """
        Global search by ITEM_DESCRIPTION (partial match).

        Args:
            db: Database session
            company: Company name (CFPL or CDPL)
            request: Request with search term

        Returns:
            GlobalSearchResponse with matching items
        """
        Model = ItemCatalogService.get_model_for_company(company)

        # Build search query with case-insensitive partial match
        search_pattern = f"%{request.search_term}%"

        query = db.query(Model).filter(
            Model.ITEM_DESCRIPTION.ilike(search_pattern)
        ).order_by(Model.ITEM_DESCRIPTION)
        
        # Only apply limit if specified
        if request.limit:
            query = query.limit(request.limit)

        items = query.all()

        results = [
            ItemDetailsResponse(
                MATERIAL_TYPE=item.MATERIAL_TYPE or "",
                ITEM_CATEGORY=item.ITEM_CATEGORY or "",
                SUB_CATEGORY=item.SUB_CATEGORY,
                ITEM_DESCRIPTION=item.ITEM_DESCRIPTION or ""
            )
            for item in items
        ]

        return GlobalSearchResponse(
            results=results,
            count=len(results),
            search_term=request.search_term
        )

    @staticmethod
    def get_all_dropdown_values_for_field(
        db: Session,
        company: str,
        field: str
    ) -> DropdownValuesResponse:
        """
        Get all unique values for a specific field without any filters.
        Useful for initial page load to populate first dropdown.

        Args:
            db: Database session
            company: Company name (CFPL or CDPL)
            field: Field name (MATERIAL_TYPE, ITEM_CATEGORY, etc.)

        Returns:
            DropdownValuesResponse with all unique values
        """
        Model = ItemCatalogService.get_model_for_company(company)

        # Validate field
        valid_fields = ['MATERIAL_TYPE', 'ITEM_CATEGORY', 'SUB_CATEGORY', 'ITEM_DESCRIPTION']
        if field not in valid_fields:
            raise ValueError(f"Invalid field: {field}. Must be one of {valid_fields}")

        field_attr = getattr(Model, field)

        # Query for distinct values
        values_query = db.query(field_attr).filter(
            field_attr.isnot(None),
            field_attr != ''
        ).distinct().order_by(field_attr)

        results = values_query.all()
        values = [str(result[0]) for result in results if result[0]]

        return DropdownValuesResponse(
            values=values,
            count=len(values)
        )

    @staticmethod
    def get_item_details_by_all_fields(
        db: Session,
        company: str,
        material_type: Optional[str] = None,
        item_category: Optional[str] = None,
        sub_category: Optional[str] = None,
        item_description: Optional[str] = None
    ) -> List[ItemDetailsResponse]:
        """
        Get item details by any combination of fields.
        Useful for validation and lookups.

        Args:
            db: Database session
            company: Company name (CFPL or CDPL)
            material_type: Optional material type filter
            item_category: Optional item category filter
            sub_category: Optional sub category filter
            item_description: Optional item description filter

        Returns:
            List of matching items
        """
        Model = ItemCatalogService.get_model_for_company(company)

        query = db.query(Model)

        if material_type:
            query = query.filter(Model.MATERIAL_TYPE == material_type)

        if item_category:
            query = query.filter(Model.ITEM_CATEGORY == item_category)

        if sub_category:
            query = query.filter(Model.SUB_CATEGORY == sub_category)

        if item_description:
            query = query.filter(Model.ITEM_DESCRIPTION == item_description)

        items = query.all()

        return [
            ItemDetailsResponse(
                MATERIAL_TYPE=item.MATERIAL_TYPE or "",
                ITEM_CATEGORY=item.ITEM_CATEGORY or "",
                SUB_CATEGORY=item.SUB_CATEGORY,
                ITEM_DESCRIPTION=item.ITEM_DESCRIPTION or ""
            )
            for item in items
        ]

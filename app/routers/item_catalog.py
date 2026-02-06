"""
API Router for Item Catalog operations.
Provides cascading dropdowns, auto-fill, and search functionality.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.item_catalog import ItemCatalogService
from app.schemas.item_catalog import (
    DropdownValuesResponse,
    CascadingDropdownRequest,
    AutoFillRequest,
    ItemDetailsResponse,
    GlobalSearchRequest,
    GlobalSearchResponse
)

router = APIRouter(
    prefix="/item-catalog",
    tags=["Item Catalog"]
)


def get_company_from_header(
    x_company_name: Optional[str] = Header(
        None,
        description="Company name: CFPL or CDPL",
        alias="X-Company-Name"
    )
) -> str:
    """
    Extract and validate company name from header.

    Args:
        x_company_name: Company name from header

    Returns:
        Validated company name

    Raises:
        HTTPException: If company name is missing or invalid
    """
    if not x_company_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-Name header is required. Must be 'CFPL' or 'CDPL'"
        )

    company = x_company_name.upper().strip()

    if company not in ["CFPL", "CDPL"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid company name: {x_company_name}. Must be 'CFPL' or 'CDPL'"
        )

    return company


@router.get(
    "/dropdown-values",
    response_model=DropdownValuesResponse,
    summary="Get cascading dropdown values",
    description="""
    Get dropdown values based on previous selections (cascading behavior).

    **Use Cases:**
    - Get all MATERIAL_TYPE values (no filters)
    - Get ITEM_CATEGORY values filtered by MATERIAL_TYPE
    - Get SUB_CATEGORY values filtered by MATERIAL_TYPE and ITEM_CATEGORY
    - Get ITEM_DESCRIPTION values filtered by all previous selections

    **Headers:**
    - `X-Company-Name`: Required. Company identifier ('CFPL' or 'CDPL')

    **Query Parameters:**
    - `field`: Target field to get values for (required)
    - `material_type`: Filter by material type (optional)
    - `item_category`: Filter by item category (optional)
    - `sub_category`: Filter by sub category (optional)

    **Example Workflows:**
    1. Initial load: `GET /dropdown-values?field=MATERIAL_TYPE`
    2. After selecting MATERIAL_TYPE='RM': `GET /dropdown-values?field=ITEM_CATEGORY&material_type=RM`
    3. After selecting ITEM_CATEGORY='Packing Material':
       `GET /dropdown-values?field=SUB_CATEGORY&material_type=RM&item_category=Packing Material`
    4. After selecting SUB_CATEGORY='Boxes':
       `GET /dropdown-values?field=ITEM_DESCRIPTION&material_type=RM&item_category=Packing Material&sub_category=Boxes`
    """
)
async def get_dropdown_values(
    field: str = Query(
        ...,
        description="Field to get values for: MATERIAL_TYPE, ITEM_CATEGORY, SUB_CATEGORY, or ITEM_DESCRIPTION"
    ),
    material_type: Optional[str] = Query(
        None,
        description="Filter by material type",
        alias="material_type"
    ),
    item_category: Optional[str] = Query(
        None,
        description="Filter by item category",
        alias="item_category"
    ),
    sub_category: Optional[str] = Query(
        None,
        description="Filter by sub category",
        alias="sub_category"
    ),
    company: str = Depends(get_company_from_header),
    db: Session = Depends(get_db)
) -> DropdownValuesResponse:
    """Get cascading dropdown values based on filters."""
    try:
        request = CascadingDropdownRequest(
            MATERIAL_TYPE=material_type,
            ITEM_CATEGORY=item_category,
            SUB_CATEGORY=sub_category,
            field=field
        )

        return ItemCatalogService.get_cascading_dropdown_values(
            db=db,
            company=company,
            request=request
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching dropdown values: {str(e)}"
        )


@router.post(
    "/auto-fill",
    response_model=ItemDetailsResponse,
    summary="Auto-fill fields from item description",
    description="""
    Auto-fill MATERIAL_TYPE, ITEM_CATEGORY, and SUB_CATEGORY when ITEM_DESCRIPTION is selected.

    This endpoint performs an exact match on ITEM_DESCRIPTION and returns all related fields.

    **Headers:**
    - `X-Company-Name`: Required. Company identifier ('CFPL' or 'CDPL')

    **Request Body:**
    - `ITEM_DESCRIPTION`: The exact item description to search for

    **Response:**
    - Returns complete item details if found
    - Returns 404 if no matching item is found

    **Example:**
    ```json
    {
        "ITEM_DESCRIPTION": "Corrugated Box 10x10x10"
    }
    ```
    """
)
async def auto_fill_from_description(
    request: AutoFillRequest,
    company: str = Depends(get_company_from_header),
    db: Session = Depends(get_db)
) -> ItemDetailsResponse:
    """Auto-fill fields based on item description."""
    try:
        result = ItemCatalogService.auto_fill_from_description(
            db=db,
            company=company,
            request=request
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No item found with description: {request.ITEM_DESCRIPTION}"
            )

        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during auto-fill: {str(e)}"
        )


@router.post(
    "/search",
    response_model=GlobalSearchResponse,
    summary="Global search by item description",
    description="""
    Search for items by ITEM_DESCRIPTION (partial match, case-insensitive).

    Returns all matching items with complete details (MATERIAL_TYPE, ITEM_CATEGORY, SUB_CATEGORY, ITEM_DESCRIPTION).

    **Headers:**
    - `X-Company-Name`: Required. Company identifier ('CFPL' or 'CDPL')

    **Request Body:**
    - `search_term`: Text to search for in ITEM_DESCRIPTION (partial match)
    - `limit`: Maximum number of results (default: 50, max: 500)

    **Response:**
    - `results`: Array of matching items with all fields
    - `count`: Number of results returned
    - `search_term`: The search term used

    **Example:**
    ```json
    {
        "search_term": "Corrugated",
        "limit": 20
    }
    ```
    """
)
async def global_search(
    request: GlobalSearchRequest,
    company: str = Depends(get_company_from_header),
    db: Session = Depends(get_db)
) -> GlobalSearchResponse:
    """Global search by item description."""
    try:
        return ItemCatalogService.global_search(
            db=db,
            company=company,
            request=request
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during search: {str(e)}"
        )


@router.get(
    "/all-values/{field}",
    response_model=DropdownValuesResponse,
    summary="Get all values for a field",
    description="""
    Get all unique values for a specific field without any filters.

    Useful for initial page load to populate the first dropdown or get complete lists.

    **Headers:**
    - `X-Company-Name`: Required. Company identifier ('CFPL' or 'CDPL')

    **Path Parameters:**
    - `field`: Field name (MATERIAL_TYPE, ITEM_CATEGORY, SUB_CATEGORY, or ITEM_DESCRIPTION)

    **Example:**
    - `GET /all-values/MATERIAL_TYPE` - Get all material types
    - `GET /all-values/ITEM_CATEGORY` - Get all item categories
    """
)
async def get_all_values_for_field(
    field: str,
    company: str = Depends(get_company_from_header),
    db: Session = Depends(get_db)
) -> DropdownValuesResponse:
    """Get all unique values for a field."""
    try:
        return ItemCatalogService.get_all_dropdown_values_for_field(
            db=db,
            company=company,
            field=field
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching values: {str(e)}"
        )


@router.get(
    "/validate",
    response_model=ItemDetailsResponse,
    summary="Validate item exists",
    description="""
    Validate that an item exists with the given field values.

    Useful for form validation before submission.

    **Headers:**
    - `X-Company-Name`: Required. Company identifier ('CFPL' or 'CDPL')

    **Query Parameters:**
    - At least one parameter must be provided
    - Returns 404 if no matching item is found
    - Returns 400 if multiple items match (should be unique combination)

    **Example:**
    - `GET /validate?item_description=Corrugated Box 10x10x10`
    """
)
async def validate_item(
    material_type: Optional[str] = Query(None, alias="material_type"),
    item_category: Optional[str] = Query(None, alias="item_category"),
    sub_category: Optional[str] = Query(None, alias="sub_category"),
    item_description: Optional[str] = Query(None, alias="item_description"),
    company: str = Depends(get_company_from_header),
    db: Session = Depends(get_db)
) -> ItemDetailsResponse:
    """Validate that an item exists with given parameters."""
    try:
        # Ensure at least one parameter is provided
        if not any([material_type, item_category, sub_category, item_description]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one query parameter must be provided"
            )

        results = ItemCatalogService.get_item_details_by_all_fields(
            db=db,
            company=company,
            material_type=material_type,
            item_category=item_category,
            sub_category=sub_category,
            item_description=item_description
        )

        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No matching item found"
            )

        if len(results) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Multiple items found ({len(results)}). Please provide more specific criteria."
            )

        return results[0]

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during validation: {str(e)}"
        )

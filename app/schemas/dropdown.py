from pydantic import BaseModel, Field
from typing import Optional, List, Literal

Company = Literal["CFPL", "CDPL"]
SortKey = Literal["alpha", "recent"]  # 'recent' reserved for future usage

class DropdownQuery(BaseModel):
    company: Company
    material_type: Optional[str] = None
    item_description: Optional[str] = None
    item_category: Optional[str] = None
    sub_category: Optional[str] = None
    search: Optional[str] = None
    sort: SortKey = "alpha"
    limit: int = Field(default=200, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)

class SelectedState(BaseModel):
    material_type: Optional[str] = None
    item_description: Optional[str] = None
    item_category: Optional[str] = None
    sub_category: Optional[str] = None

class ResolvedFromItem(BaseModel):
    material_type: Optional[str] = None
    item_category: Optional[str] = None
    sub_category: Optional[str] = None

class ResolvedFromMaterialType(BaseModel):
    item_categories: List[str] = []

class ResolvedFromCategorySub(BaseModel):
    item_descriptions: List[str] = []

class AutoSelection(BaseModel):
    resolved_from_item: ResolvedFromItem
    resolved_from_material_type: ResolvedFromMaterialType
    resolved_from_category_sub: ResolvedFromCategorySub

class Options(BaseModel):
    material_types: List[str]
    item_descriptions: List[str]
    item_categories: List[str]
    sub_categories: List[str]
    item_ids: List[int]

class Meta(BaseModel):
    total_material_types: int
    total_item_descriptions: int
    total_categories: int
    total_sub_categories: int
    limit: int
    offset: int
    sort: SortKey
    search: Optional[str] = None

class DropdownResponse(BaseModel):
    company: Company
    selected: SelectedState
    auto_selection: AutoSelection
    options: Options
    meta: Meta

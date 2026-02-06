from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from decimal import Decimal

Company = Literal["CDPL", "CFPL"]


class ComplaintArticleIn(BaseModel):
    itemCategory: str
    itemSubcategory: Optional[str] = None
    itemDescription: str
    quantity: int
    uom: str


class ComplaintCreate(BaseModel):
    company: Company
    customerName: str
    receivedDate: str
    manufacturingDate: Optional[str] = None
    itemCategory: Optional[str] = None
    itemSubcategory: Optional[str] = None
    itemDescription: Optional[str] = None
    batchCode: Optional[str] = None
    quantityRejected: Optional[int] = None
    quantityApproved: Optional[int] = None
    uom: Optional[str] = None
    complaintNature: Optional[str] = None
    otherComplaintNature: Optional[str] = None
    qaAssessment: Optional[str] = None
    justifiedStatus: Optional[str] = None
    remarks: Optional[str] = None
    proofImages: List[str] = Field(default_factory=list)
    articles: List[ComplaintArticleIn] = Field(default_factory=list)
    createdBy: str


class ComplaintArticleOut(BaseModel):
    id: int
    itemCategory: str
    itemSubcategory: Optional[str] = None
    itemDescription: str
    quantity: int
    uom: str


class ComplaintDetail(BaseModel):
    id: int
    complaintId: str
    company: Company
    customerName: str
    receivedDate: str
    manufacturingDate: Optional[str] = None
    itemCategory: Optional[str] = None
    itemSubcategory: Optional[str] = None
    itemDescription: Optional[str] = None
    batchCode: Optional[str] = None
    quantityRejected: Optional[int] = None
    quantityApproved: Optional[int] = None
    uom: Optional[str] = None
    complaintNature: Optional[str] = None
    otherComplaintNature: Optional[str] = None
    qaAssessment: Optional[str] = None
    justifiedStatus: Optional[str] = None
    remarks: Optional[str] = None
    proofImages: List[str] = Field(default_factory=list)
    articles: List[ComplaintArticleOut] = Field(default_factory=list)
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    sampleVideo: Optional[str] = None


class ComplaintCreateResponse(BaseModel):
    success: bool
    data: ComplaintDetail
    message: str


class ComplaintUpdate(BaseModel):
    id: int
    complaintId: str
    company: Company
    customerName: str
    receivedDate: str
    manufacturingDate: Optional[str] = None
    itemCategory: Optional[str] = None
    itemSubcategory: Optional[str] = None
    itemDescription: Optional[str] = None
    batchCode: Optional[str] = None
    quantityRejected: Optional[int] = None
    quantityApproved: Optional[int] = None
    uom: Optional[str] = None
    complaintNature: Optional[str] = None
    otherComplaintNature: Optional[str] = None
    qaAssessment: Optional[str] = None
    justifiedStatus: Optional[str] = None
    remarks: Optional[str] = None
    proofImages: List[str] = Field(default_factory=list)
    articles: List[ComplaintArticleOut] = Field(default_factory=list)
    updatedBy: str


class ComplaintListItem(BaseModel):
    id: int
    complaintId: str
    company: Company
    customerName: str
    itemDescription: Optional[str] = None
    batchCode: Optional[str] = None
    status: Optional[str] = None
    qaAssessment: Optional[str] = None
    justifiedStatus: Optional[str] = None
    quantityRejected: Optional[int] = None
    estimatedLoss: Optional[Decimal] = None
    measuresToResolve: Optional[str] = None
    receivedDate: str
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    sampleVideo: Optional[str] = None


class ComplaintListResponse(BaseModel):
    success: bool
    data: List[ComplaintListItem]
    meta: Dict[str, Any]


class ComplaintDeleteResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any]


class StatsResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


class VideoUploadResponse(BaseModel):
    success: bool
    data: Dict[str, Any]

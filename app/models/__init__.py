# Import all models to ensure they are registered with SQLAlchemy
from .consumption import *
from .transfer import *
from .alerts_recipients import *
from .rtv import *
from .purchase import PurchaseOrder, POItem, POItemBox
from .purchase_approval import PurchaseApproval, PurchaseApprovalItem, PurchaseApprovalBox
from .item_catalog import CFPLItem, CDPLItem

__all__ = [
    # Purchase models
    "PurchaseOrder",
    "POItem",
    "POItemBox",
    # Purchase Approval models
    "PurchaseApproval",
    "PurchaseApprovalItem",
    "PurchaseApprovalBox",
    # Item Catalog models
    "CFPLItem",
    "CDPLItem",
]
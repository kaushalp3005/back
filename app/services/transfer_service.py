# File: transfer_service.py
# Path: backend/app/services/transfer_service.py

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.models.transfer import (
    TransferRequest, TransferRequestItem, TransferScannedBox, 
    TransferInfo, WarehouseMaster
)


class TransferService:
    """Service class for transfer module business logic"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ============================================
    # REQUEST MANAGEMENT METHODS
    # ============================================
    
    def create_transfer_request(
        self,
        request_date: date,
        from_warehouse: str,
        to_warehouse: str,
        reason_description: str,
        items: List[Dict[str, Any]],
        reason: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Create a new transfer request with items
        Returns (request_no, request_id)
        """
        # Validate warehouses exist
        from_wh = self.db.query(WarehouseMaster).filter(
            WarehouseMaster.warehouse_code == from_warehouse
        ).first()
        if not from_wh:
            raise ValueError(f"From warehouse {from_warehouse} not found")
        
        to_wh = self.db.query(WarehouseMaster).filter(
            WarehouseMaster.warehouse_code == to_warehouse
        ).first()
        if not to_wh:
            raise ValueError(f"To warehouse {to_warehouse} not found")
        
        # Generate request number
        request_no = self._generate_request_no()
        
        # Create transfer request
        transfer_request = TransferRequest(
            request_no=request_no,
            request_date=request_date,
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            reason=reason,
            reason_description=reason_description,
            status="Pending",
            created_by=created_by
        )
        
        self.db.add(transfer_request)
        self.db.flush()  # Get the ID
        
        # Create items
        for i, item_data in enumerate(items, 1):
            item = TransferRequestItem(
                transfer_id=transfer_request.id,
                line_number=i,
                material_type=item_data.get("material_type"),
                item_category=item_data["item_category"],
                sub_category=item_data.get("sub_category"),
                item_description=item_data["item_description"],
                sku_id=item_data.get("sku_id"),
                quantity=Decimal(str(item_data["quantity"])),
                uom=item_data["uom"],
                pack_size=Decimal(str(item_data.get("pack_size", 0))),
                package_size=item_data.get("package_size"),
                net_weight=Decimal(str(item_data.get("net_weight", 0)))
            )
            self.db.add(item)
        
        self.db.commit()
        return request_no, transfer_request.id
    
    def get_transfer_request_with_details(self, request_id: int) -> Optional[Dict[str, Any]]:
        """Get transfer request with all related details"""
        from app.models.transfer import get_transfer_with_details
        return get_transfer_with_details(self.db, request_id)
    
    def get_transfer_requests_list(
        self,
        status: Optional[str] = None,
        from_warehouse: Optional[str] = None,
        to_warehouse: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        created_by: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get transfer requests list with filtering and pagination
        Returns (requests_list, total_count)
        """
        query = self.db.query(TransferRequest)
        
        # Apply filters
        if status:
            query = query.filter(TransferRequest.status == status)
        if from_warehouse:
            query = query.filter(TransferRequest.from_warehouse == from_warehouse)
        if to_warehouse:
            query = query.filter(TransferRequest.to_warehouse == to_warehouse)
        if date_from:
            query = query.filter(TransferRequest.request_date >= date_from)
        if date_to:
            query = query.filter(TransferRequest.request_date <= date_to)
        if created_by:
            query = query.filter(TransferRequest.created_by == created_by)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        requests = query.order_by(TransferRequest.created_at.desc()).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        
        # Build response list
        request_list = []
        for req in requests:
            # Get item count
            item_count = self.db.query(TransferRequestItem).filter(
                TransferRequestItem.transfer_id == req.id
            ).count()
            
            request_list.append({
                "id": req.id,
                "request_no": req.request_no,
                "transfer_no": req.transfer_no,
                "request_date": req.request_date,
                "from_warehouse": req.from_warehouse,
                "to_warehouse": req.to_warehouse,
                "reason_description": req.reason_description,
                "status": req.status,
                "item_count": item_count,
                "created_by": req.created_by,
                "created_at": req.created_at
            })
        
        return request_list, total
    
    # ============================================
    # TRANSFER SUBMISSION METHODS
    # ============================================
    
    def submit_transfer(
        self,
        request_no: str,
        scanned_boxes: List[Dict[str, Any]],
        transport_info: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Submit complete transfer with scanned boxes and transport details
        Returns (transfer_no, status)
        """
        # Find existing request
        transfer_request = self.db.query(TransferRequest).filter(
            TransferRequest.request_no == request_no
        ).first()
        
        if not transfer_request:
            raise ValueError(f"Transfer request {request_no} not found")
        
        if transfer_request.status != "Pending":
            raise ValueError(f"Transfer request {request_no} is already processed")
        
        # Generate transfer number if not exists
        if not transfer_request.transfer_no:
            transfer_no = self._generate_transfer_no()
            transfer_request.transfer_no = transfer_no
        else:
            transfer_no = transfer_request.transfer_no
        
        # Update status
        transfer_request.status = "In Transit"
        
        # Create scanned boxes
        for box_data in scanned_boxes:
            scanned_box = TransferScannedBox(
                transfer_id=transfer_request.id,
                box_id=box_data["box_id"],
                transaction_no=box_data["transaction_no"],
                sku_id=box_data["sku_id"],
                box_number_in_array=box_data["box_number_in_array"],
                box_number=box_data["box_number"],
                item_description=box_data.get("item_description"),
                net_weight=Decimal(str(box_data.get("net_weight", 0))),
                gross_weight=Decimal(str(box_data.get("gross_weight", 0))),
                qr_data=box_data.get("qr_data")
            )
            self.db.add(scanned_box)
        
        # Create transport info
        transport = TransferInfo(
            transfer_id=transfer_request.id,
            vehicle_number=transport_info["vehicle_number"],
            vehicle_number_other=transport_info.get("vehicle_number_other"),
            driver_name=transport_info["driver_name"],
            driver_name_other=transport_info.get("driver_name_other"),
            driver_phone=transport_info.get("driver_phone"),
            approval_authority=transport_info["approval_authority"]
        )
        self.db.add(transport)
        
        self.db.commit()
        return transfer_no, transfer_request.status
    
    # ============================================
    # SCANNER METHODS
    # ============================================
    
    def resolve_scanner_input(self, scan_value: str, warehouse: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve scanned box/lot/batch information
        This is a placeholder - integrate with your actual QR/inward system
        """
        scan_value = scan_value.strip()
        
        # Mock implementation - replace with actual QR parsing logic
        if scan_value.startswith("TX"):
            # Transaction number scan
            return {
                "scan_value": scan_value,
                "resolved_box": f"BOX{scan_value[-2:]}",
                "resolved_lot": f"LOT{scan_value[-4:-2]}",
                "resolved_batch": f"BATCH{scan_value[-6:-4]}",
                "sku_id": "SKU001234",
                "sku_name": "Wheat Flour 1kg",
                "material_type": "RM",
                "uom": "KG",
                "available_qty": Decimal("100.000"),
                "expiry_date": date(2024, 2, 15),
                "fefo_priority": 1
            }
        else:
            raise ValueError("Invalid scan format. Expected transaction number starting with 'TX'")
    
    def validate_scan_duplicate(
        self,
        transfer_id: int,
        transaction_no: str,
        sku_id: str,
        box_number_in_array: int
    ) -> bool:
        """
        Check if scan is duplicate
        Returns True if duplicate, False if new
        """
        existing = self.db.query(TransferScannedBox).filter(
            and_(
                TransferScannedBox.transfer_id == transfer_id,
                TransferScannedBox.transaction_no == transaction_no,
                TransferScannedBox.sku_id == sku_id,
                TransferScannedBox.box_number_in_array == box_number_in_array
            )
        ).first()
        
        return existing is not None
    
    # ============================================
    # DC GENERATION METHODS
    # ============================================
    
    def get_dc_data(self, transfer_no: str) -> Dict[str, Any]:
        """Get delivery challan data for DC generation"""
        from app.models.transfer import get_warehouse_addresses
        
        # Get transfer request
        transfer_request = self.db.query(TransferRequest).filter(
            TransferRequest.transfer_no == transfer_no
        ).first()
        
        if not transfer_request:
            raise ValueError(f"Transfer {transfer_no} not found")
        
        # Get warehouse addresses
        warehouse_codes = [transfer_request.from_warehouse, transfer_request.to_warehouse]
        warehouse_addresses = get_warehouse_addresses(self.db, warehouse_codes)
        
        # Get items
        items = self.db.query(TransferRequestItem).filter(
            TransferRequestItem.transfer_id == transfer_request.id
        ).order_by(TransferRequestItem.line_number).all()
        
        # Get scanned boxes
        scanned_boxes = self.db.query(TransferScannedBox).filter(
            TransferScannedBox.transfer_id == transfer_request.id
        ).order_by(TransferScannedBox.box_number_in_array).all()
        
        # Get transport info
        transport_info = self.db.query(TransferInfo).filter(
            TransferInfo.transfer_id == transfer_request.id
        ).first()
        
        if not transport_info:
            raise ValueError("Transport information not found")
        
        return {
            "transfer_no": transfer_request.transfer_no,
            "request_no": transfer_request.request_no,
            "request_date": transfer_request.request_date,
            "from_warehouse": warehouse_addresses[transfer_request.from_warehouse],
            "to_warehouse": warehouse_addresses[transfer_request.to_warehouse],
            "items": [
                {
                    "line_number": item.line_number,
                    "material_type": item.material_type,
                    "item_category": item.item_category,
                    "sub_category": item.sub_category,
                    "item_description": item.item_description,
                    "sku_id": item.sku_id,
                    "quantity": item.quantity,
                    "uom": item.uom,
                    "pack_size": item.pack_size,
                    "package_size": item.package_size,
                    "net_weight": item.net_weight
                }
                for item in items
            ],
            "scanned_boxes": [
                {
                    "box_id": box.box_id,
                    "transaction_no": box.transaction_no,
                    "sku_id": box.sku_id,
                    "box_number": box.box_number,
                    "item_description": box.item_description,
                    "net_weight": box.net_weight,
                    "gross_weight": box.gross_weight
                }
                for box in scanned_boxes
            ],
            "transport_info": {
                "vehicle_number": transport_info.vehicle_number,
                "vehicle_number_other": transport_info.vehicle_number_other,
                "driver_name": transport_info.driver_name,
                "driver_name_other": transport_info.driver_name_other,
                "driver_phone": transport_info.driver_phone,
                "approval_authority": transport_info.approval_authority
            }
        }
    
    # ============================================
    # WAREHOUSE METHODS
    # ============================================
    
    def get_warehouses(self, is_active: bool = True) -> List[Dict[str, Any]]:
        """Get warehouses for dropdowns"""
        warehouses = self.db.query(WarehouseMaster).filter(
            WarehouseMaster.is_active == is_active
        ).order_by(WarehouseMaster.warehouse_name).all()
        
        return [
            {
                "id": wh.id,
                "warehouse_code": wh.warehouse_code,
                "warehouse_name": wh.warehouse_name,
                "address": wh.address,
                "city": wh.city,
                "state": wh.state,
                "pincode": wh.pincode,
                "gstin": wh.gstin,
                "contact_person": wh.contact_person,
                "contact_phone": wh.contact_phone,
                "contact_email": wh.contact_email,
                "is_active": wh.is_active,
                "created_at": wh.created_at,
                "updated_at": wh.updated_at
            }
            for wh in warehouses
        ]
    
    def get_warehouse_by_code(self, warehouse_code: str) -> Optional[Dict[str, Any]]:
        """Get warehouse by code"""
        warehouse = self.db.query(WarehouseMaster).filter(
            WarehouseMaster.warehouse_code == warehouse_code
        ).first()
        
        if warehouse:
            return {
                "id": warehouse.id,
                "warehouse_code": warehouse.warehouse_code,
                "warehouse_name": warehouse.warehouse_name,
                "address": warehouse.address,
                "city": warehouse.city,
                "state": warehouse.state,
                "pincode": warehouse.pincode,
                "gstin": warehouse.gstin,
                "contact_person": warehouse.contact_person,
                "contact_phone": warehouse.contact_phone,
                "contact_email": warehouse.contact_email,
                "is_active": warehouse.is_active
            }
        
        return None
    
    # ============================================
    # UTILITY METHODS
    # ============================================
    
    def _generate_request_no(self) -> str:
        """Generate request number in format REQYYYYMMDDXXX"""
        from app.models.transfer import generate_request_no
        return generate_request_no(self.db)
    
    def _generate_transfer_no(self) -> str:
        """Generate transfer number in format TRANSYYYYMMDDXXX"""
        from app.models.transfer import generate_transfer_no
        return generate_transfer_no(self.db)
    
    def get_status_options(self) -> List[Dict[str, str]]:
        """Get available status options"""
        return [
            {"value": "Pending", "label": "Pending"},
            {"value": "Approved", "label": "Approved"},
            {"value": "Rejected", "label": "Rejected"},
            {"value": "In Transit", "label": "In Transit"},
            {"value": "Completed", "label": "Completed"}
        ]
    
    def get_material_types(self) -> List[Dict[str, str]]:
        """Get available material types"""
        return [
            {"value": "RM", "label": "Raw Material"},
            {"value": "PM", "label": "Packaging Material"},
            {"value": "FG", "label": "Finished Good"},
            {"value": "SFG", "label": "Semi-Finished Good"}
        ]
    
    def update_transfer_status(self, transfer_no: str, new_status: str) -> bool:
        """Update transfer status"""
        transfer_request = self.db.query(TransferRequest).filter(
            TransferRequest.transfer_no == transfer_no
        ).first()
        
        if not transfer_request:
            return False
        
        transfer_request.status = new_status
        self.db.commit()
        return True
    
    def get_transfer_statistics(self) -> Dict[str, Any]:
        """Get transfer statistics for dashboard"""
        total_requests = self.db.query(TransferRequest).count()
        pending_requests = self.db.query(TransferRequest).filter(
            TransferRequest.status == "Pending"
        ).count()
        in_transit = self.db.query(TransferRequest).filter(
            TransferRequest.status == "In Transit"
        ).count()
        completed = self.db.query(TransferRequest).filter(
            TransferRequest.status == "Completed"
        ).count()
        
        return {
            "total_requests": total_requests,
            "pending_requests": pending_requests,
            "in_transit": in_transit,
            "completed": completed,
            "completion_rate": (completed / total_requests * 100) if total_requests > 0 else 0
        }

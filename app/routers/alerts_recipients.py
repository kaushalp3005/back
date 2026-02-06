# File: alerts_recipients_router.py
# Path: backend/app/routers/alerts_recipients.py

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alerts_recipients import AlertRecipient
from app.schemas.alerts_recipients import (
    AlertRecipientCreate, AlertRecipientUpdate, AlertRecipientResponse,
    BulkRecipientCreate, BulkRecipientUpdate, BulkRecipientDelete,
    EmailSendRequest, EmailSendResponse, RecipientsStats,
    StandardResponse, PaginatedResponse
)

router = APIRouter(prefix="/alerts", tags=["Alerts Recipients Management"])


# ============================================
# ALERT RECIPIENTS CRUD ENDPOINTS
# ============================================

@router.post("/recipients", response_model=StandardResponse)
async def create_recipient(
    recipient_data: AlertRecipientCreate,
    db: Session = Depends(get_db)
):
    """Create new alert recipient"""
    try:
        # Check if email already exists for the same module and company
        existing_recipient = db.query(AlertRecipient).filter(
            and_(
                AlertRecipient.email == recipient_data.email,
                AlertRecipient.module == recipient_data.module,
                AlertRecipient.company_code == recipient_data.company_code
            )
        ).first()
        
        if existing_recipient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipient with this email already exists for this module and company"
            )
        
        # Create new recipient
        recipient = AlertRecipient(
            name=recipient_data.name,
            email=recipient_data.email,
            phone_number=recipient_data.phone_number,
            module=recipient_data.module,
            company_code=recipient_data.company_code
        )
        db.add(recipient)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Alert recipient created successfully",
            data={"recipient_id": recipient.id, "name": recipient.name}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating alert recipient: {str(e)}"
        )


@router.get("/recipients", response_model=PaginatedResponse)
async def get_recipients(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    module: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get alert recipients with pagination and filtering"""
    query = db.query(AlertRecipient)
    
    if module:
        query = query.filter(AlertRecipient.module == module.upper())
    
    if company_code:
        query = query.filter(AlertRecipient.company_code == company_code)
    
    if is_active is not None:
        query = query.filter(AlertRecipient.is_active == is_active)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                AlertRecipient.name.ilike(search_term),
                AlertRecipient.email.ilike(search_term)
            )
        )
    
    total = query.count()
    recipients = query.order_by(asc(AlertRecipient.name))\
                      .offset((page - 1) * per_page)\
                      .limit(per_page)\
                      .all()
    
    return PaginatedResponse(
        success=True,
        message="Alert recipients retrieved successfully",
        data=[{
            "id": recipient.id,
            "name": recipient.name,
            "email": recipient.email,
            "phone_number": recipient.phone_number,
            "module": recipient.module,
            "is_active": recipient.is_active,
            "company_code": recipient.company_code,
            "created_at": recipient.created_at.isoformat(),
            "updated_at": recipient.updated_at.isoformat()
        } for recipient in recipients],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@router.get("/recipients/{recipient_id}", response_model=AlertRecipientResponse)
async def get_recipient(recipient_id: int, db: Session = Depends(get_db)):
    """Get specific alert recipient by ID"""
    recipient = db.query(AlertRecipient).filter(
        AlertRecipient.id == recipient_id
    ).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert recipient not found"
        )
    
    return recipient


@router.put("/recipients/{recipient_id}", response_model=StandardResponse)
async def update_recipient(
    recipient_id: int,
    recipient_data: AlertRecipientUpdate,
    db: Session = Depends(get_db)
):
    """Update alert recipient"""
    try:
        recipient = db.query(AlertRecipient).filter(
            AlertRecipient.id == recipient_id
        ).first()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert recipient not found"
            )
        
        # Check if email already exists for the same module and company (excluding current record)
        if recipient_data.email:
            existing_recipient = db.query(AlertRecipient).filter(
                and_(
                    AlertRecipient.email == recipient_data.email,
                    AlertRecipient.module == (recipient_data.module or recipient.module),
                    AlertRecipient.company_code == (recipient_data.company_code or recipient.company_code),
                    AlertRecipient.id != recipient_id
                )
            ).first()
            if existing_recipient:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Recipient with this email already exists for this module and company"
                )
        
        # Update fields
        update_data = recipient_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(recipient, field, value)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Alert recipient updated successfully",
            data={"recipient_id": recipient_id}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating alert recipient: {str(e)}"
        )


@router.delete("/recipients/{recipient_id}", response_model=StandardResponse)
async def delete_recipient(recipient_id: int, db: Session = Depends(get_db)):
    """Delete alert recipient"""
    try:
        recipient = db.query(AlertRecipient).filter(
            AlertRecipient.id == recipient_id
        ).first()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert recipient not found"
            )
        
        db.delete(recipient)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Alert recipient deleted successfully",
            data={"recipient_id": recipient_id}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting alert recipient: {str(e)}"
        )


# ============================================
# BULK OPERATIONS
# ============================================

@router.post("/recipients/bulk", response_model=StandardResponse)
async def create_bulk_recipients(
    bulk_data: BulkRecipientCreate,
    db: Session = Depends(get_db)
):
    """Create multiple alert recipients at once"""
    try:
        created_count = 0
        failed_recipients = []
        
        for recipient_data in bulk_data.recipients:
            try:
                # Check if email already exists for the same module and company
                existing_recipient = db.query(AlertRecipient).filter(
                    and_(
                        AlertRecipient.email == recipient_data.email,
                        AlertRecipient.module == recipient_data.module,
                        AlertRecipient.company_code == recipient_data.company_code
                    )
                ).first()
                
                if not existing_recipient:
                    recipient = AlertRecipient(
                        name=recipient_data.name,
                        email=recipient_data.email,
                        phone_number=recipient_data.phone_number,
                        module=recipient_data.module,
                        company_code=recipient_data.company_code
                    )
                    db.add(recipient)
                    created_count += 1
                else:
                    failed_recipients.append(f"{recipient_data.email} (already exists)")
                    
            except Exception as e:
                failed_recipients.append(f"{recipient_data.email} ({str(e)})")
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message=f"Bulk creation completed. Created: {created_count}, Failed: {len(failed_recipients)}",
            data={
                "created_count": created_count,
                "failed_count": len(failed_recipients),
                "failed_recipients": failed_recipients
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk creation: {str(e)}"
        )


@router.put("/recipients/bulk", response_model=StandardResponse)
async def update_bulk_recipients(
    bulk_data: BulkRecipientUpdate,
    db: Session = Depends(get_db)
):
    """Update multiple alert recipients at once"""
    try:
        updated_count = 0
        failed_recipients = []
        
        for recipient_id in bulk_data.recipient_ids:
            try:
                recipient = db.query(AlertRecipient).filter(
                    AlertRecipient.id == recipient_id
                ).first()
                
                if recipient:
                    update_data = bulk_data.update_data.dict(exclude_unset=True)
                    for field, value in update_data.items():
                        setattr(recipient, field, value)
                    updated_count += 1
                else:
                    failed_recipients.append(f"ID {recipient_id} (not found)")
                    
            except Exception as e:
                failed_recipients.append(f"ID {recipient_id} ({str(e)})")
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message=f"Bulk update completed. Updated: {updated_count}, Failed: {len(failed_recipients)}",
            data={
                "updated_count": updated_count,
                "failed_count": len(failed_recipients),
                "failed_recipients": failed_recipients
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk update: {str(e)}"
        )


@router.delete("/recipients/bulk", response_model=StandardResponse)
async def delete_bulk_recipients(
    bulk_data: BulkRecipientDelete,
    db: Session = Depends(get_db)
):
    """Delete multiple alert recipients at once"""
    try:
        deleted_count = 0
        failed_recipients = []
        
        for recipient_id in bulk_data.recipient_ids:
            try:
                recipient = db.query(AlertRecipient).filter(
                    AlertRecipient.id == recipient_id
                ).first()
                
                if recipient:
                    db.delete(recipient)
                    deleted_count += 1
                else:
                    failed_recipients.append(f"ID {recipient_id} (not found)")
                    
            except Exception as e:
                failed_recipients.append(f"ID {recipient_id} ({str(e)})")
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message=f"Bulk deletion completed. Deleted: {deleted_count}, Failed: {len(failed_recipients)}",
            data={
                "deleted_count": deleted_count,
                "failed_count": len(failed_recipients),
                "failed_recipients": failed_recipients
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in bulk deletion: {str(e)}"
        )


# ============================================
# UTILITY ENDPOINTS
# ============================================

@router.get("/recipients/module/{module}")
async def get_recipients_by_module(
    module: str,
    company_code: str = Query("CFPL"),
    is_active: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Get all active recipients for a specific module"""
    recipients = db.query(AlertRecipient).filter(
        and_(
            AlertRecipient.module == module.upper(),
            AlertRecipient.company_code == company_code,
            AlertRecipient.is_active == is_active
        )
    ).order_by(AlertRecipient.name).all()
    
    return {
        "success": True,
        "message": f"Recipients for module {module} retrieved successfully",
        "data": [{
            "id": recipient.id,
            "name": recipient.name,
            "email": recipient.email,
            "phone_number": recipient.phone_number,
            "module": recipient.module
        } for recipient in recipients],
        "total": len(recipients)
    }


@router.get("/recipients/stats", response_model=RecipientsStats)
async def get_recipients_statistics(
    company_code: str = Query("CFPL"),
    db: Session = Depends(get_db)
):
    """Get statistics about alert recipients"""
    try:
        # Total recipients
        total_recipients = db.query(AlertRecipient).filter(
            AlertRecipient.company_code == company_code
        ).count()
        
        # Active recipients
        active_recipients = db.query(AlertRecipient).filter(
            and_(
                AlertRecipient.company_code == company_code,
                AlertRecipient.is_active == True
            )
        ).count()
        
        # Inactive recipients
        inactive_recipients = total_recipients - active_recipients
        
        # Recipients by module
        module_stats = db.query(
            AlertRecipient.module,
            func.count(AlertRecipient.id).label('count')
        ).filter(
            AlertRecipient.company_code == company_code
        ).group_by(AlertRecipient.module).all()
        
        recipients_by_module = {stat.module: stat.count for stat in module_stats}
        
        # Recipients by company
        company_stats = db.query(
            AlertRecipient.company_code,
            func.count(AlertRecipient.id).label('count')
        ).group_by(AlertRecipient.company_code).all()
        
        recipients_by_company = {stat.company_code: stat.count for stat in company_stats}
        
        return RecipientsStats(
            total_recipients=total_recipients,
            active_recipients=active_recipients,
            inactive_recipients=inactive_recipients,
            recipients_by_module=recipients_by_module,
            recipients_by_company=recipients_by_company
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving statistics: {str(e)}"
        )


# ============================================
# EMAIL SENDING ENDPOINT (for frontend use)
# ============================================

@router.post("/send-email", response_model=EmailSendResponse)
async def send_email(
    email_request: EmailSendRequest,
    db: Session = Depends(get_db)
):
    """Send email to recipients (frontend will handle actual sending)"""
    try:
        # Validate recipients exist in database
        recipients_in_db = db.query(AlertRecipient).filter(
            and_(
                AlertRecipient.email.in_(email_request.recipients),
                AlertRecipient.is_active == True
            )
        ).all()
        
        valid_emails = [recipient.email for recipient in recipients_in_db]
        invalid_emails = [email for email in email_request.recipients if email not in valid_emails]
        
        # Here you would typically integrate with your email service
        # For now, we'll just return success for valid emails
        
        return EmailSendResponse(
            success=True,
            message=f"Email queued for sending. Valid recipients: {len(valid_emails)}, Invalid: {len(invalid_emails)}",
            recipients_sent=len(valid_emails),
            recipients_failed=len(invalid_emails),
            failed_recipients=invalid_emails
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing email request: {str(e)}"
        )

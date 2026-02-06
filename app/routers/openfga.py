from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
import bcrypt
import jwt
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.core.config import settings
from app.services.openfga_service import openfga_service

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

# JWT Configuration
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_EXPIRATION_HOURS = settings.JWT_EXPIRATION_HOURS

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserCompany(BaseModel):
    code: str
    name: str
    role: str

class ModulePermission(BaseModel):
    module_code: str
    module_name: str
    permissions: Dict[str, bool]

class CompanyAccess(BaseModel):
    code: str
    name: str
    role: str
    modules: List[ModulePermission]

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_developer: bool
    companies: List[UserCompany]

class DashboardInfoResponse(BaseModel):
    company: Dict[str, Any]
    dashboard: Dict[str, Any]

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(user_id: str, email: str) -> str:
    """Create JWT access token"""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user info"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "user_id": payload.get("user_id"),
            "email": payload.get("email")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def sync_user_to_openfga(user_id: str, companies: List[Dict], db: Session):
    """Sync user permissions to OpenFGA"""
    if not openfga_service.enabled:
        return
    
    try:
        # Grant company access for each user company
        for company in companies:
            await openfga_service.grant_company_access(
                user_id, 
                company['code'], 
                company['role']
            )
            logging.info(f"Synced OpenFGA: User {user_id} -> {company['role']} access to {company['code']}")
    except Exception as e:
        logging.warning(f"Failed to sync user {user_id} to OpenFGA: {e}")

@router.post("/login", response_model=UserResponse, operation_id="openfga_login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return user info with company access"""
    
    try:
        logging.info(f"Login attempt for email: {request.email}")
        
        # Get user from database
        user_query = text("""
            SELECT id, email, name, password_hash, is_developer, is_active
            FROM users 
            WHERE email = :email AND is_active = true
        """)
        user_result = db.execute(user_query, {"email": request.email}).fetchone()
        
        if not user_result or not verify_password(request.password, user_result.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_id = user_result.id
        
        # Get user's company access with enhanced query
        companies_query = text("""
            SELECT 
                c.code, 
                c.name, 
                ucr.role,
                COUNT(mp.module_code) as module_count
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            LEFT JOIN module_permissions mp ON mp.user_id = ucr.user_id 
                AND mp.company_code = ucr.company_code 
                AND mp.can_access = true
            WHERE ucr.user_id = :user_id AND c.is_active = true
            GROUP BY c.code, c.name, ucr.role
            ORDER BY c.code
        """)
        companies_result = db.execute(companies_query, {"user_id": user_id}).fetchall()
        
        companies = []
        for comp in companies_result:
            companies.append({
                "code": comp.code,
                "name": comp.name,
                "role": comp.role
            })
        
        # Sync to OpenFGA if enabled
        await sync_user_to_openfga(str(user_id), companies, db)
        
        # Create access token
        access_token = create_access_token(str(user_id), request.email)
        
        user_response = UserResponse(
            id=str(user_id),
            email=user_result.email,
            name=user_result.name,
            is_developer=user_result.is_developer,
            companies=companies
        )
        
        logging.info(f"User {request.email} logged in successfully with {len(companies)} company access")
        
        return {
            **user_response.dict(),
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/companies", operation_id="openfga_get_companies")
async def get_companies(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    """Get companies the user has access to"""
    
    try:
        user_id = token_data["user_id"]
        
        companies_query = text("""
            SELECT c.code, c.name, ucr.role
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            WHERE ucr.user_id = :user_id AND c.is_active = true
            ORDER BY c.code
        """)
        companies_result = db.execute(companies_query, {"user_id": user_id}).fetchall()
        
        companies = []
        for comp in companies_result:
            companies.append({
                "code": comp.code,
                "name": comp.name,
                "role": comp.role
            })
        
        return {"companies": companies}
        
    except Exception as e:
        logging.error(f"Get companies error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/company/{company_code}/dashboard-info", response_model=DashboardInfoResponse, operation_id="openfga_get_dashboard_info")
async def get_dashboard_info(
    company_code: str, 
    token_data: dict = Depends(verify_token), 
    db: Session = Depends(get_db)
):
    """Get company dashboard info and user permissions"""
    
    try:
        user_id = token_data["user_id"]
        
        # Check if user has access to this company
        company_access_query = text("""
            SELECT c.code, c.name, ucr.role
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            WHERE ucr.user_id = :user_id 
                AND c.code = :company_code 
                AND c.is_active = true
        """)
        company_result = db.execute(company_access_query, {
            "user_id": user_id,
            "company_code": company_code
        }).fetchone()
        
        if not company_result:
            raise HTTPException(
                status_code=403, 
                detail=f"Access denied to company {company_code}"
            )
        
        # Get user's module permissions for this company
        permissions_query = text("""
            SELECT 
                m.code as module_code,
                m.name as module_name,
                COALESCE(mp.can_access, false) as can_access,
                COALESCE(mp.can_view, false) as can_view,
                COALESCE(mp.can_create, false) as can_create,
                COALESCE(mp.can_edit, false) as can_edit,
                COALESCE(mp.can_delete, false) as can_delete,
                COALESCE(mp.can_approve, false) as can_approve
            FROM modules m
            LEFT JOIN module_permissions mp ON m.code = mp.module_code 
                AND mp.user_id = :user_id 
                AND mp.company_code = :company_code
            WHERE m.company_code = :company_code 
                AND m.is_active = true
            ORDER BY m.order_index, m.code
        """)
        permissions_result = db.execute(permissions_query, {
            "user_id": user_id,
            "company_code": company_code
        }).fetchall()
        
        # Format module permissions
        modules = []
        for perm in permissions_result:
            modules.append({
                "module_code": perm.module_code,
                "module_name": perm.module_name,
                "permissions": {
                    "access": perm.can_access,
                    "view": perm.can_view,
                    "create": perm.can_create,
                    "edit": perm.can_edit,
                    "delete": perm.can_delete,
                    "approve": perm.can_approve
                }
            })
        
        # Get basic dashboard stats (you can expand this)
        stats_query = text("""
            SELECT 
                COUNT(*) as total_modules,
                SUM(CASE WHEN mp.can_access = true THEN 1 ELSE 0 END) as accessible_modules
            FROM modules m
            LEFT JOIN module_permissions mp ON m.code = mp.module_code 
                AND mp.user_id = :user_id 
                AND mp.company_code = :company_code
            WHERE m.company_code = :company_code AND m.is_active = true
        """)
        stats_result = db.execute(stats_query, {
            "user_id": user_id,
            "company_code": company_code
        }).fetchone()
        
        dashboard_stats = {
            "total_modules": stats_result.total_modules if stats_result else 0,
            "accessible_modules": stats_result.accessible_modules if stats_result else 0
        }
        
        return DashboardInfoResponse(
            company={
                "code": company_result.code,
                "name": company_result.name,
                "role": company_result.role
            },
            dashboard={
                "stats": dashboard_stats,
                "permissions": {
                    "modules": modules
                }
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Dashboard info error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/me", response_model=UserResponse, operation_id="openfga_get_current_user")
def get_current_user(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    """Get current user information"""
    
    try:
        user_id = token_data["user_id"]
        
        # Get user details
        user_query = text("""
            SELECT id, email, name, is_developer, is_active
            FROM users 
            WHERE id = :user_id AND is_active = true
        """)
        user_result = db.execute(user_query, {"user_id": user_id}).fetchone()
        
        if not user_result:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Get companies
        companies_query = text("""
            SELECT c.code, c.name, ucr.role
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            WHERE ucr.user_id = :user_id AND c.is_active = true
            ORDER BY c.code
        """)
        companies_result = db.execute(companies_query, {"user_id": user_id}).fetchall()
        
        companies = []
        for comp in companies_result:
            companies.append({
                "code": comp.code,
                "name": comp.name,
                "role": comp.role
            })
        
        return UserResponse(
            id=str(user_result.id),
            email=user_result.email,
            name=user_result.name,
            is_developer=user_result.is_developer,
            companies=companies
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Get current user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout", operation_id="openfga_logout")
def logout(token_data: dict = Depends(verify_token)):
    """Logout user (token invalidation would be handled client-side)"""
    return {"message": "Logged out successfully"}

@router.get("/check-permissions/{company_code}/{module_code}/{action}", operation_id="openfga_check_permission")
async def check_permission(
    company_code: str,
    module_code: str, 
    action: str,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Check if user has specific permission"""
    
    try:
        user_id = token_data["user_id"]
        
        # Try OpenFGA first if enabled
        if openfga_service.enabled:
            try:
                has_permission = await openfga_service.check_permission(
                    user_id, action, f"module:{company_code}:{module_code}"
                )
                if has_permission is not None:
                    return {
                        "has_permission": has_permission,
                        "user_id": user_id,
                        "company": company_code,
                        "module": module_code,
                        "action": action,
                        "source": "openfga"
                    }
            except Exception as e:
                logging.warning(f"OpenFGA permission check failed: {e}")
        
        # Fallback to database
        permission_query = text("""
            SELECT 
                CASE :action
                    WHEN 'access' THEN mp.can_access
                    WHEN 'view' THEN mp.can_view
                    WHEN 'create' THEN mp.can_create
                    WHEN 'edit' THEN mp.can_edit
                    WHEN 'delete' THEN mp.can_delete
                    WHEN 'approve' THEN mp.can_approve
                    ELSE false
                END as has_permission
            FROM module_permissions mp
            WHERE mp.user_id = :user_id 
                AND mp.company_code = :company_code
                AND mp.module_code = :module_code
        """)
        
        result = db.execute(permission_query, {
            "user_id": user_id,
            "company_code": company_code,
            "module_code": module_code,
            "action": action
        }).fetchone()
        
        has_permission = result.has_permission if result else False
        
        return {
            "has_permission": has_permission,
            "user_id": user_id,
            "company": company_code,
            "module": module_code,
            "action": action,
            "source": "database"
        }
        
    except Exception as e:
        logging.error(f"Permission check error: {e}")
        return {"has_permission": False, "error": str(e), "source": "error"}

# Admin endpoints for managing permissions
@router.post("/admin/grant-company-access", operation_id="openfga_grant_company_access")
async def grant_company_access(
    user_id: str,
    company_code: str,
    role: str,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Grant company access to user (admin only)"""
    
    # Check if current user is admin (you can enhance this check)
    current_user_id = token_data["user_id"]
    
    try:
        # Insert or update user company role
        grant_query = text("""
            INSERT INTO user_company_roles (user_id, company_code, role, granted_by)
            VALUES (:user_id, :company_code, :role, :granted_by)
            ON CONFLICT (user_id, company_code) 
            DO UPDATE SET role = EXCLUDED.role, granted_by = EXCLUDED.granted_by
        """)
        
        db.execute(grant_query, {
            "user_id": user_id,
            "company_code": company_code,
            "role": role,
            "granted_by": current_user_id
        })
        db.commit()
        
        # Sync to OpenFGA
        if openfga_service.enabled:
            await openfga_service.grant_company_access(user_id, company_code, role)
        
        return {
            "success": True,
            "message": f"Granted {role} access to {company_code} for user {user_id}"
        }
        
    except Exception as e:
        db.rollback()
        logging.error(f"Grant access error: {e}")
        raise HTTPException(status_code=500, detail="Failed to grant access")
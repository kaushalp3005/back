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

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

# JWT Configuration
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_EXPIRATION_HOURS = settings.JWT_EXPIRATION_HOURS

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CompanyInfo(BaseModel):
    code: str
    name: str
    role: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_developer: bool
    companies: List[CompanyInfo]
    access_token: str
    token_type: str = "bearer"

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash with NULL protection"""
    if not password or not hashed:
        return False
    
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError) as e:
        logging.error(f"Password verification error: {e}")
        return False

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

@router.post("/login", response_model=UserResponse, operation_id="auth_login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return user info with company access"""
    
    try:
        logging.info(f"Login attempt for email: {request.email}")
        
        # Get user from database with proper error handling
        user_query = text("""
            SELECT id, email, name, password_hash, is_developer, is_active
            FROM users 
            WHERE email = :email AND is_active = true
        """)
        user_result = db.execute(user_query, {"email": request.email}).fetchone()
        
        if not user_result:
            logging.warning(f"User not found: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Check if password hash exists
        if not user_result.password_hash:
            logging.error(f"User {request.email} has no password hash")
            raise HTTPException(status_code=401, detail="Account configuration error")
        
        # Verify password
        if not verify_password(request.password, user_result.password_hash):
            logging.warning(f"Invalid password for user: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_id = user_result.id
        
        # Get user's company access from database
        companies_query = text("""
            SELECT 
                c.code, 
                c.name, 
                ucr.role
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            WHERE ucr.user_id = :user_id 
                AND c.is_active = true
            ORDER BY 
                CASE ucr.role 
                    WHEN 'developer' THEN 6
                    WHEN 'admin' THEN 5
                    WHEN 'ops' THEN 4
                    WHEN 'approver' THEN 3
                    WHEN 'viewer' THEN 2
                    ELSE 1
                END DESC,
                c.code ASC
        """)
        companies_result = db.execute(companies_query, {"user_id": user_id}).fetchall()
        
        if not companies_result:
            logging.warning(f"User {request.email} has no company access")
            raise HTTPException(status_code=403, detail="No company access. Contact administrator.")
        
        # Format companies list
        companies = []
        for comp in companies_result:
            companies.append(CompanyInfo(
                code=comp.code,
                name=comp.name,
                role=comp.role
            ))
        
        logging.info(f"User {request.email} has access to {len(companies)} companies: {[c.code for c in companies]}")
        
        # Create access token
        access_token = create_access_token(str(user_id), request.email)
        
        # Return user response
        response = UserResponse(
            id=str(user_id),
            email=user_result.email,
            name=user_result.name,
            is_developer=user_result.is_developer,
            companies=companies,
            access_token=access_token
        )
        
        logging.info(f"Login successful for {request.email} with {len(companies)} companies")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Login error for {request.email}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/companies", operation_id="auth_get_companies")
def get_companies(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    """Get companies the user has access to"""
    
    try:
        user_id = token_data["user_id"]
        
        companies_query = text("""
            SELECT c.code, c.name, ucr.role
            FROM user_company_roles ucr
            JOIN companies c ON ucr.company_code = c.code
            WHERE ucr.user_id = :user_id AND c.is_active = true
            ORDER BY 
                CASE ucr.role 
                    WHEN 'developer' THEN 6
                    WHEN 'admin' THEN 5
                    WHEN 'ops' THEN 4
                    WHEN 'approver' THEN 3
                    WHEN 'viewer' THEN 2
                    ELSE 1
                END DESC,
                c.code ASC
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

@router.get("/company/{company_code}/dashboard-info", operation_id="auth_get_dashboard_info")
def get_dashboard_info(
    company_code: str, 
    token_data: dict = Depends(verify_token), 
    db: Session = Depends(get_db)
):
    """Get company dashboard info and user permissions"""
    
    try:
        user_id = token_data["user_id"]
        
        logging.info(f"Dashboard info request: user={user_id}, company={company_code}")
        
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
            logging.warning(f"User {user_id} denied access to company {company_code}")
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
        
        # Get basic dashboard stats
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
        
        response = {
            "company": {
                "code": company_result.code,
                "name": company_result.name,
                "role": company_result.role
            },
            "dashboard": {
                "stats": dashboard_stats,
                "permissions": {
                    "modules": modules
                }
            }
        }
        
        logging.info(f"Dashboard info response for {company_code}: {len(modules)} modules, {dashboard_stats['accessible_modules']} accessible")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Dashboard info error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/me", operation_id="auth_get_current_user")
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
        
        return {
            "id": str(user_result.id),
            "email": user_result.email,
            "name": user_result.name,
            "is_developer": user_result.is_developer,
            "companies": companies
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Get current user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout", operation_id="auth_logout")
def logout(token_data: dict = Depends(verify_token)):
    """Logout user (token invalidation would be handled client-side)"""
    return {"message": "Logged out successfully"}

@router.get("/check-permissions/{company_code}/{module_code}/{action}", operation_id="auth_check_permission")
def check_permission(
    company_code: str,
    module_code: str, 
    action: str,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Check if user has specific permission"""
    
    try:
        user_id = token_data["user_id"]
        
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
            "action": action
        }
        
    except Exception as e:
        logging.error(f"Permission check error: {e}")
        return {"has_permission": False, "error": str(e)}
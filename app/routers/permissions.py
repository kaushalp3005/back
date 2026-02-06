from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import bcrypt
import jwt
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/permissions", tags=["permissions"])
security = HTTPBearer()

# JWT Configuration
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_EXPIRATION_HOURS = settings.JWT_EXPIRATION_HOURS

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_developer: bool
    companies: List[dict]

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
    except jwt.JWTError:  # FIXED: Changed from jwt.InvalidTokenError to jwt.JWTError
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/login", response_model=UserResponse, operation_id="permissions_login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return user info with company access"""
    
    try:
        # Debug logging
        logging.info(f"Login attempt for email: {request.email}")
        
        # Get user from database
        user_query = text("""
            SELECT id, email, name, password_hash, is_developer, is_active
            FROM users 
            WHERE email = :email AND is_active = true
        """)
        user_result = db.execute(user_query, {"email": request.email}).fetchone()
        
        if not user_result:
            logging.warning(f"No user found for email: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Debug password verification
        password_valid = verify_password(request.password, user_result.password_hash)
        logging.info(f"Password verification result: {password_valid}")
        
        if not password_valid:
            logging.warning(f"Password verification failed for email: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_id = user_result.id
        
        # Get user's company access
        companies_query = text("""
            SELECT c.code, c.name, uc.role
            FROM user_companies uc
            JOIN companies c ON uc.company_id = c.id
            WHERE uc.user_id = :user_id AND c.is_active = true
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

@router.get("/me", response_model=UserResponse, operation_id="permissions_get_current_user")
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
            SELECT c.code, c.name, uc.role
            FROM user_companies uc
            JOIN companies c ON uc.company_id = c.id
            WHERE uc.user_id = :user_id AND c.is_active = true
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

@router.post("/logout", operation_id="permissions_logout")
def logout(token_data: dict = Depends(verify_token)):
    """Logout user (token invalidation would be handled client-side)"""
    return {"message": "Logged out successfully"}

@router.get("/check-permissions/{company}/{module}/{action}", operation_id="permissions_check_permission")
def check_permission(
    company: str,
    module: str, 
    action: str,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Check if user has specific permission"""
    
    try:
        user_id = token_data["user_id"]
        
        # Check user permission
        permission_query = text("""
            SELECT COUNT(*) as count
            FROM user_permissions up
            JOIN companies c ON up.company_id = c.id
            JOIN modules m ON up.module_id = m.id
            JOIN actions a ON up.action_id = a.id
            WHERE up.user_id = :user_id 
                AND c.code = :company
                AND m.code = :module
                AND a.code = :action
                AND up.granted = true
        """)
        
        result = db.execute(permission_query, {
            "user_id": user_id,
            "company": company,
            "module": module,
            "action": action
        }).fetchone()
        
        has_permission = result.count > 0 if result else False
        
        return {
            "has_permission": has_permission,
            "user_id": user_id,
            "company": company,
            "module": module,
            "action": action
        }
        
    except Exception as e:
        logging.error(f"Permission check error: {e}")
        return {"has_permission": False, "error": str(e)}
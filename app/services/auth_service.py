# File: app/services/auth_service.py
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
import jwt
import logging
from typing import Dict, Optional

from app.core.config import settings
from app.core.database import get_db
from app.services.openfga_service import openfga_service

security = HTTPBearer()
logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.jwt_secret = settings.JWT_SECRET
        self.jwt_algorithm = settings.JWT_ALGORITHM
    
    def verify_token(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, str]:
        """Verify JWT token and return user info"""
        try:
            payload = jwt.decode(
                credentials.credentials, 
                self.jwt_secret, 
                algorithms=[self.jwt_algorithm]
            )
            return {
                "user_id": payload.get("user_id"),
                "email": payload.get("email")
            }
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def require_company_access(self, company: str, role: str = "member"):
        """Decorator to require company access (with OpenFGA fallback to database)"""
        def permission_check(
            token_data: dict = Depends(self.verify_token),
            db: Session = Depends(get_db)
        ):
            user_id = token_data["user_id"]
            
            # Try OpenFGA first if enabled
            if openfga_service.enabled:
                try:
                    import asyncio
                    has_access = asyncio.run(
                        openfga_service.check_company_access(user_id, company, role)
                    )
                    if has_access:
                        return token_data
                except Exception as e:
                    logger.warning(f"OpenFGA check failed, falling back to database: {e}")
            
            # Fallback to database check
            permission_query = text("""
                SELECT COUNT(*) as count
                FROM user_companies uc
                JOIN companies c ON uc.company_id = c.id
                WHERE uc.user_id = :user_id 
                    AND c.code = :company
                    AND (uc.role = :role OR uc.role = 'admin')
            """)
            
            result = db.execute(permission_query, {
                "user_id": user_id,
                "company": company,
                "role": role
            }).fetchone()
            
            has_permission = result.count > 0 if result else False
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Company access denied: {company}"
                )
            
            return token_data
        
        return permission_check
    
    def require_permission(self, company: str, module: str, action: str):
        """Decorator to require specific permission (database-based for now)"""
        def permission_check(
            token_data: dict = Depends(self.verify_token),
            db: Session = Depends(get_db)
        ):
            user_id = token_data["user_id"]
            
            # Database permission check
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
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {action} {module} for {company}"
                )
            
            return token_data
        
        return permission_check

# Global service instance
auth_service = AuthService()

# Convenience functions for routes
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return auth_service.verify_token(credentials)

def require_company_access(company: str, role: str = "member"):
    return auth_service.require_company_access(company, role)

def require_permission(company: str, module: str, action: str):
    return auth_service.require_permission(company, module, action)
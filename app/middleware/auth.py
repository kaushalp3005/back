from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
import jwt
import logging

from app.core.config import settings
from app.core.database import get_db

security = HTTPBearer()

class AuthMiddleware:
    def __init__(self):
        self.jwt_secret = settings.JWT_SECRET
        self.jwt_algorithm = settings.JWT_ALGORITHM
    
    def verify_token(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
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
    
    def require_permission(self, company: str, module: str, action: str):
        """Decorator to require specific permission"""
        def permission_check(
            token_data: dict = Depends(self.verify_token),
            db: Session = Depends(get_db)
        ):
            user_id = token_data["user_id"]
            
            # Check permission
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

auth_middleware = AuthMiddleware()
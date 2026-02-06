# File: app/services/openfga_service.py
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from openfga_sdk import OpenFgaClient, ClientConfiguration
    from openfga_sdk.models import CheckRequest, WriteRequest, TupleKey
    OPENFGA_AVAILABLE = True
except ImportError:
    OPENFGA_AVAILABLE = False
    logging.warning("OpenFGA SDK not available. Install with: pip install openfga-sdk")

from app.core.config import settings

logger = logging.getLogger(__name__)

class OpenFGAService:
    """OpenFGA service for authorization management"""
    
    def __init__(self):
        self.enabled = settings.openfga_enabled and OPENFGA_AVAILABLE
        if not self.enabled:
            logger.warning("OpenFGA service disabled or SDK not available")
            return
            
        # Validate configuration
        if not settings.openfga_api_url or not settings.openfga_store_id:
            logger.error("OpenFGA configuration incomplete. Required: OPENFGA_API_URL, OPENFGA_STORE_ID")
            self.enabled = False
            return
        
        try:
            # Initialize OpenFGA client with SDK v0.3.4
            configuration = ClientConfiguration(
                api_scheme="https",
                api_host=settings.openfga_api_url.replace("https://", "").replace("http://", ""),
                store_id=settings.openfga_store_id,
            )
            
            self.client = OpenFgaClient(configuration)
            
            # Set authorization model if provided
            if settings.openfga_model_id:
                configuration.authorization_model_id = settings.openfga_model_id
            
            logger.info(f"OpenFGA client initialized: {settings.openfga_api_url}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenFGA client: {e}")
            self.enabled = False
    
    async def check_permission(self, user_id: str, relation: str, object_id: str) -> bool:
        """Check if user has permission on object"""
        if not self.enabled:
            return True  # Fallback to allow access when disabled
        
        try:
            request = CheckRequest(
                user=f"user:{user_id}",
                relation=relation,
                object=object_id
            )
            
            response = await self.client.check(request)
            return response.allowed
            
        except Exception as e:
            logger.error(f"OpenFGA check error: {e}")
            return True  # Fallback to allow access on error
    
    async def write_tuples(self, writes: List[TupleKey], deletes: List[TupleKey] = None) -> bool:
        """Write authorization tuples"""
        if not self.enabled:
            return True
        
        try:
            request = WriteRequest(
                writes=writes,
                deletes=deletes or []
            )
            
            await self.client.write(request)
            return True
            
        except Exception as e:
            logger.error(f"OpenFGA write error: {e}")
            return False
    
    async def grant_company_access(self, user_id: str, company_code: str, role: str) -> bool:
        """Grant user access to company with specific role"""
        tuple_key = TupleKey(
            user=f"user:{user_id}",
            relation=role,
            object=f"company:{company_code}"
        )
        
        return await self.write_tuples([tuple_key])
    
    async def revoke_company_access(self, user_id: str, company_code: str, role: str) -> bool:
        """Revoke user access to company"""
        tuple_key = TupleKey(
            user=f"user:{user_id}",
            relation=role,
            object=f"company:{company_code}"
        )
        
        return await self.write_tuples([], [tuple_key])
    
    async def grant_document_permission(self, user_id: str, document_id: str, permission: str) -> bool:
        """Grant document permission to user"""
        tuple_key = TupleKey(
            user=f"user:{user_id}",
            relation=permission,
            object=f"doc:{document_id}"
        )
        
        return await self.write_tuples([tuple_key])
    
    async def check_document_permission(self, user_id: str, document_id: str, permission: str) -> bool:
        """Check if user has document permission"""
        return await self.check_permission(
            user_id=user_id,
            relation=permission,
            object_id=f"doc:{document_id}"
        )
    
    async def check_company_access(self, user_id: str, company_code: str, role: str) -> bool:
        """Check if user has company access"""
        return await self.check_permission(
            user_id=user_id,
            relation=role,
            object_id=f"company:{company_code}"
        )
    
    async def get_user_companies(self, user_id: str) -> List[Dict[str, str]]:
        """Get companies user has access to (fallback implementation)"""
        # This would require OpenFGA list API or we maintain company list separately
        # For now, return empty list and rely on database-based company access
        return []

# Global service instance
openfga_service = OpenFGAService()

# Dependency for FastAPI
async def get_openfga_service() -> OpenFGAService:
    return openfga_service
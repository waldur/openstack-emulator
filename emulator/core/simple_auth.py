"""Simplified authentication for single-process emulator."""

import logging
from typing import Any
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def validate_token_simple(auth_token: str | None, service_name: str = "unknown") -> Any:
    """
    Validate token using shared database (single-process architecture).
    
    Args:
        auth_token: The authentication token to validate
        service_name: Name of the calling service (for logging)
        
    Returns:
        Token data if valid
        
    Raises:
        HTTPException: If token is invalid or authentication fails
    """
    logger.debug("%s: Received auth token: %s", service_name, auth_token)

    if not auth_token:
        logger.debug("%s: No auth token provided", service_name)
        raise HTTPException(status_code=401, detail="Authentication required")

    # Use shared database for token validation
    from emulator.core.database import db
    token = db.validate_token(auth_token)
    if not token:
        logger.debug("%s: Token validation failed in database", service_name)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    logger.debug("%s: Token validation succeeded", service_name)
    
    # Return a simplified object with commonly needed fields
    return type('TokenInfo', (), {
        'project_id': token.project_id,
        'project_name': token.project_name,
        'user_id': token.user_id,
        'user_name': token.user_name,
        'raw_token': token  # Keep original for any other needs
    })()
"""Simplified authentication for single-process emulator."""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """Information extracted from a validated token."""

    project_id: str
    project_name: str
    user_id: str
    user_name: str
    raw_token: Any  # The original Token object
    is_admin: bool = False


def validate_token_simple(auth_token: str | None, service_name: str = "unknown") -> TokenInfo:
    """
    Validate token using shared database (single-process architecture).

    Args:
        auth_token: The authentication token to validate
        service_name: Name of the calling service (for logging)

    Returns:
        TokenInfo with commonly needed fields

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

    # A token scoped to the cloud "admin" project is privileged and may
    # read/modify resources in any project when addressing them by id (this is
    # how Waldur operates on a tenant's resources from its admin session, e.g.
    # setting a router's external gateway or toggling port security). Tenant
    # sessions are scoped to their own project and stay isolated. This does NOT
    # widen list results — those stay scoped to the token's project unless an
    # explicit filter is supplied.
    is_admin = (token.project_name or "").lower() == "admin"

    # Return a structured object with commonly needed fields
    return TokenInfo(
        project_id=token.project_id,
        project_name=token.project_name,
        user_id=token.user_id,
        user_name=token.user_name,
        raw_token=token,
        is_admin=is_admin,
    )

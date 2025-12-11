"""Keystone Identity API endpoints for OpenStack emulator."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from emulator.core.database import db

router = APIRouter(tags=["identity"])


# Request models
class PasswordIdentity(BaseModel):
    """Password identity for authentication."""

    methods: list[str]
    password: dict[str, Any]


class AuthScope(BaseModel):
    """Authentication scope."""

    project: dict[str, Any] | None = None
    domain: dict[str, Any] | None = None


class AuthRequest(BaseModel):
    """Authentication request body."""

    identity: PasswordIdentity
    scope: AuthScope | None = None


class AuthBody(BaseModel):
    """Wrapper for auth request."""

    auth: AuthRequest


# API Version endpoints
@router.get("/")
async def list_versions() -> dict[str, Any]:
    """List all Identity API versions."""
    return {
        "versions": {
            "values": [
                {
                    "id": "v3.14",
                    "status": "stable",
                    "updated": "2020-04-07T00:00:00Z",
                    "links": [{"rel": "self", "href": "/v3/"}],
                    "media-types": [
                        {
                            "base": "application/json",
                            "type": "application/vnd.openstack.identity-v3+json",
                        }
                    ],
                }
            ]
        }
    }


@router.get("/v3")
@router.get("/v3/")
async def get_version_v3(request: Request) -> dict[str, Any]:
    """Get Identity API v3 details."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "version": {
            "id": "v3.14",
            "status": "stable",
            "updated": "2020-04-07T00:00:00Z",
            "links": [{"rel": "self", "href": f"{base_url}/v3/"}],
            "media-types": [
                {
                    "base": "application/json",
                    "type": "application/vnd.openstack.identity-v3+json",
                }
            ],
        }
    }


# Authentication endpoints
@router.post("/v3/auth/tokens")
async def create_token(body: AuthBody, request: Request, response: Response) -> dict[str, Any]:
    """Create a new authentication token.

    This is a simplified implementation that accepts any credentials
    and returns a valid token for testing purposes.
    """
    base_url = str(request.base_url).rstrip("/")

    # Extract user info from request (simplified - accepts anything)
    user_info = body.auth.identity.password.get("user", {})
    user_name = user_info.get("name", "admin")

    project_name = "admin"
    if body.auth.scope and body.auth.scope.project:
        project_name = body.auth.scope.project.get("name", "admin")

    # Create token
    token = db.create_token(
        user_name=user_name,
        project_name=project_name,
        base_url=base_url,
    )

    # Set token in header
    response.headers["X-Subject-Token"] = token.id

    return token.to_dict()


@router.get("/v3/auth/tokens")
async def validate_token(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    x_subject_token: str = Header(..., alias="X-Subject-Token"),
) -> dict[str, Any]:
    """Validate a token and return its details."""
    token = db.validate_token(x_subject_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    return token.to_dict()


@router.head("/v3/auth/tokens")
async def check_token(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    x_subject_token: str = Header(..., alias="X-Subject-Token"),
) -> Response:
    """Check if a token is valid (no response body)."""
    token = db.validate_token(x_subject_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    return Response(status_code=200)


@router.delete("/v3/auth/tokens")
async def revoke_token(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    x_subject_token: str = Header(..., alias="X-Subject-Token"),
) -> Response:
    """Revoke a token."""
    if not db.revoke_token(x_subject_token):
        raise HTTPException(status_code=404, detail="Token not found")

    return Response(status_code=204)


@router.get("/v3/auth/catalog")
async def get_catalog(
    request: Request,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get the service catalog for the current token."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    return {"catalog": token.catalog}


# Projects endpoint (simplified)
@router.get("/v3/projects")
async def list_projects(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List projects (simplified - returns default project)."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    return {
        "projects": [
            {
                "id": token.project_id,
                "name": token.project_name,
                "domain_id": token.domain_id,
                "description": "Default project",
                "enabled": True,
                "is_domain": False,
                "links": {"self": f"/v3/projects/{token.project_id}"},
            }
        ],
        "links": {"self": "/v3/projects", "previous": None, "next": None},
    }


@router.get("/v3/projects/{project_id}")
async def get_project(
    project_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a project by ID."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    if project_id != token.project_id:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "project": {
            "id": token.project_id,
            "name": token.project_name,
            "domain_id": token.domain_id,
            "description": "Default project",
            "enabled": True,
            "is_domain": False,
            "links": {"self": f"/v3/projects/{token.project_id}"},
        }
    }


# Users endpoint (simplified)
@router.get("/v3/users")
async def list_users(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List users (simplified - returns current user)."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    return {
        "users": [
            {
                "id": token.user_id,
                "name": token.user_name,
                "domain_id": token.domain_id,
                "enabled": True,
                "links": {"self": f"/v3/users/{token.user_id}"},
            }
        ],
        "links": {"self": "/v3/users", "previous": None, "next": None},
    }


@router.get("/v3/users/{user_id}")
async def get_user(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a user by ID."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")

    if user_id != token.user_id:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user": {
            "id": token.user_id,
            "name": token.user_name,
            "domain_id": token.domain_id,
            "enabled": True,
            "links": {"self": f"/v3/users/{token.user_id}"},
        }
    }

"""Keystone Identity API v3 endpoints for OpenStack emulator."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from emulator.core.database import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])


# Request models
class AuthIdentity(BaseModel):
    """Authentication identity that supports both password and token methods."""

    methods: list[str]
    password: dict[str, Any] | None = None
    token: dict[str, str] | None = None
    application_credential: dict[str, Any] | None = None


class AuthScope(BaseModel):
    """Authentication scope."""

    project: dict[str, Any] | None = None
    domain: dict[str, Any] | None = None


class AuthRequest(BaseModel):
    """Authentication request body."""

    identity: AuthIdentity
    scope: AuthScope | None = None


class AuthBody(BaseModel):
    """Wrapper for auth request."""

    auth: AuthRequest


class DomainCreate(BaseModel):
    """Domain creation request."""

    name: str
    description: str = ""
    enabled: bool = True


class DomainUpdate(BaseModel):
    """Domain update request."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class ProjectCreate(BaseModel):
    """Project creation request."""

    name: str
    domain_id: str = "default"
    description: str = ""
    enabled: bool = True
    parent_id: str | None = None
    is_domain: bool = False
    tags: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    """Project update request."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    domain_id: str | None = None
    tags: list[str] | None = None


class ProjectTagsUpdate(BaseModel):
    """Replace the full tag list of a project."""

    tags: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    """User creation request."""

    name: str
    domain_id: str = "default"
    password: str | None = None
    email: str = ""
    description: str = ""
    enabled: bool = True
    default_project_id: str | None = None


class UserUpdate(BaseModel):
    """User update request."""

    name: str | None = None
    password: str | None = None
    email: str | None = None
    description: str | None = None
    enabled: bool | None = None
    default_project_id: str | None = None


class RoleCreate(BaseModel):
    """Role creation request."""

    name: str
    description: str = ""
    domain_id: str | None = None


class RoleUpdate(BaseModel):
    """Role update request."""

    name: str | None = None
    description: str | None = None


class GroupCreate(BaseModel):
    """Group creation request."""

    name: str
    domain_id: str = "default"
    description: str = ""


class GroupUpdate(BaseModel):
    """Group update request."""

    name: str | None = None
    description: str | None = None


class ServiceCreate(BaseModel):
    """Service creation request."""

    name: str
    type: str
    description: str = ""
    enabled: bool = True


class ServiceUpdate(BaseModel):
    """Service update request."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class EndpointCreate(BaseModel):
    """Endpoint creation request."""

    service_id: str
    interface: str
    url: str
    region_id: str | None = None
    enabled: bool = True


class EndpointUpdate(BaseModel):
    """Endpoint update request."""

    interface: str | None = None
    url: str | None = None
    region_id: str | None = None
    enabled: bool | None = None


class RegionCreate(BaseModel):
    """Region creation request."""

    id: str
    description: str = ""
    parent_region_id: str | None = None


class RegionUpdate(BaseModel):
    """Region update request."""

    description: str | None = None
    parent_region_id: str | None = None


class CredentialCreate(BaseModel):
    """Credential creation request."""

    user_id: str
    type: str
    blob: str
    project_id: str | None = None


class CredentialUpdate(BaseModel):
    """Credential update request."""

    blob: str | None = None
    project_id: str | None = None


def validate_token_header(x_auth_token: str) -> Any:
    """Validate auth token and return token object."""
    token = db.validate_token(x_auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Token not found or expired")
    return token


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
    logger.debug("Keystone create_token called with body: %s", body)
    base_url = str(request.base_url).rstrip("/")

    # Determine authentication method
    auth_methods = body.auth.identity.methods
    logger.debug("Auth methods: %s", auth_methods)

    user_name = "admin"
    domain_id = "default"
    # Set when the method identifies an exact user (token rescoping, application
    # credentials); takes precedence over the name lookup in create_token.
    resolved_user_id: str | None = None
    # Application credentials carry their own immutable scope.
    forced_project_id: str | None = None
    forced_roles: list[dict[str, str]] | None = None
    federation_context: dict[str, Any] = {}

    if "application_credential" in auth_methods and body.auth.identity.application_credential:
        logger.debug("Using application credential authentication")
        app_cred_data = body.auth.identity.application_credential
        secret = app_cred_data.get("secret")
        cred = None
        if app_cred_data.get("id"):
            cred = db.find_application_credential(cred_id=app_cred_data["id"])
        elif app_cred_data.get("name"):
            user_ref = app_cred_data.get("user") or {}
            owner_id = user_ref.get("id")
            if not owner_id and user_ref.get("name"):
                owner = db.get_user_by_name(user_ref["name"], user_ref.get("domain", {}).get("id"))
                owner_id = owner.id if owner else None
            cred = db.find_application_credential(name=app_cred_data["name"], user_id=owner_id)
        if cred is None or not secret or cred.secret != secret:
            raise HTTPException(status_code=401, detail="Invalid application credential")
        if cred.expires_at and cred.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Application credential has expired")

        resolved_user_id = cred.user_id
        owner_user = db.get_user(cred.user_id)
        if owner_user:
            user_name = owner_user.name
            domain_id = owner_user.domain_id
        forced_project_id = cred.project_id
        # The credential's own role list is authoritative; it is a subset of what
        # the owning user holds, so it must not be widened by the default-role
        # fallback in create_token.
        forced_roles = cred.roles or []

    elif "password" in auth_methods and body.auth.identity.password:
        # Password-based authentication
        logger.debug("Using password authentication")
        logger.debug("Auth identity password: %s", body.auth.identity.password)
        user_info = body.auth.identity.password.get("user", {})
        logger.debug("Extracted user_info: %s", user_info)
        user_name = user_info.get("name", "admin")
        user_domain = user_info.get("domain", {})
        domain_id = user_domain.get("id", "default")
        if not domain_id:
            domain_name = user_domain.get("name", "Default")
            domain = db.get_domain_by_name(domain_name)
            domain_id = domain.id if domain else "default"

    elif "token" in auth_methods and body.auth.identity.token:
        # Token-based authentication (re-authentication with existing token)
        logger.debug("Using token authentication")
        existing_token_id = body.auth.identity.token.get("id")
        logger.debug("Existing token ID: %s", existing_token_id)

        # Validate the existing token
        existing_token = db.validate_token(existing_token_id) if existing_token_id else None
        if existing_token:
            logger.debug("Existing token is valid, using its user info")
            user_name = existing_token.user_name
            domain_id = existing_token.domain_id
            # Carry the exact user across the rescope. Federated authentication
            # relies on this: the unscoped token names a user that may not be
            # resolvable by name alone, and its provenance must survive so the
            # scoped token is still recognisably federated.
            resolved_user_id = existing_token.user_id
            if existing_token.is_federated:
                federation_context = {
                    "is_federated": True,
                    "idp_id": existing_token.idp_id,
                    "protocol_id": existing_token.protocol_id,
                    "groups": list(existing_token.groups),
                }
        else:
            logger.debug("Existing token is invalid, using defaults")
            # For emulator purposes, we'll still allow token creation even with invalid existing token
            user_name = "admin"
            domain_id = "default"

    else:
        logger.debug("No recognized auth method found, using defaults")

    # Extract project info. Scope may be by id (Waldur scopes tenant sessions by
    # project id) or by name; honor whichever is provided.
    project_name = "admin"
    project_id = None
    if forced_project_id:
        # An application credential is bound to the project it was created in;
        # the request may not rescope it.
        project_id = forced_project_id
        forced_project = db.get_project(forced_project_id)
        project_name = forced_project.name if forced_project else ""
    elif body.auth.scope and body.auth.scope.project:
        project_scope = body.auth.scope.project
        project_id = project_scope.get("id")
        # Never invent the name "admin" for an id-scoped request. A token whose
        # project is named "admin" is privileged (see validate_token_simple), so
        # defaulting the name here meant that scoping to an id the emulator did
        # not know about produced an admin token with cross-tenant access.
        # Unscoped requests keep the historical admin default.
        project_name = project_scope.get("name") or ("" if project_id else "admin")

    logger.debug(
        "Creating token for user: %s, project: %s (id=%s), domain: %s",
        user_name,
        project_name,
        project_id,
        domain_id,
    )

    # Create token
    token = db.create_token(
        user_name=user_name,
        project_name=project_name,
        base_url=base_url,
        domain_id=domain_id,
        project_id=project_id,
        user_id=resolved_user_id,
        methods=auth_methods,
        roles=forced_roles,
        # An application credential confers exactly the roles recorded on it, so
        # the "no assignments means admin" convenience must not apply.
        grant_default_admin_role=forced_roles is None,
        **federation_context,
    )

    # Set token in header
    response.headers["X-Subject-Token"] = token.id
    logger.info("Token created successfully: %s", token.id)
    logger.debug("Token will be added to database and available for validation")

    token_response = token.to_dict()
    logger.debug("Token response: %s", json.dumps(token_response, indent=2))
    return token_response


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
    token = validate_token_header(x_auth_token)
    return {"catalog": token.catalog}


# Domain endpoints
@router.get("/v3/domains")
async def list_domains(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    enabled: bool | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List domains."""
    validate_token_header(x_auth_token)
    domains = db.list_domains(enabled=enabled, name=name)
    return {
        "domains": [d.to_dict() for d in domains],
        "links": {"self": "/v3/domains", "previous": None, "next": None},
    }


@router.post("/v3/domains", status_code=201)
async def create_domain(
    body: dict[str, DomainCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a domain."""
    validate_token_header(x_auth_token)
    domain_data = body.get("domain")
    if not domain_data:
        raise HTTPException(status_code=400, detail="Missing domain in request body")

    domain = db.create_domain(
        name=domain_data.name,
        description=domain_data.description,
        enabled=domain_data.enabled,
    )
    return {"domain": domain.to_dict()}


@router.get("/v3/domains/{domain_id}")
async def get_domain(
    domain_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a domain by ID."""
    validate_token_header(x_auth_token)
    domain = db.get_domain(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"domain": domain.to_dict()}


@router.patch("/v3/domains/{domain_id}")
async def update_domain(
    domain_id: str,
    body: dict[str, DomainUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a domain."""
    validate_token_header(x_auth_token)
    domain_data = body.get("domain")
    if not domain_data:
        raise HTTPException(status_code=400, detail="Missing domain in request body")

    domain = db.update_domain(
        domain_id,
        name=domain_data.name,
        description=domain_data.description,
        enabled=domain_data.enabled,
    )
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"domain": domain.to_dict()}


@router.delete("/v3/domains/{domain_id}")
async def delete_domain(
    domain_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a domain."""
    validate_token_header(x_auth_token)
    if not db.delete_domain(domain_id):
        raise HTTPException(status_code=404, detail="Domain not found or cannot be deleted")
    return Response(status_code=204)


# Project endpoints
@router.get("/v3/projects")
async def list_projects(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    domain_id: str | None = None,
    enabled: bool | None = None,
    name: str | None = None,
    parent_id: str | None = None,
    tags: str | None = Query(None),
    tags_any: str | None = Query(None, alias="tags-any"),
    not_tags: str | None = Query(None, alias="not-tags"),
    not_tags_any: str | None = Query(None, alias="not-tags-any"),
) -> dict[str, Any]:
    """List projects."""
    validate_token_header(x_auth_token)

    def _split(value: str | None) -> list[str] | None:
        # The Identity API passes tag filters as a single comma-separated value.
        return [tag for tag in value.split(",") if tag] if value else None

    projects = db.list_projects(
        domain_id=domain_id,
        enabled=enabled,
        name=name,
        parent_id=parent_id,
        tags=_split(tags),
        tags_any=_split(tags_any),
        not_tags=_split(not_tags),
        not_tags_any=_split(not_tags_any),
    )
    return {
        "projects": [p.to_dict() for p in projects],
        "links": {"self": "/v3/projects", "previous": None, "next": None},
    }


@router.post("/v3/projects", status_code=201)
async def create_project(
    body: dict[str, ProjectCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a project."""
    validate_token_header(x_auth_token)
    project_data = body.get("project")
    if not project_data:
        raise HTTPException(status_code=400, detail="Missing project in request body")

    project = db.create_project(
        name=project_data.name,
        domain_id=project_data.domain_id,
        description=project_data.description,
        enabled=project_data.enabled,
        parent_id=project_data.parent_id,
        is_domain=project_data.is_domain,
        tags=project_data.tags,
    )
    return {"project": project.to_dict()}


@router.get("/v3/projects/{project_id}")
async def get_project(
    project_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a project by ID."""
    validate_token_header(x_auth_token)
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project.to_dict()}


@router.patch("/v3/projects/{project_id}")
async def update_project(
    project_id: str,
    body: dict[str, ProjectUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a project."""
    validate_token_header(x_auth_token)
    project_data = body.get("project")
    if not project_data:
        raise HTTPException(status_code=400, detail="Missing project in request body")

    project = db.update_project(
        project_id,
        name=project_data.name,
        description=project_data.description,
        enabled=project_data.enabled,
        domain_id=project_data.domain_id,
        tags=project_data.tags,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project.to_dict()}


@router.delete("/v3/projects/{project_id}")
async def delete_project(
    project_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a project."""
    validate_token_header(x_auth_token)
    if not db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)


# Project tag endpoints
# Constraints from keystone.resource.schema: a tag may not contain "," or "/"
# (the API-WG tag guideline), is 1..255 characters, and a project carries at
# most 80 unique tags. The comma rule matters here because the list filters are
# comma-separated.
_MAX_TAG_LENGTH = 255
_MAX_TAGS_PER_PROJECT = 80


def validate_project_tag(value: str) -> None:
    """Reject a tag Keystone's schema would not accept."""
    if not 1 <= len(value) <= _MAX_TAG_LENGTH:
        raise HTTPException(status_code=400, detail="Tag must be 1 to 255 characters long")
    if "," in value or "/" in value:
        raise HTTPException(status_code=400, detail="Tag may not contain ',' or '/'")


def validate_project_tags(tags: list[str]) -> None:
    """Reject a tag list Keystone's schema would not accept."""
    if len(tags) > _MAX_TAGS_PER_PROJECT:
        raise HTTPException(status_code=400, detail="A project may carry at most 80 tags")
    for tag in tags:
        validate_project_tag(tag)


@router.get("/v3/projects/{project_id}/tags")
async def list_project_tags(
    project_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List the tags of a project."""
    validate_token_header(x_auth_token)
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"tags": project.tags}


@router.put("/v3/projects/{project_id}/tags")
async def replace_project_tags(
    project_id: str,
    body: ProjectTagsUpdate,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Replace the full tag list of a project."""
    validate_token_header(x_auth_token)
    validate_project_tags(body.tags)
    project = db.update_project(project_id, tags=body.tags)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"tags": project.tags}


@router.delete("/v3/projects/{project_id}/tags")
async def delete_project_tags(
    project_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Remove every tag from a project."""
    validate_token_header(x_auth_token)
    project = db.update_project(project_id, tags=[])
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)


@router.put("/v3/projects/{project_id}/tags/{value}", status_code=201)
async def add_project_tag(
    project_id: str,
    value: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Add a single tag to a project."""
    validate_token_header(x_auth_token)
    validate_project_tag(value)
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    validate_project_tags([*project.tags, value])
    db.add_project_tag(project_id, value)
    return Response(
        status_code=201,
        headers={"Location": f"/v3/projects/{project_id}/tags/{value}"},
    )


@router.head("/v3/projects/{project_id}/tags/{value}")
@router.get("/v3/projects/{project_id}/tags/{value}")
async def check_project_tag(
    project_id: str,
    value: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Check whether a project carries a tag."""
    validate_token_header(x_auth_token)
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if value not in project.tags:
        raise HTTPException(status_code=404, detail="Tag not found")
    return Response(status_code=204)


@router.delete("/v3/projects/{project_id}/tags/{value}")
async def delete_project_tag(
    project_id: str,
    value: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Remove a single tag from a project."""
    validate_token_header(x_auth_token)
    if db.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.delete_project_tag(project_id, value):
        raise HTTPException(status_code=404, detail="Tag not found")
    return Response(status_code=204)


# User endpoints
@router.get("/v3/users")
async def list_users(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    domain_id: str | None = None,
    enabled: bool | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List users."""
    validate_token_header(x_auth_token)
    if name:
        logger.debug("Searching for user with name: %s", name)
    users = db.list_users(domain_id=domain_id, enabled=enabled, name=name)
    logger.debug("Found %d users matching criteria", len(users))

    response_data = {
        "users": [u.to_dict() for u in users],
        "links": {"self": "/v3/users", "previous": None, "next": None},
    }

    logger.debug("Users response: %s", json.dumps(response_data, indent=2))
    return response_data


@router.post("/v3/users", status_code=201)
async def create_user(
    body: dict[str, UserCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a user."""
    validate_token_header(x_auth_token)
    user_data = body.get("user")
    if not user_data:
        raise HTTPException(status_code=400, detail="Missing user in request body")

    user = db.create_user(
        name=user_data.name,
        domain_id=user_data.domain_id,
        password=user_data.password or "",
        email=user_data.email,
        description=user_data.description,
        enabled=user_data.enabled,
        default_project_id=user_data.default_project_id,
    )
    return {"user": user.to_dict()}


@router.get("/v3/users/{user_id}")
async def get_user(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a user by ID."""
    validate_token_header(x_auth_token)
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.to_dict()}


@router.patch("/v3/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict[str, UserUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a user."""
    validate_token_header(x_auth_token)
    user_data = body.get("user")
    if not user_data:
        raise HTTPException(status_code=400, detail="Missing user in request body")

    user = db.update_user(
        user_id,
        name=user_data.name,
        description=user_data.description,
        email=user_data.email,
        enabled=user_data.enabled,
        password=user_data.password,
        default_project_id=user_data.default_project_id,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.to_dict()}


@router.delete("/v3/users/{user_id}")
async def delete_user(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a user."""
    validate_token_header(x_auth_token)
    if not db.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=204)


@router.get("/v3/users/{user_id}/groups")
async def list_user_groups(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List groups a user belongs to."""
    validate_token_header(x_auth_token)
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    groups = db.list_groups_for_user(user_id)
    return {
        "groups": [g.to_dict() for g in groups],
        "links": {"self": f"/v3/users/{user_id}/groups", "previous": None, "next": None},
    }


@router.get("/v3/users/{user_id}/projects")
async def list_user_projects(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List projects a user has access to."""
    validate_token_header(x_auth_token)
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    # Get all role assignments for this user
    assignments = db.list_role_assignments(user_id=user_id)
    project_ids = {a.project_id for a in assignments if a.project_id}

    projects = [db.get_project(pid) for pid in project_ids if db.get_project(pid)]
    return {
        "projects": [p.to_dict() for p in projects if p],
        "links": {"self": f"/v3/users/{user_id}/projects", "previous": None, "next": None},
    }


# Role endpoints
@router.get("/v3/roles")
async def list_roles(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    domain_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List roles."""
    validate_token_header(x_auth_token)
    if name:
        logger.debug("Searching for role with name: %s", name)
    roles = db.list_roles(domain_id=domain_id, name=name)
    logger.debug("Found %d roles matching criteria", len(roles))

    response_data = {
        "roles": [r.to_dict() for r in roles],
        "links": {"self": "/v3/roles", "previous": None, "next": None},
    }

    logger.debug("Roles response: %s", json.dumps(response_data, indent=2))
    return response_data


@router.post("/v3/roles", status_code=201)
async def create_role(
    body: dict[str, RoleCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a role."""
    validate_token_header(x_auth_token)
    role_data = body.get("role")
    if not role_data:
        raise HTTPException(status_code=400, detail="Missing role in request body")

    role = db.create_role(
        name=role_data.name,
        description=role_data.description,
        domain_id=role_data.domain_id,
    )
    return {"role": role.to_dict()}


@router.get("/v3/roles/{role_id}")
async def get_role(
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a role by ID."""
    validate_token_header(x_auth_token)
    role = db.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"role": role.to_dict()}


@router.patch("/v3/roles/{role_id}")
async def update_role(
    role_id: str,
    body: dict[str, RoleUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a role."""
    validate_token_header(x_auth_token)
    role_data = body.get("role")
    if not role_data:
        raise HTTPException(status_code=400, detail="Missing role in request body")

    role = db.update_role(
        role_id,
        name=role_data.name,
        description=role_data.description,
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"role": role.to_dict()}


@router.delete("/v3/roles/{role_id}")
async def delete_role(
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a role."""
    validate_token_header(x_auth_token)
    if not db.delete_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")
    return Response(status_code=204)


# Role assignment endpoints - Projects
@router.put("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}")
async def assign_role_to_user_on_project(
    project_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Assign a role to a user on a project."""
    validate_token_header(x_auth_token)

    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if not db.get_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")

    db.assign_role_to_user_on_project(role_id, user_id, project_id)
    return Response(status_code=204)


@router.head("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}")
@router.get("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}")
async def check_role_assignment_on_project(
    project_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Check if a user has a role on a project."""
    validate_token_header(x_auth_token)

    if db.check_role_assignment(role_id, user_id=user_id, project_id=project_id):
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Role assignment not found")


@router.delete("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}")
async def revoke_role_from_user_on_project(
    project_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Revoke a role from a user on a project."""
    validate_token_header(x_auth_token)

    if not db.revoke_role_from_user_on_project(role_id, user_id, project_id):
        raise HTTPException(status_code=404, detail="Role assignment not found")
    return Response(status_code=204)


@router.get("/v3/projects/{project_id}/users/{user_id}/roles")
async def list_user_roles_on_project(
    project_id: str,
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List roles for a user on a project."""
    validate_token_header(x_auth_token)

    roles = db.get_user_roles_on_project(user_id, project_id)
    return {
        "roles": [
            {"id": r["id"], "name": r["name"], "links": {"self": f"/v3/roles/{r['id']}"}}
            for r in roles
        ],
        "links": {
            "self": f"/v3/projects/{project_id}/users/{user_id}/roles",
            "previous": None,
            "next": None,
        },
    }


# Role assignment endpoints - Domains
@router.put("/v3/domains/{domain_id}/users/{user_id}/roles/{role_id}")
async def assign_role_to_user_on_domain(
    domain_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Assign a role to a user on a domain."""
    validate_token_header(x_auth_token)

    if not db.get_domain(domain_id):
        raise HTTPException(status_code=404, detail="Domain not found")
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if not db.get_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")

    db.assign_role_to_user_on_domain(role_id, user_id, domain_id)
    return Response(status_code=204)


@router.head("/v3/domains/{domain_id}/users/{user_id}/roles/{role_id}")
@router.get("/v3/domains/{domain_id}/users/{user_id}/roles/{role_id}")
async def check_role_assignment_on_domain(
    domain_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Check if a user has a role on a domain."""
    validate_token_header(x_auth_token)

    if db.check_role_assignment(role_id, user_id=user_id, domain_id=domain_id):
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Role assignment not found")


@router.delete("/v3/domains/{domain_id}/users/{user_id}/roles/{role_id}")
async def revoke_role_from_user_on_domain(
    domain_id: str,
    user_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Revoke a role from a user on a domain."""
    validate_token_header(x_auth_token)

    if not db.revoke_role_from_user_on_domain(role_id, user_id, domain_id):
        raise HTTPException(status_code=404, detail="Role assignment not found")
    return Response(status_code=204)


@router.get("/v3/domains/{domain_id}/users/{user_id}/roles")
async def list_user_roles_on_domain(
    domain_id: str,
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List roles for a user on a domain."""
    validate_token_header(x_auth_token)

    assignments = db.list_role_assignments(user_id=user_id, domain_id=domain_id)
    roles = []
    for a in assignments:
        role = db.get_role(a.role_id)
        if role:
            roles.append(role.to_dict())
    return {
        "roles": roles,
        "links": {
            "self": f"/v3/domains/{domain_id}/users/{user_id}/roles",
            "previous": None,
            "next": None,
        },
    }


# Role assignment endpoints - Groups on Projects
@router.put("/v3/projects/{project_id}/groups/{group_id}/roles/{role_id}")
async def assign_role_to_group_on_project(
    project_id: str,
    group_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Assign a role to a group on a project."""
    validate_token_header(x_auth_token)

    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    if not db.get_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")

    db.assign_role_to_group_on_project(role_id, group_id, project_id)
    return Response(status_code=204)


@router.delete("/v3/projects/{project_id}/groups/{group_id}/roles/{role_id}")
async def revoke_role_from_group_on_project(
    project_id: str,
    group_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Revoke a role from a group on a project."""
    validate_token_header(x_auth_token)

    if not db.revoke_role_from_group_on_project(role_id, group_id, project_id):
        raise HTTPException(status_code=404, detail="Role assignment not found")
    return Response(status_code=204)


# Role assignment endpoints - Groups on Domains
@router.put("/v3/domains/{domain_id}/groups/{group_id}/roles/{role_id}")
async def assign_role_to_group_on_domain(
    domain_id: str,
    group_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Assign a role to a group on a domain."""
    validate_token_header(x_auth_token)

    if not db.get_domain(domain_id):
        raise HTTPException(status_code=404, detail="Domain not found")
    if not db.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    if not db.get_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")

    db.assign_role_to_group_on_domain(role_id, group_id, domain_id)
    return Response(status_code=204)


@router.delete("/v3/domains/{domain_id}/groups/{group_id}/roles/{role_id}")
async def revoke_role_from_group_on_domain(
    domain_id: str,
    group_id: str,
    role_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Revoke a role from a group on a domain."""
    validate_token_header(x_auth_token)

    if not db.revoke_role_from_group_on_domain(role_id, group_id, domain_id):
        raise HTTPException(status_code=404, detail="Role assignment not found")
    return Response(status_code=204)


# Role assignments listing
@router.get("/v3/role_assignments")
async def list_role_assignments(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    user_id: str | None = Query(None, alias="user.id"),
    group_id: str | None = Query(None, alias="group.id"),
    role_id: str | None = Query(None, alias="role.id"),
    scope_project_id: str | None = Query(None, alias="scope.project.id"),
    scope_domain_id: str | None = Query(None, alias="scope.domain.id"),
) -> dict[str, Any]:
    """List all role assignments."""
    validate_token_header(x_auth_token)

    assignments = db.list_role_assignments(
        user_id=user_id,
        group_id=group_id,
        role_id=role_id,
        project_id=scope_project_id,
        domain_id=scope_domain_id,
    )

    return {
        "role_assignments": [a.to_dict() for a in assignments],
        "links": {"self": "/v3/role_assignments", "previous": None, "next": None},
    }


# Group endpoints
@router.get("/v3/groups")
async def list_groups(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    domain_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List groups."""
    validate_token_header(x_auth_token)
    groups = db.list_groups(domain_id=domain_id, name=name)
    return {
        "groups": [g.to_dict() for g in groups],
        "links": {"self": "/v3/groups", "previous": None, "next": None},
    }


@router.post("/v3/groups", status_code=201)
async def create_group(
    body: dict[str, GroupCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a group."""
    validate_token_header(x_auth_token)
    group_data = body.get("group")
    if not group_data:
        raise HTTPException(status_code=400, detail="Missing group in request body")

    group = db.create_group(
        name=group_data.name,
        domain_id=group_data.domain_id,
        description=group_data.description,
    )
    return {"group": group.to_dict()}


@router.get("/v3/groups/{group_id}")
async def get_group(
    group_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a group by ID."""
    validate_token_header(x_auth_token)
    group = db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"group": group.to_dict()}


@router.patch("/v3/groups/{group_id}")
async def update_group(
    group_id: str,
    body: dict[str, GroupUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a group."""
    validate_token_header(x_auth_token)
    group_data = body.get("group")
    if not group_data:
        raise HTTPException(status_code=400, detail="Missing group in request body")

    group = db.update_group(
        group_id,
        name=group_data.name,
        description=group_data.description,
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"group": group.to_dict()}


@router.delete("/v3/groups/{group_id}")
async def delete_group(
    group_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a group."""
    validate_token_header(x_auth_token)
    if not db.delete_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    return Response(status_code=204)


@router.get("/v3/groups/{group_id}/users")
async def list_group_users(
    group_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List users in a group."""
    validate_token_header(x_auth_token)
    if not db.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    users = db.list_users_in_group(group_id)
    return {
        "users": [u.to_dict() for u in users],
        "links": {"self": f"/v3/groups/{group_id}/users", "previous": None, "next": None},
    }


@router.put("/v3/groups/{group_id}/users/{user_id}")
async def add_user_to_group(
    group_id: str,
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Add a user to a group."""
    validate_token_header(x_auth_token)
    if not db.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    db.add_user_to_group(user_id, group_id)
    return Response(status_code=204)


@router.head("/v3/groups/{group_id}/users/{user_id}")
async def check_user_in_group(
    group_id: str,
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Check if a user is in a group."""
    validate_token_header(x_auth_token)
    if db.check_user_in_group(user_id, group_id):
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="User not in group")


@router.delete("/v3/groups/{group_id}/users/{user_id}")
async def remove_user_from_group(
    group_id: str,
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Remove a user from a group."""
    validate_token_header(x_auth_token)
    if not db.remove_user_from_group(user_id, group_id):
        raise HTTPException(status_code=404, detail="User or group not found")
    return Response(status_code=204)


# Service endpoints
@router.get("/v3/services")
async def list_services(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    type: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List services."""
    validate_token_header(x_auth_token)
    services = db.list_services(service_type=type, name=name)
    return {
        "services": [s.to_dict() for s in services],
        "links": {"self": "/v3/services", "previous": None, "next": None},
    }


@router.post("/v3/services", status_code=201)
async def create_service(
    body: dict[str, ServiceCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a service."""
    validate_token_header(x_auth_token)
    service_data = body.get("service")
    if not service_data:
        raise HTTPException(status_code=400, detail="Missing service in request body")

    service = db.create_service(
        name=service_data.name,
        service_type=service_data.type,
        description=service_data.description,
        enabled=service_data.enabled,
    )
    return {"service": service.to_dict()}


@router.get("/v3/services/{service_id}")
async def get_service(
    service_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a service by ID."""
    validate_token_header(x_auth_token)
    service = db.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"service": service.to_dict()}


@router.patch("/v3/services/{service_id}")
async def update_service(
    service_id: str,
    body: dict[str, ServiceUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a service."""
    validate_token_header(x_auth_token)
    service_data = body.get("service")
    if not service_data:
        raise HTTPException(status_code=400, detail="Missing service in request body")

    service = db.update_service(
        service_id,
        name=service_data.name,
        description=service_data.description,
        enabled=service_data.enabled,
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"service": service.to_dict()}


@router.delete("/v3/services/{service_id}")
async def delete_service(
    service_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a service."""
    validate_token_header(x_auth_token)
    if not db.delete_service(service_id):
        raise HTTPException(status_code=404, detail="Service not found")
    return Response(status_code=204)


# Endpoint endpoints
@router.get("/v3/endpoints")
async def list_endpoints(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    service_id: str | None = None,
    interface: str | None = None,
    region_id: str | None = None,
) -> dict[str, Any]:
    """List endpoints."""
    validate_token_header(x_auth_token)
    endpoints = db.list_endpoints(service_id=service_id, interface=interface, region_id=region_id)
    return {
        "endpoints": [e.to_dict() for e in endpoints],
        "links": {"self": "/v3/endpoints", "previous": None, "next": None},
    }


@router.post("/v3/endpoints", status_code=201)
async def create_endpoint(
    body: dict[str, EndpointCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an endpoint."""
    validate_token_header(x_auth_token)
    endpoint_data = body.get("endpoint")
    if not endpoint_data:
        raise HTTPException(status_code=400, detail="Missing endpoint in request body")

    if not db.get_service(endpoint_data.service_id):
        raise HTTPException(status_code=400, detail="Service not found")

    endpoint = db.create_endpoint(
        service_id=endpoint_data.service_id,
        interface=endpoint_data.interface,
        url=endpoint_data.url,
        region_id=endpoint_data.region_id,
        enabled=endpoint_data.enabled,
    )
    return {"endpoint": endpoint.to_dict()}


@router.get("/v3/endpoints/{endpoint_id}")
async def get_endpoint(
    endpoint_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an endpoint by ID."""
    validate_token_header(x_auth_token)
    endpoint = db.get_endpoint(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"endpoint": endpoint.to_dict()}


@router.patch("/v3/endpoints/{endpoint_id}")
async def update_endpoint(
    endpoint_id: str,
    body: dict[str, EndpointUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update an endpoint."""
    validate_token_header(x_auth_token)
    endpoint_data = body.get("endpoint")
    if not endpoint_data:
        raise HTTPException(status_code=400, detail="Missing endpoint in request body")

    endpoint = db.update_endpoint(
        endpoint_id,
        interface=endpoint_data.interface,
        url=endpoint_data.url,
        region_id=endpoint_data.region_id,
        enabled=endpoint_data.enabled,
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"endpoint": endpoint.to_dict()}


@router.delete("/v3/endpoints/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete an endpoint."""
    validate_token_header(x_auth_token)
    if not db.delete_endpoint(endpoint_id):
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return Response(status_code=204)


# Region endpoints
@router.get("/v3/regions")
async def list_regions(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    parent_region_id: str | None = None,
) -> dict[str, Any]:
    """List regions."""
    validate_token_header(x_auth_token)
    regions = db.list_regions(parent_region_id=parent_region_id)
    return {
        "regions": [r.to_dict() for r in regions],
        "links": {"self": "/v3/regions", "previous": None, "next": None},
    }


@router.post("/v3/regions", status_code=201)
async def create_region(
    body: dict[str, RegionCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a region."""
    validate_token_header(x_auth_token)
    region_data = body.get("region")
    if not region_data:
        raise HTTPException(status_code=400, detail="Missing region in request body")

    region = db.create_region(
        region_id=region_data.id,
        description=region_data.description,
        parent_region_id=region_data.parent_region_id,
    )
    return {"region": region.to_dict()}


@router.get("/v3/regions/{region_id}")
async def get_region(
    region_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a region by ID."""
    validate_token_header(x_auth_token)
    region = db.get_region(region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"region": region.to_dict()}


@router.patch("/v3/regions/{region_id}")
async def update_region(
    region_id: str,
    body: dict[str, RegionUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a region."""
    validate_token_header(x_auth_token)
    region_data = body.get("region")
    if not region_data:
        raise HTTPException(status_code=400, detail="Missing region in request body")

    region = db.update_region(
        region_id,
        description=region_data.description,
        parent_region_id=region_data.parent_region_id,
    )
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"region": region.to_dict()}


@router.delete("/v3/regions/{region_id}")
async def delete_region(
    region_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a region."""
    validate_token_header(x_auth_token)
    if not db.delete_region(region_id):
        raise HTTPException(status_code=404, detail="Region not found")
    return Response(status_code=204)


# Credential endpoints
@router.get("/v3/credentials")
async def list_credentials(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
    user_id: str | None = None,
    type: str | None = None,
) -> dict[str, Any]:
    """List credentials."""
    validate_token_header(x_auth_token)
    credentials = db.list_credentials(user_id=user_id, credential_type=type)
    return {
        "credentials": [c.to_dict() for c in credentials],
        "links": {"self": "/v3/credentials", "previous": None, "next": None},
    }


@router.post("/v3/credentials", status_code=201)
async def create_credential(
    body: dict[str, CredentialCreate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a credential."""
    validate_token_header(x_auth_token)
    credential_data = body.get("credential")
    if not credential_data:
        raise HTTPException(status_code=400, detail="Missing credential in request body")

    credential = db.create_credential(
        user_id=credential_data.user_id,
        credential_type=credential_data.type,
        blob=credential_data.blob,
        project_id=credential_data.project_id,
    )
    return {"credential": credential.to_dict()}


@router.get("/v3/credentials/{credential_id}")
async def get_credential(
    credential_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a credential by ID."""
    validate_token_header(x_auth_token)
    credential = db.get_credential(credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"credential": credential.to_dict()}


@router.patch("/v3/credentials/{credential_id}")
async def update_credential(
    credential_id: str,
    body: dict[str, CredentialUpdate],
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a credential."""
    validate_token_header(x_auth_token)
    credential_data = body.get("credential")
    if not credential_data:
        raise HTTPException(status_code=400, detail="Missing credential in request body")

    credential = db.update_credential(
        credential_id,
        blob=credential_data.blob,
        project_id=credential_data.project_id,
    )
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"credential": credential.to_dict()}


@router.delete("/v3/credentials/{credential_id}")
async def delete_credential(
    credential_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a credential."""
    validate_token_header(x_auth_token)
    if not db.delete_credential(credential_id):
        raise HTTPException(status_code=404, detail="Credential not found")
    return Response(status_code=204)


# Application Credentials


class ApplicationCredentialRequest(BaseModel):
    """Application credential request."""

    name: str
    description: str = ""
    project_id: str | None = None
    expires_at: str | None = None
    roles: list[dict[str, str]] = Field(default_factory=list)
    unrestricted: bool = False


class ApplicationCredentialBody(BaseModel):
    """Wrapper for application credential request."""

    application_credential: ApplicationCredentialRequest


@router.get("/v3/users/{user_id}/application_credentials")
async def list_application_credentials(
    user_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List application credentials for a user."""
    validate_token_header(x_auth_token)

    credentials = db.list_application_credentials(user_id)
    return {"application_credentials": [cred.to_dict() for cred in credentials]}


@router.post("/v3/users/{user_id}/application_credentials", status_code=201)
async def create_application_credential(
    user_id: str,
    body: ApplicationCredentialBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an application credential."""
    validate_token_header(x_auth_token)
    req = body.application_credential

    # Parse expires_at if provided
    expires_at = None
    if req.expires_at:
        try:
            expires_at = datetime.fromisoformat(req.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    credential = db.create_application_credential(
        user_id=user_id,
        name=req.name,
        description=req.description,
        project_id=req.project_id,
        expires_at=expires_at,
        roles=req.roles,
        unrestricted=req.unrestricted,
    )

    return {"application_credential": credential.to_dict(include_secret=True)}


@router.get("/v3/users/{user_id}/application_credentials/{credential_id}")
async def get_application_credential(
    user_id: str,
    credential_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an application credential."""
    validate_token_header(x_auth_token)

    credential = db.get_application_credential(user_id, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Application credential not found")

    return {"application_credential": credential.to_dict()}


@router.delete("/v3/users/{user_id}/application_credentials/{credential_id}")
async def delete_application_credential(
    user_id: str,
    credential_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete an application credential."""
    validate_token_header(x_auth_token)

    if not db.delete_application_credential(user_id, credential_id):
        raise HTTPException(status_code=404, detail="Application credential not found")

    return Response(status_code=204)


# Policy Management


class PolicyRequest(BaseModel):
    """Policy request."""

    blob: str
    type: str = "application/json"


class PolicyBody(BaseModel):
    """Wrapper for policy request."""

    policy: PolicyRequest


@router.get("/v3/policies")
async def list_policies(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List policies."""
    validate_token_header(x_auth_token)

    policies = db.list_policies()
    return {"policies": [policy.to_dict() for policy in policies]}


@router.post("/v3/policies", status_code=201)
async def create_policy(
    body: PolicyBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a policy."""
    validate_token_header(x_auth_token)

    policy = db.create_policy(
        blob=body.policy.blob,
        type=body.policy.type,
    )

    return {"policy": policy.to_dict()}


@router.get("/v3/policies/{policy_id}")
async def get_policy(
    policy_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a policy."""
    validate_token_header(x_auth_token)

    policy = db.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"policy": policy.to_dict()}


@router.patch("/v3/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    body: PolicyBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a policy."""
    validate_token_header(x_auth_token)

    policy = db.update_policy(
        policy_id=policy_id,
        blob=body.policy.blob,
        type=body.policy.type,
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"policy": policy.to_dict()}


@router.delete("/v3/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a policy."""
    validate_token_header(x_auth_token)

    if not db.delete_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")

    return Response(status_code=204)


# Federation - Identity Providers


class IdentityProviderRequest(BaseModel):
    """Identity provider request."""

    description: str = ""
    enabled: bool = True
    remote_ids: list[str] = Field(default_factory=list)
    domain_id: str = "default"


class IdentityProviderBody(BaseModel):
    """Wrapper for identity provider request."""

    identity_provider: IdentityProviderRequest


@router.get("/v3/OS-FEDERATION/identity_providers")
async def list_identity_providers(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List identity providers."""
    validate_token_header(x_auth_token)

    providers = db.list_identity_providers()
    return {"identity_providers": [idp.to_dict() for idp in providers]}


@router.put("/v3/OS-FEDERATION/identity_providers/{idp_id}", status_code=201)
async def create_identity_provider(
    idp_id: str,
    body: IdentityProviderBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an identity provider."""
    validate_token_header(x_auth_token)
    req = body.identity_provider

    provider = db.create_identity_provider(
        idp_id=idp_id,
        description=req.description,
        enabled=req.enabled,
        remote_ids=req.remote_ids,
        domain_id=req.domain_id,
    )

    return {"identity_provider": provider.to_dict()}


@router.get("/v3/OS-FEDERATION/identity_providers/{idp_id}")
async def get_identity_provider(
    idp_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an identity provider."""
    validate_token_header(x_auth_token)

    provider = db.get_identity_provider(idp_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    return {"identity_provider": provider.to_dict()}


@router.patch("/v3/OS-FEDERATION/identity_providers/{idp_id}")
async def update_identity_provider(
    idp_id: str,
    body: IdentityProviderBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update an identity provider."""
    validate_token_header(x_auth_token)
    req = body.identity_provider

    provider = db.update_identity_provider(
        idp_id=idp_id,
        description=req.description,
        enabled=req.enabled,
        remote_ids=req.remote_ids,
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    return {"identity_provider": provider.to_dict()}


@router.delete("/v3/OS-FEDERATION/identity_providers/{idp_id}")
async def delete_identity_provider(
    idp_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete an identity provider."""
    validate_token_header(x_auth_token)

    if not db.delete_identity_provider(idp_id):
        raise HTTPException(status_code=404, detail="Identity provider not found")

    return Response(status_code=204)


# Federation - Mappings


class FederationMappingRequest(BaseModel):
    """Federation mapping request."""

    rules: list[dict[str, Any]] = Field(default_factory=list)


class FederationMappingBody(BaseModel):
    """Wrapper for federation mapping request."""

    mapping: FederationMappingRequest


@router.get("/v3/OS-FEDERATION/mappings")
async def list_federation_mappings(
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List federation mappings."""
    validate_token_header(x_auth_token)

    mappings = db.list_federation_mappings()
    return {"mappings": [mapping.to_dict() for mapping in mappings]}


@router.put("/v3/OS-FEDERATION/mappings/{mapping_id}", status_code=201)
async def create_federation_mapping(
    mapping_id: str,
    body: FederationMappingBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a federation mapping."""
    validate_token_header(x_auth_token)

    mapping = db.create_federation_mapping(
        mapping_id=mapping_id,
        rules=body.mapping.rules,
    )

    return {"mapping": mapping.to_dict()}


@router.get("/v3/OS-FEDERATION/mappings/{mapping_id}")
async def get_federation_mapping(
    mapping_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a federation mapping."""
    validate_token_header(x_auth_token)

    mapping = db.get_federation_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Federation mapping not found")

    return {"mapping": mapping.to_dict()}


@router.patch("/v3/OS-FEDERATION/mappings/{mapping_id}")
async def update_federation_mapping(
    mapping_id: str,
    body: FederationMappingBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a federation mapping."""
    validate_token_header(x_auth_token)

    mapping = db.update_federation_mapping(
        mapping_id=mapping_id,
        rules=body.mapping.rules,
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="Federation mapping not found")

    return {"mapping": mapping.to_dict()}


@router.delete("/v3/OS-FEDERATION/mappings/{mapping_id}")
async def delete_federation_mapping(
    mapping_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a federation mapping."""
    validate_token_header(x_auth_token)

    if not db.delete_federation_mapping(mapping_id):
        raise HTTPException(status_code=404, detail="Federation mapping not found")

    return Response(status_code=204)


# Registered Limits


class RegisteredLimitRequest(BaseModel):
    """Registered limit request."""

    service_id: str
    resource_name: str
    default_limit: int
    description: str = ""
    region_id: str | None = None


class RegisteredLimitBody(BaseModel):
    """Wrapper for registered limit request."""

    registered_limit: RegisteredLimitRequest


@router.get("/v3/registered_limits")
async def list_registered_limits(
    service_id: str | None = Query(None),
    resource_name: str | None = Query(None),
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List registered limits."""
    validate_token_header(x_auth_token)

    limits = db.list_registered_limits(service_id=service_id, resource_name=resource_name)
    return {"registered_limits": [limit.to_dict() for limit in limits]}


@router.post("/v3/registered_limits", status_code=201)
async def create_registered_limit(
    body: RegisteredLimitBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a registered limit."""
    validate_token_header(x_auth_token)
    req = body.registered_limit

    limit = db.create_registered_limit(
        service_id=req.service_id,
        resource_name=req.resource_name,
        default_limit=req.default_limit,
        description=req.description,
        region_id=req.region_id,
    )

    return {"registered_limit": limit.to_dict()}


@router.get("/v3/registered_limits/{limit_id}")
async def get_registered_limit(
    limit_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a registered limit."""
    validate_token_header(x_auth_token)

    limit = db.get_registered_limit(limit_id)
    if not limit:
        raise HTTPException(status_code=404, detail="Registered limit not found")

    return {"registered_limit": limit.to_dict()}


@router.patch("/v3/registered_limits/{limit_id}")
async def update_registered_limit(
    limit_id: str,
    body: RegisteredLimitBody,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a registered limit."""
    validate_token_header(x_auth_token)
    req = body.registered_limit

    limit = db.update_registered_limit(
        limit_id=limit_id,
        default_limit=req.default_limit,
        description=req.description,
    )
    if not limit:
        raise HTTPException(status_code=404, detail="Registered limit not found")

    return {"registered_limit": limit.to_dict()}


@router.delete("/v3/registered_limits/{limit_id}")
async def delete_registered_limit(
    limit_id: str,
    x_auth_token: str = Header(..., alias="X-Auth-Token"),
) -> Response:
    """Delete a registered limit."""
    validate_token_header(x_auth_token)

    if not db.delete_registered_limit(limit_id):
        raise HTTPException(status_code=404, detail="Registered limit not found")

    return Response(status_code=204)

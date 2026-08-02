"""Swift Object Storage API endpoints for OpenStack emulator.

Covers the account, container and object levels of the storage hierarchy, plus
the ``account_quotas`` middleware behaviour that clients rely on to cap a
project's storage: quota headers are reseller-only to write, readable by anyone,
and an object PUT that would exceed the limit is refused with 413.
"""

import base64
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from emulator.core.database import db
from emulator.core.simple_auth import TokenInfo, validate_token_simple

logger = logging.getLogger(__name__)

router = APIRouter(tags=["object-store"])

#: Quota kinds Swift stores as account system metadata.
QUOTA_TYPES = ("quota-bytes", "quota-count")

ACCOUNT_META_PREFIX = "x-account-meta-"
CONTAINER_META_PREFIX = "x-container-meta-"
OBJECT_META_PREFIX = "x-object-meta-"


def get_token_or_raise(auth_token: str | None) -> TokenInfo:
    """Validate token using shared database."""
    return validate_token_simple(auth_token, "Swift")


def authorize_account(token: TokenInfo, account: str) -> None:
    """Reject a request for an account the caller does not own.

    A reseller (here: any privileged token) may address any account; everyone
    else is confined to the ``AUTH_<their project>`` account the catalog points
    them at.
    """
    if token.is_admin:
        return
    if account != f"AUTH_{token.project_id}" and account != token.project_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _collect_meta(request: Request, prefix: str) -> dict[str, str]:
    """Extract ``X-<scope>-Meta-*`` headers, keyed without the prefix.

    Also honours the matching ``X-Remove-<scope>-Meta-*`` headers by mapping
    them to an empty value, which the storage layer treats as a removal.
    """
    metadata: dict[str, str] = {}
    remove_prefix = f"x-remove-{prefix[2:]}"
    for name, value in request.headers.items():
        lowered = name.lower()
        if lowered.startswith(prefix):
            metadata[lowered[len(prefix) :]] = value
        elif lowered.startswith(remove_prefix):
            metadata[lowered[len(remove_prefix) :]] = ""
    return metadata


def _collect_quota_headers(request: Request, token: TokenInfo) -> dict[str, str]:
    """Extract account quota headers, applying Swift's write rules.

    ``X-Account-Meta-Quota-Bytes`` is the obsoleted spelling that Swift still
    translates into ``X-Account-Quota-Bytes``; both are accepted here because
    clients in the wild send either. Only a reseller may set a quota, and a
    non-numeric value is a 400.
    """
    quotas: dict[str, str] = {}
    for quota_type in QUOTA_TYPES:
        value: str | None = None
        for header in (
            f"x-account-{quota_type}",
            f"x-account-meta-{quota_type}",
        ):
            if header in request.headers:
                value = request.headers[header]
        for header in (
            f"x-remove-account-{quota_type}",
            f"x-remove-account-meta-{quota_type}",
        ):
            if request.headers.get(header):
                value = ""  # X-Remove dominates when both are present
        if value is None:
            continue
        if not token.is_admin:
            raise HTTPException(status_code=403, detail="Forbidden")
        if value != "" and not value.isdigit():
            raise HTTPException(status_code=400, detail="Bad quota value")
        quotas[quota_type] = value
    return quotas


_FORMAT_TO_CONTENT_TYPE = {
    "json": "application/json",
    "xml": "application/xml",
    "plain": "text/plain",
}


def _listing_content_type(request: Request, format_param: str | None) -> str:
    """Pick the listing format, mirroring Swift's ``get_listing_content_type``.

    An explicit ``format`` query parameter wins; otherwise the ``Accept`` header
    is negotiated, which is how openstacksdk asks for JSON — it sends
    ``Accept: application/json`` and no ``format``. An unrecognised ``format``
    falls back to plain text, as in Swift.

    XML listings are not emulated: a client that will accept nothing else gets a
    406 rather than a body claiming to be XML.
    """
    if format_param:
        content_type = _FORMAT_TO_CONTENT_TYPE.get(format_param.lower(), "text/plain")
        if content_type == "application/xml":
            raise HTTPException(status_code=406, detail="XML listings are not emulated")
        return content_type

    accept = request.headers.get("accept", "text/plain")
    offers = [part.split(";")[0].strip().lower() for part in accept.split(",")]
    for offer in offers:
        if offer in ("*/*", "text/plain"):
            return "text/plain"
        if offer == "application/json":
            return "application/json"
        if offer in ("application/xml", "text/xml"):
            raise HTTPException(status_code=406, detail="XML listings are not emulated")
    raise HTTPException(status_code=406, detail="Not Acceptable")


def _account_headers(account: str) -> dict[str, str]:
    """Build the standard account response headers.

    Deliberately does not create the account: a HEAD or GET is a read, and
    letting it materialise state meant merely looking at an account brought it
    into existence and inflated every account listing. An account that has never
    been written to reports zeroes.
    """
    record = db.get_swift_account(account, create=False)
    usage = db.get_swift_account_usage(account)
    headers = {
        "X-Account-Container-Count": str(usage["container_count"]),
        "X-Account-Object-Count": str(usage["object_count"]),
        "X-Account-Bytes-Used": str(usage["bytes_used"]),
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Ranges": "bytes",
    }
    if record is None:
        return headers
    # Quotas are readable by everyone even though only resellers may set them.
    for quota_type in QUOTA_TYPES:
        stored = record.sysmeta.get(quota_type)
        if stored:
            headers[f"X-Account-{quota_type.title()}"] = stored
    for key, value in record.metadata.items():
        headers[f"X-Account-Meta-{key.title()}"] = value
    return headers


# Account endpoints


@router.head("/v1/{account}")
async def head_account(
    account: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Show account metadata, usage totals and quotas."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)
    return Response(status_code=204, headers=_account_headers(account))


@router.get("/v1/{account}")
async def get_account(
    account: str,
    request: Request,
    format: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """List the containers in an account."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    containers = db.list_swift_containers(account)
    headers = _account_headers(account)

    if _listing_content_type(request, format) != "application/json":
        # The plain-text listing answers 204 when there is nothing to list.
        body = "\n".join(c.name for c in containers)
        headers["Content-Type"] = "text/plain; charset=utf-8"
        if not containers:
            return Response(status_code=204, headers=headers)
        return Response(content=body + "\n", status_code=200, headers=headers)

    listing = [
        container.to_dict(**db.get_swift_container_usage(account, container.name))
        for container in containers
    ]
    return JSONResponse(content=listing, status_code=200, headers=headers)


@router.post("/v1/{account}")
async def post_account(
    account: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Set account metadata and quotas."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    quotas = _collect_quota_headers(request, token)
    metadata = _collect_meta(request, ACCOUNT_META_PREFIX)
    # Quota headers arrive under the meta prefix too; they belong in sysmeta.
    for quota_type in QUOTA_TYPES:
        metadata.pop(quota_type, None)

    db.update_swift_account(account, metadata=metadata, sysmeta=quotas)
    return Response(status_code=204, headers=_account_headers(account))


# Container endpoints


def _container_headers(account: str, container: str) -> dict[str, str]:
    """Build the standard container response headers."""
    record = db.get_swift_container(account, container)
    if record is None:
        raise HTTPException(status_code=404, detail="Container not found")
    usage = db.get_swift_container_usage(account, container)
    headers = {
        "X-Container-Object-Count": str(usage["object_count"]),
        "X-Container-Bytes-Used": str(usage["bytes_used"]),
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Ranges": "bytes",
    }
    for key, value in record.metadata.items():
        headers[f"X-Container-Meta-{key.title()}"] = value
    return headers


@router.head("/v1/{account}/{container}")
async def head_container(
    account: str,
    container: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Show container metadata and usage."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)
    return Response(status_code=204, headers=_container_headers(account, container))


@router.get("/v1/{account}/{container}")
async def get_container(
    account: str,
    container: str,
    request: Request,
    format: str | None = Query(None),
    prefix: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """List the objects in a container."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    headers = _container_headers(account, container)
    objects = db.list_swift_objects(account, container, prefix=prefix)

    if _listing_content_type(request, format) != "application/json":
        headers["Content-Type"] = "text/plain; charset=utf-8"
        if not objects:
            return Response(status_code=204, headers=headers)
        return Response(
            content="\n".join(o.name for o in objects) + "\n", status_code=200, headers=headers
        )

    return JSONResponse(content=[o.to_dict() for o in objects], status_code=200, headers=headers)


@router.put("/v1/{account}/{container}")
async def put_container(
    account: str,
    container: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Create a container, or update the metadata of an existing one."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    _record, created = db.create_swift_container(
        account, container, metadata=_collect_meta(request, CONTAINER_META_PREFIX)
    )
    return Response(status_code=201 if created else 202)


@router.post("/v1/{account}/{container}")
async def post_container(
    account: str,
    container: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Set container metadata."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    if db.get_swift_container(account, container) is None:
        raise HTTPException(status_code=404, detail="Container not found")
    db.create_swift_container(
        account, container, metadata=_collect_meta(request, CONTAINER_META_PREFIX)
    )
    return Response(status_code=204)


@router.delete("/v1/{account}/{container}")
async def delete_container(
    account: str,
    container: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an empty container."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    if db.get_swift_container(account, container) is None:
        raise HTTPException(status_code=404, detail="Container not found")
    if db.get_swift_container_usage(account, container)["object_count"]:
        raise HTTPException(
            status_code=409, detail="There was a conflict when trying to complete your request."
        )
    db.delete_swift_container(account, container)
    return Response(status_code=204)


# Object endpoints


@router.put("/v1/{account}/{container}/{object_name:path}")
async def put_object(
    account: str,
    container: str,
    object_name: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Store an object, refusing the write when it would exceed a quota."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    if db.get_swift_container(account, container) is None:
        raise HTTPException(status_code=404, detail="Container not found")

    content = await request.body()
    record = db.get_swift_account(account)
    assert record is not None  # noqa: S101 - get_swift_account creates on demand
    usage = db.get_swift_account_usage(account)

    # Resellers are deliberately not constrained by account quotas, matching the
    # account_quotas middleware.
    if not token.is_admin:
        byte_quota = record.quota("quota-bytes")
        if byte_quota >= 0 and usage["bytes_used"] + len(content) > byte_quota:
            raise HTTPException(status_code=413, detail="Upload exceeds quota.")
        count_quota = record.quota("quota-count")
        replacing = db.get_swift_object(account, container, object_name) is not None
        if count_quota >= 0 and not replacing and usage["object_count"] + 1 > count_quota:
            raise HTTPException(status_code=413, detail="Upload exceeds quota.")

    stored = db.put_swift_object(
        account,
        container,
        object_name,
        content=content,
        content_type=request.headers.get("content-type", "application/octet-stream"),
        metadata=_collect_meta(request, OBJECT_META_PREFIX),
    )
    return Response(status_code=201, headers={"Etag": stored.etag})


def _object_headers(record: Any) -> dict[str, str]:
    """Build the standard object response headers."""
    headers = {
        "Content-Length": str(record.size),
        "Content-Type": record.content_type,
        "Etag": record.etag,
        "Accept-Ranges": "bytes",
    }
    for key, value in record.metadata.items():
        headers[f"X-Object-Meta-{key.title()}"] = value
    return headers


@router.head("/v1/{account}/{container}/{object_name:path}")
async def head_object(
    account: str,
    container: str,
    object_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Show object metadata."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    record = db.get_swift_object(account, container, object_name)
    if record is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return Response(status_code=200, headers=_object_headers(record))


@router.get("/v1/{account}/{container}/{object_name:path}")
async def get_object(
    account: str,
    container: str,
    object_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Download an object."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    record = db.get_swift_object(account, container, object_name)
    if record is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return Response(
        content=base64.b64decode(record.content_b64),
        status_code=200,
        headers=_object_headers(record),
    )


@router.delete("/v1/{account}/{container}/{object_name:path}")
async def delete_object(
    account: str,
    container: str,
    object_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an object."""
    token = get_token_or_raise(x_auth_token)
    authorize_account(token, account)

    if not db.delete_swift_object(account, container, object_name):
        raise HTTPException(status_code=404, detail="Object not found")
    return Response(status_code=204)

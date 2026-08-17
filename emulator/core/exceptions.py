"""Common exception handlers for OpenStack emulator services."""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# fastapi.HTTPException subclasses this one, so handling the Starlette class
# covers both application-raised errors and the router's own 404/405.
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class PortInUseError(Exception):
    """A port is already bound to a device and cannot be attached."""

    def __init__(self, port_id: str) -> None:
        self.port_id = port_id
        super().__init__(f"Port {port_id} is still in use.")


class PortNotFoundError(Exception):
    """A server was booted against a port or network that does not exist."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(f"Port or network {resource_id} could not be found.")


class InvalidFixedIPError(Exception):
    """A fixed IP does not belong to any subnet of the target network."""

    def __init__(self, ip: str, network_id: str) -> None:
        self.ip = ip
        self.network_id = network_id
        super().__init__(f"Fixed IP {ip} is not a valid ip address for network {network_id}.")


class FixedIPAlreadyInUseError(Exception):
    """A fixed IP is already allocated to another port on the network."""

    def __init__(self, ip: str, network_id: str, subnet_id: str = "") -> None:
        self.ip = ip
        self.network_id = network_id
        # Neutron reports the conflict against the *subnet*, not the network.
        # Clients quote the message back to operators, so keep the wording.
        self.subnet_id = subnet_id
        super().__init__(f"Fixed IP {ip} is already in use.")


class IpAddressGenerationFailureError(Exception):
    """A network's subnets have no free address left to allocate.

    Neutron's ``IpAddressGenerationFailure`` subclasses ``Conflict``, so the API
    answers 409. Distinct from "network not found" on purpose: clients act on the
    difference — Waldur catches the exhaustion errors specifically to tell the
    operator the external pool is full rather than reporting a broken
    configuration.

    Note this is *not* the same as a network with no subnets at all. Neutron
    treats that as "not an error" (``Subnet.network_has_no_subnet``) and hands
    back a port with no fixed IPs; only a subnet that exists and cannot spare an
    address is a conflict.
    """

    def __init__(self, network_id: str) -> None:
        self.network_id = network_id
        super().__init__(f"No more IP addresses available on network {network_id}.")


class ScopeUnauthorizedError(Exception):
    """A token was requested for a scope the user holds no role on.

    Keystone refuses to mint such a token: ``TokenModel.mint`` runs
    ``_validate_project_scope``, which raises ``Unauthorized`` when a
    project-scoped token would carry no roles. Raised from the storage layer so
    the API layer can answer 401 with the same wording.
    """

    def __init__(self, user_id: str, project_id: str) -> None:
        self.user_id = user_id
        self.project_id = project_id
        super().__init__(f"User {user_id} has no access to project {project_id}")


class NeutronAPIError(StarletteHTTPException):
    """An error that must be rendered in Neutron's own envelope.

    Neutron does not use the ``{"error": ...}`` body the other services here
    share. It answers::

        {"NeutronError": {"type": "...", "message": "...", "detail": ""}}

    and the ``type`` is load-bearing, not decoration. python-neutronclient's
    ``exception_handler_v20`` looks up ``NeutronError.type`` and raises the
    matching ``<Type>Client`` class; with no ``NeutronError`` key it falls back
    to ``HTTP_EXCEPTION_MAP[status]`` — the generic *parent* class for that
    status.

    So emitting the shared envelope silently changes which exception a client
    sees: a caller that catches ``IpAddressAlreadyAllocatedClient`` never
    matches the ``Conflict`` produced by a typeless 409, and its whole recovery
    branch is skipped. Code under test then takes a different path here than it
    does against a real cloud, which is exactly the failure this class exists to
    prevent.
    """

    def __init__(
        self,
        status_code: int,
        neutron_type: str,
        message: str,
        detail: str = "",
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.neutron_type = neutron_type
        self.neutron_detail = detail


def add_openstack_exception_handlers(app: FastAPI) -> None:
    """Add OpenStack-style exception handlers to a FastAPI app.

    This function adds handlers for both HTTPException and generic Exception
    to format error responses in the OpenStack error format that clients expect.

    Args:
        app: The FastAPI application instance to add handlers to
    """

    # Registered ahead of the generic handler below. Starlette resolves a
    # handler by walking the exception's MRO, so the most specific registration
    # wins and NeutronAPIError keeps its own envelope while every other
    # HTTPException still gets the shared one.
    @app.exception_handler(NeutronAPIError)
    async def neutron_exception_handler(request: Request, exc: NeutronAPIError) -> JSONResponse:
        """Render a Neutron error the way Neutron does."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "NeutronError": {
                    "type": exc.neutron_type,
                    "message": exc.detail,
                    "detail": exc.neutron_detail,
                }
            },
        )

    # Registered against the Starlette base class, not fastapi.HTTPException:
    # the router raises the Starlette one for an unmatched route, so handling
    # only the FastAPI subclass let those 404s fall through to Starlette's
    # default handler and return {"detail": "Not Found"} instead of the
    # OpenStack error body. Clients then saw two different shapes for 404
    # depending on whether the route existed.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handle HTTP exceptions in OpenStack error format."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.detail,
                    "code": exc.status_code,
                }
            },
        )

    @app.exception_handler(Exception)
    async def openstack_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle exceptions in OpenStack error format."""
        logger.error(f"Internal Server Error: {exc}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(exc),
                    "code": 500,
                }
            },
        )

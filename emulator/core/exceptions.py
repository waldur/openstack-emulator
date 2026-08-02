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


class InvalidFixedIPError(Exception):
    """A fixed IP does not belong to any subnet of the target network."""

    def __init__(self, ip: str, network_id: str) -> None:
        self.ip = ip
        self.network_id = network_id
        super().__init__(f"Fixed IP {ip} is not a valid ip address for network {network_id}.")


class FixedIPAlreadyInUseError(Exception):
    """A fixed IP is already allocated to another port on the network."""

    def __init__(self, ip: str, network_id: str) -> None:
        self.ip = ip
        self.network_id = network_id
        super().__init__(f"Fixed IP {ip} is already in use.")


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


def add_openstack_exception_handlers(app: FastAPI) -> None:
    """Add OpenStack-style exception handlers to a FastAPI app.

    This function adds handlers for both HTTPException and generic Exception
    to format error responses in the OpenStack error format that clients expect.

    Args:
        app: The FastAPI application instance to add handlers to
    """

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

"""Common exception handlers for OpenStack emulator services."""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse


def add_openstack_exception_handlers(app: FastAPI) -> None:
    """Add OpenStack-style exception handlers to a FastAPI app.

    This function adds handlers for both HTTPException and generic Exception
    to format error responses in the OpenStack error format that clients expect.

    Args:
        app: The FastAPI application instance to add handlers to
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(exc),
                    "code": 500,
                }
            },
        )

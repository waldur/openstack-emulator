"""Keystone Identity API application for OpenStack emulator.

Runs on port 5000 (standard OpenStack Keystone port).
"""

import json
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from emulator.api.keystone import router as keystone_router
from emulator.core.middleware import ScenarioMiddleware
from emulator.core.exceptions import add_openstack_exception_handlers

logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenStack Keystone Emulator",
    description="A lightweight OpenStack Keystone (Identity) API emulator",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add request logging middleware
@app.middleware("http")
async def log_request_details(request: Request, call_next):
    """Log request information."""
    logger.debug("=== Keystone Request: %s %s ===", request.method, request.url)
    logger.debug("Headers: %s", dict(request.headers))

    # Log request body for POST/PUT/PATCH requests
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        try:
            if body:
                decoded_body = body.decode("utf-8")
                logger.debug("Request body: %s", decoded_body)
                try:
                    json_body = json.loads(decoded_body)
                    # Only log auth details at info level for token creation
                    if "/auth/tokens" in str(request.url):
                        logger.info(
                            "Authentication request: %s",
                            json_body.get("auth", {}).get("identity", {}).get("methods", []),
                        )
                except json.JSONDecodeError as e:
                    logger.warning("JSON decode error: %s", e)
        except Exception as e:
            logger.error("Body processing error: %s", e)

        # Need to reconstruct the request with the body for downstream processing
        request._body = body

    response = await call_next(request)
    logger.debug("Response status: %s", response.status_code)
    return response


# Add scenario injection middleware
app.add_middleware(ScenarioMiddleware, service_name="keystone")


# Add specific Pydantic validation error handler
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors with detailed information."""
    logger.error("Pydantic validation error: %s", exc.errors())
    logger.debug("Full validation error details: %s", exc.json())

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": f"Validation error: {str(exc)}",
                "details": exc.errors(),
                "code": 422,
            }
        },
    )


# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)


# Include Keystone router
app.include_router(keystone_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "keystone"}

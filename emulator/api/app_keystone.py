"""Keystone Identity API application for OpenStack emulator.

Runs on port 5000 (standard OpenStack Keystone port).
"""

import json
import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from emulator.api.keystone import router as keystone_router
from emulator.core.middleware import ScenarioMiddleware
from emulator.core.exceptions import add_openstack_exception_handlers
from emulator.core.headers import add_openstack_headers_middleware
from emulator.core.logging_middleware import add_debug_logging_middleware

# Configure logging for this process
log_level = os.getenv("EMULATOR_LOG_LEVEL", "info").lower()
level_mapping = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
logging.basicConfig(
    level=level_mapping.get(log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)

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


# Add enhanced debug logging middleware
add_debug_logging_middleware(app, "keystone")

# Add scenario injection middleware
app.add_middleware(ScenarioMiddleware, service_name="keystone")

# Add OpenStack headers middleware
add_openstack_headers_middleware(app, "identity", "3.14")


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

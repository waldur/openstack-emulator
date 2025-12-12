"""Status UI application for OpenStack emulator.

Runs on port 8080 - provides a web interface to view the status of all
services and objects in the emulator.
"""

import json
import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.status_ui import router as status_router
from emulator.core.exceptions import add_openstack_exception_handlers
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
    title="OpenStack Emulator Status",
    description="Web interface for viewing OpenStack emulator status",
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
add_debug_logging_middleware(app, "status")

# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)

# Include Status UI router
app.include_router(status_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "status"}

"""Cinder Block Storage API application for OpenStack emulator.

Runs on port 8776 (standard OpenStack Cinder port).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.cinder import router as cinder_router
from emulator.core.middleware import ScenarioMiddleware
from emulator.core.exceptions import add_openstack_exception_handlers

app = FastAPI(
    title="OpenStack Cinder Emulator",
    description="A lightweight OpenStack Cinder (Block Storage) API emulator",
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

# Add scenario injection middleware
app.add_middleware(ScenarioMiddleware, service_name="cinder")

# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)


# Include Cinder router
app.include_router(cinder_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "cinder"}

"""Glance Image API application for OpenStack emulator.

Runs on port 9292 (standard OpenStack Glance port).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.glance import router as glance_router
from emulator.core.middleware import ScenarioMiddleware
from emulator.core.exceptions import add_openstack_exception_handlers

app = FastAPI(
    title="OpenStack Glance Emulator",
    description="A lightweight OpenStack Glance (Image) API emulator",
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
app.add_middleware(ScenarioMiddleware, service_name="glance")

# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)


# Include Glance router
app.include_router(glance_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "glance"}

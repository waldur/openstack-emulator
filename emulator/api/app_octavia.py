"""Octavia Load Balancer API application for OpenStack emulator.

Runs on port 9876 (standard OpenStack Octavia port).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.octavia import router as octavia_router
from emulator.core.exceptions import add_openstack_exception_handlers

app = FastAPI(
    title="OpenStack Octavia Emulator",
    description="A lightweight OpenStack Octavia (Load Balancer) API emulator",
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

# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)


# Include Octavia router
app.include_router(octavia_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "octavia"}

"""Nova Compute API application for OpenStack emulator.

Runs on port 8774 (standard OpenStack Nova port).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.nova import router as nova_router
from emulator.core.middleware import ScenarioMiddleware
from emulator.core.exceptions import add_openstack_exception_handlers

app = FastAPI(
    title="OpenStack Nova Emulator",
    description="A lightweight OpenStack Nova (Compute) API emulator",
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
app.add_middleware(ScenarioMiddleware, service_name="nova")

# Add OpenStack-style exception handlers
add_openstack_exception_handlers(app)


# Include Nova router
app.include_router(nova_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "nova"}

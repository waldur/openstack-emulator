"""Neutron Networking API application for OpenStack emulator.

Runs on port 9696 (standard OpenStack Neutron port).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from emulator.api.neutron import router as neutron_router

app = FastAPI(
    title="OpenStack Neutron Emulator",
    description="A lightweight OpenStack Neutron (Networking) API emulator",
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


# Custom exception handler for OpenStack-style errors
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


# Include Neutron router
app.include_router(neutron_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "neutron"}

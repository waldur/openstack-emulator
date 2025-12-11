"""Octavia Load Balancer API application for OpenStack emulator.

Runs on port 9876 (standard OpenStack Octavia port).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from emulator.api.octavia import router as octavia_router

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


# Include Octavia router
app.include_router(octavia_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "octavia"}

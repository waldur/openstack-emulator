"""Keystone Identity API application for OpenStack emulator.

Runs on port 5000 (standard OpenStack Keystone port).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from emulator.api.keystone import router as keystone_router
from emulator.core.middleware import ScenarioMiddleware

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

# Add scenario injection middleware
app.add_middleware(ScenarioMiddleware, service_name="keystone")


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


# Include Keystone router
app.include_router(keystone_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "keystone"}

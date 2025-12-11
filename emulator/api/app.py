"""Main FastAPI application for OpenStack emulator."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from emulator.api.keystone import router as keystone_router
from emulator.api.nova import router as nova_router

app = FastAPI(
    title="OpenStack Emulator",
    description="A lightweight OpenStack API emulator for testing purposes",
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


# Include routers
# Keystone (Identity) API
app.include_router(keystone_router)

# Nova (Compute) API
app.include_router(nova_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


# Emulator status endpoint
@app.get("/emulator/status")
async def emulator_status() -> dict[str, object]:
    """Get emulator status and statistics."""
    from emulator.core.database import db

    return {
        "status": "running",
        "version": "0.1.0",
        "statistics": {
            "servers": len(db._servers),
            "flavors": len(db._flavors),
            "images": len(db._images),
            "tokens": len(db._tokens),
            "keypairs": len(db._keypairs),
        },
    }


# Reset endpoint for testing
@app.post("/emulator/reset")
async def reset_emulator() -> dict[str, str]:
    """Reset the emulator to initial state."""
    from emulator.core.database import db

    # Clear Nova data
    db._servers.clear()
    db._keypairs.clear()

    # Reinitialize defaults
    db._init_default_flavors()
    db._init_default_images()
    db.reset_keystone()

    return {"status": "reset complete"}

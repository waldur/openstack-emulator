"""Status UI application for OpenStack emulator.

Runs on port 8080 - provides a web interface to view the status of all
services and objects in the emulator.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from emulator.api.status_ui import router as status_router

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

# Include Status UI router
app.include_router(status_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "status"}

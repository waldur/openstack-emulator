"""Scenario management API application for OpenStack emulator.

Runs on port 8999 (custom port for scenario management).
This service is NOT subject to scenario injection (would cause recursion).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from emulator.api.presets import router as presets_router
from emulator.api.scenarios import router as scenarios_router
from emulator.core.scenario_manager import scenario_manager

app = FastAPI(
    title="OpenStack Emulator Scenario Manager",
    description="Manage failure scenarios and load simulation for OpenStack emulator",
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


# Custom exception handler
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle exceptions."""
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
app.include_router(scenarios_router)
app.include_router(presets_router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    active_count = len(scenario_manager.get_active_scenarios())
    return {
        "status": "healthy",
        "service": "scenarios",
        "active_scenarios": str(active_count),
    }


# Root endpoint with quick status
@app.get("/")
async def root() -> dict:
    """Root endpoint with scenario system status."""
    return {
        "service": "OpenStack Emulator Scenario Manager",
        "version": "0.1.0",
        "status": scenario_manager.get_status(),
        "endpoints": {
            "scenarios": {
                "list_scenarios": "GET /scenarios",
                "get_active": "GET /scenarios/active",
                "get_stats": "GET /scenarios/stats",
                "enable": "POST /scenarios/{id}/enable",
                "disable": "POST /scenarios/{id}/disable",
                "reset_all": "POST /scenarios/reset",
                "create_custom": "POST /scenarios/custom",
                "apply_preset": "POST /scenarios/preset/{name}",
                "set_load_level": "POST /scenarios/load",
            },
            "presets": {
                "list_presets": "GET /presets",
                "load_preset": "POST /presets/{name}",
                "load_inline": "POST /presets/load/inline",
                "preview_preset": "GET /presets/{name}/preview",
            },
        },
    }

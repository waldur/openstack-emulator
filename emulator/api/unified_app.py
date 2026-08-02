"""Unified OpenStack emulator application using single process with multiple ports."""

import asyncio
import logging
import os
from typing import Dict

import uvicorn
from fastapi import APIRouter, FastAPI

from emulator.api.cinder import router as cinder_router
from emulator.api.cloudkitty import router as cloudkitty_router
from emulator.api.glance import router as glance_router

# Import all service routers
from emulator.api.keystone import router as keystone_router
from emulator.api.neutron import router as neutron_router
from emulator.api.nova import router as nova_router
from emulator.api.octavia import router as octavia_router
from emulator.api.oidc import router as oidc_router
from emulator.api.placement import router as placement_router
from emulator.api.scenarios import router as scenarios_router
from emulator.api.status_ui import router as status_router
from emulator.api.swift import router as swift_router
from emulator.core.database import db
from emulator.core.exceptions import add_openstack_exception_handlers
from emulator.core.headers import add_openstack_headers_middleware
from emulator.core.logging_middleware import (
    add_access_log_middleware,
    add_debug_logging_middleware,
)
from emulator.core.middleware import ScenarioMiddleware

# Configure logging
log_level = os.getenv("EMULATOR_LOG_LEVEL", "info").lower()
level_mapping = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
logging.basicConfig(
    level=level_mapping.get(log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)


def create_service_app(
    service_name: str,
    router: APIRouter,
    api_version: str,
    description: str,
    include_scenarios: bool = True,
) -> FastAPI:
    """Create a FastAPI app for a specific OpenStack service.

    Args:
        service_name: Name of the service (keystone, nova, etc.)
        router: The FastAPI router for this service
        api_version: API version string (e.g., "3.14", "2.1")
        description: Service description
        include_scenarios: Whether to include scenario middleware

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=f"OpenStack {service_name.title()} Emulator",
        description=description,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add CORS middleware for development
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add debug logging middleware for all services
    add_debug_logging_middleware(app, service_name)

    # Add scenario injection middleware (except for scenarios service itself)
    if include_scenarios and service_name != "scenarios":
        app.add_middleware(ScenarioMiddleware, service_name=service_name)

    # Add OpenStack headers middleware
    add_openstack_headers_middleware(app, service_name, api_version)

    # One access line per request, tagged with the service that handled it.
    # Added last so it is the outermost middleware and therefore sees every
    # response, including the ones ScenarioMiddleware short-circuits: an
    # injected 503 is exactly the kind of response you want in the log, and
    # from anywhere inside the stack it would leave no trace at all.
    add_access_log_middleware(app, service_name)

    # Add OpenStack-style exception handlers
    add_openstack_exception_handlers(app)

    # Include the service router
    app.include_router(router)

    # Add health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": service_name}

    return app


def create_all_service_apps() -> Dict[str, FastAPI]:
    """Create all OpenStack service applications.

    Returns:
        Dictionary mapping service names to FastAPI apps
    """
    return {
        "keystone": create_service_app(
            "keystone",
            keystone_router,
            "3.14",
            "A lightweight OpenStack Keystone (Identity) API emulator",
        ),
        "nova": create_service_app(
            "nova",
            nova_router,
            "2.87",
            "A lightweight OpenStack Nova (Compute) API emulator",
        ),
        "cinder": create_service_app(
            "cinder",
            cinder_router,
            "3.0",
            "A lightweight OpenStack Cinder (Block Storage) API emulator",
        ),
        "glance": create_service_app(
            "glance",
            glance_router,
            "2.0",
            "A lightweight OpenStack Glance (Image) API emulator",
        ),
        "neutron": create_service_app(
            "neutron",
            neutron_router,
            "2.0",
            "A lightweight OpenStack Neutron (Networking) API emulator",
        ),
        "octavia": create_service_app(
            "octavia",
            octavia_router,
            "2.0",
            "A lightweight OpenStack Octavia (Load Balancer) API emulator",
        ),
        "placement": create_service_app(
            "placement",
            placement_router,
            "1.0",
            "A lightweight OpenStack Placement (Resource Provider) API emulator",
        ),
        "cloudkitty": create_service_app(
            "cloudkitty",
            cloudkitty_router,
            "2.0",
            "A lightweight OpenStack CloudKitty (Rating) API emulator",
        ),
        "oidc": create_service_app(
            "oidc",
            oidc_router,
            "1.0",
            "An embedded OpenID Provider, for testing Keystone federation",
        ),
        "swift": create_service_app(
            "swift",
            swift_router,
            "1.0",
            "A lightweight OpenStack Swift (Object Storage) API emulator",
        ),
        "status": create_service_app(
            "status",
            status_router,
            "1.0",
            "Web interface for viewing OpenStack emulator status",
            include_scenarios=False,
        ),
        "scenarios": create_service_app(
            "scenarios",
            scenarios_router,
            "1.0",
            "Manage failure scenarios and load simulation for OpenStack emulator",
            include_scenarios=False,
        ),
    }


# Service port mapping
SERVICE_PORTS = {
    "keystone": 5000,
    "nova": 8774,
    "cinder": 8776,
    "glance": 9292,
    "neutron": 9696,
    "octavia": 9876,
    "placement": 8778,
    "swift": 8080,
    "oidc": 5556,
    "cloudkitty": 8889,
    "status": 10000,
    "scenarios": 8999,
}


async def run_service_on_port(app: FastAPI, host: str, port: int, service_name: str) -> None:
    """Run a service app on a specific port using uvicorn.

    Args:
        app: The FastAPI application
        host: Host to bind to
        port: Port to bind to
        service_name: Name of the service for logging
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
        # Superseded by add_access_log_middleware: uvicorn's shared access
        # logger cannot say which of the co-hosted services answered.
        access_log=False,
    )
    server = uvicorn.Server(config)

    logger.info("Starting %s on %s:%s", service_name, host, port)
    await server.serve()


async def run_all_services_async(host: str = "0.0.0.0", port_offset: int = 0) -> None:
    """Run all OpenStack services asynchronously in a single process.

    Args:
        host: Host to bind to
        port_offset: Offset to add to all default ports
    """
    # Create all service apps
    service_apps = create_all_service_apps()

    # The catalog has to name the same ports the listeners bind, or every SDK
    # client resolves endpoints that nothing is serving.
    db.port_offset = port_offset

    # Calculate actual ports with offset
    ports = {service: port + port_offset for service, port in SERVICE_PORTS.items()}

    print("\nOpenStack Emulator (Single Process) running:")
    print(f"  - Keystone (Identity):     http://{host}:{ports['keystone']}")
    print(f"  - Nova (Compute):          http://{host}:{ports['nova']}")
    print(f"  - Cinder (Block Storage):  http://{host}:{ports['cinder']}")
    print(f"  - Glance (Image):          http://{host}:{ports['glance']}")
    print(f"  - Neutron (Network):       http://{host}:{ports['neutron']}")
    print(f"  - Octavia (Load Balancer): http://{host}:{ports['octavia']}")
    print(f"  - Placement (Resource):    http://{host}:{ports['placement']}")
    print(f"  - Swift (Object Storage):  http://{host}:{ports['swift']}")
    print(f"  - OIDC (OpenID Provider):  http://{host}:{ports['oidc']}")
    print(f"  - CloudKitty (Rating):     http://{host}:{ports['cloudkitty']}")
    print(f"  - Status (Web UI):         http://{host}:{ports['status']}")
    print(f"  - Scenarios (Failure Sim): http://{host}:{ports['scenarios']}")
    print(f"\nLog level: {log_level}")
    print("\nPress Ctrl+C to stop all services.\n")

    # Create tasks for all services
    tasks = []
    for service_name, app in service_apps.items():
        port = ports[service_name]
        task = asyncio.create_task(
            run_service_on_port(app, host, port, service_name), name=f"{service_name}-{port}"
        )
        tasks.append(task)

    try:
        # Wait for all services to run
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down all services...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def run_all_services(host: str = "0.0.0.0", port_offset: int = 0) -> None:
    """Run all OpenStack services in a single process.

    Args:
        host: Host to bind to
        port_offset: Offset to add to all default ports
    """
    try:
        asyncio.run(run_all_services_async(host, port_offset))
    except KeyboardInterrupt:
        print("\nShutdown complete.")


def run_single_service(service_name: str, host: str = "0.0.0.0", port: int | None = None) -> None:
    """Run a single OpenStack service.

    Args:
        service_name: Name of the service to run
        host: Host to bind to
        port: Port to bind to (uses default if None)
    """
    service_apps = create_all_service_apps()

    if service_name not in service_apps:
        raise ValueError(f"Unknown service: {service_name}")

    app = service_apps[service_name]
    actual_port = port or SERVICE_PORTS[service_name]

    print(f"Starting {service_name} on {host}:{actual_port}")
    uvicorn.run(
        app,
        host=host,
        port=actual_port,
        log_level=log_level,
    )

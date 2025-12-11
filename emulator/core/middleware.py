"""Middleware for scenario-based failure and load injection.

This middleware synchronizes with shared state to enable cross-process
scenario coordination. The scenarios service writes state to a shared file,
and other service processes read from it.
"""

import asyncio

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from emulator.core.scenario_manager import scenario_manager


def get_operation_from_method(method: str) -> str:
    """Map HTTP method to operation type."""
    method_map = {
        "GET": "read",
        "HEAD": "read",
        "OPTIONS": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }
    return method_map.get(method.upper(), "all")


def get_resource_from_path(path: str) -> str:
    """Extract resource type from URL path."""
    # Common OpenStack resource paths
    resource_patterns = [
        ("/servers", "server"),
        ("/volumes", "volume"),
        ("/snapshots", "snapshot"),
        ("/networks", "network"),
        ("/subnets", "subnet"),
        ("/ports", "port"),
        ("/routers", "router"),
        ("/floating", "floating_ip"),
        ("/security-groups", "security_group"),
        ("/images", "image"),
        ("/flavors", "flavor"),
        ("/keypairs", "keypair"),
        ("/users", "user"),
        ("/projects", "project"),
        ("/tokens", "token"),
        ("/domains", "domain"),
        ("/roles", "role"),
    ]

    path_lower = path.lower()
    for pattern, resource in resource_patterns:
        if pattern in path_lower:
            return resource

    return "all"


class ScenarioMiddleware(BaseHTTPMiddleware):
    """
    Middleware that injects failures and delays based on active scenarios.

    This middleware:
    1. Checks for active failure scenarios and returns errors if triggered
    2. Applies delays based on load simulation scenarios
    3. Handles timeouts by returning appropriate error responses
    """

    def __init__(
        self,
        app: ASGIApp,
        service_name: str,
        exclude_paths: list[str] | None = None,
    ) -> None:
        """
        Initialize the middleware.

        Args:
            app: The ASGI application
            service_name: Name of the service (nova, keystone, etc.)
            exclude_paths: Paths to exclude from injection (e.g., /health)
        """
        super().__init__(app)
        self.service_name = service_name
        self.exclude_paths = exclude_paths or ["/health", "/healthcheck", "/scenarios"]

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request with scenario injection."""
        path = request.url.path

        # Skip injection for excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        # Sync local state from shared file (enables cross-process coordination)
        # This is cached with a short TTL to avoid excessive file reads
        scenario_manager.sync_from_shared_state()

        # Get operation and resource for filtering
        operation = get_operation_from_method(request.method)
        resource = get_resource_from_path(path)

        # Check for failure scenarios first
        failure = scenario_manager.should_fail(
            service=self.service_name,
            operation=operation,
            resource=resource,
        )

        if failure and failure.should_fail:
            return JSONResponse(
                status_code=failure.status_code,
                content={
                    "error": {
                        "message": failure.message,
                        "code": failure.status_code,
                        "scenario": failure.scenario_id,
                    }
                },
                headers={
                    "X-Scenario-Injection": failure.scenario_id,
                    "X-Failure-Type": (
                        failure.failure_type.value if failure.failure_type else "unknown"
                    ),
                },
            )

        # Calculate and apply delay
        delay_result = scenario_manager.calculate_delay(
            service=self.service_name,
            operation=operation,
        )

        # Check for timeout before applying delay
        if delay_result.should_timeout:
            # Simulate timeout by waiting a bit then returning error
            await asyncio.sleep(min(delay_result.delay_ms / 1000.0, 30.0))
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "message": "Gateway Timeout: Request timed out",
                        "code": 504,
                        "scenarios": delay_result.scenario_ids,
                    }
                },
                headers={
                    "X-Scenario-Injection": ",".join(delay_result.scenario_ids or []),
                    "X-Timeout-Injected": "true",
                },
            )

        # Apply delay if any
        if delay_result.delay_ms > 0:
            await asyncio.sleep(delay_result.delay_ms / 1000.0)

        # Process the actual request
        response = await call_next(request)

        # Add headers indicating scenario injection (for debugging)
        if delay_result.delay_ms > 0 or delay_result.scenario_ids:
            # Note: We can't modify response headers directly on streaming responses
            # so we only add these for JSONResponse or similar
            pass

        return response


def create_scenario_middleware(
    service_name: str,
    exclude_paths: list[str] | None = None,
) -> type[ScenarioMiddleware]:
    """
    Factory function to create a configured ScenarioMiddleware class.

    Usage:
        app.add_middleware(create_scenario_middleware("nova"))
    """

    class ConfiguredScenarioMiddleware(ScenarioMiddleware):
        def __init__(self, app: ASGIApp) -> None:
            super().__init__(app, service_name, exclude_paths)

    return ConfiguredScenarioMiddleware


def add_scenario_middleware(
    app: ASGIApp,
    service_name: str,
    exclude_paths: list[str] | None = None,
) -> None:
    """
    Helper function to add scenario middleware to a FastAPI app.

    Usage:
        from emulator.core.middleware import add_scenario_middleware
        add_scenario_middleware(app, "nova")
    """
    from fastapi import FastAPI

    if isinstance(app, FastAPI):
        app.add_middleware(
            ScenarioMiddleware,
            service_name=service_name,
            exclude_paths=exclude_paths,
        )

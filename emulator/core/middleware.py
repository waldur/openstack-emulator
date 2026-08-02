"""Middleware for scenario-based failure and load injection.

Reads ``scenario_manager`` — the same instance the scenarios API and the status
UI write to. All services share one process, so enabling a scenario on that
singleton is immediately visible here with no synchronisation.
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
        # Object storage paths are /v1/AUTH_<project>/<container>/<object>, so
        # the account segment identifies them. Lowercase: patterns are matched
        # against path.lower() below.
        ("/v1/auth", "object_store"),
        # Rating
        ("/summary", "rating"),
        ("/dataframes", "rating"),
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

        # Scenarios can be scoped to an operation (read/create/...) and a
        # resource (server/volume/...), so derive both from the request.
        operation = get_operation_from_method(request.method)
        resource = get_resource_from_path(path)

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
                    "X-Scenario-Injection": failure.scenario_id or "unknown",
                    "X-Failure-Type": (
                        failure.failure_type.value if failure.failure_type else "unknown"
                    ),
                },
            )

        delay = scenario_manager.calculate_delay(
            service=self.service_name,
            operation=operation,
        )

        if delay.should_timeout:
            # Make the client wait as it would for a real timeout, capped so a
            # misconfigured scenario cannot hang the test suite.
            await asyncio.sleep(min(delay.delay_ms / 1000.0, 30.0))
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "message": "Gateway Timeout: Request timed out",
                        "code": 504,
                        "scenarios": delay.scenario_ids,
                    }
                },
                headers={
                    "X-Scenario-Injection": ",".join(delay.scenario_ids or []),
                    "X-Timeout-Injected": "true",
                },
            )

        if delay.delay_ms > 0:
            await asyncio.sleep(delay.delay_ms / 1000.0)

        # Process the actual request
        return await call_next(request)


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

"""OpenStack standard HTTP headers middleware."""

import uuid
from fastapi import FastAPI, Request
from fastapi.responses import Response


def add_openstack_headers_middleware(app: FastAPI, service_name: str, api_version: str) -> None:
    """Add OpenStack standard headers to all responses.

    Args:
        app: The FastAPI application instance
        service_name: Name of the service (nova, cinder, etc.)
        api_version: API version string (e.g., "2.19", "3.0")
    """

    @app.middleware("http")
    async def openstack_headers_middleware(request: Request, call_next):
        """Add standard OpenStack headers to responses."""
        response = await call_next(request)

        # Generate unique request ID for this request
        request_id = f"req-{uuid.uuid4()}"

        # Add standard OpenStack headers
        response.headers["x-openstack-request-id"] = request_id
        response.headers["openstack-api-version"] = f"{service_name} {api_version}"

        # Service-specific headers
        if service_name == "nova":
            response.headers["x-compute-request-id"] = request_id
            response.headers["x-openstack-nova-api-version"] = api_version
        elif service_name == "cinder":
            response.headers["x-compute-request-id"] = request_id

        # Add vary header for API versioning
        response.headers["vary"] = "OpenStack-API-Version"
        if service_name == "nova":
            response.headers["vary"] = "OpenStack-API-Version, X-OpenStack-Nova-API-Version"

        return response

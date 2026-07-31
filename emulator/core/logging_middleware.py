"""Enhanced logging middleware for debugging requests and responses.

Based on StackOverflow solution for proper response body capture.
"""

import json
import logging
import os
from typing import cast

from fastapi import FastAPI, Request, Response
from starlette.background import BackgroundTask
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)
#: Separate logger so access lines can be filtered independently of debug output.
access_logger = logging.getLogger("emulator.access")


def log_request_response(
    service_name: str,
    req_body: bytes,
    res_body: bytes,
    status_code: int,
    headers: dict[str, str],
    method: str,
    url: str,
) -> None:
    """Log request and response details using background task."""
    try:
        # Skip verbose logging for UI service (HTML responses are too large)
        if service_name.lower() == "status":
            # Only log non-HTML responses for status service
            content_type = headers.get("content-type", "")
            if content_type.startswith("text/html"):
                logger.debug(
                    "%s RESPONSE: HTML content (%d bytes) - skipped for brevity",
                    service_name.upper(),
                    len(res_body),
                )
                return

        # Log request
        if req_body:
            req_str = req_body.decode("utf-8")
            logger.debug("%s REQUEST BODY: %s", service_name.upper(), req_str)
            try:
                req_json = json.loads(req_str)
                logger.debug(
                    "%s REQUEST JSON: %s", service_name.upper(), json.dumps(req_json, indent=2)
                )
            except json.JSONDecodeError:
                pass

        # Log response
        if res_body:
            res_str = res_body.decode("utf-8")
            logger.debug("%s RESPONSE BODY: %s", service_name.upper(), res_str)
            try:
                res_json = json.loads(res_str)
                logger.debug(
                    "%s RESPONSE JSON: %s", service_name.upper(), json.dumps(res_json, indent=2)
                )
            except json.JSONDecodeError:
                pass

    except Exception as e:
        logger.error("%s LOGGING ERROR: %s", service_name.upper(), e)


async def debug_logging_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Middleware to log request and response bodies."""
    # Check if debug logging is enabled
    debug_enabled = (
        logger.isEnabledFor(logging.DEBUG)
        or os.getenv("EMULATOR_DEBUG", "").lower() in ("1", "true")
        or os.getenv("EMULATOR_LOG_LEVEL", "").lower() == "debug"
    )

    if not debug_enabled:
        return await call_next(request)

    # Get service name from app title or default
    service_name = (
        getattr(request.app, "title", "unknown")
        .replace("OpenStack ", "")
        .replace(" Emulator", "")
        .lower()
    )

    # Log request details
    logger.debug("%s REQUEST: %s %s", service_name.upper(), request.method, request.url)
    logger.debug("%s HEADERS: %s", service_name.upper(), dict(request.headers))

    # Get request body
    req_body = await request.body()

    # Process request
    response = await call_next(request)

    # Log response headers
    logger.debug("%s RESPONSE: %s", service_name.upper(), response.status_code)
    logger.debug("%s RESPONSE HEADERS: %s", service_name.upper(), dict(response.headers))

    # Capture response body (call_next returns StreamingResponse in practice)
    streaming_response = cast(StreamingResponse, response)
    chunks: list[bytes] = []
    async for chunk in streaming_response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk)
        elif isinstance(chunk, str):
            chunks.append(chunk.encode("utf-8"))
        else:
            chunks.append(bytes(chunk))
    res_body = b"".join(chunks)

    # Create background task to log bodies
    task = BackgroundTask(
        log_request_response,
        service_name,
        req_body,
        res_body,
        response.status_code,
        dict(response.headers),
        request.method,
        str(request.url),
    )

    # Return new response with captured body and logging task
    return Response(
        content=res_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.headers.get("content-type"),
        background=task,
    )


def add_debug_logging_middleware(app: FastAPI, service_name: str) -> None:
    """Add comprehensive debug logging middleware to a FastAPI app.

    Args:
        app: The FastAPI application instance
        service_name: Name of the service for logging prefixes
    """
    # Apply the debug logging middleware directly to the app
    app.middleware("http")(debug_logging_middleware)


def add_access_log_middleware(app: FastAPI, service_name: str) -> None:
    """Log one line per request, naming the service that answered it.

    Replaces uvicorn's access log, which cannot do this: all services run in a
    single process and uvicorn reconfigures one shared ``uvicorn.access``
    logger, whose default format carries neither the service name nor the port.
    A 404 in the pod log was therefore unattributable — it could equally have
    been the owning service rejecting the request or a different service that
    has no such route.
    """

    @app.middleware("http")
    async def access_log_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        client = f"{request.client.host}:{request.client.port}" if request.client else "-"
        query = f"?{request.url.query}" if request.url.query else ""
        # The bound port, so the line stays right under --port-offset.
        server = request.scope.get("server") or ("", 0)
        access_logger.info(
            '%s:%s %s - "%s %s%s HTTP/%s" %d',
            service_name,
            server[1],
            client,
            request.method,
            request.url.path,
            query,
            request.scope.get("http_version", "1.1"),
            response.status_code,
        )
        return response

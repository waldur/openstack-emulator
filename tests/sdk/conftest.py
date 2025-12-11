"""Pytest fixtures for SDK tests against the OpenStack emulator."""

import socket
import threading
import time
from typing import Generator

import openstack
import pytest
import uvicorn
from openstack.connection import Connection

from emulator.core.database import db


def find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class UvicornServer:
    """Uvicorn server running in a background thread."""

    def __init__(self, app: str, host: str, port: int) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="error",
            access_log=False,
        )
        self.server = uvicorn.Server(self.config)
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the server in a background thread."""
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        # Wait for server to start
        while not self.server.started:
            time.sleep(0.01)

    def stop(self) -> None:
        """Stop the server."""
        self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)


class EmulatorServers:
    """Manager for all emulator service servers."""

    def __init__(self) -> None:
        self.servers: dict[str, UvicornServer] = {}
        self.ports: dict[str, int] = {}
        self.host = "127.0.0.1"

    def start_all(self) -> None:
        """Start all emulator services on dynamic ports."""
        # Map service names to their app modules
        service_apps = {
            "keystone": "emulator.api.app_keystone:app",
            "nova": "emulator.api.app_nova:app",
            "cinder": "emulator.api.app_cinder:app",
            "glance": "emulator.api.app_glance:app",
            "neutron": "emulator.api.app_neutron:app",
        }

        for service, app_path in service_apps.items():
            port = find_free_port()
            self.ports[service] = port
            server = UvicornServer(app_path, self.host, port)
            server.start()
            self.servers[service] = server

    def stop_all(self) -> None:
        """Stop all emulator services."""
        for server in self.servers.values():
            server.stop()
        self.servers.clear()
        self.ports.clear()

    def get_url(self, service: str) -> str:
        """Get the URL for a service."""
        return f"http://{self.host}:{self.ports[service]}"


@pytest.fixture(scope="module")
def emulator_servers() -> Generator[EmulatorServers, None, None]:
    """Start all emulator services for SDK testing.

    This fixture starts real HTTP servers for each OpenStack service
    so the SDK can make actual HTTP connections.
    """
    servers = EmulatorServers()
    servers.start_all()
    yield servers
    servers.stop_all()


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    """Reset the database before each test."""
    # Reset all service data
    db.reset_keystone()
    db.reset_cinder()
    db.reset_glance()
    db.reset_neutron()
    # Clear Nova data (no reset method available)
    db._servers.clear()
    db._keypairs.clear()
    # Reinitialize defaults
    db._init_default_flavors()
    yield


@pytest.fixture
def openstack_connection(emulator_servers: EmulatorServers) -> Generator[Connection, None, None]:
    """Create an OpenStack SDK connection to the emulator.

    This creates a connection with custom endpoint overrides
    pointing to the emulator services. For services that require
    project_id in URL (like Cinder), we include it in the endpoint.
    """
    # Disable SDK logging noise
    openstack.enable_logging(debug=False)

    # First, authenticate to get the project_id
    # We need this for services that require project_id in the URL
    auth_conn = openstack.connect(
        auth_type="password",
        auth_url=emulator_servers.get_url("keystone") + "/v3",
        username="admin",
        password="secret",
        project_name="admin",
        project_domain_name="Default",
        user_domain_name="Default",
        region_name="RegionOne",
        identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
    )
    project_id = auth_conn.current_project_id
    auth_conn.close()

    # Create the main connection with all endpoint overrides
    # Include project_id in endpoints that require it (Cinder, Nova compute)
    conn = openstack.connect(
        auth_type="password",
        auth_url=emulator_servers.get_url("keystone") + "/v3",
        username="admin",
        password="secret",
        project_name="admin",
        project_domain_name="Default",
        user_domain_name="Default",
        region_name="RegionOne",
        # Override endpoints to use our test server ports
        compute_endpoint_override=emulator_servers.get_url("nova") + "/v2.1",
        identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
        image_endpoint_override=emulator_servers.get_url("glance"),
        network_endpoint_override=emulator_servers.get_url("neutron"),
        block_storage_endpoint_override=emulator_servers.get_url("cinder") + f"/v3/{project_id}",
    )

    yield conn

    conn.close()


@pytest.fixture
def admin_project_id(openstack_connection: Connection) -> str:
    """Get the admin project ID from the connection."""
    return openstack_connection.current_project_id or "admin"

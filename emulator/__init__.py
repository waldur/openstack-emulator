"""OpenStack Emulator - A testing tool for OpenStack API clients."""

import argparse
import logging
import multiprocessing
import os
import sys

import uvicorn

from emulator.api.app import app

__version__ = "0.1.0"
__all__ = ["app", "main"]


def configure_logging(log_level: str) -> None:
    """Configure Python logging for the emulator."""
    # Map string levels to logging levels
    level_mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    level = level_mapping.get(log_level.lower(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # Override any existing configuration
    )

    # Set specific loggers to debug level if needed
    if level == logging.DEBUG:
        logging.getLogger("emulator").setLevel(logging.DEBUG)
        logging.getLogger("emulator.core.auth").setLevel(logging.DEBUG)
        logging.getLogger("emulator.core.database").setLevel(logging.DEBUG)
        logging.getLogger("emulator.api").setLevel(logging.DEBUG)


def load_preset(preset_name: str | None, preset_file: str | None) -> bool:
    """Load a preset before starting services.

    Args:
        preset_name: Name of a built-in preset to load.
        preset_file: Path to a custom preset file.

    Returns:
        True if preset loaded successfully or no preset specified.
    """
    if not preset_name and not preset_file:
        return True

    from emulator.core.database import db
    from emulator.core.presets import PresetLoader

    loader = PresetLoader(db)

    if preset_file:
        print(f"Loading preset from file: {preset_file}")
        result = loader.load_preset(preset_file)
    else:
        print(f"Loading preset: {preset_name}")
        result = loader.load_preset_by_name(preset_name)  # type: ignore

    if result.success:
        print(f"Preset '{result.preset_name}' loaded successfully:")
        for service, count in result.resources_created.items():
            if count > 0:
                print(f"  - {service}: {count} resources")
        print(f"  Total: {result.resource_count} resources")
        return True
    else:
        print(f"Failed to load preset '{result.preset_name}':")
        for error in result.errors:
            print(f"  - {error}")
        return False


def list_presets() -> None:
    """List all available built-in presets."""
    from emulator.core.database import db
    from emulator.core.presets import PresetLoader

    loader = PresetLoader(db)
    presets = loader.list_available_presets()

    if not presets:
        print("No built-in presets found.")
        print(f"Preset directory: {loader.BUILTIN_PRESETS_DIR}")
        return

    print("Available presets:")
    for preset in presets:
        print(f"  - {preset['name']}: {preset['description']}")
        print(f"    File: {preset['file']}")


# Standard OpenStack service ports
SERVICE_PORTS = {
    "keystone": 5000,
    "nova": 8774,
    "cinder": 8776,
    "glance": 9292,
    "neutron": 9696,
    "octavia": 9876,
    "status": 10000,
    "scenarios": 8999,
}

SERVICE_APPS = {
    "keystone": "emulator.api.app_keystone:app",
    "nova": "emulator.api.app_nova:app",
    "cinder": "emulator.api.app_cinder:app",
    "glance": "emulator.api.app_glance:app",
    "neutron": "emulator.api.app_neutron:app",
    "octavia": "emulator.api.app_octavia:app",
    "status": "emulator.api.app_status:app",
    "scenarios": "emulator.api.app_scenarios:app",
}


def run_service(service: str, host: str, port: int, log_level: str = "info") -> None:
    """Run a single OpenStack service."""
    app_path = SERVICE_APPS.get(service)
    if not app_path:
        print(f"Unknown service: {service}")
        sys.exit(1)

    print(f"Starting {service} on {host}:{port}")
    uvicorn.run(
        app_path,
        host=host,
        port=port,
        reload=False,
        log_level=log_level,
    )


def run_all_services(host: str, port_offset: int = 0, log_level: str = "info") -> None:
    """Run all OpenStack services on their standard ports."""
    processes = []

    # Calculate actual ports with offset
    ports = {service: port + port_offset for service, port in SERVICE_PORTS.items()}

    print("\nOpenStack Emulator running:")
    print(f"  - Keystone (Identity):     http://{host}:{ports['keystone']}")
    print(f"  - Nova (Compute):          http://{host}:{ports['nova']}")
    print(f"  - Cinder (Block Storage):  http://{host}:{ports['cinder']}")
    print(f"  - Glance (Image):          http://{host}:{ports['glance']}")
    print(f"  - Neutron (Network):       http://{host}:{ports['neutron']}")
    print(f"  - Octavia (Load Balancer): http://{host}:{ports['octavia']}")
    print(f"  - Status (Web UI):         http://{host}:{ports['status']}")
    print(f"  - Scenarios (Failure Sim): http://{host}:{ports['scenarios']}")
    print(f"\nLog level: {log_level}")
    print("\nPress Ctrl+C to stop all services.\n")

    for service, port in ports.items():
        p = multiprocessing.Process(
            target=run_service,
            args=(service, host, port, log_level),
        )
        p.start()
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nStopping all services...")
        for p in processes:
            p.terminate()
            p.join()


def main() -> None:
    """Run the OpenStack emulator server."""
    parser = argparse.ArgumentParser(
        description="OpenStack Emulator - A lightweight API emulator for testing"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port override for single service mode (ignored when running all)",
    )
    parser.add_argument(
        "--service",
        choices=[
            "keystone",
            "nova",
            "cinder",
            "glance",
            "neutron",
            "octavia",
            "status",
            "scenarios",
            "all",
        ],
        default="all",
        help="Service to run: keystone (5000), nova (8774), cinder (8776), "
        "glance (9292), neutron (9696), octavia (9876), status (10000), scenarios (8999), or all (default: all)",
    )
    parser.add_argument(
        "--port-offset",
        type=int,
        default=0,
        help="Offset to add to all default ports (useful if port 5000 is in use). "
        "Example: --port-offset 1000 runs keystone on 6000",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help="Load a built-in preset by name (e.g., 'development', 'production')",
    )
    parser.add_argument(
        "--preset-file",
        type=str,
        default=None,
        help="Load a preset from a YAML file path",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available built-in presets and exit",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set the logging level (default: info)",
    )

    args = parser.parse_args()

    # Configure logging first and set environment variable for child processes
    configure_logging(args.log_level)
    os.environ["EMULATOR_LOG_LEVEL"] = args.log_level

    # Handle --list-presets
    if args.list_presets:
        list_presets()
        sys.exit(0)

    # Load preset if specified
    if not load_preset(args.preset, args.preset_file):
        sys.exit(1)

    if args.service == "all":
        if args.port:
            print("Warning: --port is ignored when running all services")
        run_all_services(args.host, args.port_offset, args.log_level)
    else:
        port = args.port or SERVICE_PORTS[args.service]
        run_service(args.service, args.host, port, args.log_level)


if __name__ == "__main__":
    main()

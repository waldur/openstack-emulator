"""OpenStack Emulator - A testing tool for OpenStack API clients."""

import argparse
import importlib.metadata
import os
import sys

from emulator.api.unified_app import SERVICE_PORTS, run_all_services, run_single_service

try:
    __version__ = importlib.metadata.version("openstack-emulator")
except importlib.metadata.PackageNotFoundError:
    # Fallback for development/testing when the package isn't installed
    __version__ = "0.0.0-dev"
__all__ = ["main"]


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
    parser.add_argument(
        "--persist-db",
        type=str,
        default=None,
        help="Path to JSON file for database persistence (e.g., 'data/emulator_db.json')",
    )
    parser.add_argument(
        "--auto-save",
        action="store_true",
        help="Enable auto-saving of database on changes",
    )

    args = parser.parse_args()

    # Configure logging
    os.environ["EMULATOR_LOG_LEVEL"] = args.log_level

    # Handle --list-presets
    if args.list_presets:
        list_presets()
        sys.exit(0)

    # Configure persistence
    if args.persist_db:
        from emulator.core.database import db

        db.persist_path = args.persist_db
        db.auto_save = args.auto_save
        try:
            db.load()
        except Exception as e:
            print(f"Failed to load database from {args.persist_db}: {e}")
            sys.exit(1)

    # Load preset if specified
    if not load_preset(args.preset, args.preset_file):
        sys.exit(1)

    if args.service == "all":
        if args.port:
            print("Warning: --port is ignored when running all services")
        run_all_services(args.host, args.port_offset)
    else:
        port = args.port or SERVICE_PORTS[args.service]
        run_single_service(args.service, args.host, port)


if __name__ == "__main__":
    main()

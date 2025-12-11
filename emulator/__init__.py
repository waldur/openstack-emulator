"""OpenStack Emulator - A testing tool for OpenStack API clients."""

import argparse
import multiprocessing
import sys

import uvicorn

from emulator.api.app import app

__version__ = "0.1.0"
__all__ = ["app", "main"]

# Standard OpenStack service ports
SERVICE_PORTS = {
    "keystone": 5000,
    "nova": 8774,
    "cinder": 8776,
    "glance": 9292,
}

SERVICE_APPS = {
    "keystone": "emulator.api.app_keystone:app",
    "nova": "emulator.api.app_nova:app",
    "cinder": "emulator.api.app_cinder:app",
    "glance": "emulator.api.app_glance:app",
}


def run_service(service: str, host: str, port: int) -> None:
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
        log_level="info",
    )


def run_all_services(host: str) -> None:
    """Run all OpenStack services on their standard ports."""
    processes = []

    for service, port in SERVICE_PORTS.items():
        p = multiprocessing.Process(
            target=run_service,
            args=(service, host, port),
        )
        p.start()
        processes.append(p)

    print(f"\nOpenStack Emulator running:")
    print(f"  - Keystone (Identity):     http://{host}:5000")
    print(f"  - Nova (Compute):          http://{host}:8774")
    print(f"  - Cinder (Block Storage):  http://{host}:8776")
    print(f"  - Glance (Image):          http://{host}:9292")
    print("\nPress Ctrl+C to stop all services.\n")

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
        choices=["keystone", "nova", "cinder", "glance", "all"],
        default="all",
        help="Service to run: keystone (5000), nova (8774), cinder (8776), "
        "glance (9292), or all (default: all)",
    )

    args = parser.parse_args()

    if args.service == "all":
        if args.port:
            print("Warning: --port is ignored when running all services")
        run_all_services(args.host)
    else:
        port = args.port or SERVICE_PORTS[args.service]
        run_service(args.service, args.host, port)


if __name__ == "__main__":
    main()

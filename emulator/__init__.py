"""OpenStack Emulator - A testing tool for OpenStack API clients."""

import uvicorn

from emulator.api.app import app

__version__ = "0.1.0"
__all__ = ["app", "main"]


def main() -> None:
    """Run the OpenStack emulator server."""
    uvicorn.run(
        "emulator.api.app:app",
        host="0.0.0.0",
        port=8774,
        reload=False,
    )


if __name__ == "__main__":
    main()

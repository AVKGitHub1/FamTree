"""Process entry point: `python -m famtree`."""

from __future__ import annotations

import errno
import os
import socket
import sys

import uvicorn

from famtree.app import create_app
from famtree.config import ConfigError, Settings
from famtree.log_config import configure_logging


def _port_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return False
            raise
    return True


def main() -> int:
    # Everything this process creates (database, WAL, backups) is owner-only.
    os.umask(0o077)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"famtree: configuration error: {exc}", file=sys.stderr)
        return 2
    configure_logging(settings.log_level)

    if not _port_available(settings.listen_host, settings.listen_port):
        print(
            f"famtree: port {settings.listen_port} on {settings.listen_host} is already in use.\n"
            "Choose another port: set FAMTREE_LISTEN_PORT to a free port (with Docker, change "
            "the host port in docker-compose.yml) and start again.",
            file=sys.stderr,
        )
        return 2

    # Uvicorn handles SIGTERM/SIGINT gracefully: in-flight requests finish, then
    # the app's shutdown hook checkpoints and closes the database.
    uvicorn.run(
        create_app(settings),
        host=settings.listen_host,
        port=settings.listen_port,
        log_config=None,
        proxy_headers=False,  # forwarding headers are interpreted by famtree.security.proxy
        server_header=False,
        timeout_graceful_shutdown=15,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

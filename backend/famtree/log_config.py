"""Logging setup. Application logs never include passwords, codes, session
tokens, private attributes or exported data; request logs carry paths only
(secrets are always sent in request bodies, never in URLs)."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    # Uvicorn's access log records the path but not query strings or bodies.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if level != "debug" else "INFO")

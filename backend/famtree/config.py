"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

DEFAULT_TRUSTED_PROXIES = "127.0.0.1/32,::1/128,172.16.0.0/12"


class ConfigError(ValueError):
    """Raised when an environment variable holds an unusable value."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    key_file: Path
    listen_host: str
    listen_port: int
    static_dir: Path | None
    require_data_mount: bool
    cookie_secure: str  # "auto" | "true" | "false"
    trusted_proxies: tuple[IPNetwork, ...]
    session_ttl_hours: int
    admin_session_ttl_hours: int
    log_level: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "famtree.db"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        static = env.get("FAMTREE_STATIC_DIR", "").strip()
        return cls(
            data_dir=Path(env.get("FAMTREE_DATA_DIR", "/data")),
            key_file=Path(env.get("FAMTREE_KEY_FILE", "/run/secrets/famtree_key")),
            listen_host=env.get("FAMTREE_LISTEN_HOST", "0.0.0.0"),
            listen_port=_int(env, "FAMTREE_LISTEN_PORT", 8080, 1, 65535),
            static_dir=Path(static) if static else None,
            require_data_mount=_bool(env, "FAMTREE_REQUIRE_DATA_MOUNT", False),
            cookie_secure=_choice(env, "FAMTREE_COOKIE_SECURE", "auto", ("auto", "true", "false")),
            trusted_proxies=_networks(env.get("FAMTREE_TRUSTED_PROXIES", DEFAULT_TRUSTED_PROXIES)),
            session_ttl_hours=_int(env, "FAMTREE_SESSION_TTL_HOURS", 24 * 30, 1, 24 * 365),
            admin_session_ttl_hours=_int(
                env, "FAMTREE_ADMIN_SESSION_TTL_HOURS", 24 * 7, 1, 24 * 90
            ),
            log_level=_choice(
                env, "FAMTREE_LOG_LEVEL", "info", ("debug", "info", "warning", "error")
            ),
        )


def _int(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _choice(env: Mapping[str, str], name: str, default: str, options: tuple[str, ...]) -> str:
    raw = env.get(name, "").strip().lower() or default
    if raw not in options:
        raise ConfigError(f"{name} must be one of {', '.join(options)}, got {raw!r}")
    return raw


def _networks(raw: str) -> tuple[IPNetwork, ...]:
    networks = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError as exc:
            raise ConfigError(f"FAMTREE_TRUSTED_PROXIES has an invalid entry {part!r}") from exc
    return tuple(networks)

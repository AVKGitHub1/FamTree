"""Client address and scheme, honouring forwarding headers only from trusted proxies
(e.g. cloudflared on the host, reaching the container through the Docker bridge)."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

from famtree.config import IPNetwork


def _trusted(address: str | None, proxies: tuple[IPNetwork, ...]) -> bool:
    if not address:
        return False
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in proxies)


def client_ip(request: Request, proxies: tuple[IPNetwork, ...]) -> str:
    peer = request.client.host if request.client else ""
    if not _trusted(peer, proxies):
        return peer or "unknown"
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
    for hop in reversed([p for p in forwarded if p]):
        if not _trusted(hop, proxies):
            return hop
    return peer


def is_https(request: Request, proxies: tuple[IPNetwork, ...]) -> bool:
    peer = request.client.host if request.client else ""
    if _trusted(peer, proxies):
        proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        if proto:
            return proto == "https"
    return request.url.scheme == "https"

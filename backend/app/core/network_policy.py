from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address

from .config import Settings


@dataclass(frozen=True)
class BindHosts:
    backend: str
    frontend: str
    lan_enabled: bool


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def resolve_bind_hosts(settings: Settings) -> BindHosts:
    backend = settings.backend_host.strip()
    frontend = settings.frontend_host.strip()
    if not backend or not frontend:
        raise ValueError("BACKEND_HOST and FRONTEND_HOST must not be empty")
    if not settings.allow_lan_access:
        unsafe = [host for host in (backend, frontend) if not is_loopback_host(host)]
        if unsafe:
            raise ValueError(
                "Non-loopback binding requires ALLOW_LAN_ACCESS=true: "
                + ", ".join(unsafe)
            )
    return BindHosts(
        backend=backend,
        frontend=frontend,
        lan_enabled=settings.allow_lan_access,
    )

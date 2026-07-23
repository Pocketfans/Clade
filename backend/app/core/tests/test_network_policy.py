import pytest

from app.core.config import Settings
from app.core.network_policy import resolve_bind_hosts


def make_settings(**overrides) -> Settings:
    values = {
        "BACKEND_HOST": "127.0.0.1",
        "FRONTEND_HOST": "127.0.0.1",
        "ALLOW_LAN_ACCESS": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_default_hosts_are_loopback() -> None:
    hosts = resolve_bind_hosts(make_settings())
    assert hosts.backend == "127.0.0.1"
    assert hosts.frontend == "127.0.0.1"
    assert hosts.lan_enabled is False


@pytest.mark.parametrize("field", ["BACKEND_HOST", "FRONTEND_HOST"])
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.25", "10.0.0.8"])
def test_non_loopback_host_requires_lan_opt_in(field: str, host: str) -> None:
    with pytest.raises(ValueError, match="ALLOW_LAN_ACCESS=true"):
        resolve_bind_hosts(make_settings(**{field: host}))


def test_explicit_lan_opt_in_allows_non_loopback_hosts() -> None:
    hosts = resolve_bind_hosts(
        make_settings(
            BACKEND_HOST="0.0.0.0",
            FRONTEND_HOST="0.0.0.0",
            ALLOW_LAN_ACCESS=True,
        )
    )
    assert hosts.backend == "0.0.0.0"
    assert hosts.frontend == "0.0.0.0"
    assert hosts.lan_enabled is True

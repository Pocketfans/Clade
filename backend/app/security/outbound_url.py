from __future__ import annotations

import socket
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Literal, TypeAlias
from urllib.parse import urlsplit, urlunsplit


OutboundErrorCode = Literal[
    "outbound_url_invalid",
    "outbound_https_required",
    "local_ai_disabled",
    "private_network_blocked",
    "outbound_dns_failed",
    "outbound_connect_failed",
    "outbound_response_too_large",
    "outbound_bad_response",
    "outbound_timeout",
]

IPAddress: TypeAlias = IPv4Address | IPv6Address
Resolver: TypeAlias = Callable[[str, int], Iterable[IPAddress]]


_IPV4_SPECIAL_PURPOSE_NETWORKS: tuple[IPv4Network, ...] = tuple(
    ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.31.196.0/24",
        "192.52.193.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "192.175.48.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)

_IPV6_SPECIAL_PURPOSE_NETWORKS: tuple[IPv6Network, ...] = tuple(
    ip_network(network)
    for network in (
        "::/96",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "2620:4f:8000::/48",
        "3fff::/20",
        "5f00::/16",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)

_IPV4_COMPATIBLE_NETWORK = ip_network("::/96")
_NAT64_NETWORKS = (ip_network("64:ff9b::/96"), ip_network("64:ff9b:1::/48"))


def _embedded_ipv4_addresses(address: IPv6Address) -> tuple[IPv4Address, ...]:
    embedded: list[IPv4Address] = []
    if address.ipv4_mapped is not None:
        embedded.append(address.ipv4_mapped)
    if address in _IPV4_COMPATIBLE_NETWORK:
        embedded.append(IPv4Address(int(address) & 0xFFFFFFFF))
    if any(address in network for network in _NAT64_NETWORKS):
        embedded.append(IPv4Address(int(address) & 0xFFFFFFFF))
    if address.sixtofour is not None:
        embedded.append(address.sixtofour)
    if address.teredo is not None:
        embedded.extend(address.teredo)
    return tuple(dict.fromkeys(embedded))


def _is_public_outbound_address(address: IPAddress) -> bool:
    if isinstance(address, IPv4Address):
        return address.is_global and not any(
            address in network for network in _IPV4_SPECIAL_PURPOSE_NETWORKS
        )

    if any(
        not _is_public_outbound_address(embedded)
        for embedded in _embedded_ipv4_addresses(address)
    ):
        return False
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_site_local
        or address.is_unspecified
    ):
        return False
    if any(address in network for network in _IPV6_SPECIAL_PURPOSE_NETWORKS):
        return False
    return address.is_global


@dataclass(frozen=True)
class CanonicalOutboundBaseURL:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int


@dataclass(frozen=True)
class ValidatedOutboundURL:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    resolved_ips: tuple[IPAddress, ...]
    is_local: bool


class OutboundRequestError(Exception):
    def __init__(
        self,
        code: OutboundErrorCode,
        status_code: int,
        public_message: str,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.status_code = status_code
        self.public_message = public_message


def _invalid_url() -> OutboundRequestError:
    return OutboundRequestError("outbound_url_invalid", 400, "外部服务地址无效")


def _dns_failed() -> OutboundRequestError:
    return OutboundRequestError("outbound_dns_failed", 502, "域名解析失败")


def _system_resolver(hostname: str, port: int) -> tuple[IPAddress, ...]:
    answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(ip_address(answer[4][0]) for answer in answers)


def canonicalize_outbound_base_url(url: str) -> CanonicalOutboundBaseURL:
    if (
        not isinstance(url, str)
        or not url
        or "\\" in url
        or any(
            char.isspace() or unicodedata.category(char) == "Cc"
            for char in url
        )
    ):
        raise _invalid_url()

    if "?" in url or "#" in url:
        raise _invalid_url()

    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        if (
            scheme not in ("http", "https")
            or not parsed.netloc
            or not hostname
            or "@" in parsed.netloc
            or parsed.netloc.endswith(":")
            or parsed.query
            or parsed.fragment
        ):
            raise _invalid_url()
        parsed_port = parsed.port
    except (TypeError, ValueError):
        raise _invalid_url() from None

    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        raise _invalid_url()
    port = (
        parsed_port
        if parsed_port is not None
        else (443 if scheme == "https" else 80)
    )

    normalized_hostname = hostname.lower()
    if normalized_hostname.endswith("."):
        normalized_hostname = normalized_hostname[:-1]
    if (
        not normalized_hostname
        or ".." in normalized_hostname
        or normalized_hostname.endswith(".")
    ):
        raise _invalid_url()
    try:
        normalized_hostname = (
            normalized_hostname.encode("idna").decode("ascii").lower()
        )
    except UnicodeError:
        raise _invalid_url() from None
    if normalized_hostname.endswith("."):
        normalized_hostname = normalized_hostname[:-1]
    if not normalized_hostname or any(
        not label for label in normalized_hostname.split(".")
    ):
        raise _invalid_url()

    url_hostname = (
        f"[{normalized_hostname}]"
        if ":" in normalized_hostname
        else normalized_hostname
    )
    netloc = (
        f"{url_hostname}:{parsed_port}"
        if parsed_port is not None
        else url_hostname
    )
    normalized_url = urlunsplit((scheme, netloc, parsed.path, "", ""))
    return CanonicalOutboundBaseURL(
        url=normalized_url,
        scheme=scheme,
        hostname=normalized_hostname,
        port=port,
    )


class OutboundURLPolicy:
    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = _system_resolver if resolver is None else resolver

    def validate(
        self,
        url: str,
        *,
        allow_local: bool,
    ) -> ValidatedOutboundURL:
        canonical = canonicalize_outbound_base_url(url)
        scheme = canonical.scheme
        normalized_hostname = canonical.hostname
        port = canonical.port

        literal_ip: IPAddress | None
        try:
            literal_ip = ip_address(normalized_hostname)
        except ValueError:
            literal_ip = None

        if literal_ip is not None:
            resolved_ips = (literal_ip,)
        else:
            try:
                answers = self._resolver(normalized_hostname, port)
                resolved_ips = tuple(
                    dict.fromkeys(
                        address
                        if isinstance(address, (IPv4Address, IPv6Address))
                        else ip_address(address)
                        for address in answers
                    )
                )
            except (OSError, TypeError, ValueError):
                raise _dns_failed() from None
            if not resolved_ips:
                raise _dns_failed()

        exact_loopback = literal_ip in (ip_address("127.0.0.1"), ip_address("::1"))
        localhost = normalized_hostname == "localhost"
        if localhost and not all(address.is_loopback for address in resolved_ips):
            raise OutboundRequestError(
                "private_network_blocked", 400, "该网络地址不允许访问"
            )
        if localhost or exact_loopback:
            if not allow_local:
                raise OutboundRequestError(
                    "local_ai_disabled", 400, "本地 AI 访问未开启"
                )
            return ValidatedOutboundURL(
                url=canonical.url,
                scheme=scheme,
                hostname=normalized_hostname,
                port=port,
                resolved_ips=resolved_ips,
                is_local=True,
            )

        if any(not _is_public_outbound_address(address) for address in resolved_ips):
            raise OutboundRequestError(
                "private_network_blocked", 400, "该网络地址不允许访问"
            )

        if scheme != "https":
            raise OutboundRequestError(
                "outbound_https_required", 400, "公网服务必须使用 HTTPS"
            )

        return ValidatedOutboundURL(
            url=canonical.url,
            scheme=scheme,
            hostname=normalized_hostname,
            port=port,
            resolved_ips=resolved_ips,
            is_local=False,
        )

"""Helpers for discovering usable local network addresses.

MoriBot binds to all interfaces by default so a phone on the same Wi-Fi can
reach the dashboard and pairing API. These helpers are used to print friendly
LAN URLs and to turn a localhost pairing link into one the phone can open.
"""

from __future__ import annotations

import ipaddress
import socket

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_loopback_host(host: str | None) -> bool:
    return (host or "").strip().lower() in _LOOPBACK_HOSTS


def local_ipv4_addresses() -> list[str]:
    """Return usable non-loopback IPv4 addresses for this machine."""
    addresses: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        address = (value or "").strip()
        if not address or address in seen:
            return
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return
        if parsed.version != 4 or parsed.is_loopback or parsed.is_link_local:
            return
        if parsed.is_unspecified or parsed.is_multicast:
            return
        seen.add(address)
        addresses.append(address)

    # The UDP route trick returns the address used for outbound traffic, which
    # is normally the address a phone on the same LAN should use.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        _, _, host_addresses = socket.gethostbyname_ex(hostname)
        for address in host_addresses:
            add(address)
    except OSError:
        pass

    return addresses


def primary_lan_ip() -> str:
    """Return the most likely LAN address, or an empty string."""
    addresses = local_ipv4_addresses()
    return addresses[0] if addresses else ""

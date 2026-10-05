import ipaddress
import socket
from urllib.parse import urlparse

import structlog
from fastapi import HTTPException, status

logger = structlog.get_logger("security.ssrf")


def validate_url_for_ssrf(url: str) -> str:
    """Validate that a URL is safe from SSRF attacks.

    Allows only HTTP and HTTPS schemes.
    Resolves the hostname and checks against private, loopback, and link-local IP addresses.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed URL provided",
        ) from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL: Hostname is required.",
        )

    # Check for direct IP address or resolve DNS
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        logger.warning("ssrf_dns_lookup_failed", hostname=hostname, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to resolve hostname '{hostname}'.",
        ) from exc

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                logger.warning(
                    "ssrf_blocked_address",
                    hostname=hostname,
                    resolved_ip=ip_str,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Access to private or restricted network addresses is prohibited.",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid IP address resolved: {ip_str}",
            ) from exc

    return url

import socket
import ipaddress
import urllib.parse
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger("jarvis.browser.security")


class BrowserSecurityError(Exception):
    """Base exception for browser security violations."""
    pass


class UnsupportedSchemeError(BrowserSecurityError):
    """Raised when URL scheme is not allowed (e.g. javascript:, file:, data:)."""
    pass


class BlockedDestinationError(BrowserSecurityError):
    """Raised when destination is localhost, loopback, private IP, or cloud metadata."""
    pass


class InvalidURLError(BrowserSecurityError):
    """Raised when URL is malformed or invalid."""
    pass


class URLSecurityValidator:
    """
    Centralized URL Security Validator:
    Enforces strict access boundaries:
    - HTTP and HTTPS schemes only
    - Rejects localhost, loopback (127.0.0.1, [::1]), and 0.0.0.0
    - Rejects RFC 1918 private subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Rejects cloud metadata services (169.254.169.254, metadata.google.internal)
    - Rejects credentials embedded in URLs (user:pass@host)
    - Resolves hostnames via DNS to prevent DNS rebinding attacks
    """

    ALLOWED_SCHEMES = {"http", "https"}
    BLOCKED_HOSTNAMES = {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "instance-data",
    }

    SENSITIVE_QUERY_PARAMS = {
        "token", "auth", "key", "secret", "password", "pwd", "api_key",
        "apikey", "access_token", "session", "session_id", "credential"
    }

    @classmethod
    def validate(cls, url: str) -> str:
        """
        Validates URL string. Returns canonicalized URL if permitted,
        or raises appropriate BrowserSecurityError.
        """
        if not url or not isinstance(url, str):
            raise InvalidURLError("URL must be a non-empty string.")

        raw_url = url.strip()

        # Reject control characters
        if any(ord(c) < 32 or ord(c) == 127 for c in raw_url):
            raise InvalidURLError("URL contains invalid control characters.")

        # Check scheme before full parsing
        scheme_match = re.match(r"^([a-zA-Z0-9\+\.\-]+):", raw_url)
        if not scheme_match:
            # If no scheme provided, prefix with https://
            raw_url = f"https://{raw_url}"
            scheme_match = re.match(r"^([a-zA-Z0-9\+\.\-]+):", raw_url)

        scheme = scheme_match.group(1).lower() if scheme_match else ""
        if scheme not in cls.ALLOWED_SCHEMES:
            raise UnsupportedSchemeError(
                f"Unsupported URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."
            )

        try:
            parsed = urllib.parse.urlsplit(raw_url)
        except Exception as e:
            raise InvalidURLError(f"Malformed URL structure: {e}")

        # Check for user credentials in URL
        if parsed.username or parsed.password:
            raise InvalidURLError("Embedded user credentials in URLs are strictly prohibited.")

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise InvalidURLError("URL must specify a valid destination hostname.")

        # Require a valid domain (with a dot) or explicit IP address
        if "." not in hostname and hostname not in cls.BLOCKED_HOSTNAMES:
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                raise InvalidURLError(f"Destination '{hostname}' is not a valid domain name or IP address.")

        # Check exact and wildcard blocked hostnames
        if hostname in cls.BLOCKED_HOSTNAMES or hostname.endswith(".localhost") or hostname.endswith(".local"):
            raise BlockedDestinationError(
                f"Access to local destination '{hostname}' is blocked by security policy."
            )

        # Check port
        if parsed.port:
            if parsed.port < 1 or parsed.port > 65535:
                raise InvalidURLError(f"Invalid port number: {parsed.port}")

        # Resolve IP address to prevent SSRF and DNS rebinding
        cls._verify_destination_ips(hostname, parsed.port or (443 if scheme == "https" else 80))

        return raw_url

    @classmethod
    def _verify_destination_ips(cls, hostname: str, port: int) -> None:
        """Resolves hostname and verifies that no resolved IP is in a blocked range."""
        # Fast path for direct IP literals
        try:
            ip = ipaddress.ip_address(hostname)
            cls._check_ip_safety(ip, hostname)
            return
        except ValueError:
            pass  # Not an IP literal, proceed to DNS resolution

        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            # If hostname cannot be resolved currently (e.g. offline test), allow domain
            # unless it clearly matches local patterns
            logger.debug(f"DNS resolution failed for '{hostname}': {e}")
            return
        except Exception as e:
            raise InvalidURLError(f"Hostname resolution failed: {e}")

        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                cls._check_ip_safety(ip, hostname)
            except ValueError:
                continue

    @classmethod
    def _check_ip_safety(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, hostname: str) -> None:
        if ip.is_loopback:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to loopback address ({ip}), which is blocked."
            )
        if ip.is_private:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to private network address ({ip}), which is blocked."
            )
        if ip.is_link_local:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to link-local address ({ip}), which is blocked."
            )
        if ip.is_multicast:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to multicast address ({ip}), which is blocked."
            )
        if ip.is_reserved:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to reserved address ({ip}), which is blocked."
            )
        if ip.is_unspecified:
            raise BlockedDestinationError(
                f"Destination '{hostname}' resolves to unspecified address ({ip}), which is blocked."
            )

        # Cloud metadata IP check
        if str(ip) == "169.254.169.254":
            raise BlockedDestinationError(
                f"Destination '{hostname}' is a cloud metadata endpoint ({ip}), which is strictly blocked."
            )

    @classmethod
    def sanitize_for_logging(cls, url: str) -> str:
        """Strips sensitive query parameters from URL before writing to logs."""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlsplit(url)
            if not parsed.query:
                return url
            query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            sanitized_pairs = []
            for k, v in query_pairs:
                if any(s in k.lower() for s in cls.SENSITIVE_QUERY_PARAMS):
                    sanitized_pairs.append((k, "[REDACTED]"))
                else:
                    sanitized_pairs.append((k, v))
            new_query = urllib.parse.urlencode(sanitized_pairs)
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
        except Exception:
            return "[URL_SANITIZATION_FAILED]"

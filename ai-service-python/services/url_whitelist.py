"""URL whitelist and fetch URL validation for Web search security.

This module defines the fixed, code-immutable whitelist of hostname patterns
that may be fetched during Web search operations. The whitelist cannot be
modified by models, external responses, or user input.

All validation error messages are sanitized and never contain the original URL.
"""

import ipaddress
import socket
from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlparse


def _platform_getaddrinfo(host: str) -> list[tuple]:
    """Thin wrapper for testability. Resolve hostname to (family, addr) tuples."""
    results = []
    for entry in socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
        addr = entry[4][0]
        results.append((entry[0], addr))
    return results


# Production hook — can be replaced in tests via dependency injection.
_getaddrinfo = _platform_getaddrinfo


FETCH_URL_WHITELIST: dict[str, list[str]] = {
    "academic_publishers": [
        "*.nature.com",
        "*.science.org",
        "*.ieee.org",
        "ieeexplore.ieee.org",
        "*.acm.org",
        "dl.acm.org",
        "*.springer.com",
        "link.springer.com",
        "*.sciencedirect.com",
        "*.cell.com",
        "*.nejm.org",
        "*.thelancet.com",
        "*.jamanetwork.com",
        "jamanetwork.com",
        "*.apa.org",
        "*.tandfonline.com",
        "*.wiley.com",
        "*.sagepub.com",
        "journals.sagepub.com",
        "*.oxfordjournals.org",
        "academic.oup.com",
        "*.cambridge.org",
        "*.mitpressjournals.org",
        "direct.mit.edu",
        # Additional major academic publishers
        "*.pnas.org",
        "*.bmj.com",
        "*.biomedcentral.com",
        "*.plos.org",
        "journals.plos.org",
        "*.frontiersin.org",
        "*.iospress.com",
        "*.mdpi.com",
        "*.peerj.com",
        "*.elifesciences.org",
        "*.royalsocietypublishing.org",
        "*.aip.org",
        "pubs.aip.org",
        "*.aps.org",
        "journals.aps.org",
        "*.iucr.org",
        "scripts.iucr.org",
        "*.biorxiv.org",
        "*.medrxiv.org",
        "*.chemrxiv.org",
    ],
    "government": [
        "*.gov",
        "*.nih.gov",
        "*.nsf.gov",
        "*.nasa.gov",
        "*.noaa.gov",
        "*.europa.eu",
        "*.who.int",
        "*.un.org",
        "*.cdc.gov",
        "*.fda.gov",
        "*.epa.gov",
        "*.energy.gov",
        "*.uspto.gov",
        "*.census.gov",
        "*.bls.gov",
        "*.ers.usda.gov",
    ],
    "organizations": [
        "*.arxiv.org",
        "arxiv.org",
        "*.semanticscholar.org",
        "api.semanticscholar.org",
        "*.crossref.org",
        "api.crossref.org",
        "*.doi.org",
        "doi.org",
        "*.orcid.org",
        "orcid.org",
        "*.datacite.org",
        "*.zenodo.org",
        "zenodo.org",
        "*.figshare.com",
        "figshare.com",
        "*.osf.io",
        "osf.io",
    ],
    "news": [
        "*.reuters.com",
        "www.reuters.com",
        "*.apnews.com",
        "apnews.com",
        "*.bbc.com",
        "www.bbc.com",
        "*.bbc.co.uk",
        "www.bbc.co.uk",
        "*.npr.org",
        "www.npr.org",
        "*.economist.com",
        "www.economist.com",
        "*.nature.com",
        "www.nature.com",
        "*.scientificamerican.com",
        "www.scientificamerican.com",
        "*.newscientist.com",
        "www.newscientist.com",
    ],
    "encyclopedia": [
        "*.wikipedia.org",
        "*.wikibooks.org",
        "*.wikiversity.org",
        "*.wiktionary.org",
        "*.britannica.com",
        "www.britannica.com",
    ],
    "code_repos": [
        "*.github.com",
        "github.com",
        "*.gitlab.com",
        "gitlab.com",
        "*.bitbucket.org",
        "bitbucket.org",
        "*.sourceforge.net",
        "sourceforge.net",
        "pypi.org",
        "*.pypi.org",
        "cran.r-project.org",
        "bioconductor.org",
        "www.bioconductor.org",
    ],
}

# Internal/private IP ranges that must never be reachable via fetch
_PRIVATE_IPV4_NETWORKS = [
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv4Network("240.0.0.0/4"),
]

_PRIVATE_IPV6_NETWORKS = [
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("::1/128"),
]


def is_internal_ip(ip_address: str) -> bool:
    """Return True if the given IPv4 or IPv6 address is in a private/reserved range."""
    if not isinstance(ip_address, str) or not ip_address.strip():
        return False
    try:
        addr = ipaddress.ip_address(ip_address.strip())
    except ValueError:
        return False

    networks = _PRIVATE_IPV4_NETWORKS if addr.version == 4 else _PRIVATE_IPV6_NETWORKS
    return any(addr in net for net in networks)


def _match_hostname(hostname: str) -> bool:
    """Check whether hostname matches any whitelisted pattern."""
    hostname_lower = hostname.strip().lower().rstrip(".")
    if not hostname_lower:
        return False
    for patterns in FETCH_URL_WHITELIST.values():
        for pattern in patterns:
            if fnmatch(hostname_lower, pattern):
                return True
    return False


def _resolve_public_ip(hostname: str) -> None:
    """Resolve hostname and raise ValueError if any resolved IP is internal.

    DNS resolution failures (NXDOMAIN, timeout, etc.) raise ValueError
    with a sanitized message.
    """
    try:
        entries = _getaddrinfo(hostname)
    except (socket.gaierror, socket.herror, OSError):
        # Sanitize exception — never include hostname in error
        raise ValueError("DNS resolution failed for the requested host.") from None

    for _family, addr in entries:
        if is_internal_ip(addr):
            raise ValueError("The requested host resolves to an internal network address.")

    if not entries:
        raise ValueError("DNS resolution returned no addresses for the requested host.")


def validate_fetch_url(url: Any) -> str:
    """Validate a URL for Web page fetching against the security whitelist.

    Performs a strict chain of validations:
    1. Must be a non-empty string
    2. Parse with urlparse
    3. HTTPS scheme only
    4. No embedded credentials
    5. Hostname must match a whitelist pattern
    6. Raw IP addresses are rejected
    7. DNS resolution must not return any private/internal IP

    Returns the normalized (lowercase, rstrip '.') hostname on success.
    Raises ValueError with a sanitized message on any failure.
    Error messages never contain the original URL.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    try:
        parsed = urlparse(url)
    except ValueError:
        raise ValueError("URL could not be parsed.")

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are allowed for page fetching.")

    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not permitted.")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("URL must contain a valid hostname.")

    # Reject raw IP addresses (both IPv4 and IPv6)
    try:
        ipaddress.ip_address(hostname)
        raise ValueError("Direct IP address access is not permitted.")
    except ValueError:
        if "IP address" in str(ValueError.__class__.__name__):
            raise
        # Not an IP address — continue with hostname validation

    # Reject localhost
    if hostname in ("localhost", "localhost.localdomain"):
        raise ValueError("Access to localhost is not permitted.")

    # Match against whitelist
    if not _match_hostname(hostname):
        raise ValueError("The requested host is not in the fetch allowlist.")

    # DNS resolution with IP validation
    _resolve_public_ip(hostname)

    return hostname

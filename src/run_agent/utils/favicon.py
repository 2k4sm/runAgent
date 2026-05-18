"""Builds a live favicon URL from an MCP server's registrable domain.

Resolving the registrable domain (``mcp.linear.app`` -> ``linear.app``) gets
the brand's real icon even though MCP endpoints sit on a faviconless subdomain.
"""

from urllib.parse import urlparse

import tldextract

_FAVICON_SERVICE = "https://www.google.com/s2/favicons?domain={domain}&sz=64"

# `suffix_list_urls=()` pins tldextract to its bundled PSL snapshot — no runtime fetch.
_extract = tldextract.TLDExtract(suffix_list_urls=())


def favicon_url(url: str) -> str | None:
    """Return a live favicon URL for the server's brand domain, or None."""
    host = urlparse(url).hostname
    if not host:
        return None
    # Fall back to the raw host when there's no public suffix (IPs, localhost).
    domain = _extract(host).registered_domain or host
    return _FAVICON_SERVICE.format(domain=domain)

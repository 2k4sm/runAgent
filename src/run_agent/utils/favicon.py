"""Favicon URL resolution for MCP servers.

Builds a live favicon URL from a server's *registrable* domain — the icon is
fetched on-demand by the client, never stored.

MCP endpoints almost always live on a service subdomain (e.g.
``https://mcp.linear.app/mcp``) that has no favicon of its own. Resolving the
registrable domain via the Public Suffix List (``mcp.linear.app`` ->
``linear.app``) yields the brand's real icon and works for any host, including
multi-part suffixes like ``example.co.uk``.
"""

from urllib.parse import urlparse

import tldextract

# Google's favicon service reliably resolves a domain's real site icon and
# always returns a PNG, with a generic globe as its own fallback.
_FAVICON_SERVICE = "https://www.google.com/s2/favicons?domain={domain}&sz=64"

# `suffix_list_urls=()` pins tldextract to its bundled Public Suffix List
# snapshot — no network fetch at runtime, fully deterministic.
_extract = tldextract.TLDExtract(suffix_list_urls=())


def favicon_url(url: str) -> str | None:
    """Return a live favicon URL for the server's brand domain, or None."""
    host = urlparse(url).hostname
    if not host:
        return None
    # Fall back to the raw host for things with no public suffix (IPs,
    # `localhost`, internal hostnames).
    domain = _extract(host).registered_domain or host
    return _FAVICON_SERVICE.format(domain=domain)

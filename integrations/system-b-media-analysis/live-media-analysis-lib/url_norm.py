"""URL normalization for System B dedup."""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Tracking params stripped before lookup
_STRIP_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_referrer", "fbclid", "gclid", "dclid",
    "msclkid", "twclid", "igshid", "si", "feature", "ref", "ref_src",
    "ref_url", "s", "t", "_ga",
})

# Regex to extract all HTTP/HTTPS URLs from a text blob
_URL_RE = re.compile(
    r"https?://[^\s\)\]\>\"\'\`]+",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    """Return all unique HTTP/HTTPS URLs found in text, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in _URL_RE.findall(text):
        # Strip trailing punctuation that is rarely part of the URL
        raw = raw.rstrip(".,;:!?")
        if raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


def normalize_url(url: str) -> str:
    """Canonicalize a URL for stable dedup lookup.

    Steps:
    - lowercase scheme and host
    - remove default ports (80 for http, 443 for https)
    - strip known tracking query params
    - sort remaining query params for stability
    - strip fragment
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Filter and sort query params
    try:
        params = [(k, v) for k, v in parse_qsl(parsed.query) if k not in _STRIP_PARAMS]
        params.sort()
        query = urlencode(params)
    except Exception:
        query = parsed.query

    return urlunparse((scheme, netloc, parsed.path, "", query, ""))

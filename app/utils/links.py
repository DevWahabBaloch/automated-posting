"""CTA link extraction and validation.

The rules enforced here are deliberately strict because the link is published
publicly on several third-party platforms:

* the message must contain exactly one link;
* the link must be an absolute ``http``/``https`` URL;
* the host must be a public, fully-qualified domain name (no IP literals,
  ``localhost`` or single-label intranet hosts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# Anything that *looks* like a link: an explicit scheme, or a bare "www." host.
# Counting both forms prevents "https://a.com and www.b.com" from slipping
# through the "exactly one link" rule.
_LINK_CANDIDATE = re.compile(r"(?:\b[a-zA-Z][a-zA-Z0-9+.-]*://|\bwww\.)\S+", re.IGNORECASE)

# Punctuation that commonly follows a URL in prose but is not part of it.
_TRAILING_PUNCTUATION = ".,;:!?'\")]}>"

_DOMAIN_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
_TLD = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$", re.IGNORECASE)

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_URL_LENGTH = 2048


class LinkValidationError(ValueError):
    """Raised when the message's CTA link is missing, duplicated or invalid."""


@dataclass(frozen=True, slots=True)
class ExtractedLink:
    url: str
    start: int


def find_links(text: str) -> list[ExtractedLink]:
    """Return every link-like token in ``text`` with its character offset."""
    links: list[ExtractedLink] = []
    for match in _LINK_CANDIDATE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        # Keep balanced closing parentheses, e.g. Wikipedia-style URLs.
        while url.count("(") > url.count(")") and match.group(0)[len(url) :].startswith(")"):
            url += ")"
        links.append(ExtractedLink(url=url, start=match.start()))
    return links


def validate_url(url: str) -> None:
    """Raise :class:`LinkValidationError` unless ``url`` is a public web URL."""
    if len(url) > _MAX_URL_LENGTH:
        raise LinkValidationError(f"CTA link exceeds {_MAX_URL_LENGTH} characters.")

    if url.lower().startswith("www."):
        raise LinkValidationError(f"CTA link '{url}' must include a scheme, e.g. 'https://{url}'.")

    try:
        parts = urlsplit(url)
        port = parts.port  # accessing .port validates it
    except ValueError as exc:
        raise LinkValidationError(f"CTA link '{url}' is not a valid URL.") from exc

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise LinkValidationError(
            f"CTA link '{url}' must use http or https (got '{parts.scheme}')."
        )
    if parts.username or parts.password:
        raise LinkValidationError("CTA link must not contain embedded credentials.")
    if port == 0:
        raise LinkValidationError(f"CTA link '{url}' has an invalid port.")

    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise LinkValidationError(f"CTA link '{url}' is missing a host name.")
    _validate_public_hostname(host, url)


def _validate_public_hostname(host: str, url: str) -> None:
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise LinkValidationError(f"CTA link '{url}' has an invalid host name.") from exc

    labels = ascii_host.split(".")
    if len(labels) < 2:
        raise LinkValidationError(
            f"CTA link '{url}' must use a fully-qualified public domain name."
        )
    if not all(_DOMAIN_LABEL.match(label) for label in labels):
        raise LinkValidationError(f"CTA link '{url}' has an invalid host name.")
    if not _TLD.match(labels[-1]):
        # Also rejects IPv4 literals such as 192.168.0.1 (numeric "TLD").
        raise LinkValidationError(f"CTA link '{url}' must use a domain name, not an IP address.")

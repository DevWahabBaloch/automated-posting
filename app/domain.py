"""Core domain objects shared by the API, service and platform layers.

These are plain, immutable dataclasses with no framework dependencies, so the
platform adapters never need to know about FastAPI or HTTP request schemas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostContent:
    """A validated message ready to be published.

    Attributes:
        text: The full message exactly as it should be published.
        link: The single call-to-action URL contained in ``text``.
        link_start: Character offset of ``link`` within ``text``.
    """

    text: str
    link: str
    link_start: int

    @property
    def link_end(self) -> int:
        return self.link_start + len(self.link)

    @property
    def text_without_link(self) -> str:
        """The message with the CTA link removed and whitespace normalised."""
        stripped = self.text[: self.link_start] + self.text[self.link_end :]
        return " ".join(stripped.split())

    def utf8_link_span(self) -> tuple[int, int]:
        """Byte offsets of the link in the UTF-8 encoded text.

        Some protocols (e.g. Bluesky rich-text facets) index by UTF-8 bytes
        rather than by characters, which matters once a message contains
        emoji or other non-ASCII characters.
        """
        start = len(self.text[: self.link_start].encode("utf-8"))
        return start, start + len(self.link.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class PublishedPost:
    """What a platform adapter returns after a successful publish.

    Attributes:
        url: Permalink to the published content, if the platform provides one.
        public: Whether the content is visible to anonymous users, as reported
            by the platform itself (the service may additionally verify it).
    """

    url: str | None
    public: bool

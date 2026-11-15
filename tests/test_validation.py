from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import MAX_MESSAGE_LENGTH, PostingRequest
from tests.conftest import VALID_MESSAGE


@pytest.mark.parametrize(
    ("message", "expected_link"),
    [
        (VALID_MESSAGE, "https://example.com"),
        ("Read the docs at https://example.com/docs?a=1&b=2.", "https://example.com/docs?a=1&b=2"),
        ("Launch day (https://example.co.uk/launch)!", "https://example.co.uk/launch"),
        (
            "See https://en.wikipedia.org/wiki/Python_(language) now",
            "https://en.wikipedia.org/wiki/Python_(language)",
        ),
        ("Grow faster 🚀 http://shop.example.io:8080/x", "http://shop.example.io:8080/x"),
        ("   Padded message https://example.com   ", "https://example.com"),
        ("Internationalised https://bücher.example/kaufen", "https://bücher.example/kaufen"),
    ],
)
def test_valid_messages_extract_the_cta_link(message: str, expected_link: str) -> None:
    content = PostingRequest(message=message).to_content()
    assert content.link == expected_link
    assert content.text[content.link_start : content.link_end] == expected_link


def test_message_is_trimmed() -> None:
    assert PostingRequest(message="  Hi there https://example.com \n").message == (
        "Hi there https://example.com"
    )


def test_exactly_max_length_is_accepted() -> None:
    link = " https://example.com"
    message = "a" * (MAX_MESSAGE_LENGTH - len(link)) + link
    assert len(message) == MAX_MESSAGE_LENGTH
    PostingRequest(message=message)


@pytest.mark.parametrize(
    ("message", "error_fragment"),
    [
        ("", "at least 1 character"),
        ("   ", "at least 1 character"),
        (
            "x" * (MAX_MESSAGE_LENGTH - 19) + " https://example.com",
            "must not exceed 200 characters (got 201)",
        ),
        ("No link here at all", "none found"),
        ("Two https://a.example and https://b.example", "2 found"),
        ("Mixed https://a.example and www.b.example", "2 found"),
        ("Missing scheme www.example.com", "must include a scheme"),
        ("FTP is not allowed ftp://example.com/file", "must use http or https"),
        ("Local https://localhost:8000/x", "fully-qualified public domain"),
        ("IP https://192.168.0.1/admin", "not an IP address"),
        ("Creds https://user:pass@example.com", "embedded credentials"),
        ("Bad host https://exa_mple.com", "invalid host name"),
        ("Bad port https://example.com:99999", "not a valid URL"),
        ("https://example.com", "text in addition to the CTA link"),
        ("Empty host https:///path", "missing a host name"),
    ],
)
def test_invalid_messages_are_rejected(message: str, error_fragment: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message=message)
    assert error_fragment in str(exc_info.value)


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PostingRequest.model_validate({"message": VALID_MESSAGE, "platforms": ["x"]})


def test_text_without_link_and_utf8_span() -> None:
    content = PostingRequest(message="Hé 🚀 https://example.com now").to_content()
    assert content.text_without_link == "Hé 🚀 now"
    start, end = content.utf8_link_span()
    encoded = content.text.encode("utf-8")
    assert encoded[start:end].decode("utf-8") == "https://example.com"

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import VALID_MESSAGE


def test_posting_returns_per_platform_results(client: TestClient) -> None:
    response = client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.json() == {
        "success": True,
        "summary": {"total": 2, "succeeded": 1, "failed": 1},
        "results": [
            {
                "platform": "Alpha",
                "status": "success",
                "posted_url": "https://alpha.example/p/1",
                "public_access": True,
                "date": "2026-11-15",
                "time": "10:30:00",
                "error": None,
            },
            {
                "platform": "Beta",
                "status": "failed",
                "posted_url": None,
                "public_access": False,
                "date": None,
                "time": None,
                "error": "Authentication failed: HTTP 401: bad token",
            },
        ],
    }


def test_validation_errors_use_the_error_envelope(client: TestClient) -> None:
    response = client.post("/posting", json={"message": "No link in this message"})

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "error": {
            "code": "validation_error",
            "message": "Message must include exactly one CTA link (none found).",
            "details": [
                {
                    "field": "message",
                    "message": "Message must include exactly one CTA link (none found).",
                }
            ],
        },
    }


def test_missing_body_and_malformed_json(client: TestClient) -> None:
    assert client.post("/posting", json={}).status_code == 422
    malformed = client.post(
        "/posting", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "validation_error"


def test_caller_cannot_choose_platforms(client: TestClient) -> None:
    response = client.post("/posting", json={"message": VALID_MESSAGE, "platforms": ["Alpha"]})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "platforms"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "version": "1.0.0",
        "platforms_configured": 2,
        "platforms_total": 2,
    }


def test_real_registry_reports_unconfigured_platforms(settings: Settings) -> None:
    """Without credentials every platform is listed with the settings it needs."""
    with TestClient(create_app(settings)) as client:
        platforms = client.get("/platforms").json()
        posting = client.post("/posting", json={"message": VALID_MESSAGE}).json()

    assert len(platforms) >= 5
    assert {p["name"] for p in platforms} >= {"Mastodon", "Bluesky", "Telegram", "Discord"}
    assert all(not p["configured"] and p["missing_settings"] for p in platforms)
    assert posting["success"] is False
    assert all(r["error"].startswith("Platform not configured") for r in posting["results"])

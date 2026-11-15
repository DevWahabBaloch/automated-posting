# Sample run

Captured from a real local run (`uvicorn app.main:app --port 4000`) **before any credentials were configured**, so every platform reports the exact environment variables it needs. Add credentials to `.env` (see the README) to get live `success` results with real post URLs.

## Requests and responses

```console
$ curl -s -X POST http://localhost:4000/posting -H "Content-Type: application/json" -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```
```json
{
    "success": false,
    "summary": {
        "total": 7,
        "succeeded": 0,
        "failed": 7
    },
    "results": [
        {
            "platform": "Mastodon",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set MASTODON_ACCESS_TOKEN"
        },
        {
            "platform": "Bluesky",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set BLUESKY_HANDLE, BLUESKY_APP_PASSWORD"
        },
        {
            "platform": "Telegram",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
        },
        {
            "platform": "Discord",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set DISCORD_WEBHOOK_URL"
        },
        {
            "platform": "GitHub Gist",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set GITHUB_TOKEN"
        },
        {
            "platform": "DEV Community",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set DEVTO_API_KEY"
        },
        {
            "platform": "Hugging Face",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set HUGGINGFACE_TOKEN, HUGGINGFACE_REPO_ID"
        }
    ]
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "No link in this message"}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "Message must include exactly one CTA link (none found).",
        "details": [
            {
                "field": "message",
                "message": "Message must include exactly one CTA link (none found)."
            }
        ]
    }
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "Two links https://a.example and https://b.example"}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "Message must include exactly one CTA link (2 found: https://a.example, https://b.example).",
        "details": [
            {
                "field": "message",
                "message": "Message must include exactly one CTA link (2 found: https://a.example, https://b.example)."
            }
        ]
    }
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "Local link https://localhost:8000"}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "CTA link 'https://localhost:8000' must use a fully-qualified public domain name.",
        "details": [
            {
                "field": "message",
                "message": "CTA link 'https://localhost:8000' must use a fully-qualified public domain name."
            }
        ]
    }
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "Bad scheme ftp://example.com/file"}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "CTA link 'ftp://example.com/file' must use http or https (got 'ftp').",
        "details": [
            {
                "field": "message",
                "message": "CTA link 'ftp://example.com/file' must use http or https (got 'ftp')."
            }
        ]
    }
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "Check out our platform https://example.com", "platforms": ["Discord"]}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "Extra inputs are not permitted",
        "details": [
            {
                "field": "platforms",
                "message": "Extra inputs are not permitted"
            }
        ]
    }
}
```

```console
$ curl -s -X POST http://localhost:4000/posting -H 'Content-Type: application/json' -d '{"message": "aaaa…(190 chars) https://example.com"}'
```
```json
{
    "success": false,
    "error": {
        "code": "validation_error",
        "message": "Message must not exceed 200 characters (got 210).",
        "details": [
            {
                "field": "message",
                "message": "Message must not exceed 200 characters (got 210)."
            }
        ]
    }
}
```

## Server log

Each line carries the request ID (also returned in the `X-Request-ID` response header), so all platform outcomes for one `/posting` call can be correlated.

```text
INFO:     Started server process [537]
INFO:     Waiting for application startup.
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: Mastodon disabled – missing MASTODON_ACCESS_TOKEN
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: Bluesky disabled – missing BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: Telegram disabled – missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: Discord disabled – missing DISCORD_WEBHOOK_URL
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: GitHub Gist disabled – missing GITHUB_TOKEN
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: DEV Community disabled – missing DEVTO_API_KEY
2026-11-16 00:33:32,047 WARNING [-] app.platforms.registry: Hugging Face disabled – missing HUGGINGFACE_TOKEN, HUGGINGFACE_REPO_ID
2026-11-16 00:33:32,047 INFO    [-] app.platforms.registry: Platforms enabled: none
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
2026-11-16 00:33:34,725 INFO    [a91dcd84ca91] app.main: POST /posting -> 422 (4 ms)
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Mastodon: failed in 0 ms – Platform not configured: set MASTODON_ACCESS_TOKEN
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Bluesky: failed in 0 ms – Platform not configured: set BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Telegram: failed in 0 ms – Platform not configured: set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Discord: failed in 0 ms – Platform not configured: set DISCORD_WEBHOOK_URL
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: GitHub Gist: failed in 0 ms – Platform not configured: set GITHUB_TOKEN
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: DEV Community: failed in 0 ms – Platform not configured: set DEVTO_API_KEY
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Hugging Face: failed in 0 ms – Platform not configured: set HUGGINGFACE_TOKEN, HUGGINGFACE_REPO_ID
2026-11-16 00:33:34,741 INFO    [194146b79eff] app.services.posting_service: Posting run finished: 0/7 platforms succeeded
2026-11-16 00:33:34,741 INFO    [194146b79eff] app.main: POST /posting -> 200 (1 ms)
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [537]
```

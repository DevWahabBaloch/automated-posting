# Sample run

Recorded with `scripts/demo_post.sh` on 2026-11-16 03:12 PKT against a local server
(`uvicorn app.main:app --port 4000`). The `posted_url` values are live, public posts.

## Platforms

```json
[
    {
        "name": "Mastodon",
        "configured": false,
        "missing_settings": [
            "MASTODON_ACCESS_TOKEN"
        ],
        "api_docs": "https://docs.joinmastodon.org/methods/statuses/#create"
    },
    {
        "name": "Bluesky",
        "configured": true,
        "missing_settings": [],
        "api_docs": "https://docs.bsky.app/docs/advanced-guides/posts"
    },
    {
        "name": "Telegram",
        "configured": false,
        "missing_settings": [
            "TELEGRAM_BOT_TOKEN"
        ],
        "api_docs": "https://core.telegram.org/bots/api#sendmessage"
    },
    {
        "name": "Discord",
        "configured": true,
        "missing_settings": [],
        "api_docs": "https://discord.com/developers/docs/resources/webhook#execute-webhook"
    },
    {
        "name": "GitHub Gist",
        "configured": true,
        "missing_settings": [],
        "api_docs": "https://docs.github.com/en/rest/gists/gists#create-a-gist"
    },
    {
        "name": "DEV Community",
        "configured": true,
        "missing_settings": [],
        "api_docs": "https://developers.forem.com/api/v1#tag/articles/operation/createArticle"
    },
    {
        "name": "Hugging Face",
        "configured": true,
        "missing_settings": [],
        "api_docs": "https://huggingface.co/docs/hub/api"
    }
]
```

## Publishing a message

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "Automated multi-platform posting with FastAPI: one API call, many platforms. https://github.com/DevWahabBaloch/automated-posting"}'
```

```json
{
    "success": true,
    "summary": {
        "total": 7,
        "succeeded": 5,
        "failed": 2
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
            "status": "success",
            "posted_url": "https://bsky.app/profile/wahabbalochk.bsky.social/post/3n2ezvdriu22t",
            "public_access": true,
            "date": "2026-11-16",
            "time": "03:12:56",
            "error": null
        },
        {
            "platform": "Telegram",
            "status": "failed",
            "posted_url": null,
            "public_access": false,
            "date": null,
            "time": null,
            "error": "Platform not configured: set TELEGRAM_BOT_TOKEN"
        },
        {
            "platform": "Discord",
            "status": "success",
            "posted_url": "https://discord.com/channels/1571625595731968040/1571625596176572498/1571649227971494123",
            "public_access": false,
            "date": "2026-11-16",
            "time": "03:12:56",
            "error": null
        },
        {
            "platform": "GitHub Gist",
            "status": "success",
            "posted_url": "https://gist.github.com/DevWahabBaloch/1c238835926edb86304b96b7136e56e8",
            "public_access": true,
            "date": "2026-11-16",
            "time": "03:12:57",
            "error": null
        },
        {
            "platform": "DEV Community",
            "status": "success",
            "posted_url": "https://dev.to/devwahabbaloch/automated-multi-platform-posting-with-fastapi-one-api-call-many-platforms-1kfd",
            "public_access": true,
            "date": "2026-11-16",
            "time": "03:12:55",
            "error": null
        },
        {
            "platform": "Hugging Face",
            "status": "success",
            "posted_url": "https://huggingface.co/datasets/wahabbaloch/announcements/blob/main/posts/2026/11/15/221255-797539ec.md",
            "public_access": true,
            "date": "2026-11-16",
            "time": "03:12:55",
            "error": null
        }
    ]
}
```

## Validation errors

### No CTA link

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "No link in this message"}'
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

### More than one link

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "Two links https://a.example and https://b.example"}'
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

### Non-public host

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "Local link https://localhost:8000"}'
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

### Unsupported scheme

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "Bad scheme ftp://example.com/file"}'
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

### Caller tries to choose platforms

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "Our platform https://example.com", "platforms": ["Discord"]}'
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

### Over 200 characters

```bash
curl -X POST http://localhost:4000/posting -H "Content-Type: application/json" \
  -d '{"message": "aaaa…(190 characters)… https://example.com"}'
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


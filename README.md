# Automated Multi-Platform Posting API

[![CI](https://github.com/DevWahabBaloch/automated-posting/actions/workflows/ci.yml/badge.svg)](https://github.com/DevWahabBaloch/automated-posting/actions/workflows/ci.yml)

A FastAPI service that validates a short message with a single call-to-action (CTA) link and publishes it **concurrently** to **7 third-party platforms** through their official APIs. It returns a per-platform report with the post URL, whether the post is publicly accessible, and the posting date and time.

| | |
|---|---|
| **Stack** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, HTTPX |
| **Platforms** | Mastodon · Bluesky · Telegram · Discord · GitHub Gist · DEV Community · Hugging Face |
| **Quality gates** | 68 tests (pytest + respx) · `ruff` lint/format · `mypy --strict` · GitHub Actions CI on 3.11–3.14 |

---

## Contents

1. [Quick start](#quick-start)
2. [API](#api)
3. [Platform research and integrations](#platform-research-and-integrations)
4. [Live verification](#live-verification)
5. [Architecture](#architecture)
6. [Key engineering decisions](#key-engineering-decisions)
7. [Configuration](#configuration)
8. [Testing and quality](#testing-and-quality)
9. [Adding a new platform](#adding-a-new-platform)
10. [Limitations and next steps](#limitations-and-next-steps)

---

## Quick start

```bash
git clone https://github.com/DevWahabBaloch/automated-posting.git
cd automated-posting

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                    # add -dev for tests & tooling

cp .env.example .env                               # then fill in credentials
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

* Swagger UI: <http://localhost:4000/docs>
* ReDoc: <http://localhost:4000/redoc>

The app starts with **no** credentials. Every platform is still listed in the response, with the exact environment variables it is missing, so a reviewer can run it immediately.

**VS Code**

Open the folder in VS Code and install the recommended extensions when prompted. Then use **Terminal → Run Task…**:

1. **Setup: create .venv and install dependencies** creates `.venv` with Python 3.11+ and copies `.env.example` to `.env`.
2. **Run API (http://localhost:4000/docs)** starts Uvicorn with auto-reload. **Stop API (free port 4000)** stops it. Alternatively, press **F5** and choose *Run API (port 4000)* to debug with breakpoints.
3. **Quality checks: lint + types + tests** runs ruff, mypy and pytest.
4. **Demo: publish a real post and record docs/sample-run.md** posts one message through the running API to every configured platform and saves the request, the response and validation examples as evidence.

**Docker**

```bash
docker build -t automated-posting .
docker run --rm -p 4000:4000 --env-file .env automated-posting
```

---

## API

### `POST /posting`

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```

**200 OK.** The message was processed, and each platform's outcome is in `results`:

```json
{
  "success": true,
  "summary": { "total": 7, "succeeded": 6, "failed": 1 },
  "results": [
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@acme/113512345678901234",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "success",
      "posted_url": "https://discord.com/channels/1234/5678/9012",
      "public_access": false,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Telegram",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Authentication failed: HTTP 401: Unauthorized"
    }
  ]
}
```

(Shortened example. [`docs/sample-run.md`](docs/sample-run.md) has real captured output.)

| Field | Meaning |
|---|---|
| `success` | `true` if the message was published to **at least one** platform |
| `summary` | Counts of total, succeeded and failed platforms |
| `results[].platform` | Platform name |
| `results[].status` | `success` or `failed` |
| `results[].posted_url` | Permalink of the published content |
| `results[].public_access` | Whether anonymous users can view it (see [Public access](#public-access-is-verified-not-assumed)) |
| `results[].date` / `time` | When the platform confirmed the post, in the configured `TIMEZONE` |
| `results[].error` | Categorised, human-readable failure reason |

**422 Unprocessable Content.** The request is invalid. Every error uses the same envelope:

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "Message must include exactly one CTA link (2 found: https://a.example, https://b.example).",
    "details": [
      { "field": "message", "message": "Message must include exactly one CTA link (2 found: https://a.example, https://b.example)." }
    ]
  }
}
```

### Validation rules

| Rule | Example of a rejected message |
|---|---|
| Not empty (whitespace is trimmed first) | `"   "` |
| At most **200** characters | 201+ characters |
| **Exactly one** link. Bare `www.` hosts count as links, so they cannot slip past the rule | `"a https://a.com and www.b.com"` |
| `http` / `https` only | `ftp://example.com` |
| Scheme required | `www.example.com` |
| Public, fully-qualified domain (no `localhost`, single-label hosts or IP literals) | `https://localhost:8000`, `https://192.168.0.1` |
| No embedded credentials, valid port, valid host labels (IDN supported) | `https://user:pass@x.com`, `https://x.com:99999` |
| Text in addition to the link | `"https://example.com"` |
| No extra fields. Platform selection is internal | `{"message": "…", "platforms": ["Discord"]}` |

Trailing punctuation is not treated as part of the URL (`…see https://x.com/a.` → `https://x.com/a`), and balanced parentheses are kept (`https://en.wikipedia.org/wiki/Python_(language)`).

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /platforms` | Each platform's configuration status, missing variables and the API docs used |
| `GET /health` | Liveness check plus a count of configured platforms |

Every response carries an `X-Request-ID` header, which is also attached to every log line (see [observability](#observability)).

---

## Platform research and integrations

### Selection criteria

1. An **official, documented REST API** that can create public content programmatically.
2. **Self-serve credentials**: no paid tier, partner program or multi-week app review.
3. Returns a **stable permalink**, so `posted_url` and `public_access` are meaningful.
4. Fits a short text post with a link.

### Integrated platforms

| Platform | Endpoint | Auth | Permalink returned | Public? | Official docs |
|---|---|---|---|---|---|
| **Mastodon** | `POST /api/v1/statuses` | OAuth bearer token | `status.url` | `visibility == "public"` | [docs](https://docs.joinmastodon.org/methods/statuses/#create) |
| **Bluesky** | `com.atproto.server.createSession` → `com.atproto.repo.createRecord` | App password → JWT | `bsky.app/profile/{handle}/post/{rkey}` built from the AT-URI | Yes | [docs](https://docs.bsky.app/docs/advanced-guides/posts) |
| **Telegram** | Bot API `sendMessage` | Bot token | `t.me/{channel}/{message_id}` | Yes for public channels | [docs](https://core.telegram.org/bots/api#sendmessage) |
| **Discord** | Execute Webhook (`?wait=true`) | Webhook URL | `discord.com/channels/{guild}/{channel}/{id}` | **No**, members only | [docs](https://discord.com/developers/docs/resources/webhook#execute-webhook) |
| **GitHub Gist** | `POST /gists` | PAT (`gist` scope) | `html_url` | `gist.public` | [docs](https://docs.github.com/en/rest/gists/gists#create-a-gist) |
| **DEV Community** | Forem `POST /api/articles` | `api-key` header | `article.url` | `article.published` | [docs](https://developers.forem.com/api/v1#tag/articles/operation/createArticle) |
| **Hugging Face** | Hub commit API `POST /api/{type}s/{repo}/commit/main` (NDJSON) | Bearer token (write) | `huggingface.co/{repo}/blob/main/{path}` | `repo.private == false` | [docs](https://huggingface.co/docs/hub/api) |

### Platform-specific details handled

* **Bluesky** does not auto-link URLs in post text. Links must be declared as *rich-text facets* addressed by **UTF-8 byte offsets**, not character offsets. The adapter computes these correctly, so messages containing emoji or accented characters still produce a clickable link (covered by a test). `createSession` is heavily rate-limited, so the session is cached and refreshed only when the PDS returns `ExpiredToken`.
* **Telegram** permalinks depend on the chat type. Public channels get `t.me/{username}/{id}` (public). Private channels get `t.me/c/{id}/{msg}` (members only). Private chats have no permalink.
* **Discord** posts send `allowed_mentions: {"parse": []}`, so a message containing `@everyone` cannot ping a whole server. The webhook URL is checked to be a real `discord.com` host. The guild ID needed for the jump link is resolved once and cached.
* **Mastodon** requests carry an `Idempotency-Key`, so a connection-level retry can never create a duplicate status.
* **DEV Community** requires a title. It is derived from the message's first sentence (link removed, word-boundary truncation), and tags are normalised to Forem's rules (lowercase alphanumeric, at most 4).
* **Hugging Face** has no "status update" endpoint. Each post is committed as a Markdown file with front matter to a public dataset repo using the Hub's commit API. Repo metadata is fetched *before* the commit. This validates the token early and reports private repos as non-public.

### On "LLM platforms"

The brief mentions *supported LLM platforms*. Model APIs (OpenAI, Anthropic, Gemini and others) *generate* text but have no feature that publishes content at a public URL, so they cannot satisfy the "posted URL / public access" contract. **Hugging Face** is the public publishing hub of the LLM ecosystem, and it was integrated for that reason. An LLM could still be added later as a *pre-processing* step, for example to adapt the message's tone per platform, behind the same interface.

### Considered and rejected

| Platform | Why it was not used |
|---|---|
| X / Twitter | Write access to the API is limited to paid or restricted tiers |
| LinkedIn | Needs an app with the *Share on LinkedIn* product and an interactive 3-legged OAuth flow |
| Reddit | New API access now requires approval, and subreddit rules often forbid self-promotion |
| Facebook / Instagram | Graph API publishing requires Meta app review and a business page or account |
| Medium | Publishing API is deprecated, and new integration tokens are no longer issued |
| Slack (webhooks) | Posts to a private workspace with no public permalink |

## Live verification

The integrations were run against the real platforms with `scripts/demo_post.sh` (VS Code task **Demo**). Full request and response: [`docs/sample-run.md`](docs/sample-run.md).

| Platform | Result | Published content |
|---|---|---|
| Bluesky | ✅ public | [bsky.app/profile/wahabbalochk.bsky.social/post/3n2ezvdriu22t](https://bsky.app/profile/wahabbalochk.bsky.social/post/3n2ezvdriu22t) |
| GitHub Gist | ✅ public | [gist.github.com/DevWahabBaloch/1c2388…](https://gist.github.com/DevWahabBaloch/1c238835926edb86304b96b7136e56e8) |
| DEV Community | ✅ public | [dev.to/devwahabbaloch/automated-multi-platform-posting…](https://dev.to/devwahabbaloch/automated-multi-platform-posting-with-fastapi-one-api-call-many-platforms-1kfd) |
| Hugging Face | ✅ public | [huggingface.co/datasets/wahabbaloch/announcements](https://huggingface.co/datasets/wahabbaloch/announcements/blob/main/posts/2026/11/15/221255-797539ec.md) |
| Discord | ✅ members-only | Posted to a server channel; Discord messages are visible only to server members, so `public_access` is `false` |
| Mastodon | ⚪ not configured | Implemented and tested against the API contract. Live run pending: sign-ups on mastodon.social are blocked from the network this was run on. Any Mastodon server works via `MASTODON_BASE_URL` |
| Telegram | ⚪ not configured | Implemented and tested against the API contract. Telegram is not accessible from the region this was run in |

Unconfigured platforms are still reported in every response with the exact variables they need, so enabling one is a configuration change, not a code change.

---

## Architecture

```text
            ┌──────────────────────────────────────────────────────────┐
 HTTP  ───► │ API layer        app/api/        routes, DI, error envelope │
            │   PostingRequest (validation) ──► PostContent (domain)    │
            ├──────────────────────────────────────────────────────────┤
            │ Service layer    app/services/   PostingService            │
            │   fan-out with asyncio.gather · per-platform timeout      │
            │   exception boundary · public-access verification         │
            ├──────────────────────────────────────────────────────────┤
            │ Platform layer   app/platforms/  Platform (ABC)            │
            │   Mastodon  Bluesky  Telegram  Discord  Gist  DEV  HF     │
            │   UnconfiguredPlatform (null object) · registry           │
            ├──────────────────────────────────────────────────────────┤
            │ Transport        PlatformHttpClient                        │
            │   pooled httpx.AsyncClient · safe retries · error mapping │
            └──────────────────────────────────────────────────────────┘
```

```text
automated-posting/
├── app/
│   ├── main.py                  # app factory, lifespan (shared HTTP client), middleware
│   ├── config.py                # typed settings from env / .env (SecretStr for credentials)
│   ├── schemas.py               # request validation + response models
│   ├── domain.py                # framework-free domain objects (PostContent, PublishedPost)
│   ├── logging_config.py        # logging with request-ID correlation
│   ├── api/
│   │   ├── routes.py            # POST /posting, GET /platforms, GET /health
│   │   ├── dependencies.py      # DI providers
│   │   └── errors.py            # uniform error envelope
│   ├── platforms/
│   │   ├── base.py              # Platform ABC + UnconfiguredPlatform null object
│   │   ├── registry.py          # the single place that chooses platforms
│   │   ├── http.py              # retries, backoff, HTTP → exception mapping
│   │   ├── exceptions.py        # typed failure hierarchy
│   │   ├── mastodon.py  bluesky.py  telegram.py  discord.py
│   │   └── github_gist.py  devto.py  huggingface.py
│   ├── services/
│   │   └── posting_service.py   # concurrent, isolated orchestration
│   └── utils/
│       └── links.py             # CTA link extraction and URL validation
├── tests/                       # 68 tests: validation, service, adapters, API
├── docs/sample-run.md           # captured requests, responses and logs
├── .github/workflows/ci.yml     # lint + types + tests on Python 3.11–3.14
├── .env.example  requirements.txt  requirements-dev.txt
├── Dockerfile  Makefile  pyproject.toml
```

**SOLID in practice**

* **Single responsibility.** Validation, orchestration, transport and each provider's protocol each live in their own module.
* **Open/closed.** A new platform is one new class plus one line in the registry. No existing code changes.
* **Liskov substitution / null object.** `UnconfiguredPlatform` is a drop-in `Platform`, so the service has no `if configured` branches.
* **Dependency inversion.** `PostingService` depends on the `Platform` abstraction, and its collaborators (platforms, clock, access checker) are injected. That is why it can be tested without HTTP or wall-clock time.

---

## Key engineering decisions

### Failure isolation and concurrency
Each platform runs in its own coroutine via `asyncio.gather`, with its own `asyncio.timeout` and its own exception boundary. A platform that errors, times out or raises an unexpected exception produces a `failed` result, and **the others are unaffected**. Total latency is roughly that of the slowest platform, not the sum of all of them (asserted in tests).

### Retries that cannot double-post
Publishing is **not idempotent**. Retrying a `POST` that timed out or returned 5xx may publish the same message twice. Retries therefore happen only when the provider provably did *not* process the request:
* the connection could not be established (`ConnectError` / `ConnectTimeout`), and
* `429 Too Many Requests` (with exponential backoff and jitter, honouring `Retry-After` up to a cap).

Read timeouts and 5xx responses fail fast and are reported.

### Typed error mapping
`PlatformHttpClient` maps HTTP outcomes to a small exception hierarchy (`PlatformAuthError`, `PlatformRateLimitError`, `PlatformRequestError`, `PlatformUnavailableError`, `PlatformResponseError`, `PlatformNotConfiguredError`). It pulls the provider's own message from varied payload shapes (`description`, `message`, `error`, `errors[]` and others). Expected errors are returned to the caller. **Unexpected exceptions are logged with a traceback but reported only as `"Internal error while publishing"`**, so internals and secrets never reach API clients.

### Public access is verified, not assumed
Each adapter reports what the platform itself says (Mastodon `visibility`, Gist `public`, Hugging Face `private`, Telegram chat type, Discord members-only). When `VERIFY_PUBLIC_ACCESS=true`, the service also fetches the URL **anonymously**. The probe can only *downgrade* a claim (for example 401/404 → `false`). An inconclusive probe (network error, 5xx, 429) keeps the platform's claim, so the API never reports false negatives because of a flaky network.

### Side-effect ordering
Auxiliary lookups (the Discord guild ID, Hugging Face repo metadata) run **before** the write. If they ran afterwards, a failed lookup could turn an already-published post into a reported failure, and a client retry would then duplicate it.

### Status codes
`/posting` returns **200** whenever the request was valid and processed, even if some or all platforms failed. Per-platform results are business outcomes, not transport errors, and `success` plus `summary` make them explicit. **422** is reserved for invalid input.

### Secret hygiene
* Credentials are read only from the environment, typed as `SecretStr` (masked in `repr` and logs), and `.env` is git-ignored.
* `httpx` request logging is turned down, because Telegram bot tokens and Discord webhook tokens appear **in request URLs**.
* `.env.example` documents every variable without real values.

### Observability
A middleware assigns each request an ID (or reuses an incoming `X-Request-ID`). The ID goes into a `ContextVar`, appears on every log line and is returned as a header, so all platform outcomes of one posting run can be correlated:

```text
2026-11-16 00:33:34,740 WARNING [194146b79eff] app.services.posting_service: Discord: failed in 0 ms – Platform not configured: set DISCORD_WEBHOOK_URL
2026-11-16 00:33:34,741 INFO    [194146b79eff] app.services.posting_service: Posting run finished: 0/7 platforms succeeded
2026-11-16 00:33:34,741 INFO    [194146b79eff] app.main: POST /posting -> 200 (1 ms)
```

### Resource management
One pooled `httpx.AsyncClient` is created in the FastAPI **lifespan** and shared by every adapter. That gives connection reuse and keep-alive, bounded pool limits and a clean shutdown, instead of a new client per request.

---

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)). A platform is enabled automatically once its required variables are set.

| Platform | Required variables | How to obtain |
|---|---|---|
| Mastodon | `MASTODON_ACCESS_TOKEN` (`MASTODON_BASE_URL` defaults to mastodon.social) | Preferences → Development → New application, scope `write:statuses` |
| Bluesky | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Settings → Privacy and security → App passwords |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (`@public_channel`) | @BotFather → `/newbot`, then add the bot as an admin of a public channel |
| Discord | `DISCORD_WEBHOOK_URL` | Server Settings → Integrations → Webhooks |
| GitHub Gist | `GITHUB_TOKEN` | Fine-grained PAT with *Gists: read & write* (or a classic PAT with `gist`) |
| DEV Community | `DEVTO_API_KEY` (`DEVTO_TAGS` optional) | dev.to → Settings → Extensions → API keys |
| Hugging Face | `HUGGINGFACE_TOKEN`, `HUGGINGFACE_REPO_ID` (`HUGGINGFACE_REPO_TYPE` = dataset) | huggingface.co/settings/tokens (write). Create the repo first |

General settings: `TIMEZONE` (IANA name, default `UTC`), `HTTP_TIMEOUT_SECONDS`, `PLATFORM_TIMEOUT_SECONDS`, `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_SECONDS`, `VERIFY_PUBLIC_ACCESS`, `LOG_LEVEL`. Settings are validated at startup. For example, an unknown timezone or a non-Discord webhook host is reported clearly instead of failing at request time.

---

## Testing and quality

```bash
pip install -r requirements-dev.txt
make check          # ruff lint + format check, mypy --strict, pytest
# or individually:
pytest              # 68 tests, < 1 s
ruff check app tests
mypy app
```

| Suite | What it covers |
|---|---|
| `test_validation.py` | Every validation rule: boundary length, multiple and bare links, schemes, localhost and IPs, credentials, ports, IDN, punctuation, parentheses, UTF-8 offsets |
| `test_posting_service.py` | Failure isolation, generic reporting of unexpected errors, timeouts, real concurrency, timezone handling, public-access probe semantics |
| `test_platforms.py` | Each adapter against a mocked provider API (`respx`): request shape, headers, auth, permalinks, Bluesky facets and session refresh, Discord mention safety, Telegram chat types, Hugging Face NDJSON, plus retry and error mapping |
| `test_api.py` | Exact response contract, error envelope, malformed JSON, forbidden `platforms` field, 404 envelope, real registry with no credentials |

No test touches the network. CI runs the full gate on Python 3.11, 3.12, 3.13 and 3.14.

---

## Adding a new platform

```python
# app/platforms/tumblr.py
class TumblrPlatform(Platform):
    name = "Tumblr"
    docs_url = "https://www.tumblr.com/docs/en/api/v2"
    required_settings = ("tumblr_token", "tumblr_blog")

    @classmethod
    def from_settings(cls, settings, http):
        return cls(http, token=..., blog=...)

    async def publish(self, post: PostContent) -> PublishedPost:
        data = await self._http.request_json("POST", ..., json=...)
        return PublishedPost(url=data["..."], public=True)
```

Then add the two settings to `Settings`, append `TumblrPlatform` to `PLATFORM_TYPES` in `registry.py`, and add a `respx` contract test. Retries, timeouts, error mapping, isolation, public-access checks and reporting all apply automatically.

---

## Limitations and next steps

* **Client-side idempotency.** Accept an `Idempotency-Key` header and persist results, so a client retry of `/posting` returns the first run's results instead of posting again.
* **Asynchronous jobs.** For many platforms or slow providers, return `202 Accepted` with a job ID and process posts through a queue (Celery, ARQ or a cloud queue) with a status endpoint.
* **Persistence and audit trail.** Store each run and its per-platform results.
* **Per-platform content adaptation.** Add hashtags, link cards (Bluesky `app.bsky.embed.external`) or LLM-assisted rewrites behind a `ContentFormatter` strategy.
* **Metrics.** Prometheus counters and histograms per platform for success rate and latency.
* **Telegram / Discord link previews** depend on the target site's Open Graph tags. That is outside this service's control.

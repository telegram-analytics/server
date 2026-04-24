# tgram-analytics · server

> Self-hosted, privacy-first analytics controlled entirely through a Telegram bot.
> No dashboard. No third parties. Just Telegram.

[![CI](https://github.com/tgram-analytics/server/actions/workflows/ci.yml/badge.svg)](https://github.com/tgram-analytics/server/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)

---

## Quick start

### 1 — Prerequisites

- Docker & Docker Compose v2
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram chat ID (message [@userinfobot](https://t.me/userinfobot) to find it)

### 2 — Configure

```bash
git clone https://github.com/tgram-analytics/server.git
cd server
cp .env.example .env
# Edit .env and fill in TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, and SECRET_KEY
```

Generate a `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3 — Run

```bash
docker compose up
```

The server starts on `http://localhost:8000`.
Verify it's running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4 — Add your first project

Open Telegram and message your bot:

```
/add myapp.com
```

The bot replies with your API key (`proj_xxxx`) and a ready-to-use JS snippet.

---

## Usage

### Track events (REST API)

```bash
curl -X POST https://your-server.com/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "proj_xxxxxxxxxxxx",
    "event": "purchase",
    "session_id": "uuid-here",
    "properties": {"amount": 49, "plan": "pro"}
  }'
```

### JavaScript SDK

```html
<script src="https://your-server.com/sdk/tga.min.js"></script>
<script>
  TGA.init('proj_xxxxxxxxxxxx', { serverUrl: 'https://your-server.com' });
  TGA.track('purchase', { amount: 49 });
</script>
```

### Flutter SDK

```dart
await TgAnalytics.init(
  apiKey: 'proj_xxxxxxxxxxxx',
  serverUrl: 'https://your-server.com',
);
await TgAnalytics.track('purchase', properties: {'amount': 49});
```

### Browser vs. server calls

One `proj_` API key handles both: embed it in your frontend **and** use it from
your backend — events land in the same project.

The **domain allowlist** (set via `/settings`) is a browser-only guard against
abuse of the public key embedded in your JS bundle. It works like this:

| Caller | `Origin` header | Behavior |
|---|---|---|
| Browser on allowed host | `https://myapp.com` | ✅ accepted |
| Browser on other host | `https://evil.com` | ❌ 403 |
| Backend SDK (Python/Node/curl) | *(absent)* | ✅ accepted — API key auth only |
| Sandboxed iframe / `file://` | `null` | ❌ 403 when allowlist is set |

Allowlist entries support bare hosts (`myapp.com`), full URLs, and wildcards
(`*.myapp.com` matches any subdomain, but not the apex — add both explicitly
if you need `myapp.com` and `www.myapp.com`).

An empty allowlist allows all origins.

### Bot commands

| Command | Description |
|---|---|
| `/start` | Greet the bot and see available commands |
| `/add <name>` | Create a new project and get its API key |
| `/projects` | List all projects |
| `/report <event>` | Get a chart for an event (with period/granularity controls) |
| `/settings` | Configure retention and domain allowlist |
| `/help` | Show this command reference |

---

## Development

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env   # edit values
```

### Run locally (with Docker DB)

```bash
make dev-db          # start postgres + quickchart in Docker
make migrate         # apply migrations
uvicorn app.main:app --reload
```

### Tests

```bash
make test            # run all tests
make test-cov        # with coverage report
```

### Code quality

```bash
make lint            # ruff linter
make typecheck       # mypy
make check           # both
```

### Database migrations

```bash
# Create a new migration
make migration MSG="add users table"

# Apply migrations
make migrate

# Roll back one step
make downgrade
```

### Database requirements

- **PostgreSQL ≥ 15**. Required for reliable core `gen_random_uuid()` and
  JSONB features used by newer migrations.
- The `pgcrypto` extension is enabled automatically by migration `0004`. On
  managed Postgres this just works; on self-managed Postgres the role running
  the first migration needs superuser (or a DBA must pre-enable the extension).

---

## Architecture

```
app/
├── api/          REST endpoints (track, pageview, projects)
├── bot/          Telegram bot handlers and conversation state
├── core/         Config, database engine, security utilities
├── models/       SQLAlchemy ORM models
├── schemas/      Pydantic request/response schemas
└── services/     Analytics, charts, scheduler, alerts
```

See [PROJECT.md](../PROJECT.md) for full architecture documentation.

---

## Deployment

### VPS (Docker Compose)

```bash
cp .env.example .env
# Fill in all values, especially WEBHOOK_BASE_URL=https://your-domain.com
docker compose up -d
```

Point your reverse proxy (Nginx/Caddy) at port `8000`.

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

Add the environment variables from `.env.example` in the Railway dashboard.

---

## Contributing

Contributions are welcome. Please open an issue before submitting a pull request for anything beyond a typo or small bug fix, so we can discuss the approach first.

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Write tests alongside your code
4. Ensure `make check` and `make test` pass
5. Open a pull request

Please follow the existing code style (ruff-enforced) and keep PRs focused.

---

## Disclaimer
> This project is an independent open-source project, not affiliated
> with or endorsed by Telegram Messenger LLP or its parent company in any way.
> "Telegram" is a trademark of Telegram Messenger LLP.

## License

[MIT](LICENSE) — see the file for details.

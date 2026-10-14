# URL Shortener

A FastAPI URL shortener with SQLAlchemy/MySQL persistence, session-scoped guest creation, JWT cookie authentication, Redis destination caching and in-process background click analytics.

## Features

- Public URL creation returns **200 HTML**, including idempotent replay results.
- Logged-in users can list, view, activate and deactivate their own URLs and view analytics.
- Guest links have nullable user ownership and a random signed-session identity; no artificial user ID 0 is required. Guest links are public to redirect, but cannot be managed through authenticated user endpoints.
- Database-generated BIGINT IDs are Base62 encoded. Allocation is safe across application workers that share this MySQL database; it does not coordinate independently writable databases.
- A unique owner/URL SHA256 fingerprint prevents duplicate destinations per owner, including concurrent creation. Different owners receive separate links.
- A transactional database idempotency ledger binds each UUID to an owner and canonical destination for 300 seconds. Retries return the original result; conflicting payloads return 409. Concurrent matching requests wait for the winning transaction. Database lock timeouts/deadlocks receive bounded retries, then 503.
- Redis caches destination metadata for 3600 seconds. Every redirect first reads committed database state, so stale cache entries cannot bypass deactivation. Redis errors fall back to the database; cache deletion failure does not undo a committed deactivation. This favors correctness over eliminating the database read on cache hits.
- Successful public redirects return 307. Unknown/inactive links return 404. Every successful GET schedules an independent click transaction; click row and counter increment commit together.
- Forms and JSON authentication requests require a session CSRF token. JWT and session cookies are HttpOnly and Secure by default. HS256 is the only supported JWT algorithm; cookie expiry follows configured JWT lifetime.

## Architecture

```mermaid
flowchart TD
    Browser["Browser"] --> App["FastAPI: forms, auth, redirects"]
    App --> ORM["SQLAlchemy"]
    ORM --> DB["MySQL: URLs, owners, idempotency"]
    App --> Cache["Redis: optional destination cache"]
    App --> Tasks["BackgroundTasks: click event"]
    Tasks --> DB
```

Redis is not an idempotency authority or a background-task broker. BackgroundTasks run inside the web process and are not durable across process termination. An in-flight redirect already authorized before deactivation may complete; subsequent database reads observe the inactive flag. The unused legacy Celery module is not used by the application.

## Setup

Python 3.11+ and a provisioned MySQL database are required. Redis is optional for availability, but recommended for exercising the cache behavior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, configure database/Redis URLs and separate strong JWT/session secrets. Use `COOKIE_SECURE=false` only for local HTTP development; leave it true on HTTPS deployments. `SHORTENER_DOMAIN` controls self-link rejection. The URL library canonicalizes host/scheme, while meaningful path slashes, query and fragments are preserved. Usernames support ASCII letters/digits plus single `_` and `-` separators, starting and ending in letters/digits.

For a **new, empty database**:

```bash
alembic upgrade head
uvicorn myapp.main:app --reload
```

For an **existing database**, first follow [the migration instructions](docs/approved-decisions.md#existing-database-migration). Do not run the fresh baseline against existing tables. The app no longer creates a missing MySQL database with administrative credentials. Start from the repository root so template/static paths resolve.

Open `http://127.0.0.1:8000/` locally. To call form/JSON mutation endpoints directly, first GET `/urls/create` or `/auth/login`, retain the session cookie, then send its CSRF token as `csrf_token` in forms or `X-CSRF-Token` in JSON requests. Registration uses MX-domain validation; it does not prove a mailbox exists. Login accepts username or email.

Expired idempotency ledger records can be cleaned in a maintenance window:

```bash
python -m myapp.maintenance
```

Expiry is enforced even before cleanup. Results already committed remain in URL storage.

## Tests

```bash
python -m pip install -r requirements-dev.txt
pytest -q
ruff check myapp tests migrations
```

The default suite uses disposable SQLite files, fake Redis and stubbed DNS. MySQL and real Redis integration tests require isolated services:

```bash
# Use only a disposable MySQL server; tests create/drop per-test schemas.
# The configured database name must start with url_shortener_test.
# The test user needs CREATE/DROP DATABASE rights on that disposable server.
export TEST_MYSQL_URL='mysql+pymysql://root:test-password@127.0.0.1:3306/url_shortener_test'
export TEST_REDIS_URL='redis://127.0.0.1:6379/0'
pytest -q
```

PowerShell uses `$env:TEST_MYSQL_URL=...` and `$env:TEST_REDIS_URL=...`. Never point tests at production services. The GitHub Actions workflow runs both default and real-service suites. [Approved decisions and verification](docs/approved-decisions.md) describe the implemented behavior and remaining limitations.

## License

This repository currently has no license file.

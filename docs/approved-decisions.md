# Approved test-plan decisions

The user approved all seven decisions in the 14 October 2026 repository review, explicitly keeping creation at **HTTP 200**. Implementation is based on commit `dd289bf1c4dd3e0e52631d8b571993c7bb5924f4`.

| Decision | Implemented behavior |
| --- | --- |
| 1. Guest persistence | Nullable user FK; random signed-session guest identity in `owner_key`. Existing user ID 0 mappings become legacy guests, without changing public short codes. |
| 2. Creation response | New creation and replay return 200 HTML with the mapping. Fresh form UUID enables the next independent operation. No PRG change. |
| 3. Idempotency | Transactional database ledger, owner/session scope, SHA256 payload binding, 300-second expiry and atomic unique-key acquisition; matching replay returns original mapping, conflicting payload returns 409. Redis outage cannot disable it. |
| 4. Analytics | Foreign/missing mapping returns 404; own mapping without clicks returns 200 with empty state. |
| 5. Redis outages/invalidation | Database fallback; deactivation commits before best-effort deletion. Every redirect checks DB activation, including a warm cache, so failed deletion/in-flight cache refill cannot authorize later requests. |
| 6. Input/auth/session policy | Preserve path/query/fragment semantics; allow ASCII `_`/`-` username separators; reject malformed JWT claims and expiry equality; HS256 only; matching cookie/JWT lifetimes; explicit CSRF verification with login token rotation, secure cookie default and HTML escaping. Stale auth cookie receives controlled 401 or HTML login redirect. |
| 7. ID generation | Database BIGINT auto-increment plus Base62; no per-request/per-worker Snowflake instance. Database uniqueness supports shared-DB workers; bounded retries handle legacy/custom short-code collisions. |

## Existing database migration

These steps are for the previous repository schema. They were exercised on disposable MySQL with pre-existing user/guest mappings and click records. No live database was accessed or migrated.

1. Back up and verify the database. Pause application writes while performing this schema migration; MySQL DDL is not fully transactional.
2. Install the new requirements. Confirm the `.env` points at the intended database.
3. For an existing **legacy database with no Alembic revision**, run `alembic stamp 0001` once. This records the old schema version; it does not create or alter tables.
4. Run `alembic upgrade head`.
5. Start the application and check an existing short link and owner analytics.

For a new empty database, run only `alembic upgrade head` (do not stamp 0001). If an unversioned database was already created from the **new** models using `init_db`, verify its complete schema against this revision before stamping `0002`; do not run a legacy backfill against it.

The migration preserves URL IDs, short codes, activation, click counts and click records. Existing authenticated owner scopes are `u:<user_id>`. Existing ID 0/null guest rows become `legacy:guest` with nullable user FK; existing guest links continue to redirect but are not transferred into a new browser session or account. Current guests use `g:<random-session-UUID>`.

The migration preflight refuses duplicate destinations within an existing owner scope rather than deleting links. Reconcile duplicates manually (including which public codes/click history to retain), then rerun. No automatic merge or deletion is performed. If custom changes to the deployed schema differ from the legacy baseline, inspect them before stamping or upgrading. A failed migration after DDL may require repair from the verified backup; never assume rollback undoes all MySQL schema changes.

Unique URL enforcement uses `(owner_key, SHA256(original_url))` instead of indexing the full 2048-character URL, keeping the MySQL index bounded. A hypothetical hash collision is rejected rather than returning a different destination. Base62 uniqueness is case-sensitive via `ascii_bin`; URL hash identity preserves case-sensitive path/query distinctions. Existing auto-increment allocation resumes above the largest retained ID. MySQL timestamp precision for click events and idempotency expiry is six fractional digits.

The Render start command now applies tracked migrations before Uvicorn. Existing installations must be baselined first; review this before merging/deploying. All deployment/schema operations against the live application remain outside this implementation run.

## Automated coverage

| Area / review cases | Executable tests |
| --- | --- |
| Fresh startup, guest FK, owner separation, same-owner duplicate destinations | `test_creation.py` |
| Base62, distinct allocated IDs, URL validation/semantics and escaping | `test_creation.py` |
| UUID validation, normalized forms, replay 200, conflict 409, expiry and rollback | `test_creation.py` |
| Registration, password hashes, cookie flags, login/logout, CSRF rotation, malformed JWTs and expiry boundary | `test_auth_and_access.py` |
| Owner detail/state/analytics isolation, controlled stale-cookie errors, 404 versus own empty analytics | `test_auth_and_access.py` |
| Warm/cold redirects, deactivate/reactivate, failed cache GET/SET/DELETE, corrupt/stale cache | `test_redirects_and_analytics.py` |
| Atomic click insert/count rollback, UTC metadata, recent-three sorting, output escaping | `test_redirects_and_analytics.py` |
| Concurrent matching keys, conflicting payloads, distinct keys/same destination, distinct destinations | `test_mysql_concurrency.py` (real MySQL) |
| Concurrent click increments and legacy custom-code collision recovery | `test_mysql_concurrency.py` (real MySQL) |
| Upgrade preserving old codes, IDs, guest rows and clicks; duplicate preflight; parallel seeding | `test_migrations.py` (real MySQL) |
| Real TTL, expiry/refill, invalidation and stale active-cache rejection | `test_real_redis.py` (real Redis) |

Not every exploratory P2/browser case from the original 66-row plan is implemented. Automated browser interaction, worker-crash durability, full multi-process deployment load testing, DNS resolver branch tests and all boundary policies remain additional coverage. The implemented tests focus on approved behavior and highest-value integrity regressions.

## Verification completed

- Default suite: **90 passed**, 10 service-dependent cases skipped.
- Full suite with isolated **MySQL 8.0.46 and Redis 7.0.15: 100 passed**, no skips.
- Ruff checks and git whitespace checks passed.
- MySQL migration preservation, duplicate preflight, concurrent creation/click increments and real Redis expiry/invalidation were executed locally against disposable services.
- The GitHub Actions workflow is supplied but its remote run is not yet verified. No live database migration or deployment was performed.

## Tradeoffs and operational limits

- Redirects now use a synchronous FastAPI route, which FastAPI runs in its worker pool. The read transaction is released before the background write. This prevents a read transaction from blocking the independent click transaction in SQLite and avoids blocking the event loop with synchronous SQL/Redis.
- Redis is an optional destination mirror, not a source of authorization truth. Warm redirects still read the database; no DB-outage availability or cache-only speedup is claimed.
- Idempotency is durable within database transactions and survives Redis outages. A database outage during the creation transaction returns a controlled unavailable response. Transactions roll back before retrying known MySQL deadlocks/lock timeouts.
- Matching concurrent requests wait for the transaction result rather than returning a separate in-progress response. A bounded lock timeout/deadlock retry can return 503, for which retrying with the same UUID is safe.
- Cross-worker IDs require one authoritative database allocator. Independent writable databases would need another design. IDs are sequential and expose no secrecy guarantee; management endpoints continue to enforce ownership.
- A 200 POST result can be resubmitted by browser refresh. The original body UUID safely replays its result within the idempotency window; a later replay of the same destination still reuses the owner mapping. HTTP 200 was intentionally retained.
- Guest ownership depends on keeping the signed session cookie. Clearing the session or logging out creates a new guest scope. Guest mappings are not account-transferable by guessable IDs.
- Cookie Secure defaults to true; local HTTP requires the explicit development override. Explicit CSRF tokens supplement SameSite cookies and also protect login/logout.
- BackgroundTasks are best-effort in-process execution. A killed worker can lose a click event; failures roll back and log the mapping ID. Long metadata is truncated to database column limits.

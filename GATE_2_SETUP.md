# Gate 2 — backend configuration and permission to run dev network tests

Gate 1 passed: the user confirmed the corrected SQL isolation test succeeded.
Stage 2 code and offline tests are written. No dev-project connection or network
test has been made by the agent. No SQL migration has been run by the agent.
Stage 3 is not started, so the existing browser UI does not yet send login tokens
or the required date and cannot log sets with the new API until Stage 3 is ready.

## Changes to existing Python/SQL query logic

- `api.py` now uses Postgres instead of SQLite. Every lifting query includes the
  verified owner ID, on top of database RLS. Bound `%s` parameters replace sqlite's
  `?` notation; values are never formatted into SQL strings.
- Exercise duplicates are rejected by the approved per-owner Postgres `lower(name)`
  index, including races. This replaces Python's casefold check; Unicode matching
  differences are documented in the migration/import plan.
- Weight must be finite and >0 to 10,000; reps must be whole numbers 1–1,000;
  trimmed names must contain 1–120 characters. These match the Stage 1 schema.
- `POST /sets` requires a browser-local `date` string in YYYY-MM-DD form, within
  one day of current UTC. Edits still cannot change the date or exercise.
- No-store headers apply to all API responses. Last-entry/history ordering and
  existing route paths/response fields are preserved. Missing/invalid login is 401;
  another user's record is hidden with the same 404 as a nonexistent record.
- `database.py` keeps a lazy one-slot encrypted pool with prepare_threshold=None.
  Each request starts a transaction, sets only verified identity locally, commits
  or rolls back, and returns the connection. Role checks refuse privileged/owner
  connections. No auth-schema access is needed for the corrected RLS policies.
- `authentication.py` verifies asymmetric tokens through PyJWT and cached project
  JWKS; issuer, audience, expiration, issued-at time, algorithm, role, and UUID
  subject are checked. HS256 uses Supabase's Auth server rather than a shared
  signing secret. Failed verification never supplies a database identity.
- `pyproject.toml` explicitly selects `api:app` for Vercel. API module import makes
  no connections; local `.env` loading is opt-in through `run_local.py`.
- The retained photo module still has its isolated SQLite test fixture. Its image
  files, folder, implementation, and migration are untouched and not exposed.

Sources: [Supabase verification](https://supabase.com/docs/guides/auth/jwts),
[transaction pooler](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Psycopg pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html),
[Vercel Python entrypoint](https://vercel.com/docs/functions/runtimes/python).

## 1. Prepare local settings, without sending them to the agent

1. In the project root, copy `.env.example` to a new `.env` file. It is ignored by
   Git. Do not replace or overwrite an existing `.env`; edit its required fields.
2. Fill in these names locally. Never paste values into chat:

| Name | Where the value comes from | Scope |
| --- | --- | --- |
| DATABASE_URL | Dev project Connect → Transaction pooler; restricted incline_api role, port 6543 | Backend secret |
| SUPABASE_URL | Dev project's HTTPS origin, without a trailing path | Public setting |
| SUPABASE_JWT_ALGORITHM | Current signing key algorithm: ES256, RS256, or legacy HS256 | Public setting |
| SUPABASE_PUBLISHABLE_KEY | Dev project API keys → publishable key; never service_role/secret key | Public key; used locally by login tests and legacy verification |
| TEST_USER_A_EMAIL | First dashboard-created dev account | Local tests only |
| TEST_USER_A_PASSWORD | That dev account's password | Local test secret |
| TEST_USER_B_EMAIL | Second distinct dashboard-created dev account | Local tests only |
| TEST_USER_B_PASSWORD | That dev account's password | Local test secret |

3. Find the actual pooler hostname and database name in Supabase's **Connect**
   dialog. Use transaction mode (6543). The username must be
   `incline_api.<your-project-reference>`, not `postgres.<your-project-reference>`.
   Use the **incline_api role password**, not the postgres/database-admin password.
   URL-encode special characters in a URI password. Do not share the resulting URL.
4. Keep each `.env` setting on one line as NAME=value, optionally wrapping the
   value in matching single/double quotes. No shell commands or `export` prefix.
   The local reader does not execute code or override already-exported settings.
5. The API pool requires encryption and checks the server's actual database role.
   Do not substitute admin credentials to bypass a failed connection.

## 2. Existing backend role needs credentials — approval required

Stage 1 deliberately created `incline_api` as **NOLOGIN**. It cannot yet connect
through the pooler. Before network tests, approve enabling LOGIN on this existing
role and assigning it a strong, separate password. This is credential setup for
that role, not a new table or RLS change. The agent has not changed the role.

After approving, you can do this yourself in the DEV project's SQL editor as
postgres. Use a NEW query with the following placeholder, replace it only in the
SQL editor, and never save the real password into a tracked file or chat:

```sql
ALTER ROLE incline_api LOGIN PASSWORD 'REPLACE_WITH_A_STRONG_ROLE_PASSWORD';
```

A password-manager-generated letters/numbers password avoids SQL quote escaping.
For a password containing a single quote, use PostgreSQL's correct escaping or
ask for help before running; do not paste the password into chat. If you already
have psql, its interactive `\password incline_api` avoids writing the plaintext
password into query text, followed by `ALTER ROLE incline_api LOGIN;` as admin.
No psql install is requested or required. No role memberships or broader grants
are needed. Keep the password private and use it in DATABASE_URL locally.

This one credential step needs your explicit approval before the agent performs
anything. You may run it yourself after review. Do not rerun the initial migration
or the Stage 1 test's NOLOGIN preflight after enabling login.

## 3. Approve network tests before they run

Reply that `.env` is filled and approve **dev-project network tests**. Also confirm
that you approve/have completed the restricted role's login/password setup above.
The tests will:

- Sign in the two existing dev accounts with Supabase's password-login endpoint.
- Fetch public signing keys (or call Auth server verification for legacy tokens).
- Connect only to the configured dev transaction pooler as incline_api.
- Exercise existing API routes using real tokens and create temporary lifting
  fixtures inside an outer rollback transaction, including testing delete on
  those new fixtures only. No pre-existing lifting records or accounts are deleted.
- Check RLS directly, cross-account reads/edits/deletes/links/owner changes, and
  real transaction commit/rollback identity cleanup on reused connections.
- Roll back all test lifting writes. Numeric ID counters can advance normally.
- Never run schema files, change roles, import SQLite, deploy, or print credentials.

Prepared command (NOT executed yet):

```sh
INCLINE_RUN_DEV_TESTS=1 .venv/bin/python -m unittest -v test_supabase_dev
```

The explicit flag is required; ordinary test discovery skips these three network
checks. The tests never create accounts or install/change the database schema.

## Local checks and later use

Stage 2 result: 30 offline tests passed; 3 live checks skipped pending approval.
The frontend production build and Vercel TOML parsing passed. Transactions finish
before API success responses are sent, including a tested commit-failure case.

Offline checks need no `.env` and never contact Supabase:

```sh
INCLINE_RUN_DEV_TESTS=0 .venv/bin/python -m unittest discover -v
npm --prefix frontend run build
```

After dev connectivity is approved, the API can be started locally with:

```sh
.venv/bin/python run_local.py
```

This loads the ignored `.env` using a small standard-library reader. Vercel will
use its own backend environment settings instead. Do not deploy this branch yet:
Stage 5 adds the necessary private-file exclusions and routing configuration.

Stop at Gate 2. No Stage 3 frontend authentication work starts until approval.

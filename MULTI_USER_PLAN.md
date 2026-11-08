# Incline multi-user plan — multi-user branch

Scope: accounts, exercises, set logging, last entry, History, and the rest timer.
Progress photos are deferred and excluded from this migration and deployment.
Their local files, folder, source modules, and existing SQLite table remain intact.

## 1. Architecture and hosting — approved design, not deployed

Use option B: React → FastAPI → Supabase Postgres. React also uses Supabase Auth
for login and logout. Friends are created manually in the Supabase dashboard,
public signup is disabled, and password reset is deferred. Supabase manages passwords.

### Hosting: Vercel for both frontend and backend

Use two approved Vercel projects from this repository, presented through one public app
address. This avoids combining two framework builds into an ambiguous deployment.
Neither project has been created.

- Frontend project: root `frontend`, Vite build `npm run build`, output `dist`.
- Backend project: repository root, FastAPI framework, Python function loading
  `api:app`. Its deployment must not publish the SQLite database, local backups,
  private folders, or environment files as assets or function bundle data. Add
  explicit deployment exclusions later; Git ignore rules alone are not the plan.
- Frontend routing will forward `/exercises`, `/sets`, and their subpaths to the
  backend project, keeping existing browser API paths and query strings. A rewrite
  means forwarding a request on the server without changing the browser address.
  Put these rules before any frontend fallback that serves `index.html`.
- Preserve methods, request bodies, and Authorization headers through forwarding.
  Test authenticated GET, POST, PUT, and DELETE requests, including errors.
- User-specific API responses must disable shared caching; apply `no-store` and
  verify the forwarding layer does not cache exercise/history data between users.
- Keep preview deployments paired with the intended preview backend and test
  database. Do not route preview writes into production by accident.
- Choose the API function region close to the Supabase database. Vercel runs the
  FastAPI app as one scalable function; it is not a permanently running Uvicorn
  process. Check function duration, concurrency, bundle limits, and cost before launch.

This arrangement uses Vercel's documented FastAPI entrypoint and rewrite support:
[Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi),
[Vercel rewrites](https://vercel.com/docs/routing/rewrites).

### How the existing api.py should be structured

The existing top-level `app = FastAPI(...)` and route functions are the correct
shape. Keep the file and explicitly configure `tool.vercel.entrypoint` as `api:app`
in a future root `pyproject.toml`. An entrypoint tells Vercel which Python object
handles requests. This is important because this repository also has a terminal
`app.py`; automatic filename detection must not select it.

Do not start Uvicorn, run the terminal menu, migrate data, or create tables during
module import. Vercel imports and invokes the app itself. Keep Uvicorn for local
use only. Declare compatible Python/dependency versions in deployment metadata.
Replace `sqlite3`/`DB_PATH` and the `get_db` dependency with approved Postgres access;
a function's local disk is not the production database. Keep the existing routes,
validation, and most-recent-entry behavior. Vercel does not require splitting each
route into a separate function or moving this app into an `/api` directory.

These deployment changes remain planned; the SQL-file step does not change
Python application code, deployment configuration, or dependencies.
[Python entrypoints](https://vercel.com/docs/functions/runtimes/python).

### Supabase connections and account isolation

A connection pooler shares a limited number of database connections across many
requests. For Vercel, use the Supabase **shared transaction pooler**, normally port
**6543**, copying the actual host and credentials from the project's Connect panel.
A transaction is a group of database operations that commit or roll back together.
The pooler holds one database connection for that transaction, then releases it.

- Keep the database URL in backend-only Vercel environment variables; require TLS
  encryption. Select the approved restricted database role, not the default owner.
- Propose Psycopg 3 (the Python Postgres driver) with a small, thread-safe pool per
  warm function instance, initially capped at one connection. A warm instance is
  a running function process reused for requests. Borrow exclusively per request,
  commit/roll back, then return the connection; never share one active transaction
  between concurrent requests. Reconnect after stale connections. Do not open an
  eager database connection during module import/build. Psycopg/psycopg-pool
  installation is pre-approved for Stage 2.
- The shared transaction pooler does not support prepared statements, a feature
  that stores reusable query plans on a database session. With Psycopg, disable
  automatic preparation using `prepare_threshold=None`. This does NOT disable
  parameterized SQL; user values must still be bound separately from SQL text.
- FastAPI verifies the Supabase login token, then sets its verified user ID using
  transaction-local database settings. All RLS-protected queries for the request
  run inside that same transaction. Never trust an owner ID supplied in the body.
- RLS means database rules restricting each account to its own records. Enable it
  on both app tables and use a non-owner role without BYPASSRLS. Database login
  alone does not pass a Supabase user's identity into RLS; FastAPI must supply it.
  Local identity settings expire at transaction end, preventing cross-user leakage.
- No session-level identity, temporary tables, or other cross-transaction state.
  Use direct/session-mode connections for approved migration/admin tasks where
  needed, separate from normal API requests. Test transaction-pooler behavior with
  two accounts and reused connections before deployment.

Sources: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Psycopg prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).

### Does one address remove CORS setup?

Yes for React-to-FastAPI requests that stay on the same origin. An origin is the
combination of protocol, hostname, and port. CORS is the browser permission system
for JavaScript requests between different origins.

React should keep relative requests such as `/sets` on the frontend address, with
Vercel forwarding them internally. That needs no FastAPI CORS middleware. Merely
hosting both projects on Vercel is NOT enough: calling `backend.vercel.app` directly
from `frontend.vercel.app` is still cross-origin. Subdomains also differ.

Locally, keep the existing Vite forwarding setup to avoid cross-origin browser
requests. If direct cross-origin API access is deliberately introduced later,
configure an explicit allowed-origin list then. Supabase Auth requests are still
to Supabase's separate origin, which Supabase handles; its login return URLs still
need configuration. Same-origin forwarding does not replace token verification,
RLS, or any future cookie-based cross-site request protections.

Sources: [Origin definition](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy),
[Vercel rewrites](https://vercel.com/docs/routing/rewrites).

### Railway fallback

| Choice | Fit for Incline | Tradeoff |
| --- | --- | --- |
| Vercel frontend + Vercel Python function | Recommended first for short exercise/set requests, with both deployments managed in one platform. | Requires serverless-safe database handling and function-limit checks. |
| Vercel frontend + Railway FastAPI service | Fallback if the API needs a persistent Python process or function constraints become awkward. Run Uvicorn as a normal web service. | Adds a hosting platform and service to manage. Revisit connection-pool settings; a persistent service may use the Supabase session pooler (5432) or a supported direct connection. |

If Railway is used, Vercel can still forward the same browser-facing API paths to
it, retaining one origin and avoiding browser CORS setup. Direct browser calls to
Railway would require CORS. The account rules and database structure stay the same.
[Railway FastAPI guide](https://railway.com/guides/fastapi).

### Secrets and approval

Store real secrets only in ignored local environment files and backend deployment
settings. Only public Supabase settings belong in frontend settings: Vite embeds
frontend variables in downloaded JavaScript. Never ship service_role keys or
Postgres passwords to the browser. Do not use privileged credentials for ordinary
user queries.

This hosting change is a planning instruction, not deployment permission. Review
actual costs, approve any dependency installations, and review concrete deployment
configuration before release. The schema design is approved; its SQL is written
for the user to run manually. No cloud project, deployment, or
account setup has happened.

## 2. Preserve the existing database — completed locally

Created a consistent SQLite backup using SQLite's backup interface, with the
source opened read-only. The source database was not changed.

- Backup: `backups/pre-multi-user-20261108T182530256391Z/gym_tracker.db`.
- Manifest beside it records timestamp, SHA-256 checksum, counts, and integrity result.
  A checksum is a file fingerprint used to detect later changes.
- Verified backup integrity: `ok`; 2 exercise records and 8 set records.
- Backups and `.env` files are ignored by Git.
- Use a separate working copy for migration rehearsal. Never migrate from the only
  copy. Capture another consistent backup immediately before final migration if
  more sets have been logged since this snapshot.
- Do not upload the database or import data until the migration script is reviewed.

## 3. Approved database structure — SQL written, not applied

A schema is the structure of the database: its tables, columns, and rules.
The cloud version will have these app tables, alongside Supabase's managed accounts.

| Table | Proposed columns | Important rules |
| --- | --- | --- |
| exercises | id (generated whole-number ID), user_id (Supabase account ID), name | Required owner and trimmed 1–120 character name; case-insensitive name uniqueness within one account. Different accounts may use the same name. |
| sets | id (generated whole-number ID), user_id (Supabase account ID), exercise_id, weight, reps, date | Required owner/exercise/date; finite weight >0 and ≤10,000; whole-number reps 1–1,000. |

Both user_id columns reference Supabase's managed account records. Account deletion cascades to its exercises and sets; exercise deletion also cascades
to its sets. No exercise-delete API is introduced. Existing numeric IDs can be
preserved for the one-time import; reset generated ID counters afterward
so future inserts do not collide. Rehearse this in an empty test database.

Add a database relationship checking BOTH user_id and exercise_id against the
exercise's owner and ID. This prevents account A attaching a set to account B's
exercise, even if a request guesses the other exercise ID.

RLS behavior for each table:

- Logged-out requests: no access.
- Read/delete: only when the row's user_id matches the verified account.
- Insert: the new row must belong to the verified account.
- Update: both the old and new row must belong to that account.
- Limit editable fields: exercise name where supported; set weight/reps only.
  Ownership, IDs, exercise link, and original set date cannot be changed by editing a set.

Index exercises by owner and sets by owner/exercise/newest ID for efficient queries.
Keep last-set and History ordering newest-inserted-first by ID; no warm-up filtering
or workout sessions. Keep original dates during import. For new sets the browser sends its local
YYYY-MM-DD date; the server rejects dates more than one day from current UTC.
Enforce this at the API boundary rather than a moving database CHECK so historical
records can still be imported.

The import must explicitly assign the existing exercises and sets to the user's
chosen Supabase account, preserve their links, and check counts and values afterward.
Report duplicate names, blank names, invalid numbers, or missing exercise links
before enforcing the new rules; do not silently delete or repair records. Review
Unicode name matching because Postgres case-insensitive comparison can differ
from Python's current casefold behavior.

The user approved this schema and the two-project Vercel hosting design.
The commented SQL is in
`supabase/migrations/202611080001_initial_multi_user.sql` for manual review and
execution by the user in Supabase's SQL editor. Codex has not run it.
It creates empty tables and a NOLOGIN restricted `incline_api` role; backend
credentials are configured securely later. It grants data access only to that
backend role, not the browser's anon/authenticated roles. It requires unused
object names and stops on a rerun rather than replacing existing objects.
The SQLite import is separate and has not been written or run. The current
SQLite schema and saved data remain unchanged. No package installation, backend
connection changes, cloud setup, or deployment has occurred in this step.

## Later steps — not started

4. Configure Supabase Auth, approved schema, restricted database role, and RLS.
5. Adapt FastAPI to verify accounts and use parameterized Postgres queries through
   the shared transaction pooler. Configure the explicit Vercel `api:app` entrypoint
   and same-origin API forwarding after reviewing the configuration.
   Postgres drivers use different parameter notation than sqlite3; retain bound
   parameters rather than formatting user values into SQL.
6. Add account screens and attach login tokens to existing React API requests.
   Clear account-specific data on logout/account switching.
7. Write a one-time import script for review; rehearse on copies and verify results.
8. Test two accounts: no reading/editing/deleting each other's records, no ownership
   changes or cross-account exercise links, and no logged-out access. Retain the
   existing functional checks and production build.
9. After deployment approval, deploy paired Vercel frontend/backend previews,
   configure login return URLs, same-origin forwarding, no-cache rules, and secrets;
   test on a phone, then approve the final import and production release.

No cloud setup, account implementation, SQL migration, data import, package
installation, or deployment is authorized by this document alone.


## Staged implementation and gates (latest user instructions)

Work only on `multi-user`. After each stage run all tests and the frontend build,
commit only that stage with a clear message, and report at most eight summary
lines. Never continue through a gate without the user's explicit response.
Pre-approved installs: psycopg, psycopg-pool, a JWT verification library, and
@supabase/supabase-js. Ask before other installs, schema changes beyond the initial
SQL file, or deletions. Flag all changes to existing Python/SQL logic. Do not touch
saved photo files. Keep secrets out of Git and chat; examples contain placeholders.

| Stage | Work | Current status / gate |
| --- | --- | --- |
| 1 | Review initial SQL; add cascades/caps; write two-user isolation SQL. | Files written and statically reviewed; SQL NOT executed. Waiting at Gate 1. |
| 2 | Postgres pooler, verified tokens, transaction-local identity, owner filters, date/caps, entrypoint, and two-user API tests. | Not started. Gate 2: user fills ignored .env and approves dev network tests. |
| 3 | Login only, publishable key, authorized requests, local logging date, account clearing. | Not started. Gate 3: user tests both accounts locally. |
| 4 | Reviewed SQLite-copy importer: dry-run default, confirm flag, validation report, counts, ID counters. | Not started. Gate 4: user runs dry-run. |
| 5 | Two-project Vercel configs, rewrites before SPA fallback, no-store, exclusions, region guidance, DEPLOY_CHECKLIST.md. | Not started. Gate 5: user deploys; agent never deploys. |

Stage 1 review found/fixed SQL gaps: account and exercise cascade deletion; name
length 1–120, weight >0 to 10,000, reps 1–1,000; postgres membership for explicitly
simulating the restricted role. The existing SQL keeps BEGIN/COMMIT, per-owner
case-insensitive uniqueness, same-owner links, eight RLS policies, and no lifting
grants to anon/authenticated. Python and the live schema are unchanged.

Manual tests: `supabase/tests/202611080002_two_user_isolation.sql`. They use two
existing dashboard-created dev accounts and roll back fixture records. They do
not delete accounts or touch prior records, but generated ID counters may advance.

Detailed Gate 1 clicks and expected results: [GATE_1_SETUP.md](GATE_1_SETUP.md).
Token choice for Stage 2: PyJWT + project JWKS for asymmetric signing keys, checking
signature/issuer/audience/expiry/algorithm/role/subject. For legacy HS256, use the
Supabase Auth-server verification route, not a shared secret. References and
manual signup-disabled account setup are in the Gate 1 guide.

Stage 1 local validation: `python -m unittest discover -v` passed all 9 tests;
`npm run build` in frontend passed; `git diff --check` passed. The migration and
manual SQL isolation tests have only been reviewed as text, never executed.
Gate 1 is waiting for the user's explicit confirmation; no later-stage code has
been written and no packages were installed in Stage 1.


Stage 1 Gate 1 repair: hosted Supabase does not let postgres grant auth-schema
USAGE to the restricted role. Removed that ineffective grant and auth.uid() calls
from runtime defaults, policies, and test identity checks. The existing SQL now
reads the verified UUID subject directly from transaction-local request.jwt.claims.
This changes existing SQL logic, not the owner-only security design; no new schema
objects or role memberships are added. The matching manual repair for already
created tables is in GATE_1_SETUP.md; Codex has not executed it. User reported
schema_access=false/helper_access=true; Gate 1 is still pending, Stage 2 unstarted.

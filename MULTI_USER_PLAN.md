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
  private folders, or environment files as assets or function bundle data. Explicit
  deployment exclusions are now prepared in Stage 5; Git ignore rules alone are not the plan.
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
in the existing root `pyproject.toml`. An entrypoint tells Vercel which Python object
handles requests. This is important because this repository also has a terminal
`app.py`; automatic filename detection must not select it.

Do not start Uvicorn, run the terminal menu, migrate data, or create tables during
module import. Vercel imports and invokes the app itself. Keep Uvicorn for local
use only. Declare compatible Python/dependency versions in deployment metadata.
Replace `sqlite3`/`DB_PATH` and the `get_db` dependency with approved Postgres access;
a function's local disk is not the production database. Keep the existing routes,
validation, and most-recent-entry behavior. Vercel does not require splitting each
route into a separate function or moving this app into an `/api` directory.

The entrypoint and Postgres adaptation are implemented in Stage 2. Stage 5
configuration is prepared below; no deployment has been performed.
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

## 3. Approved database structure — user applied to dev; agent never runs it

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
The SQLite import is separate; Stage 4 below records its preparation. It has not been run. The current
SQLite schema and saved data remain unchanged. No package installation, backend
connection changes, cloud setup, or deployment has occurred in this step.

## Original roadmap — see current staged status below

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
| 1 | Review initial SQL; add cascades/caps; write two-user isolation SQL. | User confirmed corrected migration/isolation test passed. Gate 1 passed. |
| 2 | Postgres pooler, verified tokens, transaction-local identity, owner filters, date/caps, entrypoint, and two-user API tests. | User reported Gate 2 tests passed. Gate 2 passed. |
| 3 | Login only, publishable key, authorized requests, local logging date, account clearing. | User confirmed two-account manual checks and automated checks passed. Gate 3 passed. |
| 4 | Reviewed SQLite-copy importer: dry-run default, confirm flag, validation report, counts, ID counters. | User confirmed local dry-run passed: 2 exercises, 8 sets. Gate 4 passed; actual import not run. |
| 5 | Two-project Vercel configs, rewrites before SPA fallback, no-store, exclusions, region guidance, DEPLOY_CHECKLIST.md. | Configuration and checklist prepared. Waiting at Gate 5; user deploys, agent never deploys. |

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
Stage 1 was committed, then the user explicitly confirmed the corrected SQL
isolation test passed. Gate 1 is now open; no packages were installed in Stage 1.


Stage 1 Gate 1 repair: hosted Supabase does not let postgres grant auth-schema
USAGE to the restricted role. Removed that ineffective grant and auth.uid() calls
from runtime defaults, policies, and test identity checks. The existing SQL now
reads the verified UUID subject directly from transaction-local request.jwt.claims.
This changes existing SQL logic, not the owner-only security design; no new schema
objects or role memberships are added. The matching manual repair for already
created tables is in GATE_1_SETUP.md; Codex has not executed it. User reported
schema_access=false/helper_access=true; the user later confirmed the repaired
isolation test passed, opening Gate 1.


## Stage 2 status — Gate 2 passed by user confirmation

Gate 1 passed by user confirmation. Stage 2 replaces existing api.py SQLite logic
with account-scoped Postgres queries and bound %s parameters. Every lifting query
also filters by the verified owner in code. Name uniqueness now uses Postgres's
approved per-owner lower(name) index rather than Python casefold; dates are supplied
by the browser and checked within ±1 UTC calendar day; caps match the SQL. Route
paths and response fields remain the same. Responses are marked no-store.

New modules: authentication.py (PyJWT + project JWKS; legacy HS256 Auth-server
fallback), database.py (lazy encrypted one-slot pool, no prepared statements,
restricted-role check, per-request transaction-local identity), settings.py,
local_env.py, and run_local.py. pyproject.toml selects api:app and declares runtime
dependencies. The approved psycopg/psycopg-pool/PyJWT packages and their normal
binary/crypto dependencies were installed; no other direct package was installed.

Offline tests validate both users' routes WITHOUT simulated RLS, real signed JWTs,
malformed/expired/wrong-account claims, caps/dates, transaction identity cleanup,
error sanitization, and lazy encrypted pool settings. Retained photo tests now
provide their own disposable SQLite dependency instead of depending on api.DB_PATH.
The active API never imports the photo module or accesses its files.

Three real-project tests are prepared in test_supabase_dev.py and skipped unless
INCLINE_RUN_DEV_TESTS=1 is explicitly set. They validate real token verification,
HTTP account isolation, database RLS, same-owner links, and identity clearing across
real transactions; their fixture writes roll back. The agent did not run them; the user subsequently reported they passed, opening
Gate 2. No Supabase endpoint or dev database was contacted by the agent during
Stage 2 development.

Gate 2 instructions: [GATE_2_SETUP.md](GATE_2_SETUP.md). The user fills the ignored
.env using placeholder-only .env.example, confirms/approves securely enabling login
and credentials for the existing NOLOGIN incline_api role, and approves dev network
tests. The agent has not enabled that role or made schema changes. The user confirmed
Gate 2 completion; Stage 3 is now implemented as recorded below. Hosting/deployment and SQLite data import remain unstarted.

Stage 2 local validation: all 30 offline tests passed; 3 dev-network tests were
explicitly skipped behind Gate 2 (33 discovered total). The frontend production
build, TOML entrypoint/dependency parsing, and git diff whitespace check passed.
A commit-failure test also proves transactions finish before sending a success
response; FastAPI's yielded database dependency uses function scope for that reason.
No user .env was read, no dev API/database was contacted, and no cloud SQL ran.


## Stage 3 status — Gate 3 passed by user confirmation

The user reported that Gate 2 tests passed and authorized Stage 3. That confirmation
opens Gate 2; no additional live-project tests were run by the agent in Stage 3.

Added the pre-approved @supabase/supabase-js dependency. Login is email/password
only for dashboard-created accounts; no signup/reset/provider integration. Only
VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY enter the frontend. Build-time
and runtime config validation reject privileged/legacy keys without echoing them.
The backend .env stays separate from ignored frontend/.env.local.

accountSession.js coordinates auth state, local-scope logout, and API calls. It
gets the current SDK session before attaching the bearer token, rejects a changed
account before sending, aborts pending work on account boundaries, and rejects late
responses even if cancellation is ignored. A changed account generation/user key
unmounts the entire React app, clearing exercises, History, last entries, drafts,
messages, filters, and timer. Same-account token refresh does not reset that key.
A 401 clears state and saved local login; logout clears visible data immediately,
even when server logout fails. Passwords and SDK exception details are not logged.

main.jsx adds the cream/dark login screen, account email/logout control, and date
submission using browser-local calendar fields. Existing logging/History requests
now use the authorized request helper. Form max values match backend caps. Route
paths and database schema are unchanged. No existing Python/SQL logic changed in
Stage 3; saved photo files and deferred modules remain untouched.

Node's built-in offline tests cover sign-in, headers for all API methods, local
dates, same-account refresh, account switches, late bootstrap/replies, failed SDK
session reads, 401/logout, public-only config, and external URL rejection. The
manual browser checklist is [GATE_3_CHECKLIST.md](GATE_3_CHECKLIST.md).

The user confirmed all Gate 3 two-account checks passed and approved Stage 4
preparation. Stage 5 configuration is now recorded below; deployment remains unstarted.

Stage 3 validation: all 35 offline Python tests and 19 frontend tests passed;
3 live dev checks were intentionally skipped. The frontend production build and
git diff --check passed. Frontend tests use fake SDK/fetch objects only. No actual
account login or live Supabase connection was performed by the agent.


## Stage 4 status — Gate 4 dry-run passed

Gate 3 passed by user confirmation. import_sqlite.py reads only a detached backup,
validates without repairing, and defaults to local-only dry-run. IMPORT_USER_ID
assigns every exercise/set to one existing account; original IDs, links, dates,
and values are preserved. Photo tables/files are ignored. Existing API Python
and schema/SQL migration logic are unchanged; the new importer uses bound SQL.

An explicit --confirm would use a separate local postgres admin connection on
5432, block conflicting IDs/names before inserting, skip identical rows on rerun,
verify full row values and owner/global counts in one transaction, and advance
ID counters across all users without moving backward. Sequence changes can leave
safe gaps on rollback. No updates, deletions, schema changes, or cloud access were
performed. The actual import has NOT run, including against the existing backup.

Offline fixtures test validation, read-only source handling, owner mapping,
repeatability/conflicts, rollback, counter alignment, and sanitized failures.
Guide and required placeholder variables: GATE_4_IMPORT_GUIDE.md and .env.example.
The user confirmed the local-only dry-run passed with 2 exercises and 8 sets,
then explicitly approved Stage 5 preparation. Actual import remains unrun and
requires separate approval; passing Gate 4 did not authorize uploading rows.

Stage 4 validation: 46 offline Python tests passed; 3 live-project tests were
explicitly skipped. All 19 frontend tests and the production build passed.
Offline importer tests used disposable fixtures only, never the real backup or
Supabase. git diff --check passed.


## Stage 5 status — configuration prepared, STOP at Gate 5

Root vercel.json selects FastAPI, sets the api.py function limit to 30 seconds,
adds no-store headers, and explicitly excludes private/legacy/import/test files
from the function bundle. Existing pyproject.toml still selects api:app.
Root and frontend .vercelignore exclude databases, backups, private photo files,
local environment files and development artifacts without deleting local files.
Frontend vercel.json selects Vite/dist and forwards /exercises, /sets and their
subpaths before the page fallback; API responses disable caching at both layers.
No existing application Python/SQL logic, schema, dependencies, or UI changed.

The forwarding origin is deliberately https://incline-api.example.invalid until
the user creates the backend. Replace all four origins with the intended backend
before frontend deployment; never point previews at production inadvertently.
There is no runtime environment-variable interpolation in these static rewrites.
Region selection is left to the user to match the actual Supabase database.

DEPLOY_CHECKLIST.md contains manual steps for both projects, branch/root choices,
backend-only versus public variables, restricted pooler credentials, Supabase
return URLs, manual friends' accounts, signup off, deployment-protection handling,
preview separation, exclusions, and deployed two-account/phone checks.

All five implementation stages are prepared. Gates 1–4 passed by user reports;
Gate 5 remains pending the user's deployment and final tests. The agent has not
created projects, deployed, run cloud SQL, contacted the dev database, or imported
actual SQLite records. The actual import is still a separate, unapproved action.

Stage 5 validation: 49 offline Python tests passed (including three deployment
configuration guards); 3 live-project tests were explicitly skipped. All 19
frontend tests and the production build passed. git diff --check passed.
These are local/static checks, not proof of live Vercel routing or bundle output;
the user must perform the deployed checks at Gate 5. No packages were installed.

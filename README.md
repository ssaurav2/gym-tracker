# Incline

Install dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On the `multi-user` branch the HTTP API uses Supabase Postgres, not SQLite.
The user confirmed Gate 2 backend tests passed. Stage 3 frontend login is
implemented; follow [GATE_3_CHECKLIST.md](GATE_3_CHECKLIST.md) to configure public
frontend settings and test both accounts. Do not deploy yet.
The existing SQLite database and terminal `app.py` are preserved and not migrated.
Do not rerun `database_setup.py` or execute cloud migrations automatically.

Once configured, start the API from the project directory with:

```sh
.venv/bin/python run_local.py
```

This loads an ignored `.env` without printing values. Supabase login tokens are
required for all lifting routes. `POST /sets` also requires a YYYY-MM-DD local date
within one day of current UTC. The frontend now sends login tokens and the browser-local logging date. Password signup/reset are
not being built: accounts are created manually in the Supabase dashboard.

Run all offline checks (no Supabase connection) with:

```sh
INCLINE_RUN_DEV_TESTS=0 .venv/bin/python -m unittest discover -v
```

The real dev-project tests are explicitly opt-in and remain behind Gate 2.
The Vercel backend entrypoint is `api:app`, configured in `pyproject.toml`.

## React frontend

On the `multi-user` branch, the mobile-first frontend has Log a Set, Exercises,
and History screens. History groups sets by date and supports filtering, editing, and confirmed
deletion. It also includes a rest timer. The timer runs in the browser and does not save data.

Copy `frontend/.env.example` to ignored `frontend/.env.local` and fill only its
project URL and publishable key. Never copy backend secrets into frontend settings.
See the Gate 3 checklist for exact steps. Keep the Python server running with the
command above. In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the local address printed by Vite (normally http://127.0.0.1:5173).
Vite is the tool that runs and builds the frontend. During development it forwards
`/exercises` and `/sets` requests to the Python server at port 8000, keeping
the existing API paths. Logging sets and adding exercises save to your real database.

To check the production build, run `npm run build` inside `frontend/`.
The generated `frontend/dist/` files need a server that also forwards those API
paths to Python before they can be deployed; this setup is for local development.


## Multi-user preparation

See [MULTI_USER_PLAN.md](MULTI_USER_PLAN.md) for the proposed FastAPI + Supabase
architecture, the verified local SQLite backup, and the schema awaiting approval.
The HTTP API now requires Supabase configuration and a verified account.
Frontend login is implemented; deployment remains a later stage. The legacy
terminal app still uses SQLite. No SQLite data import has been performed.

Pump Progress is deferred on this branch: its navigation entry and API routes are
not exposed. Its source modules, local photo files/folder, and existing SQLite table
are preserved. Nothing from that feature will be imported or deployed in this pass.

Run all checks with:

```sh
INCLINE_RUN_DEV_TESTS=0 .venv/bin/python -m unittest discover -v
```

`test_api` checks the active API, including that photo routes return 404.
`test_progress_photos` tests the retained module on an isolated test app using a
throwaway database and directory; it does not enable those routes on the real app.

## Main-page quotes

`frontend/src/quotes.js` holds the quote list. The main-page subheading rotates
through it every 15 seconds while the logging screen is open. It cycles through the five user-provided quotes and their attributions, then repeats.

Frontend offline auth/request tests: `npm --prefix frontend test`. These use fake
clients and requests, not your dev accounts. Real two-account UI checks await Gate 3.

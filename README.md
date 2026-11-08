# Incline

Install dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The API uses `gym_tracker.db` beside `api.py`. Only for a fresh database,
run `.venv/bin/python database_setup.py` once. Do not rerun setup on an
existing database. Exercise and set routes use these tables unchanged.

Start from the project directory:

```sh
.venv/bin/python -m uvicorn api:app --reload
```

Open http://127.0.0.1:8000/docs. Expand an endpoint, click **Try it out**,
enter the JSON body, and click **Execute**. These operations use your real
database.

1. `POST /exercises` with `{"name":"Bench Press"}` returns 201 and an ID.
   Repeating with `bench press` returns 409. Blank names return 422.
2. `GET /exercises` lists exercise IDs. `GET /exercises/{exercise_id}/last-set`
   returns `null` until you log a set.
3. `POST /sets` with `{"exercise_id":1,"weight":155,"reps":8}` (substitute
   your exercise ID) returns 201 with today's local date.
4. Check the last-set endpoint again. It returns the latest inserted set,
   ordered by ID, with no filtering. `GET /sets` lists newest first; its
   optional `exercise_id` query parameter filters by exercise.
5. `PUT /sets/{set_id}` with `{"weight":160,"reps":8}` fixes a set while
   preserving its date and exercise. Weight or reps of zero or below return
   422 on both creation and editing. Reps must be a whole number.
6. `DELETE /sets/{set_id}` deletes a mistake and returns 204. Missing exercise
   or set IDs return 404.

Run isolated API checks with `.venv/bin/python -m unittest -v test_api`.
Tests use a temporary database, leaving saved data untouched.

`app.py` remains the existing terminal interface. `api.py` provides resource
routes used by the React frontend. There is no authentication or user ID yet;
account scoping is deferred. Duplicate-name checks apply to API writes;
the existing terminal interface does not perform them.

## React frontend

On the `multi-user` branch, the mobile-first frontend has Log a Set, Exercises,
and History screens. History groups sets by date and supports filtering, editing, and confirmed
deletion. It also includes a rest timer. The timer runs in the browser and does not save data.

Keep the Python server running with the command above. In a second terminal:

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
The app still runs locally on SQLite; accounts and deployment are not implemented.

Pump Progress is deferred on this branch: its navigation entry and API routes are
not exposed. Its source modules, local photo files/folder, and existing SQLite table
are preserved. Nothing from that feature will be imported or deployed in this pass.

Run all checks with:

```sh
.venv/bin/python -m unittest -v test_api test_progress_photos
```

`test_api` checks the active API, including that photo routes return 404.
`test_progress_photos` tests the retained module on an isolated test app using a
throwaway database and directory; it does not enable those routes on the real app.

## Main-page quotes

`frontend/src/quotes.js` holds the quote list. The main-page subheading rotates
through it every 15 seconds while the logging screen is open. It cycles through the five user-provided quotes and their attributions, then repeats.

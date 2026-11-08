# Gym tracker

Install dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The API uses `gym_tracker.db` beside `api.py`. Only for a fresh database,
run `.venv/bin/python database_setup.py` once. Do not rerun setup on an
existing database. Exercise and set routes use these tables unchanged; the photo
gallery needs the separate database update described below.

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

The mobile-first frontend has Log a Set, Exercises, History, and Pump Progress
screens. History groups sets by date and supports filtering, editing, and confirmed
deletion. It also includes a rest timer. The timer runs in the browser and does not save data.

Keep the Python server running with the command above. In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the local address printed by Vite (normally http://127.0.0.1:5173).
Vite is the tool that runs and builds the frontend. During development it forwards
`/exercises`, `/sets`, and `/progress-photos` requests to the Python server at port 8000, keeping
the existing API paths. Logging sets and adding exercises save to your real database.

To check the production build, run `npm run build` inside `frontend/`.
The generated `frontend/dist/` files need a server that also forwards those API
paths to Python before they can be deployed; this setup is for local development.


## Pump Progress photos

After installing requirements, run this once for both existing and fresh databases
(after `database_setup.py` on a fresh installation):

```sh
.venv/bin/python migrate_progress_photos.py
```

This repeatable database update adds `progress_photos` without altering exercises
or sets. Restart the Python server after updating dependencies or source files.

Open the app at `http://127.0.0.1:5173` or `http://localhost:5173` on the computer
running it. Photo access is deliberately local-only: both the Python routes and
Vite's forwarding layer reject remote photo requests. Existing lifting features
can still be used from a phone on the local network, but Pump Progress cannot yet.
There are no accounts or per-user photo permissions. Do not deploy these photo
routes behind another forwarding server until it enforces equivalent restrictions
or authentication is implemented. A generated filename is not access protection.

Choose a JPEG or PNG up to 10 MB, with no more than 24 million pixels and no side
over 10,000 pixels. HEIC, animated images, and other formats are rejected. Category
is optional: front, back, or side. The server records upload time in UTC; the browser
displays it in local time. Both chronological sort directions are available.

Pillow verifies and decodes the actual image, corrects its orientation, resizes it
to fit 2048 × 2048, and writes a new JPEG without embedded metadata (including GPS).
Original uploaded bytes and names are not retained. This is a resized progress
copy, not an archive of the original photo. Photos use generated names and limited
file permissions in `private/progress-photos/`, which Git ignores. Set `GYM_PHOTO_DIR`
on the Python server to use another private directory outside publicly served files.
SQLite stores only the generated relative path, upload timestamp, category, and ID.

API routes:

- `POST /progress-photos`: file-form upload (`file`, optional `category`).
- `GET /progress-photos?sort=newest`: photo records; also accepts `oldest`.
- `GET /progress-photos/{id}/image`: image bytes, with caching disabled.
- `DELETE /progress-photos/{id}`: remove the file and database record.

The browser asks for confirmation before deletion. SQLite and the filesystem
cannot commit one shared operation: deletion removes the file before the record;
if the database commit fails, retry finishes removing the remaining record.
Failed uploads roll back database writes and attempt to remove the new file.
A process crash can leave an unlisted file; no automatic file purge runs.
Deleting here cannot remove copies in external backups. Back up both the database
and private directory together if you want to preserve your gallery.

Run all API checks with:

```sh
.venv/bin/python -m unittest -v test_api test_progress_photos
```

Photo tests use a disposable database and directory, never your saved gallery.
They cover file validation, size limits, metadata removal, ordering, local-access
restrictions, deletion failures, and repeatable database updates.

## Main-page quotes

`frontend/src/quotes.js` holds the quote list. The main-page subheading rotates
through it every 15 seconds while the logging screen is open. It cycles through the five user-provided quotes and their attributions, then repeats.

# AGENTS.md

## What this app is
A gym tracker for progressive overload, built by a CS student as a learning project, meant to eventually be useful to other people too. The user logs sets as they lift and sees what
they did last time for each exercise, so they can decide whether to
add weight or reps.

## Design decisions (already made, don't redesign)
- No "workout sessions". The user just logs sets as they go, and each
  set is auto-stamped with today's date.
- The user builds their own exercise list, then picks from it when logging.
- When logging, show the most recent entry for that exercise
  ("last time: 155 x 8"). This is the core feature.
- No notes. No bodyweight tracking (that comes later, with the macro tracker).
- Basic edit/delete for fixing mistakes.
- Keep it simple. "Most recent entry" means literally that, with no
  warm-up filtering or smart logic.
- Design references are in design/. Read design-notes.md before any UI work.
- Rest timer runs in the browser.

## Tech
- Python + SQLite (gym_tracker.db). Plain sqlite3, no ORM.
- Tables: exercises (id, name), sets (id, exercise_id, weight, reps, date), and progress_photos (id, file_path, uploaded_at, category).
- Files: database_setup.py (run once), app.py (terminal menu + functions).
- React frontend in frontend/, talking to api.py through the existing development forwarding setup.
- Progress photos: progress_photos.py routes and private/progress-photos/ files; additive table setup in migrate_progress_photos.py.

## How to work with me
- Move fast. You can make multi-step changes and write whole features,
  especially frontend and styling.
- Keep explanations short. After each change, give a 3-5 line summary:
  which files changed, what each one does, and anything non-obvious.
- Before starting a big feature, give a brief plan (a few bullets)
  and wait for my go-ahead.
- Always ask before: changing the database schema, deleting files or
  data, installing packages, or changing how the frontend talks to
  the backend.
- If you change any of my existing SQL/Python logic, flag it clearly.
- Use parameterized SQL (? placeholders), never string-formatted SQL.
- If something I wrote has a bug or a questionable design, tell me
  plainly.
  - Explain things in plain, simple language. I'm a beginner and only
  just learning about APIs in class.
- Define any technical term the first time you use it, in one sentence.
- Use everyday analogies when they help.
- Keep summaries short, and don't assume I already know a concept.

## Current state
Built: terminal interface; React exercise creation and set logging with last entry;
rest timer; History grouped by day with filtering, editing, and confirmed deletion.
On the multi-user branch, Pump Progress is deferred: its navigation entry and
API routes are disconnected. Source modules, photo files/folder, and the existing
SQLite table are preserved. Do not re-enable or migrate them in this pass.
The main-page subheading rotates through five user-provided quotes every 15 seconds.
## Long-term goal
Eventually usable by other people (multiple users with accounts).
On the multi-user branch, accounts and user_id ownership are planned but not
implemented yet. The schema is approved; a commented SQL migration has been
written for the user to review and execute manually. Do not run it automatically.
Keep the existing UI and avoid single-user assumptions in the API design.

## Pump Progress Gallery (deferred on multi-user branch)

The following is retained future context, not work to implement in this pass.

Add a private "Pump Progress" section where the user can upload physique progress photos and view them in a chronological gallery.

### Product decisions

- Photos are progress check-ins, not social posts.
- Keep the gallery private by default.
- Show the upload date for every photo.
- Let the user view photos newest-first and oldest-first.
- Support opening a photo in a larger view.
- Do not add likes, comments, followers, public profiles, or social sharing.
- Do not require workout sessions.
- Do not add bodyweight tracking in this pass.
- Do not require notes or captions.
- Optional photo categories may include front, back, and side.
- The user should be able to delete a photo after confirmation.

### Privacy and storage

- Treat physique photos as sensitive personal data.
- Never expose uploaded photos through a public URL by default.
- The API and Vite enforce local-only photo access; future proxies must preserve this restriction until authentication is added.
- Current uploads are capped at 10 MB and 24 megapixels, converted to JPEG, resized to fit 2048 × 2048, and stripped of embedded metadata.
- Store image files outside the SQLite database; store only the file path, date, and category in SQLite.
- Validate file type and size before saving.
- Use generated filenames instead of the original filename.
- Do not log image contents or personal metadata.
- Ask before changing the database schema or installing image-processing packages.

### UI direction

- Add "Pump Progress" as a separate navigation section.
- Keep the gallery visual, simple, and fast to use.
- Use large thumbnails in a responsive grid.
- Make uploading a photo possible in a few taps.
- Match the existing dark background, lime accent, rounded cards, and large touch targets.
- Avoid cluttering the set-logging screen with progress-photo features.

### Future possibilities

- Compare two photos side by side.
- Add a timeline slider.
- Add optional private measurements later.
- Add encrypted cloud storage only after accounts and authentication exist.

## Multi-user plan
- Database and login: Supabase (Postgres + Supabase Auth). Don't build
  my own password system.
- Frontend hosting: Vercel.
- Never put the Supabase service_role key in the frontend or in git.
  Secrets go in .env (gitignored) and Vercel environment variables.
- Every table must have Row Level Security on, with policies so a user
  can only see and change their own rows.
- Ask before changing the schema, and migrate my existing SQLite data
  with a one-time script I can review. Never run it on the only copy.
  - Progress photos are deferred. Don't build or migrate them in the
  multi-user version. Remove the Pump Progress tab and photo endpoints
  from the deployed app, but don't delete any photo files.

Preparation status: see MULTI_USER_PLAN.md for the option B hosting proposal,
verified local database backup, and approved database design. The SQL file in
supabase/migrations/ is written but has not been executed. No cloud resources
or live schema changes have been made.


## Staged multi-user work (latest instructions)

Use only the multi-user branch. Stages and mandatory gates are recorded in
MULTI_USER_PLAN.md. Stage 1 SQL must be run by the user, not the agent. Stop at
Gate 1 until the user confirms both files ran OK. After every stage, run all tests
and the frontend build, commit that stage, and summarize in at most eight lines.
The approved installs are psycopg, psycopg-pool, a JWT verification library, and
@supabase/supabase-js; other installs require approval. Do not expose secrets.
Login only: manual dashboard-created accounts, signup disabled, reset deferred.
Dates: browser-local YYYY-MM-DD on insert, accepted only within one day of UTC.
Caps: exercise name 1–120 characters, weight >0 to 10,000, reps 1–1,000.
Account deletion cascades through exercises/sets. Initial SQL edits are authorized;
additional schema changes/deletions need approval. Saved photo files stay untouched.

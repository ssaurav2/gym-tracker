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
- add a rest timer

## Tech
- Python + SQLite (gym_tracker.db). Plain sqlite3, no ORM.
- Tables: exercises (id, name) and sets (id, exercise_id, weight, reps, date).
- Files: database_setup.py (run once), app.py (terminal menu + functions).
- Planned later: a JavaScript/React frontend talking to a Python backend.

## How to work with me (important)
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
Built: add_exercise, view_exercises, log_set, get_cursor helper,
terminal menu.
Next: show the last entry for an exercise, view logged sets, edit/delete.
## Long-term goal
Eventually usable by other people (multiple users with accounts).
Not in this pass: no auth and no user_id yet. But don't hardcode
single-user assumptions into the API design. UI is functional and
plain for now; visual polish is a separate later pass.

## Planned feature: Pump Progress Gallery

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
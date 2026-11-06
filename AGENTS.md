# AGENTS.md

## What this app is
A personal gym tracker for progressive overload, built by a CS student
as a learning project. The user logs sets as they lift and sees what
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

## Current state
Built: add_exercise, view_exercises, log_set, get_cursor helper,
terminal menu.
Next: show the last entry for an exercise, view logged sets, edit/delete.
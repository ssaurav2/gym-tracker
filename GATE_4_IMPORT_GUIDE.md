# Gate 4: review and local dry-run

Stop here after the dry-run. No cloud SQL or import has been run by the agent.
The dry-run reads a backup and prints a report; it does not contact Supabase.

## What maps to your account

| SQLite backup | Supabase |
| --- | --- |
| exercises.id, name | Same ID and exact name; user_id = IMPORT_USER_ID |
| sets.id, exercise_id, weight, reps, date | Same IDs, links, values and original dates; user_id = IMPORT_USER_ID |
| progress_photos | Ignored completely; photo files are never opened |

All source records go to ONE existing Supabase account. A UUID is the account's
unique identifier, not its email address. Historical dates are preserved; the
API's within-one-day rule applies to new logging, not this historical import.
No existing API, SQL migration, schema, or frontend behavior was changed.

## Do this now

1. In Supabase, open your **dev** project → Authentication → Users. Open your
   account and copy its User UID. Check it is your account, not your friend's.
2. In the repository's ignored `.env`, add `IMPORT_USER_ID` with that UID.
   Do not paste passwords, database URLs, tokens, or keys into chat.
3. Use a standalone SQLite **backup copy**, not the root `gym_tracker.db`.
   The existing snapshot below had 2 exercises and 8 sets when created. It does
   not contain sets logged after that snapshot. If needed, prepare a fresh
   consistent backup separately before final import; don't copy an actively
   written SQLite file with pending journals. Keep the original and backup.
4. From the repository root, run this **without --confirm**:

   ```sh
   .venv/bin/python import_sqlite.py --source backups/pre-multi-user-20261108T182530256391Z/gym_tracker.db
   ```

5. Expect `status: dry_run_valid`, `destination_contacted: false`, your target
   UUID, source counts, a SHA-256 fingerprint (a file-change detector), and
   `issues: []`. Source bytes must stay unchanged. No destination credentials
   are needed for this step.
6. If `blocked`, review the issue codes. `source_row` means the 1-based row
   position when that table is sorted by ID. Blank/duplicate/oversized/untrimmed
   names, invalid values/dates/IDs, and missing exercise links are reported,
   never repaired. Don't delete or fix records just to make this pass; discuss
   the report first. Unicode names receive conservative casefold screening;
   exact Postgres lowercase matching is checked later at the destination.
7. Tell me whether the dry-run passed, its counts, and any issue codes.
   **Wait at Gate 4 before a confirmed import or deployment work.**

## Later confirmed import — review only, do not run yet

The explicit `--confirm` flag enables destination access. Before using it:

- Review the script and approve the actual import separately. Rehearse against
  the dev project first. Never use the only SQLite copy.
- Fill `IMPORT_DATABASE_URL` locally with the dev project's **postgres admin**
  direct/session connection, port **5432**, from its Connect panel. This is a
  separate credential from the restricted API `DATABASE_URL` on port 6543.
  The importer needs permission to preserve IDs and advance counters. Never
  deploy its admin credential, put it in frontend variables, or commit it.
  Password URL characters must be encoded as required by the connection URL.
- Pause all application writers and other imports. The importer temporarily
  locks both app tables against writes; ordinary reads can continue. Lock and
  statement timeouts stop it rather than waiting indefinitely.
- The target account must exist. An ID already used by another account or with
  different values blocks the entire import. A same-account exercise name with
  a different ID also blocks it. Nothing is overwritten, renumbered, or deleted.
  Manual test records may cause conflicts: stop and review, don't clear them.
- Exact matching records are skipped. Repeating the same backup/account is safe;
  changing backup records is not treated as an update. Do not keep logging to
  the legacy database expecting this script to synchronize edits.
- Inserts and verification run together in one transaction, meaning one group
  of changes that succeeds together or rolls back. Every imported row and both
  owner/global counts are checked. Generated ID counters advance past the
  largest ID across ALL accounts and never move backward. Nonstandard sequence
  settings require review rather than being changed automatically.
- Postgres counter changes are not rolled back. A failed attempt can leave safe
  unused ID gaps. If a connection fails during commit, it can be unclear whether
  the commit succeeded: inspect destination state before retrying. The script
  does not print database exception text or credentials.

The future invocation is the same command with `--confirm` appended, only after
approval. Reports show inserted/unchanged counts, verified destination counts,
and counters advanced. No schema changes, UPDATE, DELETE, or photo migration.

References: [Postgres counter behavior](https://www.postgresql.org/docs/current/functions-sequence.html),
[Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
[SQLite read-only URI connections](https://docs.python.org/3/library/sqlite3.html).

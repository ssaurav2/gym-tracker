# Gate 3 — test the real login flow with two dev accounts

The user confirmed Gate 2 tests passed. Stage 3 adds React login/token/date handling
and local account-state clearing. The agent has NOT logged in to your dev accounts,
run live Supabase tests, imported data, changed schema/roles, or deployed anything.
No signup/password-reset screen or photo feature is added.

## Set up the two public frontend settings

1. Keep your existing backend `.env` private in the project root.
2. In `frontend`, copy `.env.example` to a NEW `.env.local` file. If `.env.local`
   exists already, edit its required fields instead of overwriting it.
3. Fill these two names only, using the SAME dev project as the backend:
   - `VITE_SUPABASE_URL`: HTTPS project origin, matching backend SUPABASE_URL.
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: that project's `sb_publishable_...` key.
4. Do NOT copy the backend `.env` into the frontend. Never add DATABASE_URL,
   database/admin passwords, friend passwords, access tokens, service_role, or
   `sb_secret_...` keys to frontend variables. Build tools reject a non-publishable
   key in the expected key field before emitting the browser bundle.
5. `.env.local` is ignored by Git. No settings need to be pasted into chat.

## Start the app

1. Open a terminal in the repository root and start the backend:
   `.venv/bin/python run_local.py`.
2. In a second terminal, open `frontend` and run `npm run dev`.
   If either server is already running, stop only that server with Ctrl+C and
   restart it after changing its environment settings. Do not kill unrelated apps.
3. Open the local frontend URL printed by Vite (normally http://127.0.0.1:5173).
4. You should see Incline's cream/dark login screen. If it says login is unavailable,
   check both public frontend settings and restart Vite. No signup/reset links should
   appear. The database is separate from the legacy SQLite tracker, so old SQLite
   sets will not appear until the later import stage.

## Check account A

1. Log in with the first dashboard-created dev account. Do not send its credentials
   to the agent. Confirm its email appears above the app controls.
2. Try a wrong password first if you want to verify error handling: the screen should
   show a generic failure and clear the password field, without logging details.
3. Add an exercise named `Gate 3 test press`. Log a set with distinctive values such
   as weight 101, reps 7. This creates real dev records, unlike rolled-back API tests.
4. Check “Last time” shows 101 × 7. Log another set, then confirm Last time updates.
5. Open History: newest-first sets, date headings, and exercise filter should work.
   The new set's date must match YOUR browser's local day, even near UTC midnight.
6. Edit weight/reps on one of these new test sets; confirm Last time updates if it
   was the latest entry. The date and exercise must remain unchanged.
7. If testing delete, use only a new test set you deliberately created here: click
   Delete and cancel first to confirm it stays. Then optionally confirm deletion
   yourself and verify only that test set disappears. Do not delete existing data.
8. Start the rest timer and leave weight/reps typed in the Log form for the next check.

## Log out and switch to account B

1. Click **Log out**. The login page should appear immediately. No exercise names,
   history rows, Last time, timer state, input drafts, or account A email should remain.
2. Refresh the page. It should stay logged out; no brief flash of account A data.
3. Log in with account B. Confirm account B's email appears and A's new records do
   not appear. History/filter/Last time/forms should start from B's own data.
4. Add the SAME exercise name (`Gate 3 test press`). This must succeed because names
   are unique per account. Log different values, such as weight 202, reps 4.
5. Check B's Last time and History show B's values. Log out and return to A: A should
   still see its own values, never B's. Repeat the switch in the opposite direction.
6. Refresh while logged in: the same account may be restored through Supabase's
   saved session, but data should load only after the login check finishes.

## Check slow requests and expiry

1. With an account logged in, you may open Chrome DevTools → Network and choose
   a slow network preset. Request History, then log out before it finishes.
   A late result must not reappear on the login page or under the next account.
2. If using two tabs on the same frontend address, switch accounts or log out in one
   tab. The other should clear/remount the old account view when Supabase's auth
   event arrives; it must not mix the two accounts' records.
3. Return DevTools to **No throttling** after the check. Don't share screenshots of
   request headers/storage: these contain login tokens. No need to paste tokens or
   manually edit stored JWTs. Expired/missing login behavior is covered offline:
   a 401 clears the view, aborts pending work, and returns to login.
4. A token refresh for the SAME account should keep your current weight/reps draft
   and timer; only logout/account switching resets the whole account view.

Requests send a fresh session token in Authorization and the logging date using
local calendar fields (not UTC string conversion). Backend signature verification
and RLS remain the actual access controls; hiding frontend rows is not security.
Logging out uses Supabase's local scope, so other devices are not forcibly logged
out. Existing access tokens remain valid until expiry, as Supabase documents.
[Login](https://supabase.com/docs/reference/javascript/auth-signinwithpassword),
[auth events](https://supabase.com/docs/reference/javascript/auth-onauthstatechange),
[local logout](https://supabase.com/docs/reference/javascript/auth-signout).

## Offline checks available

- `npm --prefix frontend test`: Node's built-in test runner, with a fake auth client
  and fake fetch calls only. No extra test package or Supabase connection is needed.
- `INCLINE_RUN_DEV_TESTS=0 .venv/bin/python -m unittest discover -v`: all offline
  backend checks; the three real-project checks remain skipped for this run.
- `npm --prefix frontend run build`: frontend production build.

## Stop at Gate 3

Tell me whether both-account login/logout, isolation, local dates, History edits,
and account clearing passed. Report any failure using UI text and steps only—no
credentials, tokens, database URLs, or raw request headers. Do not deploy or import
SQLite yet. Stage 4 waits for your confirmation at this gate.

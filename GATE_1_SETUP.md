# Gate 1 — create the dev database and run the reviewed SQL yourself

Stage 1 changes files only. Neither SQL file has been executed by Codex.
Do not start Stage 2 until you have reported that both ran successfully.

## What changed in the existing SQL

- Kept BEGIN/COMMIT, all eight owner-only RLS policies, same-owner exercise links,
  and no lifting-data grants to anon/authenticated.
- Changed both account foreign keys to ON DELETE CASCADE: deleting an account
  removes its exercises and sets. The exercise-to-set link also cascades so
  dependent sets do not block account cleanup. There is no exercise-delete API.
- Added caps: name 1–120 characters, weight greater than zero and at most 10,000,
  reps 1–1,000. Weight must remain finite; the chosen weight unit is unchanged.
- Granted only the administrative postgres role membership in incline_api so the
  SQL editor can run the tests under restricted permissions. The backend role
  stays NOLOGIN until credentials are configured in Stage 2.
- No existing Python logic, SQLite data, photos, or application behavior changed.

If you already ran an older version of the migration, STOP and tell me. The
migration deliberately refuses existing objects. Do not drop tables, delete
accounts, or try to run only selected lines to get around that protection.

## 1. Create a separate development project

1. Sign in to the [Supabase dashboard](https://supabase.com/dashboard).
2. Click **New project** and choose your organization. Review any billing choice
   yourself; use a development project separate from production.
3. Name it **incline-dev**. Choose a strong database password and save it privately
   in your password manager. Never paste it into chat or a tracked file.
4. Choose a region near where you expect to run the Vercel Python backend.
5. Click **Create new project** and wait for the database to be ready.
6. Confirm the selected project is **incline-dev** before continuing.

## 2. Configure manual accounts; no email delivery needed

1. In the project sidebar, click **Authentication**.
2. Open **Sign In / Providers** (some dashboard versions label it **Providers**).
3. Under user signup settings, switch **Allow new users to sign up** OFF and save.
   Keep anonymous sign-ins OFF. This blocks public registration while allowing
   existing dashboard-created accounts to sign in.
4. In the **Email** provider, keep email/password sign-in enabled. Do not configure
   a custom email provider. We are not adding signup or password-reset screens.
5. Open **Authentication → Users → Add user → Create new user**. Choose creation,
   not invitation; invitations depend on email delivery.
6. Enter the first dev account's email and a unique password. Choose **Auto Confirm
   User** if offered, then create it. This account won't need a confirmation email.
7. Repeat for a second dev account, with a different email and password. Keep both
   sets of credentials private; do not paste them into SQL, Git, or chat.
8. Open each user and copy its **User UID / ID** somewhere local for step 4 below.
   These are account identifiers, not passwords. Do not commit personalized SQL.
9. Find **JWT Signing Keys** under project settings (it may be grouped under
   **JWT Keys**). Note ONLY the current algorithm, for example ES256 or RS256.
   Do not copy keys/secrets or rotate anything. If it says HS256, tell me only
   that algorithm at the gate so the backend uses the documented fallback.

Supabase confirms that turning signup off still permits existing users to log in:
[general configuration](https://supabase.com/docs/guides/auth/general-configuration).
[Password login](https://supabase.com/docs/guides/auth/passwords) is separate from
email confirmation/reset delivery. Dashboard user management is documented
[here](https://supabase.com/docs/guides/auth/managing-user-data).

## 3. Run the migration once

1. Open the local file `supabase/migrations/202611080001_initial_multi_user.sql`
   and read the comments. Copy the entire file.
2. In **incline-dev**, click **SQL Editor → New query** (the `+` button).
3. Paste the whole file. Use the administrative **postgres** role and primary
   database connection in the editor, not a browser anon/authenticated role.
4. Click **Run**. Run the entire file, not a highlighted subset.
5. Expect a success result, typically **Success. No rows returned**. It creates
   empty `public.exercises` and `public.sets`, eight RLS policies, indexes, and the
   restricted `incline_api` role. It does not create/import lifting records.
6. In **Table Editor**, verify both tables exist and are empty. RLS should be on.
   The SQL editor is administrative: its ability to see tables is not an RLS test.

On any error, stop and report the error text with private values removed. If the
editor says the transaction is aborted, use a fresh editor connection or roll it
back before retrying an approved fix. Do not delete objects to make the file run.

## 4. Run the isolation test

1. Open `supabase/tests/202611080002_two_user_isolation.sql`; read and copy it.
2. In **SQL Editor → New query**, paste it and keep **postgres** selected. The
   script itself changes into `incline_api` for its isolation checks.
3. In THIS EDITOR COPY ONLY, replace `REPLACE_WITH_DEV_USER_A_UUID` and
   `REPLACE_WITH_DEV_USER_B_UUID` with the two User UIDs from Authentication.
   Leave the quote marks around each value. No passwords or tokens go here.
4. Click **Run** on the complete script. Expected denied operations are caught
   internally: success requires ALL tests to pass, in both user directions.
5. The final result must read exactly:
   **PASS: all Stage 1 isolation checks passed**.
6. Refresh **Table Editor**: both tables should still be empty. The test rolls
   back its records; it never deletes your Auth accounts or existing lifting
   records. Numeric ID sequences advance even on rollback, so gaps are normal.
7. If anything errors, do not continue to Stage 2. Keep the error message and
   report it with personal values removed. A failed transaction must be rolled
   back/reconnected; expected permission failures should NOT escape the script.

The test checks both owners' reads, edits, deletes, inserts, exercise links,
immutable ownership/IDs/dates, allowed own writes, limits, case-insensitive
uniqueness, missing identity, browser-role privileges, and cascade definitions.
It tests database permissions, not HTTP token verification; that comes in Stage 2.

## Token verification selected for Stage 2

For an asymmetric signing key, use **PyJWT to verify signatures against the
project's public JWKS endpoint**, with a bounded cache and checks for issuer,
audience, expiry, allowed algorithm, authenticated role, and a UUID subject.
JWKS is the project's published set of public verification keys; it contains no
private signing key. This follows Supabase's documented JWT-library verification
path and avoids copying a signing secret into the backend. No library is installed
in Stage 1. Supabase's getClaims helper is another supported route; we are choosing
the pre-approved JWT-library route instead of adding the Python Supabase SDK.

For a legacy HS256 project, use Supabase's Auth-server `/auth/v1/user` verification
rather than obtaining a shared signing secret, as its current docs recommend.
No unverified JWT claims will be used as an account identity.
[Verification guidance](https://supabase.com/docs/guides/auth/jwts),
[signing keys](https://supabase.com/docs/guides/auth/signing-keys).

## Stop here

Reply **both SQL files ran OK** (and optionally the signing algorithm only).
Do not send passwords, database URLs, access tokens, or keys. That reply opens
Gate 1. Until then, Stage 2 and all later stages remain unstarted.


## Gate 1 repair: custom role cannot use auth.uid()

Hosted Supabase protects its auth schema. `postgres` cannot grant its schema
access onward to incline_api, even if the GRANT appears to succeed. Therefore
`schema_access = false` and `helper_access = true` are expected for this role.
The earlier suggestion to repeat those grants was incorrect. Do not grant broad
roles or disable RLS. The corrected migration and test no longer call auth.uid()
as the restricted role: they read the verified sub from transaction-local claims.
[Supabase's explanation and claims-based solution](https://supabase.com/kb/troubleshooting/permission-errors-when-granting-custom-roles-access-to-the-auth-schema-9e32e7).

If the initial migration was already applied, do NOT rerun it. Instead:

1. In `incline-dev`, open **SQL Editor → New query**, with role **postgres**.
2. If the previous test left a failed transaction, run `ROLLBACK; RESET ROLE;`
   separately first. A warning that no transaction is in progress is harmless.
3. Paste and run this complete repair. It changes only the defaults and eight
   existing policies to match the corrected initial migration; it adds no tables,
   functions, or role memberships and does not delete or recreate any records.

```sql
-- Repair existing Incline tables only. Run as postgres in incline-dev.
-- No data is deleted; RLS stays enabled. Run this entire block.
BEGIN;
ALTER TABLE public.exercises ALTER COLUMN user_id SET DEFAULT ((nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid);
ALTER POLICY exercises_select_own ON public.exercises
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY exercises_insert_own ON public.exercises
    WITH CHECK (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY exercises_update_own ON public.exercises
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid))
    WITH CHECK (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY exercises_delete_own ON public.exercises
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER TABLE public.sets ALTER COLUMN user_id SET DEFAULT ((nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid);
ALTER POLICY sets_select_own ON public.sets
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY sets_insert_own ON public.sets
    WITH CHECK (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY sets_update_own ON public.sets
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid))
    WITH CHECK (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
ALTER POLICY sets_delete_own ON public.sets
    USING (user_id = (SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid));
COMMIT;
```

4. Expect **Success. No rows returned**.
5. Open the UPDATED local file `supabase/tests/202611080002_two_user_isolation.sql`.
   Copy it into a new SQL editor query; do not reuse the old editor copy.
6. Replace the two UUID placeholders with the same two dev User UIDs, in the editor
   only, and run the whole file. Expect **PASS: all Stage 1 isolation checks passed**.
7. Gate 1 stays closed until you report success. The schema-access diagnostic can
   remain false; access to the managed auth schema is no longer required.

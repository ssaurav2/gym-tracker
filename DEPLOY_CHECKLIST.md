# Gate 5 — you deploy Incline

The agent has prepared files only. No Vercel project, deployment, cloud SQL, or
actual SQLite import was run. Gate 4 passed: your local-only dry-run reported
**2 exercises and 8 sets**. Those rows are still only in the backup.

Start with the existing **dev Supabase project**. Deployment means publishing
code to a host; publishing code does not copy your SQLite records.

## 1. Review the two projects

| Vercel project | Root Directory | Configuration |
| --- | --- | --- |
| Incline backend | repository root (`./`) | root `vercel.json`; `pyproject.toml` loads `api:app` |
| Incline frontend | `frontend` | `frontend/vercel.json`; Vite builds `dist` |

A rewrite forwards a request without changing the address in your browser.
The four frontend API rewrites come before the single-page app fallback (which
serves `index.html` for page navigation). `/assets/` misses remain misses rather
than returning HTML. Both layers mark API responses `no-store`, meaning caches
must not save them. Existing Python already marks responses that way too.
[Vercel rewrites](https://vercel.com/docs/routing/rewrites),
[configuration reference](https://vercel.com/docs/project-configuration/vercel-json).

Root and frontend `.vercelignore` exclude database files, backups, photos, and
local env files from uploads. Backend `excludeFiles` adds bundle exclusions for
Git builds too. It also omits legacy/import/test code and the frontend; nothing
is deleted locally. Backend dependencies come from `pyproject.toml`; legacy
`requirements.txt` is excluded from upload/bundle, not edited. Check build logs
for which dependency manifest Vercel actually selects and for any install errors.
[Python entrypoints and bundles](https://vercel.com/docs/functions/runtimes/python),
[ignore file rules](https://vercel.com/docs/deployments/vercel-ignore).

## 2. Gather settings privately

Use Vercel's environment-variable form, never source code or chat. An environment
variable is a named setting supplied to a running application.

| Variable name | Project | Value to obtain privately |
| --- | --- | --- |
| DATABASE_URL | Backend ONLY | Supabase shared transaction pooler, restricted `incline_api.PROJECT_REF` login, port 6543 |
| SUPABASE_URL | Backend | HTTPS project origin |
| SUPABASE_JWT_ALGORITHM | Backend | Actual project signing algorithm: ES256, RS256, or legacy HS256 |
| SUPABASE_PUBLISHABLE_KEY | Backend | Publishable key; required for HS256 Auth-server verification |
| VITE_SUPABASE_URL | Frontend | Same HTTPS project origin |
| VITE_SUPABASE_PUBLISHABLE_KEY | Frontend | Same public `sb_publishable_` key |

Use the **same Supabase project** for every row. Copy the working Gate 2 backend
settings privately. The API requires the restricted role, not postgres. It uses
TLS (encrypted connections), one pooled connection per running function instance,
transaction-local identity, and `prepare_threshold=None`; no changes are needed.
Do not deploy `IMPORT_DATABASE_URL`, `IMPORT_USER_ID`, `TEST_USER_*`, or
`INCLINE_RUN_DEV_TESTS`. Never deploy a service-role/secret key to the frontend.
Vite embeds its public settings into downloaded JavaScript; changing them requires
a new build.

## 3. Create the backend project yourself

1. Save/push this reviewed branch to your Git host yourself. No push is done by
   the agent. Keep `.env`, databases, and photos ignored; never upload them.
2. In Vercel, choose **Add New → Project → Import Git Repository** and select
   this repository. Name the project, for example `incline-api-dev`.
3. Set **Root Directory** to the repository root. Select the **FastAPI** preset.
   Leave the build/install/output overrides at their framework defaults.
   Do not use Uvicorn as a build command. `api:app` is already explicit so the
   preserved terminal `app.py` is not selected.
4. Add the backend-only variables above. For this rehearsal select only the
   environments you intend to use with the dev project. Do not populate a real
   production environment with test credentials or point test previews at real data.
5. Check the deployment source branch is `multi-user` before clicking Deploy.
   If the import screen cannot select it, stop and ask for help rather than
   deploying the default branch. For an existing project, change its Production
   Branch under **Settings → Git / Environments** before creating the deployment.
   In Vercel terminology
   a dev rehearsal project can still have a “Production” environment: its settings
   must point to **dev Supabase**, not your future production database.
6. Choose **Deploy** yourself. Inspect build logs: correct Python dependencies,
   `api.py` function, and no migration/import commands. If the build fails, stop
   and share only a sanitized error; don't paste environment values or raw logs
   containing credentials.
7. Open **Settings → Functions → Function Region**. Choose the supported region
   nearest your **Supabase database**, not necessarily nearest your phone, then
   redeploy if requested. Examples: `iad1` for US East, `sfo1` for US West. No region
   is pinned in the file because your database region isn't known. Alternatively
   set the root `regions` array after checking the actual database location.
   [Vercel regions](https://vercel.com/docs/functions/configuring-functions/region).
8. Copy the backend's stable HTTPS project address from its Domains page.
   Opening `/exercises` without a token must give a JSON **401**, not a login
   page or terminal output. The backend root `/` returning JSON 404 is normal.
9. If Vercel Deployment Protection intercepts requests, external rewrites cannot
   use the API until that is resolved. For this two-project setup, make the
   selected backend deployment publicly reachable in **Settings → Deployment
   Protection**, while keeping Supabase token checks fully enabled. Test the
   chosen URL privately in an incognito browser. Do not put a protection-bypass
   secret in `vercel.json`, a URL, or frontend variables. If you want to retain
   backend Vercel protection, stop for a separate server-side forwarding design.

## 4. Fill the forwarding address, then create the frontend

1. Open `frontend/vercel.json`. Replace **all four** occurrences of
   `https://incline-api.example.invalid` with the backend HTTPS origin from step 3,
   without a trailing slash. Keep each `/exercises`, `/sets`, and `/:path*` suffix.
   The reserved `.invalid` placeholder deliberately cannot reach a real service.
   Don't replace it with the frontend address (that would forward to itself).
2. Save, review, commit, and push that non-secret URL change yourself. Confirm
   all four destinations are for the intended dev backend. Plain JSON rewrites
   do not interpolate a `BACKEND_URL` environment variable.
3. In Vercel, **Add New → Project → Import** the same repository a second time.
   Name it, for example `incline-web-dev`. Set **Root Directory: frontend**.
4. Select **Vite**, **Build Command: npm run build**, **Output Directory: dist**,
   and the normal package-lock install default. Use a supported Node version
   compatible with Vite 7 (Node 22.12+). Do not install a Vercel CLI locally.
5. Leave “include source files outside the Root Directory” disabled. Add ONLY
   the two `VITE_` variables above for the intended environment. Set the branch
   to `multi-user` for this rehearsal, matching the backend.
6. Choose **Deploy** yourself. Open the frontend address; the login screen should
   appear. That is the single address you and friends use. The backend retains its
   own technical URL, but browser API calls stay on the frontend origin, so no
   FastAPI CORS setup is needed. CORS is the browser's cross-address permission
   system. Don't replace the frontend's relative API calls with the backend URL.

## 5. Supabase login settings and friends

1. Open the matching Supabase project → **Authentication → URL Configuration**.
   Set **Site URL** to the frontend HTTPS origin. Under **Redirect URLs**, add
   the exact frontend URL you use and local `http://localhost:5173/` if needed.
   Add exact preview URLs only when needed; avoid broad production wildcards.
   Password login currently stays on the page; these settings prepare allowed
   return destinations, not a new signup/reset flow.
   [Supabase return URLs](https://supabase.com/docs/guides/auth/redirect-urls).
2. Under **Authentication → Sign In / Providers** (or the Auth general settings),
   turn **Allow new users to sign up OFF** and **anonymous sign-ins OFF**. Leave
   email/password login enabled. Public signup must stay disabled even though
   the app has no signup button.
   [Supabase access settings](https://supabase.com/docs/guides/auth/general-configuration).
3. Under **Authentication → Users → Add user → Create new user**, enter each
   friend's email and a strong password privately. Use the **Auto Confirm User**
   option for these manually managed accounts, then create the user. Choose
   **Create new user**, not the email invitation flow. If dashboard labels differ,
   find the manual email/password creation option; don't enable public signup.
4. Share credentials privately, never in this repo/chat. No custom email provider,
   invitation handling, password-reset UI, or social login is part of this release.
   Each friend starts with an empty exercise list. Don't change RLS or grant data
   access to browser roles to make an account work.

## 6. Preview and real production separation

For now keep BOTH projects paired with dev Supabase. A stable dev-backend alias
means all frontend previews with that configuration share the dev database.
Only use that arrangement for testing. Review automatic Git deployment settings:
a later push may deploy code after you connect the repository.

Before a real launch, configure an explicit production frontend/backend pairing
and production Supabase settings, using only a schema you have reviewed/applied
manually. Don't rerun initial SQL in the already configured dev project. On
branches with previews, keep the committed forwarding origin pointed at a dev
backend, or disable those previews until separate environment-aware forwarding is
reviewed. Changing frontend variables alone does NOT change its rewrite target.
Never let a preview forward writes to the production backend by accident.

## 7. Final checks — do these on the deployed dev address

- [ ] Login A, create an exercise, log a set, check “last time” and History.
- [ ] Login B in a separate private browser: A's records must never appear.
- [ ] Alternate reads in A/B repeatedly; responses must not switch accounts.
- [ ] Edit weight/reps, cancel a deletion, then confirm deletion of a disposable
      test set only. Refresh and check the result. Use each account's own data.
- [ ] History filtering/day headings and local logging dates remain correct.
- [ ] Logout/account switch clears History, last entry, drafts, and timer. Refresh
      preserves the correct current account or shows login when logged out.
- [ ] Browser Network shows `/exercises`, `/sets`, and last-set subpaths on the
      FRONTEND address; responses are JSON, not index.html or Vercel login HTML.
      GET/POST/PUT/DELETE work through forwarding with their request bodies.
- [ ] Unauthenticated GET/POST/PUT/DELETE API calls return 401. Invalid inputs
      return API errors, and another user's IDs return 404 without changing data.
      Inspect status/result privately; never paste bearer tokens into chat.
- [ ] Query filters such as `/sets?exercise_id=...` survive forwarding. Errors
      remain API errors rather than being rewritten into a successful HTML page.
- [ ] API replies (including 401/404/422 and 204 deletion) show `Cache-Control:
      no-store`. No user-data response shows a CDN cache HIT. Vercel may consume
      its own CDN-control header internally rather than displaying it to browsers.
- [ ] Refresh `/` and a page path: app loads; compiled JS/CSS load correctly.
- [ ] On the backend address, `/gym_tracker.db`, `/backups/...`, `/private/...`,
      `/.env`, and `/photos` do not serve files. Frontend equivalents may hit its
      page fallback, but must never contain file contents. Inspect function bundle
      files/build output where Vercel exposes them; these URL checks alone cannot
      prove sensitive files were excluded from the bundle.
- [ ] Phone: login, log, timer, History edit/delete, fixed bottom navigation.
- [ ] Review Vercel/Supabase usage and function limits before inviting friends.

STOP at Gate 5 and report your deployment/test results. The actual SQLite import
still needs separate approval; don't append `--confirm` as part of deployment.
If something fails, keep using the local app while we inspect it. Do not delete
cloud data or rerun schema/import scripts as a deployment repair.

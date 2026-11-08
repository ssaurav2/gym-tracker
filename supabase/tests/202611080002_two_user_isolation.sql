-- Incline: manual Stage 1 isolation test. Codex has NOT run this file.
-- Run AFTER the initial migration, as postgres, on your DEV Supabase project.
-- Create two test accounts through Authentication > Users > Add user > Create
-- new user first. Replace ONLY the two UUID placeholders below in the SQL editor.
-- Do not enter passwords, tokens, keys, or connection strings in this file/chat.
--
-- This creates only temporary test lifting records, NOT Auth accounts. Every
-- lifting change is inside the transaction that ends in ROLLBACK. It never
-- deletes an account or targets pre-existing lifting records. Identity sequences
-- still advance on rollback; harmless gaps in numeric IDs are expected.
-- On success the final result is: PASS: all Stage 1 isolation checks passed.
-- On ANY ERROR, stop, roll back/reconnect the editor, and report the error text
-- after removing private identifiers. Do not skip a failed check or continue.
BEGIN;

SELECT set_config('incline_test.user_a', 'REPLACE_WITH_DEV_USER_A_UUID', true);
SELECT set_config('incline_test.user_b', 'REPLACE_WITH_DEV_USER_B_UUID', true);

-- Refuse to run with missing/identical accounts or a privileged runtime role.
DO $preflight$
DECLARE
    user_a uuid := current_setting('incline_test.user_a')::uuid;
    user_b uuid := current_setting('incline_test.user_b')::uuid;
BEGIN
    IF user_a = user_b THEN
        RAISE EXCEPTION 'FAIL: use two different dev accounts.';
    END IF;
    IF (SELECT count(*) FROM auth.users WHERE id IN (user_a, user_b)) <> 2 THEN
        RAISE EXCEPTION 'FAIL: create both dev accounts in Authentication > Users first.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'incline_api' AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolcanlogin
    ) THEN
        RAISE EXCEPTION 'FAIL: expected the restricted NOLOGIN incline_api role.';
    END IF;
    IF (SELECT count(*) FROM pg_class
        WHERE oid IN ('public.exercises'::regclass, 'public.sets'::regclass)
          AND relrowsecurity AND relforcerowsecurity) <> 2 THEN
        RAISE EXCEPTION 'FAIL: both tables need enabled and forced RLS.';
    END IF;
    IF (SELECT count(*) FROM pg_constraint
        WHERE conname IN ('exercises_owner_fk', 'sets_owner_fk')
          AND conrelid IN ('public.exercises'::regclass, 'public.sets'::regclass)
          AND confrelid = 'auth.users'::regclass AND confdeltype = 'c') <> 2 THEN
        RAISE EXCEPTION 'FAIL: both account links must cascade on account deletion.';
    END IF;
END;
$preflight$;

-- This temporary ledger holds fixture IDs, so tests never target real records.
CREATE TEMP TABLE incline_test_fixtures (
    user_id uuid PRIMARY KEY,
    exercise_id bigint NOT NULL,
    set_id bigint NOT NULL
) ON COMMIT DROP;

-- Seed random-named fixtures as admin. Both accounts use the SAME exercise name;
-- this proves that uniqueness is per owner, not global. No auth.users writes.
DO $fixtures$
DECLARE
    exercise_name text := 'Incline test ' || gen_random_uuid()::text;
    owner_id uuid;
    exercise_key bigint;
    set_key bigint;
BEGIN
    FOREACH owner_id IN ARRAY ARRAY[
        current_setting('incline_test.user_a')::uuid,
        current_setting('incline_test.user_b')::uuid
    ] LOOP
        INSERT INTO public.exercises (user_id, name)
        VALUES (owner_id, exercise_name) RETURNING id INTO exercise_key;
        INSERT INTO public.sets (user_id, exercise_id, weight, reps, date)
        VALUES (owner_id, exercise_key, 100, 8, (now() AT TIME ZONE 'UTC')::date)
        RETURNING id INTO set_key;
        INSERT INTO incline_test_fixtures VALUES (owner_id, exercise_key, set_key);
    END LOOP;
END;
$fixtures$;
GRANT SELECT ON TABLE incline_test_fixtures TO incline_api;

-- All isolation checks below run as the real restricted role, NOT as postgres.
SET LOCAL ROLE incline_api;
DO $isolation$
DECLARE
    mine record;
    theirs record;
    affected bigint;
    probe_exercise bigint;
    probe_set bigint;
BEGIN
    IF current_user <> 'incline_api' THEN
        RAISE EXCEPTION 'FAIL: tests must run under incline_api.';
    END IF;

    -- Repeat in both directions: A cannot affect B, and B cannot affect A.
    FOR mine IN SELECT * FROM incline_test_fixtures ORDER BY user_id LOOP
        SELECT * INTO STRICT theirs FROM incline_test_fixtures WHERE user_id <> mine.user_id;
        -- Clear the legacy sub setting before setting modern claims. No session state.
        PERFORM set_config('request.jwt.claim.sub', '', true);
        PERFORM set_config('request.jwt.claims', json_build_object('sub', mine.user_id, 'role', 'authenticated')::text, true);
        IF auth.uid() IS DISTINCT FROM mine.user_id THEN
            RAISE EXCEPTION 'FAIL: simulated identity does not match.';
        END IF;

        -- Own records are visible; other-owner records are invisible.
        IF NOT EXISTS (SELECT 1 FROM public.exercises WHERE id = mine.exercise_id)
           OR NOT EXISTS (SELECT 1 FROM public.sets WHERE id = mine.set_id) THEN
            RAISE EXCEPTION 'FAIL: own records must be visible.';
        END IF;
        IF EXISTS (SELECT 1 FROM public.exercises WHERE user_id <> mine.user_id)
           OR EXISTS (SELECT 1 FROM public.sets WHERE user_id <> mine.user_id) THEN
            RAISE EXCEPTION 'FAIL: cross-user reads were allowed.';
        END IF;

        UPDATE public.exercises SET name = 'Must not change' WHERE id = theirs.exercise_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 0 THEN RAISE EXCEPTION 'FAIL: cross-user exercise edit.'; END IF;
        UPDATE public.sets SET weight = 101 WHERE id = theirs.set_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 0 THEN RAISE EXCEPTION 'FAIL: cross-user set edit.'; END IF;
        DELETE FROM public.sets WHERE id = theirs.set_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 0 THEN RAISE EXCEPTION 'FAIL: cross-user set delete.'; END IF;
        DELETE FROM public.exercises WHERE id = theirs.exercise_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 0 THEN RAISE EXCEPTION 'FAIL: cross-user exercise delete.'; END IF;

        -- Expected failures are caught narrowly; an unexpected success raises FAIL.
        BEGIN
            INSERT INTO public.sets (user_id, exercise_id, weight, reps, date)
            VALUES (mine.user_id, theirs.exercise_id, 100, 8, CURRENT_DATE);
            RAISE EXCEPTION 'FAIL: cross-user exercise link was allowed.';
        EXCEPTION WHEN foreign_key_violation THEN NULL;
        END;
        BEGIN
            INSERT INTO public.exercises (user_id, name)
            VALUES (theirs.user_id, 'Must not insert');
            RAISE EXCEPTION 'FAIL: inserting another owner exercise was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            INSERT INTO public.sets (user_id, exercise_id, weight, reps, date)
            VALUES (theirs.user_id, theirs.exercise_id, 100, 8, CURRENT_DATE);
            RAISE EXCEPTION 'FAIL: inserting another owner set was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            UPDATE public.exercises SET user_id = theirs.user_id WHERE id = mine.exercise_id;
            RAISE EXCEPTION 'FAIL: exercise ownership change was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET user_id = theirs.user_id WHERE id = mine.set_id;
            RAISE EXCEPTION 'FAIL: set ownership change was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET exercise_id = theirs.exercise_id WHERE id = mine.set_id;
            RAISE EXCEPTION 'FAIL: changing the exercise link was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET date = CURRENT_DATE - 5 WHERE id = mine.set_id;
            RAISE EXCEPTION 'FAIL: changing the original set date was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET id = id + 1 WHERE id = mine.set_id;
            RAISE EXCEPTION 'FAIL: changing a set ID was allowed.';
        EXCEPTION WHEN insufficient_privilege THEN NULL;
        END;
        BEGIN
            INSERT INTO public.exercises (name)
            SELECT upper(name) FROM public.exercises WHERE id = mine.exercise_id;
            RAISE EXCEPTION 'FAIL: same-owner case-insensitive duplicate was allowed.';
        EXCEPTION WHEN unique_violation THEN NULL;
        END;

        -- Own writes must work too; a deny-everything policy would fail here.
        INSERT INTO public.exercises (name) VALUES ('Own write ' || gen_random_uuid()::text)
        RETURNING id INTO probe_exercise;
        INSERT INTO public.sets (exercise_id, weight, reps, date)
        VALUES (probe_exercise, 10000, 1000, CURRENT_DATE) RETURNING id INTO probe_set;
        UPDATE public.sets SET weight = 100, reps = 8 WHERE id = probe_set;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN RAISE EXCEPTION 'FAIL: own set edit was blocked.'; END IF;
        UPDATE public.exercises SET name = 'Edited ' || gen_random_uuid()::text WHERE id = probe_exercise;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN RAISE EXCEPTION 'FAIL: own exercise edit was blocked.'; END IF;

        BEGIN
            UPDATE public.sets SET weight = 10001 WHERE id = probe_set;
            RAISE EXCEPTION 'FAIL: overweight value was allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET weight = 'NaN'::numeric WHERE id = probe_set;
            RAISE EXCEPTION 'FAIL: NaN weight was allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET weight = 0 WHERE id = probe_set;
            RAISE EXCEPTION 'FAIL: zero weight was allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET reps = 1001 WHERE id = probe_set;
            RAISE EXCEPTION 'FAIL: too many reps were allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.sets SET reps = 0 WHERE id = probe_set;
            RAISE EXCEPTION 'FAIL: zero reps were allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.exercises SET name = repeat('x', 121) WHERE id = probe_exercise;
            RAISE EXCEPTION 'FAIL: too-long name was allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.exercises SET name = '   ' WHERE id = probe_exercise;
            RAISE EXCEPTION 'FAIL: blank name was allowed.';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        -- Only deletes a test record created immediately above, and rolls back.
        DELETE FROM public.sets WHERE id = probe_set;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN RAISE EXCEPTION 'FAIL: own set delete was blocked.'; END IF;
        DELETE FROM public.exercises WHERE id = probe_exercise;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN RAISE EXCEPTION 'FAIL: own exercise delete was blocked.'; END IF;
    END LOOP;

    -- Missing identity exposes no rows and cannot create records.
    PERFORM set_config('request.jwt.claim.sub', '', true);
    PERFORM set_config('request.jwt.claims', '{}', true);
    IF EXISTS (SELECT 1 FROM public.exercises) OR EXISTS (SELECT 1 FROM public.sets) THEN
        RAISE EXCEPTION 'FAIL: missing identity exposed data.';
    END IF;
    BEGIN
        INSERT INTO public.exercises (user_id, name) VALUES (mine.user_id, 'No identity');
        RAISE EXCEPTION 'FAIL: missing identity could insert.';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END;
$isolation$;
RESET ROLE;

-- Independently check that attacks did not modify or remove the seeded fixtures.
DO $verify$
DECLARE
    fixture record;
    browser_role text;
    target_table text;
BEGIN
    FOR fixture IN SELECT * FROM incline_test_fixtures LOOP
        IF NOT EXISTS (SELECT 1 FROM public.sets WHERE id = fixture.set_id
                       AND user_id = fixture.user_id AND weight = 100 AND reps = 8)
           OR NOT EXISTS (SELECT 1 FROM public.exercises WHERE id = fixture.exercise_id
                          AND user_id = fixture.user_id AND name LIKE 'Incline test %') THEN
            RAISE EXCEPTION 'FAIL: an isolation attack modified a fixture.';
        END IF;
    END LOOP;
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        FOREACH target_table IN ARRAY ARRAY['public.exercises', 'public.sets'] LOOP
            IF has_table_privilege(browser_role, target_table, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_any_column_privilege(browser_role, target_table, 'SELECT,INSERT,UPDATE,REFERENCES') THEN
                RAISE EXCEPTION 'FAIL: % has table/column access to %.', browser_role, target_table;
            END IF;
        END LOOP;
    END LOOP;
END;
$verify$;

ROLLBACK;
SELECT 'PASS: all Stage 1 isolation checks passed' AS result;

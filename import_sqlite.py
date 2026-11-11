"""Reviewed one-time import. Default dry-run is local-only; never edits SQLite.

Only main() can opt into a destination connection, and only with --confirm after
local validation succeeds. Keep import credentials separate from the API role.
All SQL identifiers are fixed strings; values use sqlite ? / Postgres %s binding.
"""
import argparse
import hashlib
import json
import math
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from local_env import load_local_env

LEGACY_DATABASE = Path(__file__).resolve().parent / 'gym_tracker.db'
MAX_ID = 9223372036854775806  # Leave room for the next generated bigint ID.


class ImportFailure(Exception):
    """Contains only an application-defined code, never raw database errors."""


@dataclass(frozen=True)
class Exercise:
    id: int
    name: str


@dataclass(frozen=True)
class LoggedSet:
    id: int
    exercise_id: int
    weight: Decimal
    reps: int
    date: date


@dataclass(frozen=True)
class Source:
    path: Path
    sha256: str
    exercises: tuple
    sets: tuple
    issues: tuple
    exercise_count: int
    set_count: int

    def report(self, owner):
        return {
            'status': 'blocked' if self.issues else 'dry_run_valid',
            'destination_contacted': False,
            'source_sha256': self.sha256,
            'target_user_id': str(owner),
            'source_counts': {'exercises': self.exercise_count, 'sets': self.set_count},
            'mapping': 'Original IDs, exercise links, values and dates retained; every user_id is IMPORT_USER_ID.',
            'issues': list(self.issues),
            'note': 'Local validation only; destination IDs/names and Postgres collation are checked only on an explicitly confirmed import.',
        }


def fingerprint(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_source(path):
    """Read a standalone backup as immutable/read-only; reject the live DB/aliases."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ImportFailure('source_file_missing')
    if LEGACY_DATABASE.exists() and path.samefile(LEGACY_DATABASE):
        raise ImportFailure('source_must_be_a_backup_copy_not_the_live_database')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-journal')):
        raise ImportFailure('source_must_be_a_standalone_backup_without_journals')
    before = fingerprint(path)
    try:
        # immutable prevents even journal/shared-memory writes. It is appropriate
        # ONLY for a detached, stable backup, never the actively used database.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ImportFailure('source_integrity_check_failed')
            exercise_columns = {row['name'] for row in db.execute('PRAGMA table_info(exercises)')}
            set_columns = {row['name'] for row in db.execute('PRAGMA table_info(sets)')}
            if not {'id', 'name'} <= exercise_columns or not {'id', 'exercise_id', 'weight', 'reps', 'date'} <= set_columns:
                raise ImportFailure('source_legacy_tables_or_columns_missing')
            if 'user_id' in exercise_columns or 'user_id' in set_columns:
                raise ImportFailure('source_already_has_owners_requires_separate_review')
            # Never select progress_photos or open any external photo path.
            exercises = [dict(row) for row in db.execute('SELECT id, name FROM exercises ORDER BY id')]
            sets = [dict(row) for row in db.execute('SELECT id, exercise_id, weight, reps, date FROM sets ORDER BY id')]
    except sqlite3.Error:
        raise ImportFailure('source_could_not_be_read_as_legacy_sqlite') from None
    if fingerprint(path) != before:
        raise ImportFailure('source_changed_during_read')
    return validate_source(path, before, exercises, sets)


def valid_id(value):
    return type(value) is int and 1 <= value <= MAX_ID


def validate_source(path, digest, exercise_rows, set_rows):
    issues, exercises, sets = [], [], []
    exercise_ids, set_ids = set(), set()
    names = defaultdict(list)

    def issue(table, position, code):
        # Positions identify source records without echoing names or invalid values.
        issues.append({'table': table, 'source_row': position, 'code': code})

    for position, row in enumerate(exercise_rows, 1):
        key, name = row['id'], row['name']
        good = True
        if not valid_id(key):
            issue('exercises', position, 'invalid_id'); good = False
        elif key in exercise_ids:
            issue('exercises', position, 'duplicate_id'); good = False
        else:
            exercise_ids.add(key)
        if not isinstance(name, str) or not name.strip():
            issue('exercises', position, 'blank_or_nontext_name'); good = False
        elif len(name) > 120:
            issue('exercises', position, 'name_exceeds_120_characters'); good = False
        elif name != name.strip():
            issue('exercises', position, 'name_has_surrounding_whitespace'); good = False
        else:
            # Conservative Unicode screening. PostgreSQL's exact lower()/collation
            # is additionally checked at the destination, before any insertion.
            names[name.casefold()].append(position)
        if good:
            exercises.append(Exercise(key, name))
    for positions in names.values():
        if len(positions) > 1:
            for position in positions:
                issue('exercises', position, 'case_insensitive_duplicate_name_review_required')

    for position, row in enumerate(set_rows, 1):
        good = True
        key, exercise_id = row['id'], row['exercise_id']
        if not valid_id(key):
            issue('sets', position, 'invalid_id'); good = False
        elif key in set_ids:
            issue('sets', position, 'duplicate_id'); good = False
        else:
            set_ids.add(key)
        if not valid_id(exercise_id) or exercise_id not in exercise_ids:
            issue('sets', position, 'missing_or_invalid_exercise_link'); good = False
        weight = row['weight']
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 < weight <= 10000:
            issue('sets', position, 'weight_must_be_finite_and_greater_than_0_to_10000'); good = False
        reps = row['reps']
        if type(reps) is not int or not 1 <= reps <= 1000:
            issue('sets', position, 'reps_must_be_integer_1_to_1000'); good = False
        try:
            if not isinstance(row['date'], str):
                raise ValueError()
            logged_date = date.fromisoformat(row['date'])
            if logged_date.isoformat() != row['date']:
                raise ValueError()
        except ValueError:
            issue('sets', position, 'date_must_be_valid_yyyy_mm_dd'); good = False
        if good:
            sets.append(LoggedSet(key, exercise_id, Decimal(str(weight)), reps, logged_date))
    return Source(path, digest, tuple(exercises), tuple(sets), tuple(issues), len(exercise_rows), len(set_rows))


# Queries are fixed rather than constructed from table names or user values.
TABLES = {
    'exercises': {
        'rows': 'SELECT id, user_id, name FROM public.exercises WHERE id = ANY(%s::bigint[])',
        'counts': 'SELECT count(*) AS total, count(*) FILTER (WHERE user_id = %s) AS owned FROM public.exercises',
        'max': 'SELECT max(id) AS max_id FROM public.exercises',
        'sequence': 'public.exercises_id_seq',
        'state': 'SELECT last_value, is_called FROM public.exercises_id_seq',
    },
    'sets': {
        'rows': 'SELECT id, user_id, exercise_id, weight, reps, date FROM public.sets WHERE id = ANY(%s::bigint[])',
        'counts': 'SELECT count(*) AS total, count(*) FILTER (WHERE user_id = %s) AS owned FROM public.sets',
        'max': 'SELECT max(id) AS max_id FROM public.sets',
        'sequence': 'public.sets_id_seq',
        'state': 'SELECT last_value, is_called FROM public.sets_id_seq',
    },
}


def expected_exercise(row, owner):
    return {'id': row.id, 'user_id': owner, 'name': row.name}


def expected_set(row, owner):
    return {'id': row.id, 'user_id': owner, 'exercise_id': row.exercise_id,
            'weight': row.weight, 'reps': row.reps, 'date': row.date}


def destination_rows(connection, table, source_rows):
    return {row['id']: dict(row) for row in connection.execute(TABLES[table]['rows'],
                                                             ([row.id for row in source_rows],)).fetchall()}


def check_sequences(connection):
    for table in TABLES.values():
        row = connection.execute('SELECT seqincrement, seqcache, seqcycle FROM pg_catalog.pg_sequence WHERE seqrelid = %s::regclass',
                                 (table['sequence'],)).fetchone()
        if not row or row['seqincrement'] != 1 or row['seqcache'] != 1 or row['seqcycle']:
            raise ImportFailure('destination_sequence_settings_require_review')
        maximum = connection.execute(table['max']).fetchone()['max_id']
        if maximum is not None and maximum > MAX_ID:
            raise ImportFailure('destination_has_no_available_next_id')


def align_sequences(connection):
    """Advance only, including IDs owned by OTHER users and rolled-back allocations.

    setval is not transactional in Postgres: a failed import may leave safe gaps,
    never a backward counter or partial lifting rows. Normal INSERTs must remain
    paused; the transaction holds write locks on both tables throughout.
    """
    advanced = []
    for name, table in TABLES.items():
        maximum = connection.execute(table['max']).fetchone()['max_id']
        state = connection.execute(table['state']).fetchone()
        if maximum is not None and (maximum > state['last_value'] or
                                    (maximum == state['last_value'] and not state['is_called'])):
            connection.execute('SELECT pg_catalog.setval(%s::regclass, %s, true)',
                               (table['sequence'], maximum))
            advanced.append(name)
    return advanced


def import_destination(connection, source, owner):
    """Only called by --confirm. Uses one transaction; no update/delete/upsert/DDL."""
    if source.issues:
        raise ImportFailure('source_validation_failed')
    if fingerprint(source.path) != source.sha256:
        raise ImportFailure('source_changed_before_import')
    result = source.report(owner)
    result['destination_contacted'] = True
    with connection.transaction():
        connection.execute('SELECT set_config(%s, %s, true)', ('lock_timeout', '5000'))
        connection.execute('SELECT set_config(%s, %s, true)', ('statement_timeout', '30000'))
        if connection.execute('SELECT current_user AS name').fetchone()['name'] != 'postgres':
            raise ImportFailure('import_requires_separate_admin_connection_not_runtime_role')
        if not connection.execute('SELECT EXISTS (SELECT 1 FROM auth.users WHERE id = %s) AS present', (owner,)).fetchone()['present']:
            raise ImportFailure('target_account_not_found')
        # Block concurrent imports/API writes while checking IDs, inserting, and
        # aligning counters. Ordinary reads may continue. No schema/RLS changes.
        connection.execute('LOCK TABLE public.exercises, public.sets IN SHARE ROW EXCLUSIVE MODE')
        check_sequences(connection)
        before = {name: connection.execute(table['counts'], (owner,)).fetchone() for name, table in TABLES.items()}
        exercise_rows = destination_rows(connection, 'exercises', source.exercises)
        set_rows = destination_rows(connection, 'sets', source.sets)
        conflicts = []
        new_exercises, new_sets = [], []
        source_names = connection.execute('SELECT name, lower(name) AS name_key FROM unnest(%s::text[]) AS source(name)',
                                          ([row.name for row in source.exercises],)).fetchall()
        name_keys = {row['name']: row['name_key'] for row in source_names}
        existing_names = {row['name_key']: row['id'] for row in connection.execute(
            'SELECT id, lower(name) AS name_key FROM public.exercises WHERE user_id = %s', (owner,)).fetchall()}
        planned_names = {}
        for row in source.exercises:
            actual = exercise_rows.get(row.id)
            normalized = name_keys[row.name]
            if actual is not None and actual != expected_exercise(row, owner):
                conflicts.append({'table': 'exercises', 'source_id': row.id, 'code': 'destination_id_conflict'})
            elif normalized in existing_names and existing_names[normalized] != row.id:
                conflicts.append({'table': 'exercises', 'source_id': row.id, 'code': 'destination_name_conflict'})
            elif normalized in planned_names:
                conflicts.append({'table': 'exercises', 'source_id': row.id, 'code': 'postgres_collation_duplicate'})
            elif actual is None:
                new_exercises.append(row)
            planned_names[normalized] = row.id
        for row in source.sets:
            actual = set_rows.get(row.id)
            if actual is not None and actual != expected_set(row, owner):
                conflicts.append({'table': 'sets', 'source_id': row.id, 'code': 'destination_id_or_values_conflict'})
            elif actual is None:
                new_sets.append(row)
        if conflicts:
            return {**result, 'status': 'blocked', 'issues': conflicts, 'inserted': {'exercises': 0, 'sets': 0}}

        for row in new_exercises:
            connection.execute('INSERT INTO public.exercises (id, user_id, name) VALUES (%s, %s, %s)',
                               (row.id, owner, row.name))
        for row in new_sets:
            connection.execute('INSERT INTO public.sets (id, user_id, exercise_id, weight, reps, date) VALUES (%s, %s, %s, %s, %s, %s)',
                               (row.id, owner, row.exercise_id, row.weight, row.reps, row.date))
        inserted = {'exercises': len(new_exercises), 'sets': len(new_sets)}
        expected_rows = {
            'exercises': {row.id: expected_exercise(row, owner) for row in source.exercises},
            'sets': {row.id: expected_set(row, owner) for row in source.sets},
        }
        verified_counts = {}
        for name, rows in (('exercises', source.exercises), ('sets', source.sets)):
            if destination_rows(connection, name, rows) != expected_rows[name]:
                raise ImportFailure('destination_record_verification_failed')
            counts = connection.execute(TABLES[name]['counts'], (owner,)).fetchone()
            if any(counts[key] != before[name][key] + inserted[name] for key in ('total', 'owned')):
                raise ImportFailure('destination_count_verification_failed')
            verified_counts[name] = counts
        if fingerprint(source.path) != source.sha256:
            raise ImportFailure('source_changed_during_import')
        advanced = align_sequences(connection)
        # Returned only after the transaction manager has committed successfully.
        result.update(status='imported' if any(inserted.values()) else 'already_present', issues=[],
                      inserted=inserted,
                      unchanged={'exercises': len(source.exercises) - len(new_exercises), 'sets': len(source.sets) - len(new_sets)},
                      verified_destination_counts=verified_counts, counters_advanced=advanced)
    return result


def connect_destination(url):
    try:
        settings = conninfo_to_dict(url)
    except psycopg.Error:
        raise ImportFailure('import_database_url_invalid') from None
    user = settings.get('user', '')
    if not url or not settings.get('host') or settings.get('port', '5432') != '5432' or not (user == 'postgres' or user.startswith('postgres.')):
        raise ImportFailure('import_requires_admin_direct_or_session_connection_on_5432')
    return psycopg.connect(url, autocommit=True, sslmode='require', prepare_threshold=None,
                           row_factory=dict_row, connect_timeout=10)


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown argument values; never echo a pasted URL.
        raise ImportFailure('invalid_arguments_use_help')


def main(argv=None):
    try:
        parser = PrivateArgumentParser(description=__doc__)
        parser.add_argument('--source', required=True, help='Path to a standalone SQLite BACKUP COPY (never the live database).')
        parser.add_argument('--confirm', action='store_true', help='Explicitly connect and import; default is local-only dry-run.')
        args = parser.parse_args(argv)
        load_local_env()
        try:
            owner = UUID(os.environ.get('IMPORT_USER_ID', ''))
        except ValueError:
            raise ImportFailure('set_import_user_id_to_the_target_account_uuid') from None
        source = read_source(args.source)
        result = source.report(owner)
        if args.confirm and not source.issues:
            # Never reads the admin URL or contacts Postgres in the dry-run path.
            with connect_destination(os.environ.get('IMPORT_DATABASE_URL', '')) as connection:
                result = import_destination(connection, source, owner)
        print(json.dumps(result, indent=2))
        return 2 if result['status'] == 'blocked' else 0
    except ImportFailure as error:
        print(json.dumps({'status': 'stopped', 'code': error.args[0]}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'code': 'review_destination_before_retrying_if_confirm_was_used'}))
        return 130
    except Exception:
        # Exception strings/tracebacks can include passwords, URLs or private rows.
        # A lost commit acknowledgement is ambiguous; exact-row reruns are safe.
        print(json.dumps({'status': 'stopped', 'code': 'operation_failed_no_private_details_printed',
                          'note': 'If --confirm was used, review destination state before retrying; a lost connection does not prove the commit failed.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

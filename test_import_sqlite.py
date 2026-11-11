"""Offline importer checks: disposable SQLite fixtures and an in-memory destination."""
import copy
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager, nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import import_sqlite as imp

OWNER = UUID('00000000-0000-4000-8000-000000000001')
OTHER = UUID('00000000-0000-4000-8000-000000000002')


class Cursor:
    def __init__(self, rows=()):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class Destination:
    def __init__(self):
        self.rows = {'exercises': {}, 'sets': {}}
        self.sequences = {name: {'last_value': 1, 'is_called': False} for name in imp.TABLES}
        self.present = True
        self.role = 'postgres'
        self.corrupt = False
        self.writes = 0
        self.commit_failure = False

    @contextmanager
    def transaction(self):
        before = copy.deepcopy(self.rows)
        try:
            yield
            if self.commit_failure:
                raise RuntimeError('private commit error')
        except Exception:
            self.rows = before
            raise

    def execute(self, query, params=()):
        if query.startswith('SELECT set_config') or query.startswith('LOCK TABLE'):
            return Cursor()
        if query == 'SELECT current_user AS name':
            return Cursor([{'name': self.role}])
        if 'FROM auth.users' in query:
            return Cursor([{'present': self.present}])
        if 'FROM pg_catalog.pg_sequence' in query:
            return Cursor([{'seqincrement': 1, 'seqcache': 1, 'seqcycle': False}])
        if 'FROM unnest' in query:
            return Cursor([{'name': name, 'name_key': name.lower()} for name in params[0]])
        if query.startswith('SELECT id, lower(name)'):
            return Cursor([{'id': r['id'], 'name_key': r['name'].lower()} for r in self.rows['exercises'].values() if r['user_id'] == params[0]])
        if query.startswith('SELECT pg_catalog.setval'):
            name = next(name for name, spec in imp.TABLES.items() if spec['sequence'] == params[0])
            self.sequences[name] = {'last_value': params[1], 'is_called': True}
            return Cursor()
        for name, spec in imp.TABLES.items():
            rows = list(self.rows[name].values())
            if query == spec['max']:
                return Cursor([{'max_id': max(self.rows[name], default=None)}])
            if query == spec['state']:
                return Cursor([dict(self.sequences[name])])
            if query == spec['counts']:
                return Cursor([{'total': len(rows), 'owned': sum(r['user_id'] == params[0] for r in rows)}])
            if query == spec['rows']:
                result = [dict(r) for r in rows if r['id'] in params[0]]
                if self.corrupt and self.writes and result:
                    result[0]['user_id'] = OTHER
                return Cursor(result)
            if query.startswith('INSERT INTO public.' + name + ' '):
                columns = ('id', 'user_id', 'name') if name == 'exercises' else ('id', 'user_id', 'exercise_id', 'weight', 'reps', 'date')
                self.rows[name][params[0]] = dict(zip(columns, params))
                self.writes += 1
                return Cursor()
        raise AssertionError('Unexpected fixed query')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'backup.db'
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('CREATE TABLE exercises(id INTEGER, name TEXT); CREATE TABLE sets(id INTEGER, exercise_id INTEGER, weight REAL, reps INTEGER, date TEXT); CREATE TABLE progress_photos(private_value TEXT);')
            db.execute('INSERT INTO exercises VALUES (?, ?)', (7, 'Squat'))
            db.execute('INSERT INTO sets VALUES (?, ?, ?, ?, ?)', (12, 7, 155.5, 8, '2020-01-02'))
            db.commit()
        self.source = imp.read_source(self.path)

    def cli(self, args, **patches):
        output = io.StringIO()
        with patch.object(imp, 'load_local_env'), patch.dict(os.environ, {'IMPORT_USER_ID': str(OWNER)}, clear=True), redirect_stdout(output):
            with (patch.multiple(imp, **patches) if patches else nullcontext()):
                code = imp.main(args)
        return code, json.loads(output.getvalue())

    def test_default_is_local_readonly_and_preserves_historical_values(self):
        before = self.path.read_bytes()
        from unittest.mock import Mock
        connect = Mock(side_effect=AssertionError('No network allowed'))
        code, report = self.cli(['--source', str(self.path)], connect_destination=connect)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'dry_run_valid')
        self.assertFalse(report['destination_contacted'])
        self.assertEqual(report['source_counts'], {'exercises': 1, 'sets': 1})
        connect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(str(self.source.sets[0].date), '2020-01-02')

    def test_validation_reports_all_problems_without_repair(self):
        exercises = [{'id': 1, 'name': 'Squat'}, {'id': 2, 'name': 'SQUAT'}, {'id': 2, 'name': ' '}, {'id': 4, 'name': ' padded '}, {'id': 5, 'name': 'x' * 121}]
        sets = [{'id': 1, 'exercise_id': 99, 'weight': float('inf'), 'reps': 0, 'date': '2020-02-30'}, {'id': 1, 'exercise_id': 1, 'weight': -1, 'reps': 1.5, 'date': '20200101'}]
        source = imp.validate_source(self.path, self.source.sha256, exercises, sets)
        codes = {issue['code'] for issue in source.issues}
        self.assertTrue({'duplicate_id', 'blank_or_nontext_name', 'name_has_surrounding_whitespace', 'name_exceeds_120_characters', 'case_insensitive_duplicate_name_review_required', 'missing_or_invalid_exercise_link', 'date_must_be_valid_yyyy_mm_dd', 'reps_must_be_integer_1_to_1000'} <= codes)
        with self.assertRaises(imp.ImportFailure):
            imp.import_destination(Destination(), source, OWNER)

    def test_live_database_alias_and_journal_are_rejected(self):
        with patch.object(imp, 'LEGACY_DATABASE', self.path):
            with self.assertRaises(imp.ImportFailure):
                imp.read_source(self.path)
            alias = self.path.parent / 'alias.db'
            alias.symlink_to(self.path)
            with self.assertRaises(imp.ImportFailure):
                imp.read_source(alias)
        Path(str(self.path) + '-wal').touch()
        with self.assertRaises(imp.ImportFailure):
            imp.read_source(self.path)

    def test_import_maps_owner_preserves_links_and_is_repeatable(self):
        db = Destination()
        first = imp.import_destination(db, self.source, OWNER)
        self.assertEqual(first['inserted'], {'exercises': 1, 'sets': 1})
        self.assertEqual(db.rows['sets'][12], imp.expected_set(self.source.sets[0], OWNER))
        self.assertEqual(db.rows['exercises'][7], imp.expected_exercise(self.source.exercises[0], OWNER))
        second = imp.import_destination(db, self.source, OWNER)
        self.assertEqual(second['status'], 'already_present')
        self.assertEqual(second['inserted'], {'exercises': 0, 'sets': 0})
        self.assertEqual(db.writes, 2)
        self.assertEqual(db.sequences['sets'], {'last_value': 12, 'is_called': True})

    def test_other_owner_or_changed_values_block_before_writes(self):
        for owner in (OWNER, OTHER):
            db = Destination()
            db.rows['exercises'][7] = {'id': 7, 'user_id': owner, 'name': 'Changed'}
            before = copy.deepcopy(db.rows)
            result = imp.import_destination(db, self.source, OWNER)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(db.rows, before)
            self.assertEqual(db.writes, 0)

    def test_case_insensitive_destination_name_conflict(self):
        db = Destination()
        db.rows['exercises'][99] = {'id': 99, 'user_id': OWNER, 'name': 'SQUAT'}
        result = imp.import_destination(db, self.source, OWNER)
        self.assertEqual(result['issues'][0]['code'], 'destination_name_conflict')
        self.assertEqual(db.writes, 0)

    def test_verification_and_commit_errors_rollback_rows(self):
        for attribute in ('corrupt', 'commit_failure'):
            db = Destination()
            setattr(db, attribute, True)
            with self.assertRaises(Exception):
                imp.import_destination(db, self.source, OWNER)
            self.assertEqual(db.rows, {'exercises': {}, 'sets': {}})

    def test_sequence_never_moves_back_and_accounts_for_other_users(self):
        db = Destination()
        db.sequences['exercises'] = {'last_value': 500, 'is_called': True}
        db.rows['sets'][900] = {'id': 900, 'user_id': OTHER}
        imp.import_destination(db, self.source, OWNER)
        self.assertEqual(db.sequences['exercises']['last_value'], 500)
        self.assertEqual(db.sequences['sets']['last_value'], 900)

    def test_changed_source_wrong_role_or_missing_account_stop(self):
        for attribute, value in (('role', 'incline_api'), ('present', False)):
            db = Destination()
            setattr(db, attribute, value)
            with self.assertRaises(imp.ImportFailure):
                imp.import_destination(db, self.source, OWNER)
            self.assertEqual(db.writes, 0)
        self.path.write_bytes(b'changed')
        with self.assertRaises(imp.ImportFailure):
            imp.import_destination(Destination(), self.source, OWNER)

    def test_secrets_in_errors_or_unknown_arguments_are_not_printed(self):
        from unittest.mock import Mock
        secret = 'PRIVATE_PASSWORD_OR_URL'
        code, report = self.cli(['--source', str(self.path), '--confirm'], connect_destination=Mock(side_effect=RuntimeError(secret)))
        self.assertEqual(code, 2)
        self.assertNotIn(secret, json.dumps(report))
        code, report = self.cli(['--source', str(self.path), '--unknown', secret])
        self.assertEqual(code, 2)
        self.assertNotIn(secret, json.dumps(report))

    def test_admin_connection_configuration_and_no_network_on_bad_source(self):
        with patch.object(imp.psycopg, 'connect') as connect:
            for url in ('postgresql://incline_api:placeholder@localhost:5432/postgres', 'postgresql://postgres:placeholder@localhost:6543/postgres'):
                with self.assertRaises(imp.ImportFailure):
                    imp.connect_destination(url)
            connect.assert_not_called()
        from unittest.mock import Mock
        connect = Mock()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE exercises SET name = ?', ('',))
            db.commit()
        code, result = self.cli(['--source', str(self.path), '--confirm'], connect_destination=connect)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'blocked')
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()

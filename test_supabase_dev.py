"""GATE 2 ONLY: opt-in network checks against the configured dev Supabase project.

Skipped unless INCLINE_RUN_DEV_TESTS=1 is explicitly exported for this command.
Never applies schema, creates/deletes accounts, or imports SQLite. All test lifting
writes are rolled back. Identity sequences can advance, leaving harmless gaps.
"""
import json
import os
import unittest
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from uuid import UUID, uuid4

from psycopg import Error as DatabaseError
from psycopg.errors import ForeignKeyViolation, InsufficientPrivilege
from psycopg_pool import PoolTimeout

import api
import database
from local_env import load_local_env
from settings import auth_settings
from test_api import request


class SingleConnectionPool:
    def __init__(self, connection):
        self.db = connection

    @contextmanager
    def connection(self):
        yield self.db


@unittest.skipUnless(os.environ.get('INCLINE_RUN_DEV_TESTS') == '1', 'Gate 2: dev network tests require explicit approval')
class DevProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = 'user A authentication'
        try:
            load_local_env()
            config = auth_settings()
            cls.users = []
            for letter in ('A', 'B'):
                stage = f'user {letter} authentication'
                payload = {'email': os.environ[f'TEST_USER_{letter}_EMAIL'],
                           'password': os.environ[f'TEST_USER_{letter}_PASSWORD']}
                login = Request(config.issuer + '/token?grant_type=password',
                                data=json.dumps(payload).encode(), method='POST',
                                headers={'apikey': config.publishable_key, 'Content-Type': 'application/json'})
                with urlopen(login, timeout=10) as response:
                    result = json.load(response)
                cls.users.append((UUID(result['user']['id']), result['access_token']))
            if cls.users[0][0] == cls.users[1][0]:
                raise ValueError('Two distinct accounts required')
            stage = 'database configuration'
            cls.pool = database.get_pool()
        except Exception as error:
            if stage == 'database configuration':
                # Inspect code locations/types only, never exception messages or
                # frame locals. Do not open a connection just for diagnostics.
                trace = error.__traceback__
                while trace is not None:
                    if trace.tb_frame.f_code is database.check_runtime_role.__code__:
                        stage = 'restricted role validation'
                        break
                    trace = trace.tb_next
                else:
                    if isinstance(error, (DatabaseError, PoolTimeout)):
                        stage = 'database connection'
            if isinstance(error, HTTPError):
                error.close()
            raise RuntimeError(f'Dev setup failed: {stage}') from None
        cls.addClassCleanup(database.close_pool)

    def call(self, method, path, body=None, user=0):
        token = None if user is None else self.users[user][1]
        status, data, headers = request(method, path, body, token)
        self.assertEqual(headers.get(b'cache-control'), b'no-store')
        return status, data

    @contextmanager
    def rollback_requests(self):
        # Nested per-request savepoints permit testing HTTP commits/errors while
        # rolling back the outer fixture transaction. A separate test below checks
        # REAL end-of-transaction identity cleanup without this outer transaction.
        with self.pool.connection() as connection:
            with connection.transaction(force_rollback=True):
                with patch.object(database, 'get_pool', return_value=SingleConnectionPool(connection)):
                    yield connection

    def fixtures(self):
        name = 'Dev isolation ' + str(uuid4())
        exercises, sets = [], []
        for user in (0, 1):
            status, exercise = self.call('POST', '/exercises', {'name': name}, user)
            self.assertEqual(status, 201)
            status, entry = self.call('POST', '/sets', {'exercise_id': exercise['id'], 'weight': 100,
                                      'reps': 8, 'date': api.utc_today().isoformat()}, user)
            self.assertEqual(status, 201)
            exercises.append(exercise)
            sets.append(entry)
        return exercises, sets

    def test_two_accounts_on_all_routes(self):
        with self.rollback_requests():
            exercises, sets = self.fixtures()
            for mine, theirs in ((0, 1), (1, 0)):
                self.assertIn(exercises[mine], self.call('GET', '/exercises', user=mine)[1])
                self.assertNotIn(exercises[theirs], self.call('GET', '/exercises', user=mine)[1])
                self.assertIn(sets[mine], self.call('GET', '/sets', user=mine)[1])
                self.assertNotIn(sets[theirs], self.call('GET', '/sets', user=mine)[1])
                eid, sid = exercises[theirs]['id'], sets[theirs]['id']
                self.assertEqual(self.call('GET', f'/exercises/{eid}/last-set', user=mine)[0], 404)
                self.assertEqual(self.call('GET', f'/sets?exercise_id={eid}', user=mine)[0], 404)
                self.assertEqual(self.call('POST', '/sets', {'exercise_id': eid, 'weight': 100, 'reps': 8,
                                             'date': api.utc_today().isoformat()}, mine)[0], 404)
                self.assertEqual(self.call('PUT', f'/sets/{sid}', {'weight': 110, 'reps': 9}, mine)[0], 404)
                self.assertEqual(self.call('DELETE', f'/sets/{sid}', user=mine)[0], 404)
                self.assertEqual(self.call('GET', f'/exercises/{exercises[mine]["id"]}/last-set', user=mine)[1], sets[mine])
                self.assertEqual(self.call('POST', '/exercises', {'name': exercises[mine]['name'].upper()}, mine)[0], 409)
            for mine in (0, 1):
                sid = sets[mine]['id']
                self.assertEqual(self.call('PUT', f'/sets/{sid}', {'weight': 110, 'reps': 9}, mine)[0], 200)
                # Deletes only this transaction's new fixture; outer rollback removes all writes.
                self.assertEqual(self.call('DELETE', f'/sets/{sid}', user=mine)[0], 204)
            self.assertEqual(self.call('GET', '/sets', user=None)[0], 401)

    def test_postgres_rls_and_same_owner_link_without_api_filters(self):
        with self.rollback_requests() as connection:
            exercises, sets = self.fixtures()
            for mine, theirs in ((0, 1), (1, 0)):
                with database.user_transaction(SingleConnectionPool(connection), self.users[mine][0]) as db:
                    self.assertEqual(db.execute('SELECT id FROM public.sets WHERE id = %s',
                                                (sets[theirs]['id'],)).fetchall(), [])
                    self.assertEqual(db.execute('UPDATE public.sets SET weight = %s WHERE id = %s RETURNING id',
                                                (999, sets[theirs]['id'])).fetchall(), [])
                    self.assertEqual(db.execute('DELETE FROM public.sets WHERE id = %s RETURNING id',
                                                (sets[theirs]['id'],)).fetchall(), [])
                    with self.assertRaises(ForeignKeyViolation):
                        with connection.transaction():
                            db.execute('INSERT INTO public.sets (exercise_id, weight, reps, date) VALUES (%s, %s, %s, %s)',
                                       (exercises[theirs]['id'], 100, 8, api.utc_today()))
                    with self.assertRaises(InsufficientPrivilege):
                        with connection.transaction():
                            db.execute('UPDATE public.sets SET user_id = %s WHERE id = %s',
                                       (self.users[theirs][0], sets[mine]['id']))

    def test_identity_clears_between_real_transactions_on_reused_connection(self):
        # No outer transaction here: these are real commits/rollbacks on a one-slot pool.
        for user_id, _ in self.users:
            with database.user_transaction(self.pool, user_id) as db:
                subject = db.execute("SELECT current_setting('request.jwt.claims', true)::jsonb ->> 'sub' AS subject").fetchone()['subject']
                self.assertEqual(subject, str(user_id))
            with self.pool.connection() as connection:
                self.assertIsNone(connection.execute("SELECT nullif(current_setting('request.jwt.claims', true), '') AS claims").fetchone()['claims'])
            with self.assertRaises(RuntimeError):
                with database.user_transaction(self.pool, user_id):
                    raise RuntimeError('simulate an aborted request')
            with self.pool.connection() as connection:
                self.assertIsNone(connection.execute("SELECT nullif(current_setting('request.jwt.claims', true), '') AS claims").fetchone()['claims'])


if __name__ == '__main__':
    unittest.main()

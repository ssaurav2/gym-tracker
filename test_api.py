"""Offline route tests: execute owner-filtered SQL on a disposable SQLite adapter.

This adapter intentionally has NO RLS. Tests prove the API filters owners itself;
Postgres RLS and actual pool behavior are separately tested against dev at Gate 2.
"""
import asyncio
import json
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from urllib.parse import urlsplit
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from psycopg import OperationalError
from psycopg.errors import UniqueViolation

import api
import authentication
import database

USER_A = UUID('00000000-0000-4000-8000-000000000001')
USER_B = UUID('00000000-0000-4000-8000-000000000002')


def request(method, path, body=None, token=None, app=api.app):
    async def run():
        target = urlsplit(path)
        messages = []
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                await asyncio.Event().wait()
            delivered = True
            return {'type': 'http.request', 'body': json.dumps(body).encode() if body is not None else b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        headers = [(b'content-type', b'application/json')]
        if token is not None:
            headers.append((b'authorization', ('Bearer ' + token).encode()))
        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': method, 'scheme': 'http', 'path': target.path, 'raw_path': target.path.encode(),
                   'query_string': target.query.encode(), 'headers': headers,
                   'client': ('127.0.0.1', 1), 'server': ('test', 80)}, receive, send)
        status = messages[0]['status']
        data = b''.join(message.get('body', b'') for message in messages[1:])
        return status, json.loads(data) if data else None, dict(messages[0]['headers'])

    return asyncio.run(run())


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class OfflineConnection:
    def __init__(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.claims = None
        self.identities = []
        self.db.executescript('''
            CREATE TABLE exercises (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL);
            CREATE UNIQUE INDEX owner_name ON exercises(user_id, lower(name));
            CREATE TABLE sets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                exercise_id INTEGER NOT NULL, weight REAL NOT NULL, reps INTEGER NOT NULL, date TEXT NOT NULL);
        ''')

    def execute(self, query, parameters=()):
        if query == 'SELECT set_config(%s, %s, true)':
            if parameters[0] == 'request.jwt.claims':
                self.claims = json.loads(parameters[1])
                self.identities.append(self.claims['sub'])
            return None
        values = tuple(str(value) if isinstance(value, (UUID, date)) else value for value in parameters)
        try:
            return Cursor(self.db.execute(query.replace('public.', '').replace('%s', '?'), values))
        except sqlite3.IntegrityError as error:
            if 'UNIQUE' in str(error):
                raise UniqueViolation('duplicate') from None
            raise

    @contextmanager
    def transaction(self):
        if self.claims is not None:
            raise AssertionError('A previous request leaked its identity')
        self.db.execute('BEGIN')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        finally:
            self.claims = None


class OfflinePool:
    def __init__(self):
        self.db = OfflineConnection()

    @contextmanager
    def connection(self):
        yield self.db


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.pool = OfflinePool()
        self.addCleanup(self.pool.db.db.close)
        patcher = patch.object(database, 'get_pool', return_value=self.pool)
        patcher.start()
        self.addCleanup(patcher.stop)

        def verified(token):
            if token not in {'user-a', 'user-b'}:
                raise authentication.unauthorized()
            return USER_A if token == 'user-a' else USER_B

        patcher = patch.object(authentication, 'verify_token', side_effect=verified)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, method, path, body=None, user='user-a'):
        status, data, headers = request(method, path, body, user)
        self.assertEqual(headers.get(b'cache-control'), b'no-store')
        return status, data

    def exercise(self, name='Bench Press', user='user-a'):
        status, exercise = self.request('POST', '/exercises', {'name': name}, user)
        self.assertEqual(status, 201)
        return exercise

    def logged_set(self, exercise, user='user-a', **values):
        body = {'exercise_id': exercise['id'], 'weight': 100, 'reps': 8, 'date': api.utc_today().isoformat(), **values}
        status, entry = self.request('POST', '/sets', body, user)
        self.assertEqual(status, 201)
        return entry

    def test_workflow(self):
        eid = self.exercise(' Bench Press ')['id']
        self.assertEqual(self.request('POST', '/exercises', {'name': 'BENCH PRESS'})[0], 409)
        self.assertEqual(self.request('GET', f'/exercises/{eid}/last-set'), (200, None))
        first = self.logged_set({'id': eid})
        latest = self.logged_set({'id': eid}, weight=105)
        other = self.logged_set(self.exercise('Squat'), weight=135)
        self.assertEqual([row['id'] for row in self.request('GET', '/sets')[1]], [other['id'], latest['id'], first['id']])
        self.assertEqual(self.request('GET', f'/exercises/{eid}/last-set')[1], latest)
        self.assertEqual([row['id'] for row in self.request('GET', f'/sets?exercise_id={eid}')[1]], [latest['id'], first['id']])
        self.assertEqual(self.request('GET', '/sets?exercise_id=invalid')[0], 422)
        status, edited = self.request('PUT', f"/sets/{latest['id']}", {'weight': 110, 'reps': 9})
        self.assertEqual(status, 200)
        self.assertEqual(edited, {**latest, 'weight': 110, 'reps': 9})
        self.assertEqual(self.request('GET', f'/exercises/{eid}/last-set')[1], edited)
        self.assertEqual(self.request('DELETE', f"/sets/{latest['id']}"), (204, None))
        self.assertEqual(self.request('DELETE', f"/sets/{latest['id']}")[0], 404)
        self.assertEqual(self.request('GET', f'/exercises/{eid}/last-set')[1], first)
        self.assertEqual(self.request('GET', '/sets?exercise_id=999')[0], 404)
        self.assertEqual(self.request('PUT', '/sets/999', {'weight': 100, 'reps': 8})[0], 404)
        empty = self.exercise('Deadlift')
        self.assertEqual(self.request('GET', f"/sets?exercise_id={empty['id']}"), (200, []))

    def test_every_route_requires_login(self):
        for user in (None, 'invalid'):
            for method, path, body in [('GET', '/exercises', None), ('POST', '/exercises', {'name': 'Bench'}),
                                       ('GET', '/exercises/1/last-set', None), ('GET', '/sets', None),
                                       ('POST', '/sets', {}), ('PUT', '/sets/1', {}), ('DELETE', '/sets/1', None)]:
                self.assertEqual(self.request(method, path, body, user)[0], 401)
        self.assertEqual(self.pool.db.identities, [])

    def test_two_users_all_routes_and_ownership(self):
        exercises = {user: self.exercise(user=user) for user in ('user-a', 'user-b')}
        sets = {user: self.logged_set(exercise, user) for user, exercise in exercises.items()}
        for mine, theirs in [('user-a', 'user-b'), ('user-b', 'user-a')]:
            self.assertEqual(self.request('GET', '/exercises', user=mine)[1], [exercises[mine]])
            self.assertEqual(self.request('GET', '/sets', user=mine)[1], [sets[mine]])
            self.assertEqual(self.request('GET', f"/exercises/{exercises[theirs]['id']}/last-set", user=mine)[0], 404)
            self.assertEqual(self.request('GET', f"/sets?exercise_id={exercises[theirs]['id']}", user=mine)[0], 404)
            self.assertEqual(self.request('POST', '/sets', {'exercise_id': exercises[theirs]['id'], 'weight': 100,
                             'reps': 8, 'date': api.utc_today().isoformat()}, mine)[0], 404)
            self.assertEqual(self.request('PUT', f"/sets/{sets[theirs]['id']}", {'weight': 120, 'reps': 9}, mine)[0], 404)
            self.assertEqual(self.request('DELETE', f"/sets/{sets[theirs]['id']}", user=mine)[0], 404)
            self.assertEqual(self.request('GET', '/sets', user=theirs)[1], [sets[theirs]])
            self.assertEqual(self.request('POST', '/exercises', {'name': 'Forged', 'user_id': str(USER_B)}, mine)[0], 422)
            self.assertEqual(self.request('PUT', f"/sets/{sets[mine]['id']}", {'weight': 100, 'reps': 8, 'user_id': str(USER_B)}, mine)[0], 422)

    def test_consecutive_requests_clear_identity_even_after_error(self):
        self.exercise(user='user-a')
        self.assertIsNone(self.pool.db.claims)
        self.assertEqual(self.request('POST', '/exercises', {'name': 'BENCH PRESS'})[0], 409)
        self.assertIsNone(self.pool.db.claims)
        self.assertEqual(self.request('GET', '/exercises', user='user-b'), (200, []))
        self.assertIsNone(self.pool.db.claims)
        self.assertEqual(len(self.request('GET', '/exercises')[1]), 1)
        self.assertIsNone(self.pool.db.claims)
        self.assertEqual(self.pool.db.identities[-2:], [str(USER_B), str(USER_A)])

    def test_commit_failure_is_reported_before_success_response(self):
        original = self.pool.db.transaction

        @contextmanager
        def failed_commit():
            with original():
                yield
                raise OperationalError('private commit failure')

        with patch.object(self.pool.db, 'transaction', failed_commit):
            status, body = self.request('POST', '/exercises', {'name': 'Must roll back'})
        self.assertEqual(status, 503)
        self.assertNotIn('private', body['detail'])
        self.assertEqual(self.request('GET', '/exercises'), (200, []))
        self.assertIsNone(self.pool.db.claims)

    def test_date_window_and_format(self):
        exercise = self.exercise()
        today = api.utc_today()
        for delta in (-1, 0, 1):
            chosen = (today + timedelta(days=delta)).isoformat()
            self.assertEqual(self.logged_set(exercise, date=chosen)['date'], chosen)
        for value in ((today - timedelta(days=2)).isoformat(), (today + timedelta(days=2)).isoformat(),
                      '2026-02-30', '20260101', 1700000000, today.isoformat() + 'T00:00:00', None):
            self.assertEqual(self.request('POST', '/sets', {'exercise_id': exercise['id'], 'weight': 100, 'reps': 8, 'date': value})[0], 422)
        self.assertEqual(self.request('POST', '/sets', {'exercise_id': exercise['id'], 'weight': 100, 'reps': 8})[0], 422)

    def test_caps_and_immutable_fields(self):
        for name in ('', '  ', 'x' * 121):
            self.assertEqual(self.request('POST', '/exercises', {'name': name})[0], 422)
        self.exercise('x' * 120)
        exercise = self.exercise()
        entry = self.logged_set(exercise, weight=10000, reps=1000)
        for weight, reps in [(0, 8), (-1, 8), (10001, 8), (100, 0), (100, -1), (100, 1001), (100, 1.5), (100, True), ('Infinity', 8), ('NaN', 8)]:
            values = {'weight': weight, 'reps': reps}
            self.assertEqual(self.request('POST', '/sets', {**values, 'exercise_id': exercise['id'], 'date': api.utc_today().isoformat()})[0], 422)
            self.assertEqual(self.request('PUT', f"/sets/{entry['id']}", values)[0], 422)
        for key, value in [('id', 999), ('exercise_id', 999), ('date', api.utc_today().isoformat())]:
            self.assertEqual(self.request('PUT', f"/sets/{entry['id']}", {'weight': 100, 'reps': 8, key: value})[0], 422)

    def test_sql_values_are_bound(self):
        name = "Press'); DELETE FROM sets; --"
        self.assertEqual(self.exercise(name)['name'], name)
        self.assertEqual(self.request('GET', '/exercises')[1][0]['name'], name)

    def test_progress_photos_are_not_exposed(self):
        paths = self.request('GET', '/openapi.json')[1]['paths']
        self.assertFalse(any(path.startswith('/progress-photos') for path in paths))
        for method, path in [('GET', '/progress-photos'), ('POST', '/progress-photos'),
                             ('GET', '/progress-photos/1/image'), ('DELETE', '/progress-photos/1')]:
            self.assertEqual(self.request(method, path)[0], 404)


if __name__ == '__main__':
    unittest.main()

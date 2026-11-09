"""Offline checks for transaction cleanup and serverless pool configuration."""
from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

import database
from local_env import load_local_env
from settings import ConfigurationError
from test_api import OfflinePool, USER_A, USER_B


class DatabaseTest(unittest.TestCase):
    def tearDown(self):
        database.close_pool()

    def test_identity_is_scoped_to_each_transaction(self):
        pool = OfflinePool()
        self.addCleanup(pool.db.db.close)
        with database.user_transaction(pool, USER_A):
            self.assertEqual(pool.db.claims['sub'], str(USER_A))
        self.assertIsNone(pool.db.claims)
        with self.assertRaises(RuntimeError):
            with database.user_transaction(pool, USER_B):
                self.assertEqual(pool.db.claims['sub'], str(USER_B))
                raise RuntimeError('abort this request')
        self.assertIsNone(pool.db.claims)
        with database.user_transaction(pool, USER_A):
            self.assertEqual(pool.db.claims['sub'], str(USER_A))
        self.assertIsNone(pool.db.claims)

    def test_pool_is_lazy_small_encrypted_and_preparation_disabled(self):
        # Synthetic non-routable configuration, not a real connection URL.
        with patch.dict('os.environ', {'DATABASE_URL': 'host=pool.invalid port=6543 user=incline_api.test dbname=postgres'}, clear=True):
            with patch.object(database, 'ConnectionPool') as factory:
                pool = database.get_pool()
                self.assertIs(pool, database.get_pool())
                options = factory.call_args.kwargs
                self.assertEqual(options['max_size'], 1)
                self.assertEqual(options['min_size'], 0)
                self.assertFalse(options['open'])
                self.assertIsNone(options['kwargs']['prepare_threshold'])
                self.assertTrue(options['kwargs']['autocommit'])
                self.assertEqual(options['kwargs']['sslmode'], 'require')
                factory.assert_called_once()
                pool.open.assert_called_once_with(wait=False)

    def test_owner_connection_and_wrong_pooler_are_rejected(self):
        for value in ('', 'host=pool.invalid user=postgres.test port=6543',
                      'host=pool.invalid user=incline_api.test port=5432'):
            with patch.dict('os.environ', {'DATABASE_URL': value}, clear=True):
                with self.assertRaises(ConfigurationError):
                    database.get_pool()

    def test_role_must_be_restricted_nonowner(self):
        safe = {'name': 'incline_api', 'rolsuper': False, 'rolbypassrls': False, 'owns_tables': False, 'rolcreatedb': False, 'rolcreaterole': False}
        connection = Mock()
        for changed in ({'name': 'postgres'}, {'rolsuper': True}, {'rolbypassrls': True}, {'owns_tables': True}, {'rolcreatedb': True}, {'rolcreaterole': True}):
            connection.execute.return_value.fetchone.return_value = {**safe, **changed}
            with self.assertRaises(ConfigurationError):
                database.check_runtime_role(connection)
        connection.execute.return_value.fetchone.return_value = safe
        database.check_runtime_role(connection)

    def test_driver_details_are_not_returned_to_client(self):
        for error in (OperationalError('private server detail'), PoolTimeout('private connection detail'), ConfigurationError('private setting')):
            with patch.object(database, 'get_pool', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    next(database.get_db(USER_A))
                self.assertEqual(caught.exception.status_code, 503)
                self.assertNotIn('private', caught.exception.detail)

    def test_local_env_is_data_not_shell_and_never_overrides_exported_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'example.env'
            path.write_text('# comment\nEXAMPLE_NAME="literal $(no-shell)"\nOTHER_NAME=sample\n')
            with patch.dict('os.environ', {'OTHER_NAME': 'existing'}, clear=True):
                load_local_env(path)
                import os
                self.assertEqual(os.environ['EXAMPLE_NAME'], 'literal $(no-shell)')
                self.assertEqual(os.environ['OTHER_NAME'], 'existing')
            path.write_text('invalid line')
            with self.assertRaisesRegex(ValueError, 'line 1'):
                load_local_env(path)


if __name__ == '__main__':
    unittest.main()

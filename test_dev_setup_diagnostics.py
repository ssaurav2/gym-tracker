"""Offline-only setup diagnostics: all configuration and network calls are mocked."""
import json
import traceback
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from psycopg import OperationalError
from psycopg_pool import PoolTimeout

import database
import test_supabase_dev as dev
from settings import ConfigurationError


class SetupDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.sensitive = 'SENSITIVE_VALUE_MUST_NEVER_APPEAR'
        self.config = SimpleNamespace(issuer='https://dev.invalid/auth/v1', publishable_key=self.sensitive)
        self.probe = type('SetupProbe', (), {'addClassCleanup': Mock()})
        for target, value in [('load_local_env', None), ('auth_settings', self.config)]:
            patcher = patch.object(dev, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.dict('os.environ', {
            'TEST_USER_A_EMAIL': self.sensitive, 'TEST_USER_A_PASSWORD': self.sensitive,
            'TEST_USER_B_EMAIL': self.sensitive, 'TEST_USER_B_PASSWORD': self.sensitive,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def response(self, user):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'user': {'id': f'00000000-0000-4000-8000-00000000000{user}'},
            'access_token': self.sensitive,
        }).encode()
        return response

    def check_failure(self, expected, responses, pool_error=None):
        with patch.object(dev, 'urlopen', side_effect=responses):
            with patch.object(database, 'get_pool', side_effect=pool_error):
                try:
                    dev.DevProjectTest.setUpClass.__func__(self.probe)
                except RuntimeError as error:
                    self.assertEqual(str(error), 'Dev setup failed: ' + expected)
                    self.assertNotIn(self.sensitive, ''.join(traceback.format_exception(error)))
                    self.assertTrue(error.__suppress_context__)
                else:
                    self.fail('Expected a sanitized setup failure')

    def test_authentication_stages(self):
        self.check_failure('user A authentication', [RuntimeError(self.sensitive)])
        self.check_failure('user B authentication', [self.response(1), RuntimeError(self.sensitive)])

    def test_database_configuration_stage(self):
        self.check_failure('database configuration', [self.response(1), self.response(2)], ConfigurationError(self.sensitive))

    def test_database_connection_stage(self):
        for error in (OperationalError(self.sensitive), PoolTimeout(self.sensitive)):
            self.check_failure('database connection', [self.response(1), self.response(2)], error)

    def test_restricted_role_stage(self):
        def invalid_role():
            connection = Mock()
            connection.execute.return_value.fetchone.return_value = {'name': 'postgres'}
            database.check_runtime_role(connection)

        self.check_failure('restricted role validation', [self.response(1), self.response(2)], invalid_role)

    def test_success_keeps_existing_call_order_without_connecting(self):
        pool = Mock()
        with patch.object(dev, 'urlopen', side_effect=[self.response(1), self.response(2)]) as auth:
            with patch.object(database, 'get_pool', return_value=pool) as get_pool:
                dev.DevProjectTest.setUpClass.__func__(self.probe)
        self.assertEqual(auth.call_count, 2)
        get_pool.assert_called_once_with()
        self.assertIs(self.probe.pool, pool)
        pool.connection.assert_not_called()
        self.probe.addClassCleanup.assert_called_once_with(database.close_pool)


if __name__ == '__main__':
    unittest.main()

"""Real signed JWTs and public keys, generated in memory; no network or secrets."""
import json
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException

import authentication as auth
from settings import AuthSettings, ConfigurationError, auth_settings
from test_api import USER_A


class AuthenticationTest(unittest.TestCase):
    def setUp(self):
        self.config = AuthSettings('https://project.invalid', 'ES256', 'public-test-key')
        patcher = patch.object(auth, 'auth_settings', return_value=self.config)
        self.settings = patcher.start()
        self.addCleanup(patcher.stop)
        self.key = ec.generate_private_key(ec.SECP256R1())
        public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid='test-key', alg='ES256', use='sig')
        self.public = jwt.PyJWK.from_dict(public)
        self.client = Mock()
        self.client.get_signing_key_from_jwt.return_value = self.public
        patcher = patch.object(auth, 'jwks_client', return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def claims(self, **changes):
        now = int(time.time())
        return {'sub': str(USER_A), 'iss': self.config.issuer, 'aud': 'authenticated',
                'role': 'authenticated', 'iat': now - 1, 'exp': now + 300, **changes}

    def token(self, claims=None, key=None, algorithm='ES256', headers=None):
        return jwt.encode(claims or self.claims(), key or self.key, algorithm=algorithm,
                          headers={'kid': 'test-key', **(headers or {})})

    def denied(self, token, status=401):
        with self.assertRaises(HTTPException) as error:
            auth.verify_token(token)
        self.assertEqual(error.exception.status_code, status)

    def test_valid_asymmetric_token(self):
        self.assertEqual(auth.verify_token(self.token()), USER_A)

    def test_rejects_bad_signature_and_claims(self):
        self.denied(self.token(key=ec.generate_private_key(ec.SECP256R1())))
        for claims in [self.claims(exp=int(time.time()) - 60), self.claims(iat=int(time.time()) + 600),
                       self.claims(iss='https://other.invalid/auth/v1'), self.claims(aud='other'),
                       self.claims(role='service_role'), self.claims(sub='not-a-uuid'), self.claims(is_anonymous=True)]:
            self.denied(self.token(claims))
        for field in ('exp', 'iat', 'iss', 'aud', 'role', 'sub'):
            claims = self.claims()
            del claims[field]
            self.denied(self.token(claims))

    def test_rejects_missing_key_unknown_algorithm_and_malformed_token(self):
        self.denied(self.token(headers={'kid': ''}))
        self.denied(jwt.encode(self.claims(), 'x' * 64, algorithm='HS256'))
        self.denied(jwt.encode(self.claims(), key='', algorithm='none'))
        self.denied('not.a.token')
        self.client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientError('unknown key')
        self.denied(self.token())

    def test_jwks_network_failure_is_not_authorized(self):
        self.client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientConnectionError('unavailable')
        self.denied(self.token(), 503)

    def test_rsa_token(self):
        self.settings.return_value = AuthSettings(self.config.url, 'RS256', '')
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        public.update(kid='rsa-key', alg='RS256', use='sig')
        self.client.get_signing_key_from_jwt.return_value = jwt.PyJWK.from_dict(public)
        token = jwt.encode(self.claims(), key, algorithm='RS256', headers={'kid': 'rsa-key'})
        self.assertEqual(auth.verify_token(token), USER_A)

    def test_legacy_tokens_require_auth_server_confirmation(self):
        self.settings.return_value = AuthSettings(self.config.url, 'HS256', 'public-test-key')
        token = jwt.encode(self.claims(), 'x' * 64, algorithm='HS256')
        with patch.object(auth, 'auth_server_user', return_value={'id': str(USER_A)}) as server:
            self.assertEqual(auth.verify_token(token), USER_A)
            server.assert_called_once()
        with patch.object(auth, 'auth_server_user', return_value={'id': str(UUID(int=1))}):
            self.denied(token)
        with patch.object(auth, 'auth_server_user', side_effect=auth.unauthorized()):
            self.denied(token)
        self.client.get_signing_key_from_jwt.assert_not_called()

    def test_legacy_auth_server_errors_and_fixed_destination(self):
        config = AuthSettings('https://project.invalid', 'HS256', 'public-test-key')
        response = Mock(status=200)
        response.read.return_value = json.dumps({'id': str(USER_A)}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(auth, 'urlopen', return_value=response) as opener:
            self.assertEqual(auth.auth_server_user(config, 'test-token')['id'], str(USER_A))
            self.assertEqual(opener.call_args.args[0].full_url, config.issuer + '/user')
        for reason, expected in [(HTTPError(config.url, 401, 'denied', {}, None), 401),
                                 (HTTPError(config.url, 503, 'down', {}, None), 503),
                                 (URLError('down'), 503)]:
            with patch.object(auth, 'urlopen', side_effect=reason):
                with self.assertRaises(HTTPException) as caught:
                    auth.auth_server_user(config, 'test-token')
                self.assertEqual(caught.exception.status_code, expected)

    def test_configuration_rejects_non_https_or_secret_key(self):
        for variables in [{}, {'SUPABASE_URL': 'http://project.invalid'},
                          {'SUPABASE_URL': 'https://project.invalid/path'},
                          {'SUPABASE_URL': 'https://project.invalid', 'SUPABASE_JWT_ALGORITHM': 'none'},
                          {'SUPABASE_URL': 'https://project.invalid', 'SUPABASE_PUBLISHABLE_KEY': 'sb_secret_example'}]:
            with patch.dict('os.environ', variables, clear=True):
                with self.assertRaises(ConfigurationError):
                    auth_settings()


if __name__ == '__main__':
    unittest.main()

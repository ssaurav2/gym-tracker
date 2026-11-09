"""Read backend settings without opening connections or printing credentials."""
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


class ConfigurationError(Exception):
    """An intentionally generic error: configuration values may contain secrets."""


@dataclass(frozen=True, repr=False)
class AuthSettings:
    url: str
    algorithm: str
    publishable_key: str

    @property
    def issuer(self):
        return self.url + '/auth/v1'


def auth_settings():
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    parsed = urlsplit(url)
    algorithm = os.environ.get('SUPABASE_JWT_ALGORITHM', 'ES256')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ConfigurationError('Configure SUPABASE_URL with the HTTPS project origin.')
    if algorithm not in {'ES256', 'RS256', 'HS256'}:
        raise ConfigurationError('Configure the project signing algorithm.')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if algorithm == 'HS256' and not key:
        raise ConfigurationError('Configure the publishable key for Auth-server verification.')
    if key and not key.startswith('sb_publishable_'):
        raise ConfigurationError('Use the publishable key, not a secret or legacy service-role key.')
    return AuthSettings(url, algorithm, key)

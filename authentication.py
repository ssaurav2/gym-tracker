"""Verify Supabase tokens before any identity reaches the database."""
import json
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from settings import ConfigurationError, auth_settings

bearer = HTTPBearer(auto_error=False)


def unauthorized():
    return HTTPException(401, 'Please log in again.', headers={'WWW-Authenticate': 'Bearer'})


@lru_cache(maxsize=4)
def jwks_client(issuer):
    # Only the configured project can supply keys; never trust a URL in a JWT.
    return jwt.PyJWKClient(issuer + '/.well-known/jwks.json', cache_keys=False,
                           cache_jwk_set=True, lifespan=300, timeout=5)


def auth_server_user(config, token):
    """Supabase's recommended fallback for a legacy HS256 signing key."""
    request = UrlRequest(config.issuer + '/user', headers={
        'apikey': config.publishable_key, 'Authorization': 'Bearer ' + token,
    })
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise unauthorized()
            user = json.loads(response.read(65537))
            if not isinstance(user, dict):
                raise ValueError('Invalid Auth response')
            return user
    except HTTPError as error:
        error.close()
        if error.code in {401, 403}:
            raise unauthorized() from None
        raise HTTPException(503, 'Login verification is temporarily unavailable.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(503, 'Login verification is temporarily unavailable.') from None


def verify_token(token):
    try:
        config = auth_settings()
        header = jwt.get_unverified_header(token)
        # Unverified header selects only whether we REJECT; it never supplies identity.
        if header.get('alg') != config.algorithm:
            raise unauthorized()
        options = {'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'role'],
                   'verify_exp': True, 'verify_iat': True, 'verify_aud': True,
                   'verify_iss': True, 'verify_sub': True}
        if config.algorithm == 'HS256':
            # Claim checks alone do not verify a signature. Authorization requires
            # the independent Auth-server check below to succeed and match the sub.
            claims = jwt.decode(token, options={**options, 'verify_signature': False},
                                audience='authenticated', issuer=config.issuer)
            user = auth_server_user(config, token)
            if user.get('id') != claims['sub'] or user.get('is_anonymous', False):
                raise unauthorized()
        else:
            if not isinstance(header.get('kid'), str) or not header['kid']:
                raise unauthorized()
            signing_key = jwks_client(config.issuer).get_signing_key_from_jwt(token)
            if signing_key.algorithm_name != config.algorithm:
                raise unauthorized()
            claims = jwt.decode(token, signing_key.key, algorithms=[config.algorithm],
                                audience='authenticated', issuer=config.issuer, options=options)
        if claims['role'] != 'authenticated' or claims.get('is_anonymous', False):
            raise unauthorized()
        return UUID(claims['sub'])
    except ConfigurationError:
        raise HTTPException(503, 'Login verification is not configured.') from None
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, 'Login verification is temporarily unavailable.') from None
    except (jwt.InvalidTokenError, jwt.PyJWKClientError, ValueError, TypeError, KeyError):
        raise unauthorized() from None


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None or credentials.scheme.lower() != 'bearer' or len(credentials.credentials) > 16384:
        raise unauthorized()
    return verify_token(credentials.credentials)

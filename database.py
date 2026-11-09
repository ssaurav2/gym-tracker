"""A small lazy Postgres pool and one isolated transaction per API request."""
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

from fastapi import Depends, HTTPException
from psycopg import Error as DatabaseError
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from authentication import require_user
from settings import ConfigurationError

_pool = None
_pool_lock = Lock()


def check_runtime_role(connection):
    row = connection.execute('''
        SELECT current_user AS name, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
               EXISTS (SELECT 1 FROM pg_class WHERE oid IN
                   ('public.exercises'::regclass, 'public.sets'::regclass)
                   AND relowner = pg_roles.oid) AS owns_tables
        FROM pg_roles WHERE rolname = current_user
    ''').fetchone()
    if not row or row['name'] != 'incline_api' or row['rolsuper'] or row['rolbypassrls'] or row['rolcreatedb'] or row['rolcreaterole'] or row['owns_tables']:
        raise ConfigurationError('The API requires the restricted incline_api database role.')


def get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            url = os.environ.get('DATABASE_URL', '')
            try:
                parameters = conninfo_to_dict(url)
            except DatabaseError:
                raise ConfigurationError('Configure the backend transaction-pooler URL.') from None
            username = parameters.get('user', '')
            if not url or parameters.get('port') != '6543' or not parameters.get('host') or not username.startswith('incline_api.'):
                raise ConfigurationError('Use the shared transaction pooler with the incline_api role on port 6543.')
            _pool = ConnectionPool(
                conninfo=url, min_size=0, max_size=1, open=False, timeout=10,
                max_idle=60, max_lifetime=300,
                kwargs={'autocommit': True, 'row_factory': dict_row, 'prepare_threshold': None,
                        'sslmode': 'require', 'connect_timeout': 5},
                configure=check_runtime_role, check=ConnectionPool.check_connection,
            )
            _pool.open(wait=False)
        return _pool


def close_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@dataclass(frozen=True)
class UserDatabase:
    connection: object
    user_id: UUID

    def execute(self, query, parameters=()):
        return self.connection.execute(query, parameters)


@contextmanager
def user_transaction(pool, user_id):
    with pool.connection() as connection:
        # autocommit is enabled on the connection: this explicit block owns the
        # whole request transaction. Claims disappear on commit AND rollback.
        with connection.transaction():
            connection.execute('SELECT set_config(%s, %s, true)',
                               ('request.jwt.claims', json.dumps({'sub': str(user_id), 'role': 'authenticated'})))
            connection.execute('SELECT set_config(%s, %s, true)', ('statement_timeout', '10000'))
            yield UserDatabase(connection, user_id)


def get_db(user_id: UUID = Depends(require_user)):
    try:
        with user_transaction(get_pool(), user_id) as db:
            yield db
    except ConfigurationError:
        raise HTTPException(503, 'The database connection is not configured correctly.') from None
    except (PoolTimeout, DatabaseError):
        # Driver exceptions can contain server details and record values.
        raise HTTPException(503, 'The database is temporarily unavailable. Please retry.') from None

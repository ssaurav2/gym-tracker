"""Add the photo table without modifying exercises, sets, or their saved data."""
from contextlib import closing
import sqlite3
from pathlib import Path


def migrate(connection):
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS progress_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                uploaded_at TEXT NOT NULL,
                category TEXT CHECK (category IS NULL OR category IN ('front', 'back', 'side'))
            )
        ''')


if __name__ == '__main__':
    database = Path(__file__).resolve().parent / 'gym_tracker.db'
    # Refuse to accidentally create a database in place of an existing installation.
    with closing(sqlite3.connect(database.as_uri() + '?mode=rw', uri=True)) as connection:
        migrate(connection)
    print('Progress photo table is ready. Existing exercises and sets are unchanged.')

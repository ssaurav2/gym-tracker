"""Test the deferred photo module in isolation; api.app exposes no photo routes."""
from contextlib import closing
import asyncio
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from PIL import Image
from fastapi import FastAPI

import progress_photos
from migrate_progress_photos import migrate


class PhotoApiTest(unittest.TestCase):
    def setUp(self):
        self.photo_app = FastAPI()
        self.photo_app.add_middleware(progress_photos.PhotoPrivacyMiddleware)
        self.photo_app.include_router(progress_photos.create_router(self.get_photo_db))
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database_path = Path(self.folder.name) / 'test.db'
        self.directory_patch = patch.object(progress_photos, 'PHOTO_DIR', Path(self.folder.name) / 'photos')
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        with closing(sqlite3.connect(self.database_path)) as db:
            migrate(db)

    def get_photo_db(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def request(self, method, path='/progress-photos', body=b'', content_type='application/json', client='127.0.0.1', host='localhost', extra_headers=()):
        target = urlsplit(path)

        async def run():
            messages = []
            delivered = False

            async def receive():
                nonlocal delivered
                if delivered:
                    await asyncio.Event().wait()
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}

            async def send(message):
                messages.append(message)

            await self.photo_app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                           'method': method, 'scheme': 'http', 'path': target.path, 'raw_path': target.path.encode(),
                           'query_string': target.query.encode(), 'headers': [(b'host', host.encode()), (b'content-type', content_type.encode()), *extra_headers],
                           'client': (client, 1), 'server': ('localhost', 80)}, receive, send)
            status = messages[0]['status']
            headers = dict(messages[0]['headers'])
            data = b''.join(message.get('body', b'') for message in messages[1:])
            if headers.get(b'content-type', b'').startswith(b'application/json'):
                data = json.loads(data)
            return status, data, headers

        return asyncio.run(run())

    def image(self, format='PNG', metadata=False):
        output = io.BytesIO()
        photo = Image.new('RGB', (12, 16), 'green')
        if metadata:
            exif = Image.Exif()
            exif[270] = 'private metadata'
            photo.save(output, format=format, exif=exif)
        else:
            photo.save(output, format=format)
        return output.getvalue()

    def upload(self, data=None, category=None, filename='../../private-name.png', content_type='image/png'):
        boundary = 'gym-photo-test'
        body = b''
        if category is not None:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="category"\r\n\r\n{category}\r\n'.encode()
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
        body += self.image() if data is None else data
        body += f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST', body=body, content_type=f'multipart/form-data; boundary={boundary}')

    def saved_files(self):
        return list(progress_photos.PHOTO_DIR.glob('*'))

    def test_upload_list_view_delete(self):
        self.assertEqual(self.request('GET')[1], [])
        first_status, first, headers = self.upload(self.image('JPEG', metadata=True), 'front')
        self.assertEqual(first_status, 201)
        self.assertEqual(headers[b'cache-control'], b'no-store')
        self.assertEqual(set(first), {'id', 'uploaded_at', 'category'})
        self.assertEqual(first['category'], 'front')
        self.assertIn('+00:00', first['uploaded_at'])
        status, second, _ = self.upload(category='back')
        self.assertEqual(status, 201)
        self.assertEqual([item['id'] for item in self.request('GET')[1]], [second['id'], first['id']])
        self.assertEqual([item['id'] for item in self.request('GET', '/progress-photos?sort=oldest')[1]], [first['id'], second['id']])
        self.assertEqual(self.request('GET', '/progress-photos?sort=bad')[0], 422)
        # Ties remain deterministic in both directions.
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute('UPDATE progress_photos SET uploaded_at = ?', (first['uploaded_at'],))
            db.commit()
        self.assertEqual(self.request('GET')[1][0]['id'], second['id'])
        self.assertEqual(self.request('GET', '/progress-photos?sort=oldest')[1][0]['id'], first['id'])
        status, image, headers = self.request('GET', f"/progress-photos/{first['id']}/image")
        self.assertEqual(status, 200)
        self.assertEqual(headers[b'cache-control'], b'no-store')
        self.assertEqual(headers[b'content-type'], b'image/jpeg')
        with Image.open(io.BytesIO(image)) as decoded:
            self.assertEqual(decoded.format, 'JPEG')
            self.assertFalse(decoded.getexif())
        for file in self.saved_files():
            self.assertRegex(file.name, r'^[a-f0-9]{32}\.jpg$')
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.request('DELETE', f"/progress-photos/{first['id']}")[0], 204)
        self.assertEqual(len(self.saved_files()), 1)
        self.assertEqual(self.request('GET', f"/progress-photos/{first['id']}/image")[0], 404)
        self.assertEqual(self.request('DELETE', f"/progress-photos/{first['id']}")[0], 404)
        self.assertEqual(self.request('GET')[1][0]['id'], second['id'])

    def test_validation_leaves_no_files(self):
        self.assertEqual(self.upload(category='legs')[0], 422)
        self.assertEqual(self.upload(b'not an image')[0], 415)
        self.assertEqual(self.upload(b'')[0], 415)
        self.assertEqual(self.upload(self.image('GIF'))[0], 415)
        self.assertEqual(self.upload(self.image()[:35])[0], 415)
        with patch.object(progress_photos, 'MAX_UPLOAD_BYTES', 10):
            self.assertEqual(self.upload()[0], 413)
            self.assertEqual(self.request('POST', body=b'x' * 70000)[0], 413)
        with patch.object(progress_photos, 'MAX_PIXELS', 100):
            self.assertEqual(self.upload()[0], 413)
        self.assertEqual(self.saved_files(), [])
        self.assertEqual(self.request('GET')[1], [])
        self.assertEqual(self.upload(content_type='text/plain')[0], 201)  # Real bytes, not the claimed MIME type, determine format.

    def test_private_access(self):
        for arguments in [{'client': '192.168.1.4'}, {'host': '192.168.1.4'}, {'host': 'evil.example'},
                          {'extra_headers': [(b'origin', b'https://evil.example')]},
                          {'extra_headers': [(b'sec-fetch-site', b'cross-site')]}]:
            for method, path in [('GET', '/progress-photos'), ('GET', '/progress-photos/1/image'),
                                 ('POST', '/progress-photos'), ('DELETE', '/progress-photos/1')]:
                status, _, headers = self.request(method, path, **arguments)
                self.assertEqual(status, 403)
                self.assertEqual(headers[b'cache-control'], b'no-store')
        self.assertEqual(self.request('GET', extra_headers=[(b'origin', b'http://localhost')])[0], 200)
        self.assertEqual(self.request('GET', client='::1', host='[::1]')[0], 200)

    def test_upload_failure_cleans_file_and_record(self):
        with patch.object(progress_photos, 'require_photo', side_effect=sqlite3.OperationalError('disk error')):
            self.assertEqual(self.upload()[0], 503)
        self.assertEqual(self.saved_files(), [])
        self.assertEqual(self.request('GET')[1], [])

    def test_filename_collision_never_deletes_existing_image(self):
        fixed_id = Mock(hex='a' * 32)
        with patch.object(progress_photos, 'uuid4', return_value=fixed_id):
            self.assertEqual(self.upload()[0], 201)
            original = self.saved_files()[0].read_bytes()
            self.assertEqual(self.upload()[0], 503)
            self.assertEqual(self.saved_files()[0].read_bytes(), original)
            self.assertEqual(len(self.request('GET')[1]), 1)

    def test_delete_failure_can_be_retried(self):
        _, photo, _ = self.upload()
        with patch.object(progress_photos, 'photo_path', return_value=Mock(unlink=Mock(side_effect=OSError('permission denied')))):
            self.assertEqual(self.request('DELETE', f"/progress-photos/{photo['id']}")[0], 503)
        self.assertEqual(len(self.saved_files()), 1)
        self.assertEqual(len(self.request('GET')[1]), 1)
        self.assertEqual(self.request('DELETE', f"/progress-photos/{photo['id']}")[0], 204)
        # A missing file after an interrupted delete can also be finished by retrying.
        _, photo, _ = self.upload()
        self.saved_files()[0].unlink()
        self.assertEqual(self.request('DELETE', f"/progress-photos/{photo['id']}")[0], 204)

    def test_migration_is_repeatable_and_preserves_sets(self):
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute('CREATE TABLE sets (id INTEGER PRIMARY KEY, weight REAL)')
            db.execute('INSERT INTO sets (weight) VALUES (?)', (155,))
            db.commit()
            migrate(db)
            migrate(db)
            self.assertEqual(db.execute('SELECT weight FROM sets').fetchall(), [(155.0,)])


if __name__ == '__main__':
    unittest.main()

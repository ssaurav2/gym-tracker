"""Local-only photo routes. Image bytes stay outside SQLite and public folders."""

import io
import ipaddress
import os
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

PHOTO_DIR = Path(os.environ.get('GYM_PHOTO_DIR', Path(__file__).resolve().parent / 'private' / 'progress-photos'))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAX_DIMENSION = 10_000


def require_local(request: Request):
    """No accounts yet: reject remote clients, hosts, and cross-site browser requests."""
    try:
        local_client = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local_client = False
    if not local_client or request.url.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise HTTPException(403, 'Progress photos are available only on this computer for now.')
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        raise HTTPException(403, 'Cross-site photo requests are not allowed.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site photo requests are not allowed.')


class PhotoPrivacyMiddleware:
    """Check local access and cap the entire upload before multipart parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/progress-photos'):
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend([(b'cache-control', b'no-store'),
                                (b'x-content-type-options', b'nosniff'),
                                (b'cross-origin-resource-policy', b'same-origin')])
                message = {**message, 'headers': headers}
            await send(message)

        try:
            require_local(Request(scope))
        except HTTPException as error:
            return await JSONResponse({'detail': error.detail}, status_code=error.status_code)(scope, receive, private_send)

        if scope['method'] == 'POST':
            # Includes a small allowance for the form envelope; file bytes have a tighter limit.
            limit = MAX_UPLOAD_BYTES + 64 * 1024
            chunks = []
            total = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                total += len(chunk)
                if total > limit:
                    return await JSONResponse({'detail': 'Choose a photo smaller than 10 MB.'}, status_code=413)(scope, receive, private_send)
                chunks.append(chunk)
                if not message.get('more_body', False):
                    break
            body = b''.join(chunks)
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if delivered:
                    return {'type': 'http.disconnect'}
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}

            return await self.app(scope, buffered_receive, private_send)
        return await self.app(scope, receive, private_send)


def photo_path(filename):
    # Only generated filenames are valid, including records read from the database.
    stem = filename.removesuffix('.jpg')
    if len(stem) != 32 or any(char not in '0123456789abcdef' for char in stem) or filename != stem + '.jpg':
        raise HTTPException(404, 'Photo not found')
    path = PHOTO_DIR / filename
    if path.is_symlink():
        raise HTTPException(404, 'Photo not found')
    return path


def public_photo(row):
    return {key: row[key] for key in ('id', 'uploaded_at', 'category')}


def require_photo(db, photo_id):
    row = db.execute('SELECT id, file_path, uploaded_at, category FROM progress_photos WHERE id = ?', (photo_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Photo not found')
    return row


def clean_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG'}:
                    raise HTTPException(415, 'Choose a JPEG or PNG image.')
                if source.width * source.height > MAX_PIXELS or max(source.size) > MAX_DIMENSION:
                    raise HTTPException(413, 'Photo dimensions are too large (maximum 24 megapixels and 10,000 pixels per side).')
                if getattr(source, 'n_frames', 1) != 1:
                    raise HTTPException(415, 'Choose a still JPEG or PNG image.')
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((2048, 2048))
                rgba = oriented.convert('RGBA')
                # A fresh image deliberately excludes EXIF, GPS, comments, and other metadata.
                clean = Image.new('RGB', rgba.size, 'white')
                clean.paste(rgba, mask=rgba.getchannel('A'))
                output = io.BytesIO()
                clean.save(output, format='JPEG', quality=88)
                return output.getvalue()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, 'Photo dimensions are too large.') from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(415, 'That file is not a readable JPEG or PNG image.') from None


def create_router(get_db):
    router = APIRouter(prefix='/progress-photos', dependencies=[Depends(require_local)])

    @router.get('')
    def list_photos(sort: Literal['newest', 'oldest'] = 'newest', db=Depends(get_db)):
        # Separate fixed queries keep the sort input out of SQL text.
        query = ('SELECT id, uploaded_at, category FROM progress_photos ORDER BY uploaded_at DESC, id DESC'
                 if sort == 'newest' else
                 'SELECT id, uploaded_at, category FROM progress_photos ORDER BY uploaded_at ASC, id ASC')
        return [public_photo(row) for row in db.execute(query)]

    @router.post('', status_code=201)
    def upload_photo(file: UploadFile = File(...), category: Literal['front', 'back', 'side'] | None = Form(None), db=Depends(get_db)):
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'Choose a photo smaller than 10 MB.')
        if not data:
            raise HTTPException(415, 'Choose a JPEG or PNG image.')
        encoded = clean_image(data)
        filename = uuid4().hex + '.jpg'
        path = photo_path(filename)
        created = False
        try:
            PHOTO_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Create exclusively, with permissions limited to the computer account.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, 'wb') as output:
                output.write(encoded)
            with db:
                cursor = db.execute(
                    'INSERT INTO progress_photos (file_path, uploaded_at, category) VALUES (?, ?, ?)',
                    (filename, datetime.now(timezone.utc).isoformat(), category),
                )
                result = public_photo(require_photo(db, cursor.lastrowid))
            return result
        except (OSError, sqlite3.Error):
            if created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # Never hide the failed save or delete an unrelated file after a collision.
            raise HTTPException(503, 'Couldn’t save the photo. Please retry.') from None

    @router.get('/{photo_id}/image')
    def image(photo_id: int, db=Depends(get_db)):
        path = photo_path(require_photo(db, photo_id)['file_path'])
        if not path.is_file():
            raise HTTPException(404, 'Photo file not found')
        return FileResponse(path, media_type='image/jpeg')

    @router.delete('/{photo_id}', status_code=204)
    def delete_photo(photo_id: int, db=Depends(get_db)):
        try:
            # Files and SQLite cannot share a transaction. Keep the record until the file
            # is removed; if commit fails, retry can remove the remaining record.
            with db:
                db.execute('BEGIN IMMEDIATE')
                row = require_photo(db, photo_id)
                photo_path(row['file_path']).unlink(missing_ok=True)
                db.execute('DELETE FROM progress_photos WHERE id = ?', (photo_id,))
        except (OSError, sqlite3.Error):
            raise HTTPException(503, 'Couldn’t finish deleting the photo. Please retry.') from None
        return Response(status_code=204)

    return router

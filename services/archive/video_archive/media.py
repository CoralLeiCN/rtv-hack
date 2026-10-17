import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse


def media_id(source):
    if not isinstance(source, str) or not source.startswith('media://'):
        raise ValueError('Invalid media reference')
    value = source.removeprefix('media://')
    if str(UUID(value)) != value:
        raise ValueError('Invalid media reference')
    return UUID(value)


class MediaStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, key):
        part = PurePosixPath(key)
        if not key or part.is_absolute() or '..' in part.parts or '\\' in key:
            raise ValueError('Invalid storage key')
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError('Invalid storage key')
        return path

    def ready(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=self.root) as file:
            file.write(b'probe')

    def import_video(self, source):
        # Stage and hash in one pass: the stored bytes define the checksum even
        # if the caller changes its source while import is running.
        self.ready()
        with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as file:
            temporary = Path(file.name)
            digest = hashlib.sha256()
            try:
                with Path(source).open('rb') as input_file:
                    while chunk := input_file.read(1024 * 1024):
                        digest.update(chunk)
                        file.write(chunk)
                file.flush()
                os.fsync(file.fileno())
                checksum = digest.hexdigest()
                key = f'originals/{checksum}.video'
                target = self.path(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, target)
                return checksum, key
            finally:
                temporary.unlink(missing_ok=True)

    def response(self, key, method, range_header=None, if_range=None):
        try:
            path = self.path(key)
            # Symlink containment is checked above. Media directories are writable
            # only by the trusted worker, never by API callers.
            handle = path.open('rb')
        except (ValueError, OSError):
            raise HTTPException(404, 'Media is unavailable') from None
        stat = os.fstat(handle.fileno())
        size = stat.st_size
        etag = f'"{stat.st_mtime_ns:x}-{size:x}"'
        headers = {'Accept-Ranges': 'bytes', 'ETag': etag, 'Content-Type': 'video/mp4'}
        start, end, status = 0, size - 1, 200
        if range_header and (not if_range or if_range == etag):
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header) if len(range_header) <= 100 else None
            if not match or not any(match.groups()):
                handle.close()
                return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                start = max(0, size - int(last))
            if start >= size or start > end or (not first and int(last) == 0):
                handle.close()
                return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
            status = 206
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        headers['Content-Length'] = str(max(0, end - start + 1))
        if method == 'HEAD':
            handle.close()
            return Response(status_code=status, headers=headers)
        handle.seek(start)

        def chunks():
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

        class LocalResponse(StreamingResponse):
            async def __call__(self, scope, receive, send):
                try:
                    await super().__call__(scope, receive, send)
                finally:
                    handle.close()

        return LocalResponse(chunks(), status_code=status, headers=headers)

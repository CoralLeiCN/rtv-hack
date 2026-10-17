from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


def http_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Expected an HTTP(S) service URL without credentials, query or fragment')
    return value.rstrip('/')


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default='', repr=False)
    worker_database_url: str = field(default='', repr=False)
    api_key: str = field(default='', repr=False)
    qdrant_url: str = 'http://127.0.0.1:6333'
    qdrant_api_key: str = field(default='', repr=False)
    collection: str = 'microduck_embeddinggemma2_768'
    media_root: Path = Path('media')
    embedding_model: str = 'google/embeddinggemma-2'
    embedding_revision: str = 'main'
    embedding_device: str = 'cpu'
    cosmos_url: str = 'http://127.0.0.1:8002/v1'
    cosmos_model: str = 'nvidia/Cosmos3-Nano'
    cosmos_revision: str = 'main'
    cosmos_api_key: str = field(default='', repr=False)
    model_timeout: float = 180
    dimensions: int = 768

    @classmethod
    def from_env(cls):
        values = {**dotenv_values(os.environ.get('ARCHIVE_ENV_FILE', '.env'), interpolate=False), **os.environ}
        names = {
            'database_url': 'DATABASE_URL', 'worker_database_url': 'WORKER_DATABASE_URL',
            'api_key': 'ARCHIVE_API_KEY', 'qdrant_url': 'QDRANT_URL', 'qdrant_api_key': 'QDRANT_API_KEY',
            'collection': 'QDRANT_COLLECTION', 'embedding_model': 'EMBEDDING_MODEL',
            'embedding_revision': 'EMBEDDING_REVISION', 'embedding_device': 'EMBEDDING_DEVICE',
            'cosmos_url': 'COSMOS_URL', 'cosmos_model': 'COSMOS_MODEL',
            'cosmos_revision': 'COSMOS_REVISION', 'cosmos_api_key': 'COSMOS_API_KEY',
        }
        args = {key: values[name] for key, name in names.items() if values.get(name)}
        args['media_root'] = Path(values.get('MEDIA_ROOT') or 'media').expanduser().resolve()
        return cls(**args)

    def validate(self):
        if not self.database_url or not self.api_key or not self.api_key.isascii() or any(c.isspace() for c in self.api_key):
            raise ValueError('Set DATABASE_URL and a nonblank ARCHIVE_API_KEY')
        http_url(self.qdrant_url)
        http_url(self.cosmos_url)
        if self.dimensions != 768:
            raise ValueError('This index requires 768-dimensional EmbeddingGemma 2 vectors')

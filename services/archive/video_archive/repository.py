from contextlib import contextmanager, nullcontext
from importlib.resources import files
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb


class Repository:
    def __init__(self, settings, *, connection=None):
        self.settings = settings
        self._connection = connection

    def connect(self, *, worker=False):
        if self._connection is not None:
            # Never reconnect a worker: losing this session also loses its lock.
            return nullcontext(self._connection)
        # Session advisory locks require Neon's DIRECT (non-pooler) connection.
        dsn = (self.settings.worker_database_url or self.settings.database_url) if worker else self.settings.database_url
        if worker and '-pooler' in conninfo_to_dict(dsn).get('host', ''):
            raise ValueError('Worker requires a direct Postgres URL, not a transaction pooler')
        return psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row,
                               autocommit=True, options='-c statement_timeout=30000')

    def initialize(self):
        with self.connect() as conn:
            with conn.transaction():
                conn.execute(files('video_archive').joinpath('schema.sql').read_text())

    def ready(self):
        with self.connect() as conn:
            conn.execute('SELECT id,index_id FROM archive_segments LIMIT 0')

    @contextmanager
    def worker_lock(self):
        with self.connect(worker=True) as conn:
            acquired = conn.execute('SELECT pg_try_advisory_lock(847203315) AS acquired').fetchone()['acquired']
            if not acquired:
                raise ValueError('Another archive worker is active')
            try:
                yield Repository(self.settings, connection=conn)
            finally:
                conn.execute('SELECT pg_advisory_unlock(847203315)')

    def assert_worker(self):
        if self._connection is None:
            raise ValueError('Worker operations require the lock-owning session')
        self._connection.execute('SELECT 1')

    def enqueue(self, video_id, checksum, key, job_id, options):
        with self.connect() as conn:
            with conn.transaction():
                conn.execute('INSERT INTO archive_videos(id,checksum,storage_key) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                             (video_id, checksum, key))
                conn.execute('INSERT INTO archive_jobs(id,video_id,settings) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                             (job_id, video_id, Jsonb(options)))
        return str(job_id)

    def next_job(self):
        with self.connect() as conn:
            conn.execute("UPDATE archive_jobs SET status='failed', error_code='worker_interrupted' WHERE status='running' AND attempts >= 3")
            # A single advisory-locked worker owns running jobs. A crash releases
            # the lock, and its successor may immediately resume the running job.
            return conn.execute("""UPDATE archive_jobs SET status='running', attempts=attempts+1, updated_at=now()
                WHERE id=(SELECT id FROM archive_jobs WHERE status IN ('pending','running')
                    AND attempts < 3 AND available_at <= now() ORDER BY created_at LIMIT 1)
                RETURNING *""").fetchone()

    def finish(self, job_id, error=None):
        with self.connect() as conn:
            conn.execute("""UPDATE archive_jobs SET status=CASE WHEN %s::text IS NULL THEN 'complete'
                WHEN attempts >= 3 THEN 'failed' ELSE 'pending' END, error_code=%s,
                available_at=now()+interval '30 seconds', updated_at=now() WHERE id=%s""", (error, error, job_id))

    def retry(self, job_id):
        with self.worker_lock() as worker, worker.connect() as conn:
            row = conn.execute("""UPDATE archive_jobs SET status='pending', attempts=0,
                available_at=now(), error_code=NULL WHERE id=%s RETURNING id""", (job_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown job')

    def jobs(self):
        with self.connect() as conn:
            return conn.execute('SELECT id,status,attempts,error_code FROM archive_jobs ORDER BY created_at DESC LIMIT 100').fetchall()

    def video(self, video_id):
        with self.connect() as conn:
            return conn.execute('SELECT * FROM archive_videos WHERE id=%s', (video_id,)).fetchone()

    def save_segment(self, row):
        with self.connect() as conn:
            conn.execute('''INSERT INTO archive_segments
                (id,index_id,job_id,video_id,storage_key,caption,start_sec,end_sec,dataset_id,tags,embedding_identity)
                VALUES (%(id)s,%(index_id)s,%(job_id)s,%(video_id)s,%(storage_key)s,%(caption)s,%(start_sec)s,%(end_sec)s,%(dataset_id)s,%(tags)s,%(embedding_identity)s)
                ON CONFLICT(id) DO UPDATE SET indexed=false, index_id=EXCLUDED.index_id,
                    storage_key=EXCLUDED.storage_key''', row)

    def segment(self, segment_id):
        with self.connect() as conn:
            return conn.execute('SELECT * FROM archive_segments WHERE id=%s', (segment_id,)).fetchone()

    def mark_indexed(self, segment_id):
        with self.connect() as conn:
            conn.execute('UPDATE archive_segments SET indexed=true WHERE id=%s', (segment_id,))

    def indexed(self, ids, tags, identity):
        if not ids:
            return {}
        with self.connect() as conn:
            rows = conn.execute('''SELECT * FROM archive_segments WHERE index_id=ANY(%s)
                AND indexed AND embedding_identity=%s AND (%s::text[]='{}' OR tags && %s)''',
                ([UUID(str(item)) for item in ids], identity, tags, tags)).fetchall()
            return {str(row['index_id']): row for row in rows}

    def metadata(self):
        with self.connect() as conn:
            tags = conn.execute('SELECT DISTINCT unnest(tags) AS tag FROM archive_segments WHERE indexed ORDER BY tag').fetchall()
            datasets = conn.execute('SELECT DISTINCT dataset_id FROM archive_segments WHERE indexed ORDER BY dataset_id').fetchall()
            return {'tags': [r['tag'] for r in tags], 'datasets': [r['dataset_id'] for r in datasets]}

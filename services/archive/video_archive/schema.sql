CREATE TABLE IF NOT EXISTS archive_videos (
    id uuid PRIMARY KEY,
    checksum text NOT NULL,
    storage_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archive_jobs (
    id uuid PRIMARY KEY,
    video_id uuid NOT NULL REFERENCES archive_videos(id),
    settings jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','complete','failed')),
    attempts integer NOT NULL DEFAULT 0,
    error_code text,
    available_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archive_segments (
    id uuid PRIMARY KEY,
    index_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES archive_jobs(id),
    video_id uuid NOT NULL REFERENCES archive_videos(id),
    storage_key text NOT NULL,
    caption text NOT NULL,
    start_sec double precision NOT NULL CHECK (start_sec >= 0),
    end_sec double precision NOT NULL CHECK (end_sec > start_sec),
    dataset_id text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}',
    embedding_identity text NOT NULL,
    indexed boolean NOT NULL DEFAULT false,
    UNIQUE(job_id, start_sec)
);
-- Upgrade existing archives without invalidating their published vector IDs.
ALTER TABLE archive_segments ADD COLUMN IF NOT EXISTS index_id uuid;
UPDATE archive_segments SET index_id=id WHERE index_id IS NULL;
ALTER TABLE archive_segments ALTER COLUMN index_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS archive_segments_index_id ON archive_segments(index_id);
CREATE INDEX IF NOT EXISTS archive_segments_tags ON archive_segments USING gin(tags);
CREATE INDEX IF NOT EXISTS archive_jobs_queue ON archive_jobs(status, available_at);

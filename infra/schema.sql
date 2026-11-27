-- Batches group the images from one upload session.
CREATE TABLE IF NOT EXISTS batches (
    id          UUID PRIMARY KEY,
    operation   TEXT NOT NULL,                        -- e.g. 'resize'
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- operation parameters (width, height, ...)
    status      TEXT NOT NULL DEFAULT 'awaiting_upload'
                CHECK (status IN ('awaiting_upload', 'queued')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    queued_at   TIMESTAMPTZ
);

-- One job per image. PostgreSQL is the source of truth for job state.
CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY,
    batch_id      UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    source_key    TEXT NOT NULL UNIQUE,
    result_key    TEXT NOT NULL UNIQUE,   -- deterministic, so a retried job overwrites instead of duplicating
    status        TEXT NOT NULL DEFAULT 'awaiting_upload'
                  CHECK (status IN ('awaiting_upload', 'upload_missing', 'queued', 'processing', 'done', 'failed')),
    attempts      INT  NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_batch_id_idx ON jobs (batch_id);

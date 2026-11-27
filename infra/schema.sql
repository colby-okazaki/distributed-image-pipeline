CREATE TABLE IF NOT EXISTS batches (
    id          UUID PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'uploading',  -- uploading | queued | processing | done | partial_failure
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id           UUID PRIMARY KEY,
    batch_id     UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    source_key   TEXT NOT NULL,
    result_key   TEXT,
    operation    TEXT NOT NULL DEFAULT 'resize',
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done | failed
    attempts     INT  NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_batch_id_idx ON jobs (batch_id);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'Entwurf',
    fine_tuned_model TEXT
);

CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    workflow_id INTEGER REFERENCES workflows(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    credits_estimate INTEGER NOT NULL DEFAULT 0,
    credits_used INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL DEFAULT 'info',
    block_id TEXT,
    api_status TEXT,
    duration_ms REAL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_log_run ON run_log(run_id, id);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    protocol TEXT NOT NULL,
    config TEXT NOT NULL,
    unit TEXT,
    min REAL,
    max REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

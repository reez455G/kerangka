-- 001_initial.sql — Agent Control Plane schema for my-ai-agents-db
-- Safe to re-run (all CREATE TABLE IF NOT EXISTS).
-- Run via: wrangler d1 execute my-ai-agents-db --file=cloudflare/schema/001_initial.sql

-- resources: registered infrastructure resources owned by this ecosystem
CREATE TABLE IF NOT EXISTS resources (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  type        TEXT NOT NULL,        -- worker|d1_database|kv_namespace|r2_bucket|queue|workflow|cron|tunnel|domain
  environment TEXT NOT NULL DEFAULT 'production',
  owner       TEXT NOT NULL DEFAULT 'my-ai-agents',
  purpose     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',  -- active|retired|error
  external_id TEXT,                -- Cloudflare resource ID/UUID
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  metadata    TEXT,                -- JSON blob for extra fields
  UNIQUE(name, type, environment)
);

-- agent_runs: execution records for meaningful agent runs
CREATE TABLE IF NOT EXISTS agent_runs (
  id            TEXT PRIMARY KEY,
  agent_id      TEXT NOT NULL,
  project_id    TEXT,
  started_at    TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at   TEXT,
  status        TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed|cancelled
  trigger       TEXT,             -- manual|cron|webhook|agent
  model         TEXT,
  result        TEXT,             -- brief result summary (no secrets, no large content)
  error         TEXT,
  artifact_refs TEXT,             -- JSON array of artifact IDs
  metadata      TEXT              -- JSON
);

-- agent_events: ordered timeline of events within a run
CREATE TABLE IF NOT EXISTS agent_events (
  id         TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL,
  agent_id   TEXT NOT NULL,
  event_type TEXT NOT NULL,       -- started|tool_call|skill_used|memory_recalled|error|completed
  timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
  data       TEXT,                -- JSON (no secrets)
  FOREIGN KEY (run_id) REFERENCES agent_runs(id)
);

-- artifacts: metadata for files stored in R2 (binary content lives in R2, not here)
CREATE TABLE IF NOT EXISTS artifacts (
  id           TEXT PRIMARY KEY,
  run_id       TEXT,
  agent_id     TEXT,
  type         TEXT NOT NULL,     -- report|screenshot|export|log|generated-file|backup
  storage      TEXT NOT NULL DEFAULT 'r2',
  object_key   TEXT NOT NULL,     -- R2 key (e.g. my-ai-agents/agent-runs/production/claude/run-abc/result.json)
  size         INTEGER,
  content_type TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  metadata     TEXT              -- JSON
);

-- indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_id  ON agent_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status    ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_started   ON agent_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_run_id  ON agent_events(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_ts      ON agent_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id     ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_agent_id   ON artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_resources_type       ON resources(type);
CREATE INDEX IF NOT EXISTS idx_resources_status     ON resources(status);

-- 002_idempotency.sql — Add idempotency_key to agent_runs
-- Safe to re-run (ALTER TABLE IF NOT EXISTS is not SQLite syntax;
-- wrangler D1 execute is idempotent at the file level via bookmarks).
-- Run via: wrangler d1 execute my-ai-agents-db --file=cloudflare/schema/002_idempotency.sql --remote

ALTER TABLE agent_runs ADD COLUMN idempotency_key TEXT;

-- Partial unique index: deduplicate only when key is supplied.
-- Runs without an idempotency_key can always be created freely.
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_runs_idempotency
  ON agent_runs(idempotency_key)
  WHERE idempotency_key IS NOT NULL;

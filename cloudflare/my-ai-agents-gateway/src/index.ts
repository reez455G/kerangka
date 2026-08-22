/**
 * my-ai-agents-gateway — Agent Control Plane HTTP API
 *
 * Thin HTTP layer over D1 my-ai-agents-db.
 * Agents write artifacts directly to R2 (metadata only stored here) EXCEPT
 * the daily digest cron job below, which owns and writes its own R2 object
 * because it runs entirely inside the Worker with no external agent caller.
 *
 * Auth: Authorization: Bearer <GATEWAY_TOKEN> on all /v1/* routes.
 */

export interface Env {
  DB: D1Database;
  R2: R2Bucket;
  GATEWAY_TOKEN: string;
  HINDSIGHT_API_URL: string;
  HINDSIGHT_API_TOKEN: string;
}

const VALID_STATUSES: Record<string, true> = { running: true, completed: true, failed: true, cancelled: true };
const ARTIFACT_PREFIX = "my-ai-agents/";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errRes(message: string, status = 400): Response {
  return jsonRes({ error: message }, status);
}

function nanoid(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 20);
}

// ── router ────────────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { pathname } = url;
    const method = request.method;

    if (pathname === "/health" && method === "GET") {
      return jsonRes({ status: "ok", service: "my-ai-agents-gateway", timestamp: new Date().toISOString() });
    }

    if (pathname.startsWith("/v1/")) {
      const authHeader = request.headers.get("Authorization") ?? "";
      if (authHeader !== `Bearer ${env.GATEWAY_TOKEN}`) {
        return errRes("Unauthorized", 401);
      }
      // Manual trigger for the daily digest — same logic the Cron Trigger runs.
      // Useful for testing without waiting for the schedule.
      if (pathname === "/v1/digest/run" && method === "POST") {
        const result = await runDailyDigest(env);
        return jsonRes(result, 201);
      }
      return routeV1(request, url, env);
    }

    return errRes("Not found", 404);
  },

  // Cloudflare Cron Trigger entrypoint — see wrangler.toml [triggers].
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runDailyDigest(env));
  },
};

async function routeV1(request: Request, url: URL, env: Env): Promise<Response> {
  const { pathname } = url;
  const method = request.method;

  // ── Resources ──────────────────────────────────────────────────────────────

  if (pathname === "/v1/resources") {
    if (method === "GET") {
      const rows = await env.DB.prepare(
        "SELECT * FROM resources WHERE status != 'retired' ORDER BY type, name"
      ).all();
      return jsonRes({ resources: rows.results });
    }

    if (method === "POST") {
      const body: Record<string, unknown> = await request.json();
      const { name, type, environment = "production", owner = "my-ai-agents",
              purpose, status = "active", external_id = null, metadata = null } = body;
      if (!name || !type || !purpose) return errRes("Missing: name, type, purpose");

      const id = `res-${nanoid()}`;
      // RETURNING id gives back the actual stored id (existing or newly inserted).
      const row = await env.DB.prepare(
        `INSERT INTO resources (id, name, type, environment, owner, purpose, status, external_id, metadata)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(name, type, environment) DO UPDATE
           SET owner=excluded.owner, purpose=excluded.purpose, status=excluded.status,
               external_id=excluded.external_id, metadata=excluded.metadata,
               updated_at=datetime('now')
         RETURNING id`
      ).bind(id, name, type, environment, owner, purpose, status, external_id,
             metadata ? JSON.stringify(metadata) : null).first<{ id: string }>();

      return jsonRes({ id: row?.id ?? id }, 201);
    }
  }

  // ── Agent Runs ─────────────────────────────────────────────────────────────

  if (pathname === "/v1/runs") {
    if (method !== "POST") return errRes("Method not allowed", 405);

    const body: Record<string, unknown> = await request.json();
    const { agent_id, project_id = null, trigger = "manual",
            model = null, metadata = null, idempotency_key = null } = body;
    if (!agent_id) return errRes("Missing: agent_id");

    // Idempotency: if key supplied, return existing run instead of creating duplicate.
    if (idempotency_key) {
      const existing = await env.DB.prepare(
        "SELECT id, agent_id, status FROM agent_runs WHERE idempotency_key = ?"
      ).bind(idempotency_key).first<{ id: string; agent_id: string; status: string }>();
      if (existing) return jsonRes({ id: existing.id, agent_id: existing.agent_id, status: existing.status });
    }

    const id = `run-${nanoid()}`;
    await env.DB.prepare(
      `INSERT INTO agent_runs (id, agent_id, project_id, trigger, model, metadata, idempotency_key)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(id, agent_id, project_id, trigger, model,
           metadata ? JSON.stringify(metadata) : null, idempotency_key ?? null).run();

    return jsonRes({ id, agent_id, status: "running" }, 201);
  }

  // ── Single Run ─────────────────────────────────────────────────────────────

  const runMatch = pathname.match(/^\/v1\/runs\/([^/]+)$/);
  if (runMatch) {
    const runId = runMatch[1];

    if (method === "GET") {
      const row = await env.DB.prepare("SELECT * FROM agent_runs WHERE id = ?").bind(runId).first();
      if (!row) return errRes("Run not found", 404);
      return jsonRes(row);
    }

    if (method === "PATCH") {
      const body: Record<string, unknown> = await request.json();
      const { status, result = null, error = null, artifact_refs = null } = body;

      if (status !== undefined && !VALID_STATUSES[status as string]) {
        return errRes(`Invalid status. Allowed: ${Object.keys(VALID_STATUSES).join(", ")}`);
      }

      const terminal = ["completed", "failed", "cancelled"].includes(status as string);

      // COALESCE: only overwrite result/error/artifact_refs when the new value is non-null.
      // This makes PATCH idempotent — re-calling with just {status} preserves prior result.
      await env.DB.prepare(
        `UPDATE agent_runs
         SET status=COALESCE(?, status),
             result=COALESCE(?, result),
             error=COALESCE(?, error),
             artifact_refs=COALESCE(?, artifact_refs),
             finished_at=CASE WHEN ? THEN COALESCE(finished_at, datetime('now')) ELSE finished_at END
         WHERE id=?`
      ).bind(status ?? null, result, error,
             artifact_refs ? JSON.stringify(artifact_refs) : null,
             terminal ? 1 : 0, runId).run();

      return jsonRes({ id: runId, status });
    }
  }

  // ── Run Events ─────────────────────────────────────────────────────────────

  const eventsMatch = pathname.match(/^\/v1\/runs\/([^/]+)\/events$/);
  if (eventsMatch) {
    const runId = eventsMatch[1];

    if (method === "GET") {
      const rows = await env.DB.prepare(
        "SELECT * FROM agent_events WHERE run_id = ? ORDER BY timestamp ASC"
      ).bind(runId).all();
      return jsonRes({ events: rows.results });
    }

    if (method === "POST") {
      const body: Record<string, unknown> = await request.json();
      const { agent_id, event_type, data = null } = body;
      if (!agent_id || !event_type) return errRes("Missing: agent_id, event_type");

      // Verify parent run exists before inserting an orphan event.
      const run = await env.DB.prepare("SELECT id FROM agent_runs WHERE id = ?").bind(runId).first();
      if (!run) return errRes("Run not found", 404);

      const id = `evt-${nanoid()}`;
      await env.DB.prepare(
        `INSERT INTO agent_events (id, run_id, agent_id, event_type, data)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(id, runId, agent_id, event_type,
             data ? JSON.stringify(data) : null).run();
      return jsonRes({ id }, 201);
    }
  }

  // ── Artifacts ──────────────────────────────────────────────────────────────

  if (pathname === "/v1/artifacts") {
    if (method === "GET") {
      const run_id = url.searchParams.get("run_id");
      const agent_id = url.searchParams.get("agent_id");
      let query = "SELECT * FROM artifacts WHERE 1=1";
      const params: (string | null)[] = [];
      if (run_id) { query += " AND run_id = ?"; params.push(run_id); }
      if (agent_id) { query += " AND agent_id = ?"; params.push(agent_id); }
      query += " ORDER BY created_at DESC";
      const rows = await env.DB.prepare(query).bind(...params).all();
      return jsonRes({ artifacts: rows.results });
    }

    if (method === "POST") {
      const body: Record<string, unknown> = await request.json();
      const { run_id = null, agent_id = null, type, object_key,
              size = null, content_type = null, metadata = null } = body;
      if (!type || !object_key) return errRes("Missing: type, object_key");

      // Enforce R2 key prefix so agents can't register keys outside the agent namespace.
      if (!(object_key as string).startsWith(ARTIFACT_PREFIX)) {
        return errRes(`object_key must start with "${ARTIFACT_PREFIX}"`);
      }

      const id = `art-${nanoid()}`;
      await env.DB.prepare(
        `INSERT INTO artifacts (id, run_id, agent_id, type, object_key, size, content_type, metadata)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(id, run_id, agent_id, type, object_key, size, content_type,
             metadata ? JSON.stringify(metadata) : null).run();
      return jsonRes({ id }, 201);
    }
  }

  const artifactMatch = pathname.match(/^\/v1\/artifacts\/([^/]+)$/);
  if (artifactMatch && method === "GET") {
    const row = await env.DB.prepare("SELECT * FROM artifacts WHERE id = ?").bind(artifactMatch[1]).first();
    if (!row) return errRes("Artifact not found", 404);
    return jsonRes(row);
  }

  return errRes("Not found", 404);
}

// ── Daily Digest ──────────────────────────────────────────────────────────────
// Summarizes all Hindsight memory written in the last 24h across every
// connected OMP device/project sharing bank "my-ai-agent" (not scoped to
// this repo only). Runs as: create D1 run -> fetch Hindsight memories ->
// group by tag -> synthesize prose via Hindsight's own reflect() (reuses
// its already-configured LLM, no new AI infra) -> retain digest back to
// Hindsight -> write markdown to R2 -> register D1 artifact -> close run.

const BANK_ID = "my-ai-agent";
// Hindsight sits behind Cloudflare; requests without a recognized User-Agent
// get edge-blocked (same fix already applied in ingest-okf-to-hindsight.py).
const HINDSIGHT_UA = "curl/8.0.0";

interface HindsightMemory {
  text: string;
  date: string;
  tags?: string[];
}

async function hindsightFetch(env: Env, path: string, init: RequestInit = {}): Promise<any> {
  const headers = {
    Authorization: `Bearer ${env.HINDSIGHT_API_TOKEN}`,
    "User-Agent": HINDSIGHT_UA,
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(init.headers ?? {}),
  };
  const resp = await fetch(`${env.HINDSIGHT_API_URL}${path}`, { ...init, headers });
  if (!resp.ok) throw new Error(`Hindsight ${path} -> HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

async function fetchRecentMemories(env: Env, cutoff: Date): Promise<HindsightMemory[]> {
  const collected: HindsightMemory[] = [];
  const pageSize = 100;
  const maxPages = 20; // safety cap: 2000 memories/day ceiling before we stop paginating
  for (let page = 0; page < maxPages; page++) {
    const offset = page * pageSize;
    const data = await hindsightFetch(
      env,
      `/v1/default/banks/${BANK_ID}/memories/list?limit=${pageSize}&offset=${offset}`
    );
    const items: HindsightMemory[] = data.items ?? [];
    if (items.length === 0) break;
    let hitCutoff = false;
    for (const item of items) {
      if (new Date(item.date) < cutoff) { hitCutoff = true; break; }
      collected.push(item);
    }
    if (hitCutoff || items.length < pageSize) break;
  }
  return collected;
}

function tagCounts(items: HindsightMemory[], prefix: string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    for (const tag of item.tags ?? []) {
      if (tag.startsWith(prefix)) counts[tag] = (counts[tag] ?? 0) + 1;
    }
  }
  return counts;
}

async function synthesizeDigest(env: Env, items: HindsightMemory[]): Promise<string> {
  if (items.length === 0) return "Tidak ada aktivitas baru dalam 24 jam terakhir.";
  // Cap the fact list fed into reflect() to keep the prompt bounded.
  const factList = items.slice(0, 80).map((i) => `- ${i.text}`).join("\n");
  const query =
    `Berikut adalah ${items.length} fakta/memori baru yang ditulis dalam 24 jam terakhir ` +
    `lintas semua device/project yang terhubung ke bank memori ini:\n\n${factList}\n\n` +
    `Buat ringkasan aktivitas harian dalam Bahasa Indonesia: apa saja yang dikerjakan, ` +
    `project/device mana saja aktif, dan insight atau keputusan penting apa yang muncul. Singkat dan padat.`;
  const data = await hindsightFetch(env, `/v1/default/banks/${BANK_ID}/reflect`, {
    method: "POST",
    body: JSON.stringify({ query, budget: "low", max_tokens: 1024 }),
  });
  return data.text ?? data.response ?? "(reflect tidak mengembalikan ringkasan)";
}

async function runDailyDigest(env: Env): Promise<{ run_id: string; facts_processed: number; artifact_id: string }> {
  const runId = `run-${nanoid()}`;
  await env.DB.prepare(
    `INSERT INTO agent_runs (id, agent_id, trigger, model) VALUES (?, 'daily-digest-cron', 'cron', NULL)`
  ).bind(runId).run();
  await env.DB.prepare(
    `INSERT INTO agent_events (id, run_id, agent_id, event_type) VALUES (?, ?, 'daily-digest-cron', 'started')`
  ).bind(`evt-${nanoid()}`, runId).run();

  try {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000);
    const items = await fetchRecentMemories(env, cutoff);
    const byProject = tagCounts(items, "project:");
    const byBrain = tagCounts(items, "brain:");
    const prose = await synthesizeDigest(env, items);

    const dateStr = new Date().toISOString().slice(0, 10);
    const lines = [
      `# Daily Digest — ${dateStr}`,
      "",
      `Total fakta baru (24 jam terakhir): ${items.length}`,
      "",
      "## Breakdown per project",
      ...(Object.keys(byProject).length
        ? Object.entries(byProject).map(([k, v]) => `- ${k}: ${v}`)
        : ["(tidak ada tag project)"]),
      "",
      "## Breakdown per brain (otak/agent)",
      ...(Object.keys(byBrain).length
        ? Object.entries(byBrain).map(([k, v]) => `- ${k}: ${v}`)
        : ["(tidak ada tag brain)"]),
      "",
      "## Ringkasan",
      "",
      prose,
      "",
    ];
    const digest = lines.join("\n");

    // Retain back into Hindsight so future recall()/reflect() surfaces past digests.
    await hindsightFetch(env, `/v1/default/banks/${BANK_ID}/memories`, {
      method: "POST",
      body: JSON.stringify({
        items: [
          {
            content: digest,
            context: `Daily digest ${dateStr}`,
            document_id: `daily-digest:${dateStr}`,
            timestamp: new Date().toISOString(),
            tags: ["daily-digest", `date:${dateStr}`],
          },
        ],
        async: false,
      }),
    });

    // Durable readable copy in R2.
    const objectKey = `${ARTIFACT_PREFIX}digests/${dateStr}.md`;
    await env.R2.put(objectKey, digest, { httpMetadata: { contentType: "text/markdown" } });

    const artId = `art-${nanoid()}`;
    await env.DB.prepare(
      `INSERT INTO artifacts (id, run_id, agent_id, type, object_key, size, content_type)
       VALUES (?, ?, 'daily-digest-cron', 'report', ?, ?, 'text/markdown')`
    ).bind(artId, runId, objectKey, digest.length).run();

    await env.DB.prepare(
      `INSERT INTO agent_events (id, run_id, agent_id, event_type, data) VALUES (?, ?, 'daily-digest-cron', 'completed', ?)`
    ).bind(`evt-${nanoid()}`, runId, JSON.stringify({ facts_processed: items.length, projects: Object.keys(byProject).length })).run();

    await env.DB.prepare(
      `UPDATE agent_runs SET status='completed', result=?, finished_at=datetime('now'), artifact_refs=? WHERE id=?`
    ).bind(`${items.length} fakta diproses dari ${Object.keys(byProject).length} project`, JSON.stringify([artId]), runId).run();

    return { run_id: runId, facts_processed: items.length, artifact_id: artId };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    await env.DB.prepare(
      `UPDATE agent_runs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?`
    ).bind(message, runId).run();
    throw e;
  }
}

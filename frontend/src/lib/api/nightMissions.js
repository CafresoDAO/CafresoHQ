// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — Night Shift chain-wake mirror (Sprint 4 MVP-2, ships dark)
//
// serve.py's scheduled-missions.json stays the source of truth for WHAT runs;
// this mirror exists only so a cafresohq_state timer can WAKE a stopped fleet
// container shortly before a mission is due (HMAC-signed outcall to the fleet
// gateway — inert until the plan admin sets wake config on-chain). Times cross
// this seam in ms and live on-chain in ns, matching the canister clock.
// ─────────────────────────────────────────────────────────────────────────────

import { getStateActor, stateCanisterConfigured } from '$lib/api/stateActor.js';

const MS_TO_NS = 1_000_000n;

/** Mirror one serve.py schedule on-chain (upsert by id). */
export async function putMissionSchedule({ id, agentId, topic, recurrence, durationSecs, intervalSecs, enabled, nextRunAtMs }) {
  const a = await getStateActor();
  await a.putMissionSchedule(
    String(id || '').slice(0, 64),
    String(agentId || '').slice(0, 64),
    String(topic || '').slice(0, 500),
    recurrence === 'daily' ? 'daily' : 'once',
    BigInt(Math.min(4 * 3600, Math.max(60, Math.floor(durationSecs || 0)))),
    BigInt(Math.max(60, Math.floor(intervalSecs || 0))),
    !!enabled,
    BigInt(Math.max(0, Math.floor(nextRunAtMs || 0))) * MS_TO_NS
  );
  return true;
}

export async function listMissionSchedules() {
  if (!stateCanisterConfigured()) return [];
  const rows = await (await getStateActor()).listMissionSchedules();
  return rows.map((r) => ({
    id: r.id,
    agentId: r.agentId,
    topic: r.topic,
    recurrence: r.recurrence,
    durationSecs: Number(r.durationSecs),
    intervalSecs: Number(r.intervalSecs),
    enabled: r.enabled,
    nextRunAtMs: Number(r.nextRunAt / MS_TO_NS),
    lastWakeAtMs: Number(r.lastWakeAt / MS_TO_NS),
    lastWakeResult: r.lastWakeResult
  }));
}

export async function deleteMissionSchedule(id) {
  const a = await getStateActor();
  return await a.deleteMissionSchedule(String(id || ''));
}

/** Config presence only ({enabled, urlSet, secretSet}) — never the secret. */
export async function wakeStatus() {
  if (!stateCanisterConfigured()) return { enabled: false, urlSet: false, secretSet: false };
  return await (await getStateActor()).wakeStatus();
}

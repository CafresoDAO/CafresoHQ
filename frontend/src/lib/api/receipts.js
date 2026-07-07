// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — on-chain work receipts (Sprint 3 trust layer)
//
// The embedded HQ app hashes a deliverable and asks the shell (via the
// chain:receipt:* bridge) to anchor {tool, title, argHash, contentSha256} in
// cafresohq_state. Anyone can then verify the artifact from the public page
//   https://<state-canister>.icp0.io/<principal>/receipt/<id>
// with no login and no JS — sha256 the artifact and compare. Anchoring is
// best-effort by design: it never blocks or fails a tool.
// ─────────────────────────────────────────────────────────────────────────────

import { get } from 'svelte/store';
import { getStateActor, stateCanisterConfigured, stateCanisterId } from '$lib/api/stateActor.js';

/** Anchor a receipt → { id, verifyUrl } (throws if unconfigured/signed-out). */
export async function putWorkReceipt({ agentId, agentName, tool, title, argHash, contentSha256, ownerPrincipalText }) {
  const a = await getStateActor();
  const id = await a.putWorkReceipt(
    String(agentId || '').slice(0, 100),
    String(agentName || '').slice(0, 100),
    String(tool || '').slice(0, 40),
    String(title || '').slice(0, 300),
    String(argHash || '').slice(0, 80),
    String(contentSha256 || '').slice(0, 80)
  );
  return { id: Number(id), verifyUrl: verifyUrlFor(ownerPrincipalText, Number(id)) };
}

export function verifyUrlFor(ownerPrincipalText, id) {
  const canister = get(stateCanisterId);
  if (!canister || !ownerPrincipalText) return null;
  return `https://${canister}.icp0.io/${ownerPrincipalText}/receipt/${id}`;
}

export async function listWorkReceipts(ownerPrincipalText) {
  if (!stateCanisterConfigured()) return [];
  try {
    const rows = await (await getStateActor()).listWorkReceipts();
    return rows.map((r) => ({
      id: Number(r.id),
      agentId: r.agentId,
      agentName: r.agentName,
      tool: r.tool,
      title: r.title,
      argHash: r.argHash,
      contentSha256: r.contentSha256,
      ts: r.ts.toString(),
      verifyUrl: verifyUrlFor(ownerPrincipalText, Number(r.id))
    }));
  } catch (e) {
    console.warn('[receipts] listWorkReceipts failed', e);
    return [];
  }
}

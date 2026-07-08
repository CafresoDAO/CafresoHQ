// ─────────────────────────────────────────────────────────────────────────────
// Operator control plane — the network-wide switches the planAdmin sets on
// cafresohq_state and every client reads (public /operator/config.json). Gates
// features and surfaces operator messages (e.g. "GPU node currently down").
//
// Read is anonymous plain fetch (works signed-out); writes go through the actor
// from the admin panel. Shape is operator-defined; consumers read defensively.
//   { gpuNode:{enabled,label,downMessage}, searchNetwork:{enabled},
//     trialBrain:{enabled,dailyCap}, money:{enabled}, publish:{enabled} }
// ─────────────────────────────────────────────────────────────────────────────
import { writable, get } from 'svelte/store';
import { libraryPublicBase } from '../api/library.js';

export const operatorConfig = writable({});
let lastFetch = 0;

/** Refresh from the canister; cached ~60s. Safe to call often. */
export async function refreshOperatorConfig(force = false) {
  const base = libraryPublicBase();
  if (!base) return get(operatorConfig);
  if (!force && Date.now() - lastFetch < 60_000) return get(operatorConfig);
  try {
    const r = await fetch(base + '/operator/config.json');
    if (r.ok) {
      const j = await r.json();
      if (j && typeof j === 'object') { operatorConfig.set(j); lastFetch = Date.now(); }
    }
  } catch (_e) { /* keep last good */ }
  return get(operatorConfig);
}

// Small typed accessors so consumers don't repeat defensive reads.
export function gpuNodeDown(cfg) {
  const g = (cfg || get(operatorConfig)).gpuNode || {};
  return g.enabled === false;
}
export function gpuDownMessage(cfg) {
  const g = (cfg || get(operatorConfig)).gpuNode || {};
  return g.downMessage || 'The compute node is currently down.';
}
export function searchPaused(cfg) {
  const s = (cfg || get(operatorConfig)).searchNetwork || {};
  return s.enabled === false;
}
export function moneyDisabled(cfg) {
  const m = (cfg || get(operatorConfig)).money || {};
  return m.enabled === false;
}
export function publishDisabled(cfg) {
  const p = (cfg || get(operatorConfig)).publish || {};
  return p.enabled === false;
}

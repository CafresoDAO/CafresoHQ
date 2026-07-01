// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — ICP Services + agent-wallet client (SvelteKit parent shell)
//
// This runs in the AUTHENTICATED shell, which holds the II delegation. The
// embedded HQ app (iframe) has no on-chain client and reaches these ops over the
// postMessage bridge (see routes/hq/app/+page.svelte). The agent only ever
// REQUESTS — every signature happens here, under the user's identity, gated by
// the on-chain spend cap in cafresohq_state.
//
// An agent's "HQ wallet" is an ICRC subaccount of the USER's principal:
//   owner = user principal, subaccount = SHA-256(ctx : principal : agentId).
// Custody never leaves the user; the agent can't sign. Funding is an internal
// transfer (user default → agent subaccount); spending moves out of it, gated.
// ─────────────────────────────────────────────────────────────────────────────

import { getBalance, transfer, toRawAmount, TOKENS } from '$lib/api/icrc1.js';
import { getStateActor, stateCanisterConfigured } from '$lib/api/stateActor.js';

// ── Deterministic per-agent subaccount ───────────────────────────────────────
const SUBACCOUNT_CTX = 'cafresohq-agent-wallet-v1';

export async function deriveAgentSubaccount(principalText, agentId) {
  const data = new TextEncoder().encode(`${SUBACCOUNT_CTX}:${principalText}:${agentId}`);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return new Uint8Array(digest); // exactly 32 bytes
}
export function subaccountToHex(u8) {
  return Array.from(u8, (b) => b.toString(16).padStart(2, '0')).join('');
}
export function hexToSubaccount(hex) {
  const u = new Uint8Array(32);
  for (let i = 0; i < 32 && i * 2 < hex.length; i++) u[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return u;
}

// ── Installed-service flags (on-chain source of truth) ───────────────────────
export async function listInstalledServices() {
  if (!stateCanisterConfigured()) return [];
  try {
    return await (await getStateActor()).listServiceFlags();
  } catch (e) {
    console.warn('[walletServices] listServiceFlags failed', e);
    return [];
  }
}
export async function setServiceInstalled(serviceId, enabled, configJson = '') {
  const a = await getStateActor();
  return a.putServiceFlag(serviceId, enabled, configJson);
}

// ── Agent-wallet policy (cap, window, pause) ─────────────────────────────────
const walletOut = (w) =>
  w && {
    agentId: w.agentId,
    subaccountHex: w.subaccountHex,
    token: w.token,
    spendCap: w.spendCap, // BigInt (base units)
    windowSecs: Number(w.windowSecs),
    windowSpent: w.windowSpent, // BigInt
    windowResetAt: w.windowResetAt,
    paused: w.paused,
    updatedAt: w.updatedAt
  };
const optOne = (v) => (Array.isArray(v) ? (v.length ? v[0] : null) : v ?? null);

export async function listAgentWallets() {
  if (!stateCanisterConfigured()) return [];
  try {
    return (await (await getStateActor()).listAgentWallets()).map(walletOut);
  } catch (e) {
    console.warn('[walletServices] listAgentWallets failed', e);
    return [];
  }
}
export async function getAgentWalletPolicy(agentId) {
  if (!stateCanisterConfigured()) return null;
  try {
    return walletOut(optOne(await (await getStateActor()).getAgentWallet(agentId)));
  } catch (e) {
    console.warn('[walletServices] getAgentWallet failed', e);
    return null;
  }
}
export async function putAgentWalletPolicy({ agentId, subaccountHex, token, spendCap, windowSecs, paused }) {
  const a = await getStateActor();
  return a.putAgentWallet(agentId, subaccountHex, token, BigInt(spendCap), BigInt(windowSecs || 0), !!paused);
}
export async function deleteAgentWallet(agentId) {
  const a = await getStateActor();
  return a.deleteAgentWallet(agentId);
}
export async function setAllSpendPaused(paused) {
  const a = await getStateActor();
  return a.setAllSpendPaused(!!paused);
}
export async function spendPausedAll() {
  if (!stateCanisterConfigured()) return false;
  try {
    return await (await getStateActor()).spendPausedAll();
  } catch {
    return false;
  }
}
/** Atomic cap gate. → { kind:'ok'|'over'|'paused'|'noWallet', ... }. */
async function recordSpend(agentId, amountRaw) {
  const res = await (await getStateActor()).recordSpend(agentId, BigInt(amountRaw));
  const kind = Object.keys(res)[0];
  return { kind, ...res[kind] };
}

// ── High-level wallet ops (used by the bridge) ───────────────────────────────
/** All balances for an agent's wallet subaccount, keyed by token. Values are BigInt|null. */
export async function agentBalances(principalText, agentId, tokenKeys = Object.keys(TOKENS)) {
  const sub = await deriveAgentSubaccount(principalText, agentId);
  const out = {};
  await Promise.all(
    tokenKeys.map(async (k) => {
      out[k] = await getBalance(k, principalText, sub);
    })
  );
  return out;
}

/** Fund an agent wallet: internal transfer from the user's default subaccount. */
export async function fundAgent({ principalText, agentId, tokenKey, amount }) {
  const sub = await deriveAgentSubaccount(principalText, agentId);
  return transfer({ tokenKey, toPrincipalText: principalText, amount, toSubaccount: sub, memoText: `fund:${agentId}`.slice(0, 32) });
}

/**
 * Send from an agent's wallet. Unless `force` (the user already approved an
 * over-cap send in the shell), it runs the on-chain cap gate first:
 *   → { status:'ok', block }         within cap; executed
 *   → { status:'needsApproval', … }  over cap / wrong token; DON'T sign, ask user
 *   → { status:'paused' | 'noWallet' }
 *   → { status:'error', error }
 */
export async function agentSend({ principalText, agentId, tokenKey, amount, to, memo, force = false }) {
  const sub = await deriveAgentSubaccount(principalText, agentId);
  const rawAmount = toRawAmount(tokenKey, amount);

  if (!force) {
    const policy = await getAgentWalletPolicy(agentId);
    if (!policy) return { status: 'noWallet' };
    if (policy.paused) return { status: 'paused' };
    // The cap is denominated in the wallet's configured token; anything else
    // can't be auto-authorized → route to user approval.
    if (tokenKey !== policy.token) {
      return { status: 'needsApproval', reason: 'token differs from the wallet cap' };
    }
    if (stateCanisterConfigured()) {
      const gate = await recordSpend(agentId, rawAmount);
      if (gate.kind === 'paused') return { status: 'paused' };
      if (gate.kind === 'noWallet') return { status: 'noWallet' };
      if (gate.kind === 'over') {
        return {
          status: 'needsApproval',
          reason: 'exceeds the per-window spend cap',
          cap: gate.cap?.toString(),
          windowSpent: gate.windowSpent?.toString()
        };
      }
      // #ok → recorded; fall through and sign.
    }
  }

  const res = await transfer({ tokenKey, toPrincipalText: to, amount, fromSubaccount: sub, memoText: memo });
  if (res.err) return { status: 'error', error: res.err };
  return { status: 'ok', block: res.ok };
}

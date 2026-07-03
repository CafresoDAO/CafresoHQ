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

import { Principal } from '@dfinity/principal';
import { sha224 } from '@noble/hashes/sha256';
import { getBalance, transfer, toRawAmount, getFee, approve, getAllowance, TOKENS } from '$lib/api/icrc1.js';
import { getStateActor, stateCanisterConfigured, stateCanisterId } from '$lib/api/stateActor.js';
import { get as _get } from 'svelte/store';

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

// ── Shareable address formats for an agent wallet ────────────────────────────
// Tips arrive by plain ICRC-1 transfer to (owner=user, subaccount=agent), so an
// address just needs DISPLAYING — but wallet compatibility is fragmented:
//  · ICRC-1 textual encoding (owner-CHECKSUM.subhex) — modern ICRC wallets
//  · legacy AccountIdentifier (hex) — exchanges + older ICP-ledger-only wallets
//  · raw principal + subaccount hex — wallets with split input fields
// We surface all three.

// CRC-32 (zlib/ISO-3309 polynomial), big-endian byte output.
function crc32be(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  crc = (crc ^ 0xffffffff) >>> 0;
  return new Uint8Array([crc >>> 24, (crc >>> 16) & 0xff, (crc >>> 8) & 0xff, crc & 0xff]);
}
// RFC 4648 Base32, no padding, lowercase (the ICRC-1 textual-encoding alphabet).
function base32lower(bytes) {
  const A = 'abcdefghijklmnopqrstuvwxyz234567';
  let bits = 0, value = 0, out = '';
  for (const b of bytes) {
    value = (value << 8) | b; bits += 8;
    while (bits >= 5) { out += A[(value >>> (bits - 5)) & 31]; bits -= 5; }
  }
  if (bits > 0) out += A[(value << (5 - bits)) & 31];
  return out;
}
const _isZeroSub = (u8) => !u8 || Array.from(u8).every((b) => b === 0);

/**
 * ICRC-1 textual account encoding. Default (absent/all-zero) subaccount MUST
 * encode as the bare principal text; otherwise:
 *   <owner>-<base32(crc32(ownerBytes ‖ 32-byte sub))>.<subHex, leading zero
 *   CHARACTERS trimmed, lowercase>
 */
export function encodeIcrcAccountText(ownerPrincipalText, subaccountHex) {
  const sub = subaccountHex ? hexToSubaccount(subaccountHex) : null;
  if (_isZeroSub(sub)) return ownerPrincipalText;
  const ownerBytes = Principal.fromText(ownerPrincipalText).toUint8Array();
  const joined = new Uint8Array(ownerBytes.length + 32);
  joined.set(ownerBytes); joined.set(sub, ownerBytes.length);
  const checksum = base32lower(crc32be(joined));
  const trimmed = subaccountToHex(sub).toLowerCase().replace(/^0+/, '') || '0';
  return `${ownerPrincipalText}-${checksum}.${trimmed}`;
}

/**
 * Legacy ICP AccountIdentifier (what exchanges/older wallets send to):
 * hex( crc32(h) ‖ h ) where h = sha224( "\x0Aaccount-id" ‖ owner ‖ sub ).
 */
export function legacyAccountIdText(ownerPrincipalText, subaccountHex) {
  const ownerBytes = Principal.fromText(ownerPrincipalText).toUint8Array();
  const sub = subaccountHex ? hexToSubaccount(subaccountHex) : new Uint8Array(32);
  const domain = new TextEncoder().encode('\x0Aaccount-id');
  const data = new Uint8Array(domain.length + ownerBytes.length + 32);
  data.set(domain); data.set(ownerBytes, domain.length); data.set(sub, domain.length + ownerBytes.length);
  const h = sha224(data);
  const out = new Uint8Array(4 + h.length);
  out.set(crc32be(h)); out.set(h, 4);
  return subaccountToHex(out);
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

// ── Payroll (Sprint 2: canister-timer salaries over a user-signed allowance) ──
// The user approves the STATE CANISTER as ICRC-2 spender; its 5-min timer then
// pulls user main account → agent subaccount. The allowance is the hard budget.

const variantKey = (v) => (v && typeof v === 'object' ? Object.keys(v)[0] : String(v ?? ''));
const salaryOut = (s) =>
  s && {
    agentId: s.agentId,
    ledger: s.ledger?.toText ? s.ledger.toText() : String(s.ledger),
    token: s.token,
    amount: s.amount.toString(),
    fee: s.fee.toString(),
    lowWatermark: s.lowWatermark.toString(),
    periodSecs: Number(s.periodSecs),
    nextRunAt: s.nextRunAt.toString(),
    mode: variantKey(s.mode),
    active: s.active,
    stalledSince: Array.isArray(s.stalledSince) ? (s.stalledSince[0]?.toString() ?? null) : null,
    lastResult: s.lastResult,
    updatedAt: s.updatedAt.toString()
  };
const payoutOut = (p) =>
  p && {
    key: p.key,
    agentId: p.agentId,
    token: p.token,
    amount: p.amount.toString(),
    scheduledAt: p.scheduledAt.toString(),
    status: p.status,
    blockIndex: Array.isArray(p.blockIndex) ? (p.blockIndex[0]?.toString() ?? null) : null,
    ts: p.ts.toString()
  };

/** Create/update a salary. Amounts in WHOLE token units; fee auto-read from the ledger. */
export async function putSalary({ agentId, tokenKey, amount, lowWatermark = 0, periodSecs, mode = 'salary', active = true }) {
  const token = TOKENS[tokenKey];
  if (!token) throw new Error(`Unknown token: ${tokenKey}`);
  const fee = (await getFee(tokenKey)) ?? 10_000n;
  const a = await getStateActor();
  await a.putSalary(
    agentId,
    Principal.fromText(token.canister),
    token.symbol,
    toRawAmount(tokenKey, amount),
    BigInt(fee),
    toRawAmount(tokenKey, lowWatermark),
    BigInt(periodSecs),
    mode === 'refill' ? { refill: null } : { salary: null },
    !!active
  );
  return true;
}
export async function listSalaries() {
  if (!stateCanisterConfigured()) return [];
  try {
    return (await (await getStateActor()).listSalaries()).map(salaryOut);
  } catch (e) {
    console.warn('[walletServices] listSalaries failed', e);
    return [];
  }
}
export async function deleteSalary(agentId) {
  return (await getStateActor()).deleteSalary(agentId);
}
export async function setPayrollPaused(paused) {
  return (await getStateActor()).setPayrollPaused(!!paused);
}
export async function payrollPaused() {
  if (!stateCanisterConfigured()) return false;
  try {
    return await (await getStateActor()).payrollPaused();
  } catch {
    return false;
  }
}
export async function listPayouts() {
  if (!stateCanisterConfigured()) return [];
  try {
    return (await (await getStateActor()).listPayouts()).map(payoutOut);
  } catch (e) {
    console.warn('[walletServices] listPayouts failed', e);
    return [];
  }
}
export async function runPayrollNow(agentId) {
  return (await getStateActor()).runPayrollNow(agentId);
}

/**
 * Sign the payroll budget: icrc2_approve(spender = state canister). REAL
 * signature — only call from an explicit user confirmation in the shell.
 * `amount` in whole units. Remember: approve OVERWRITES the prior allowance,
 * and each pull burns amount + fee of allowance — size as spend + pulls × fee.
 */
export async function approvePayroll({ tokenKey, amount, expiresAtMs = null, noExpiry = false }) {
  const spender = _get(stateCanisterId);
  if (!spender) return { err: 'state canister not configured' };
  return approve({ tokenKey, spenderPrincipalText: spender, amount, expiresAtMs, noExpiry });
}
/** Current payroll allowance → { allowance, expiresAtNs } (BigInts) or null. */
export async function payrollAllowance({ tokenKey, ownerPrincipalText }) {
  const spender = _get(stateCanisterId);
  if (!spender) return null;
  return getAllowance({ tokenKey, ownerPrincipalText, spenderPrincipalText: spender });
}

/** Lifetime recorded agent spend → { [agentId]: { [token]: rawString } }. */
export async function getSpendTotals() {
  if (!stateCanisterConfigured()) return {};
  try {
    const rows = await (await getStateActor()).getSpendTotals();
    const out = {};
    for (const [agentId, tokens] of rows) {
      out[agentId] = {};
      for (const [tok, n] of tokens) out[agentId][tok] = n.toString();
    }
    return out;
  } catch (e) {
    console.warn('[walletServices] getSpendTotals failed', e);
    return {};
  }
}

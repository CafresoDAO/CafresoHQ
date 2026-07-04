// Minimal read-only ICRC-1 client for balance lookups.
//
// We don't ship full candid bindings for every ledger — just hand-roll the
// `icrc1_balance_of` query via a tiny IDL factory per token. Each call is an
// anonymous query (no identity needed for read), which means the profile
// page can show balances before the user signs in.
//
// Decimals used for display — display helpers in lib/format.js must match.

import { browser } from '$app/environment';
import { Actor, HttpAgent } from '@dfinity/agent';
import { IDL } from '@dfinity/candid';
import { Principal } from '@dfinity/principal';
import { currentIdentity } from '$lib/stores/auth.js';

// Mainnet ICRC-1 ledgers (sourced from the minegold backend's hard-coded
// principals at src/backend/minegold/main.mo lines 123-129 for sGLDT and
// ckUNI, and the standard DFINITY ICP ledger canister).
// Mainnet ICRC-1 ledgers — confirmed by the user 2026-04-19. `decimals` must
// match each ledger's `icrc1_decimals` query; we hard-code here to avoid a
// second network call on profile load.
export const TOKENS = {
  ICP: {
    symbol: 'ICP',
    canister: 'ryjl3-tyaaa-aaaaa-aaaba-cai',
    decimals: 8,
    logo: '/assets/icp.png'
  },
  ckUNI: {
    symbol: 'ckUNI',
    canister: 'ilzky-ayaaa-aaaar-qahha-cai',
    decimals: 18,
    logo: null
  },
  sGLDT: {
    symbol: 'sGLDT',
    canister: 'i2s4q-syaaa-aaaan-qz4sq-cai',
    decimals: 8,
    logo: null
  },
  nanas: {
    symbol: '$nanas',
    canister: 'mwen2-oqaaa-aaaam-adaca-cai',
    decimals: 8,
    logo: '/assets/nanas-coin.png'
  },
  // ckUSDT — the chain-key Tether stablecoin. NOTE: 6 decimals (not 8).
  // Mainnet ledger: https://dashboard.internetcomputer.org/canister/cngnf-gddge-nq2mj-vjyfl-v76et-6c2pt-xg3n3-jzihw-d3iyp-ughtf-3ae
  // logo: null → renders the text-avatar fallback (like ckUNI/sGLDT); drop a
  // /assets/ckusdt.png later for a real mark.
  ckUSDT: {
    symbol: 'ckUSDT',
    canister: 'cngnf-gddge-nq2mj-vjyfl-v76et-6c2pt-xg3n3-jzihw-d3iyp-ughtf-3ae',
    decimals: 6,
    logo: null
  }
};

const HOST = 'https://icp0.io';

// ICRC-1 Account record: principal + optional 32-byte subaccount. We only
// need the default subaccount (empty opt) for user wallets.
const Account = IDL.Record({
  owner: IDL.Principal,
  subaccount: IDL.Opt(IDL.Vec(IDL.Nat8))
});

// `TransferArg` per the ICRC-1 spec. We only need the owner-call path —
// the caller's authed identity is the `owner` in an implicit default
// subaccount. `fee` and `memo` are optional; we leave them empty.
function idlFactory({ IDL: _IDL }) {
  const Subaccount = _IDL.Vec(_IDL.Nat8);
  const Account_ = _IDL.Record({
    owner: _IDL.Principal,
    subaccount: _IDL.Opt(Subaccount)
  });
  const TransferArg = _IDL.Record({
    from_subaccount: _IDL.Opt(Subaccount),
    to: Account_,
    amount: _IDL.Nat,
    fee: _IDL.Opt(_IDL.Nat),
    memo: _IDL.Opt(_IDL.Vec(_IDL.Nat8)),
    created_at_time: _IDL.Opt(_IDL.Nat64)
  });
  const TransferError = _IDL.Variant({
    GenericError: _IDL.Record({ error_code: _IDL.Nat, message: _IDL.Text }),
    TemporarilyUnavailable: _IDL.Null,
    BadBurn: _IDL.Record({ min_burn_amount: _IDL.Nat }),
    Duplicate: _IDL.Record({ duplicate_of: _IDL.Nat }),
    BadFee: _IDL.Record({ expected_fee: _IDL.Nat }),
    CreatedInFuture: _IDL.Record({ ledger_time: _IDL.Nat64 }),
    TooOld: _IDL.Null,
    InsufficientFunds: _IDL.Record({ balance: _IDL.Nat })
  });
  const TransferResult = _IDL.Variant({ Ok: _IDL.Nat, Err: TransferError });
  // ICRC-2 approve — authorises a spender (a canister) to pull up to `amount`
  // from the caller's account. Used for trustless plan purchase: the buyer
  // approves the index canister, which then icrc2_transfer_from's the price.
  const ApproveArgs = _IDL.Record({
    from_subaccount: _IDL.Opt(Subaccount),
    spender: Account_,
    amount: _IDL.Nat,
    expected_allowance: _IDL.Opt(_IDL.Nat),
    expires_at: _IDL.Opt(_IDL.Nat64),
    fee: _IDL.Opt(_IDL.Nat),
    memo: _IDL.Opt(_IDL.Vec(_IDL.Nat8)),
    created_at_time: _IDL.Opt(_IDL.Nat64)
  });
  const ApproveError = _IDL.Variant({
    GenericError: _IDL.Record({ error_code: _IDL.Nat, message: _IDL.Text }),
    TemporarilyUnavailable: _IDL.Null,
    Duplicate: _IDL.Record({ duplicate_of: _IDL.Nat }),
    BadFee: _IDL.Record({ expected_fee: _IDL.Nat }),
    AllowanceChanged: _IDL.Record({ current_allowance: _IDL.Nat }),
    CreatedInFuture: _IDL.Record({ ledger_time: _IDL.Nat64 }),
    TooOld: _IDL.Null,
    Expired: _IDL.Record({ ledger_time: _IDL.Nat64 }),
    InsufficientFunds: _IDL.Record({ balance: _IDL.Nat })
  });
  const ApproveResult = _IDL.Variant({ Ok: _IDL.Nat, Err: ApproveError });
  const AllowanceArgs = _IDL.Record({ account: Account_, spender: Account_ });
  const Allowance = _IDL.Record({ allowance: _IDL.Nat, expires_at: _IDL.Opt(_IDL.Nat64) });
  return _IDL.Service({
    icrc1_balance_of: _IDL.Func([Account_], [_IDL.Nat], ['query']),
    icrc1_decimals: _IDL.Func([], [_IDL.Nat8], ['query']),
    icrc1_symbol: _IDL.Func([], [_IDL.Text], ['query']),
    icrc1_fee: _IDL.Func([], [_IDL.Nat], ['query']),
    icrc1_transfer: _IDL.Func([TransferArg], [TransferResult], []),
    icrc2_approve: _IDL.Func([ApproveArgs], [ApproveResult], []),
    icrc2_allowance: _IDL.Func([AllowanceArgs], [Allowance], ['query'])
  });
}

const _agents = new Map();
function agent() {
  if (!browser) return null;
  if (_agents.has('anon')) return _agents.get('anon');
  const a = new HttpAgent({ host: HOST });
  _agents.set('anon', a);
  return a;
}

const _actors = new Map();
function ledgerActor(canisterId) {
  if (!browser) return null;
  if (_actors.has(canisterId)) return _actors.get(canisterId);
  const a = agent();
  if (!a) return null;
  const actor = Actor.createActor(idlFactory, { agent: a, canisterId });
  _actors.set(canisterId, actor);
  return actor;
}

// Separate cache for authed actors (one per principal) — `icrc1_transfer`
// must run under the owner's identity, not the anonymous agent.
const _authActors = new Map();
function authedLedgerActor(canisterId, identity) {
  if (!browser || !canisterId || !identity) return null;
  const key = (() => {
    try {
      return `${canisterId}:${identity.getPrincipal().toText()}`;
    } catch {
      return canisterId;
    }
  })();
  if (_authActors.has(key)) return _authActors.get(key);
  const a = new HttpAgent({ host: HOST, identity });
  const actor = Actor.createActor(idlFactory, { agent: a, canisterId });
  _authActors.set(key, actor);
  return actor;
}

// `subaccount` (optional Uint8Array/number[]) reads a non-default subaccount of
// `principalText` — used for per-agent "HQ wallet" balances (owner = user
// principal, subaccount = deterministic per-agent). Omit for the main wallet.
export async function getBalance(tokenKey, principalText, subaccount = null) {
  if (!principalText) return null;
  const token = TOKENS[tokenKey];
  if (!token) return null;
  const actor = ledgerActor(token.canister);
  if (!actor) return null;
  try {
    const owner = Principal.fromText(principalText);
    const sub = subaccount ? [Array.from(subaccount)] : [];
    return await actor.icrc1_balance_of({ owner, subaccount: sub });
  } catch (e) {
    console.warn(`[icrc1] ${tokenKey} balance lookup failed`, e);
    return null;
  }
}

export async function getAllBalances(principalText) {
  if (!principalText) return {};
  const entries = await Promise.all(
    Object.keys(TOKENS).map(async (key) => [key, await getBalance(key, principalText)])
  );
  return Object.fromEntries(entries);
}

// Per-token fee cache — ICRC-1 ledgers publish a fixed `icrc1_fee` (e.g. ICP
// is 10_000 e8s). We read once per session and reuse; the send modal also
// shows it upfront so users aren't surprised by a dust deduction.
const _feeCache = new Map();
export async function getFee(tokenKey) {
  if (!browser) return null;
  if (_feeCache.has(tokenKey)) return _feeCache.get(tokenKey);
  const token = TOKENS[tokenKey];
  if (!token) return null;
  const actor = ledgerActor(token.canister);
  if (!actor) return null;
  try {
    const fee = await actor.icrc1_fee();
    _feeCache.set(tokenKey, fee);
    return fee;
  } catch (e) {
    console.warn(`[icrc1] ${tokenKey} fee lookup failed`, e);
    return null;
  }
}

// Convert a whole-unit amount (e.g. 3200 $nanas) to raw e8s / e18 as the
// ledger expects.
export function toRawAmount(tokenKey, wholeUnits) {
  const token = TOKENS[tokenKey];
  if (!token) return 0n;
  const n = Number(wholeUnits);
  if (!Number.isFinite(n) || n < 0) return 0n;
  // toFixed the FULL value so a fractional carry lands in the integer part.
  // Computing `whole` separately as Math.floor(n) then slicing "0." off the
  // fraction dropped the carry when the fraction rounded up to 1.0 (e.g.
  // 1.999999999 → whole=1, frac="00000000" → 1.0 instead of ~2.0), silently
  // under-paying by a whole token. Splitting the rounded string is carry-safe.
  const [whole, frac = ''] = n.toFixed(token.decimals).split('.');
  return BigInt(whole) * 10n ** BigInt(token.decimals) + BigInt(frac || '0');
}

// Execute an ICRC-1 transfer from the signed-in user to `toPrincipalText`.
// Returns `{ ok: blockIndex }` on success or `{ err: string }` otherwise.
// The caller MUST have been authenticated via II before calling.
// `fromSubaccount` / `toSubaccount` (optional Uint8Array/number[]) move funds
// out of / into a non-default subaccount — used for agent-wallet spends
// (from_subaccount = the agent's) and funding (to.subaccount = the agent's).
export async function transfer({ tokenKey, toPrincipalText, amount, memoText, fromSubaccount = null, toSubaccount = null }) {
  if (!browser) return { err: 'Not available server-side.' };
  const token = TOKENS[tokenKey];
  if (!token) return { err: `Unknown token: ${tokenKey}` };
  const identity = currentIdentity();
  if (!identity) return { err: 'Sign in first.' };
  const actor = authedLedgerActor(token.canister, identity);
  if (!actor) return { err: 'Ledger unreachable.' };

  let to;
  try {
    to = {
      owner: Principal.fromText(toPrincipalText),
      subaccount: toSubaccount ? [Array.from(toSubaccount)] : []
    };
  } catch {
    return { err: `Bad recipient principal: ${toPrincipalText}` };
  }

  const rawAmount = typeof amount === 'bigint' ? amount : toRawAmount(tokenKey, amount);
  if (rawAmount <= 0n) return { err: 'Amount must be > 0.' };

  const memo = memoText
    ? [Array.from(new TextEncoder().encode(memoText).slice(0, 32))]
    : [];

  const arg = {
    from_subaccount: fromSubaccount ? [Array.from(fromSubaccount)] : [],
    to,
    amount: rawAmount,
    fee: [], // let the ledger pick the default
    memo,
    created_at_time: []
  };

  try {
    const res = await actor.icrc1_transfer(arg);
    if ('Ok' in res) return { ok: Number(res.Ok) };
    // TransferError is a variant — surface the label + details if any.
    const key = Object.keys(res.Err)[0];
    const detail = res.Err[key];
    if (key === 'InsufficientFunds') {
      return { err: `Insufficient funds (balance: ${detail.balance}).` };
    }
    if (key === 'BadFee') {
      return { err: `Bad fee — ledger expects ${detail.expected_fee}.` };
    }
    if (key === 'GenericError') {
      return { err: detail.message || 'Generic ledger error.' };
    }
    return { err: `Transfer failed: ${key}` };
  } catch (e) {
    console.warn('[icrc1] transfer failed', e);
    return { err: String(e?.message || e) };
  }
}

// ICRC-2 approve: authorise `spenderPrincipalText` (a canister) to pull up to
// `amount` (raw base units) from the signed-in user via icrc2_transfer_from.
// Returns { ok: blockIndex } or { err }. The user must be II-authenticated.
//
// Expiry: by default the allowance expires in 10 minutes (one-shot purchases —
// no standing pull authorization left dangling). For STANDING budgets (payroll)
// pass `expiresAtMs` (an absolute epoch-ms deadline) or `noExpiry: true`.
// NOTE: icrc2_approve OVERWRITES the allowance — it does not add to it. Each
// transfer_from decrements the allowance by amount + fee, so size standing
// budgets as intended_spend + expected_pulls × fee.
export async function approve({ tokenKey, spenderPrincipalText, amount, expiresAtMs = null, noExpiry = false }) {
  if (!browser) return { err: 'Not available server-side.' };
  const token = TOKENS[tokenKey];
  if (!token) return { err: `Unknown token: ${tokenKey}` };
  const identity = currentIdentity();
  if (!identity) return { err: 'Sign in first.' };
  const actor = authedLedgerActor(token.canister, identity);
  if (!actor) return { err: 'Ledger unreachable.' };

  let spender;
  try {
    spender = { owner: Principal.fromText(spenderPrincipalText), subaccount: [] };
  } catch {
    return { err: `Bad spender principal: ${spenderPrincipalText}` };
  }

  const rawAmount = typeof amount === 'bigint' ? amount : toRawAmount(tokenKey, amount);
  if (rawAmount < 0n) return { err: 'Amount must be ≥ 0.' };   // 0 = revoke the allowance

  const expiresAtNs = noExpiry
    ? null
    : expiresAtMs
      ? BigInt(Math.floor(expiresAtMs)) * 1_000_000n
      : BigInt(Date.now()) * 1_000_000n + 600_000_000_000n; // default: 10 min
  const arg = {
    from_subaccount: [],
    spender,
    amount: rawAmount,
    expected_allowance: [],
    expires_at: rawAmount === 0n || expiresAtNs === null ? [] : [expiresAtNs],
    fee: [],
    memo: [],
    created_at_time: []
  };

  try {
    const res = await actor.icrc2_approve(arg);
    if ('Ok' in res) return { ok: Number(res.Ok) };
    const key = Object.keys(res.Err)[0];
    const detail = res.Err[key];
    if (key === 'InsufficientFunds') return { err: `Insufficient ${token.symbol} (balance: ${detail.balance}).` };
    if (key === 'GenericError') return { err: detail.message || 'Ledger error.' };
    return { err: `Approve failed: ${key}` };
  } catch (e) {
    console.warn('[icrc1] approve failed', e);
    return { err: String(e?.message || e) };
  }
}

// Read the current allowance the signed-in user has granted `spenderPrincipalText`.
// Anonymous query is fine (allowances are public data), but we need the OWNER's
// principal, so require sign-in. → { allowance: BigInt, expiresAtNs: BigInt|null } or null.
export async function getAllowance({ tokenKey, ownerPrincipalText, spenderPrincipalText }) {
  const token = TOKENS[tokenKey];
  if (!token || !ownerPrincipalText || !spenderPrincipalText) return null;
  const actor = ledgerActor(token.canister);
  if (!actor) return null;
  try {
    const res = await actor.icrc2_allowance({
      account: { owner: Principal.fromText(ownerPrincipalText), subaccount: [] },
      spender: { owner: Principal.fromText(spenderPrincipalText), subaccount: [] }
    });
    return {
      allowance: res.allowance,
      expiresAtNs: Array.isArray(res.expires_at) ? (res.expires_at[0] ?? null) : (res.expires_at ?? null)
    };
  } catch (e) {
    console.warn(`[icrc1] ${tokenKey} allowance lookup failed`, e);
    return null;
  }
}

export function formatBalance(raw, decimals, digits = 4) {
  if (raw === null || raw === undefined) return '—';
  const n = typeof raw === 'bigint' ? Number(raw) / 10 ** decimals : Number(raw) / 10 ** decimals;
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits
  });
}

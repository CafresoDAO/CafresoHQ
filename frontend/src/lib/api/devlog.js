// Dev Log + Forums API client (Phase 2 — CanDB-backed).
//
// Talks to the IndexCanister (which holds the "app" partition's data:
// posts, comments, burns, products, orders, treasury). The "user" partition
// data (User records, addresses, order histories) lives in the spawned
// UserService canister and is accessed separately from user.js.
//
// Falls back to seed data when offline so SSR/preview never blanks.

import { browser } from '$app/environment';
import { createActor } from '$lib/declarations/index';
import { currentIdentity } from '$lib/stores/auth.js';
import { POSTS as SEED_POSTS, COMMENTS as SEED_COMMENTS } from '$lib/data/blog.js';
import { layoutFromTheme, themeFromLayout } from '$lib/themes.js';

const MAINNET_INDEX = 'bek5d-2qaaa-aaaab-agqrq-cai';
const canisterId =
  import.meta.env.PUBLIC_INDEX_CANISTER_ID || MAINNET_INDEX;
const network = import.meta.env.PUBLIC_DFX_NETWORK || 'ic';
const host = network === 'local' ? 'http://127.0.0.1:4943' : 'https://icp0.io';

let _anonActor = null;
let _authActor = null;
let _authPrincipal = null;

function actor({ authed = false } = {}) {
  if (!browser || !canisterId) return null;
  if (authed) {
    const identity = currentIdentity();
    if (!identity) return null;
    const principal = (() => {
      try { return identity.getPrincipal().toText(); } catch { return null; }
    })();
    if (_authActor && _authPrincipal === principal) return _authActor;
    try {
      _authActor = createActor(canisterId, { agentOptions: { host, identity } });
      _authPrincipal = principal;
      return _authActor;
    } catch (e) {
      console.warn('[devlog] authed actor creation failed', e);
      return null;
    }
  }
  if (_anonActor) return _anonActor;
  try {
    _anonActor = createActor(canisterId, { agentOptions: { host } });
    return _anonActor;
  } catch (e) {
    console.warn('[devlog] anon actor creation failed, using seed', e);
    return null;
  }
}

// ---------- Shape mapping ----------
// Canister Post → frontend Post.
// Canister stores `body` as a JSON string; UI expects an array of blocks.
// `authorName` / `authorHue` / `authorRole` are flat fields on the canister
// type — we re-nest them into `author: {…}` for UI convenience.
function canisterToPost(p) {
  let body = [];
  // Early posts (pre-blocks format) stored the body as a plain string —
  // surface it as a single paragraph rather than dropping the content.
  try { body = p.body && p.body !== '' ? JSON.parse(p.body) : []; } catch { body = [{ kind: 'p', text: p.body }]; }
  if (!Array.isArray(body)) body = [{ kind: 'p', text: String(p.body) }];
  return {
    slug: p.slug,
    title: p.title,
    cat: p.category,
    layout: p.layout === 'banking-brave' ? 'banking-brave' : 'standard',
    theme: themeFromLayout(p.layout),
    author: {
      name: p.authorName,
      role: p.authorRole,
      hue: Number(p.authorHue),
    },
    authorPrincipal: p.authorPrincipal,
    date: p.date,
    readMin: Number(p.readMin),
    excerpt: p.excerpt,
    hero: p.hero,
    pinned: p.pinned,
    canister: p.canister,
    block: Number(p.block),
    burned: Number(p.burned),
    tips: Number(p.tips),
    comments: Number(p.comments),
    body,
    timestampCreated: Number(p.timestampCreated),
    timestampUpdated: Number(p.timestampUpdated),
  };
}

function frontendToCanisterPost(post) {
  return {
    slug: post.slug,
    title: post.title,
    category: post.cat || post.category || 'build-log',
    // Theme key persists in `layout` (the canister has no theme field).
    layout: post.theme ? layoutFromTheme(post.theme) : (post.layout || 'standard'),
    authorName: post.author?.name || '',
    authorHue: BigInt(post.author?.hue ?? 24),
    authorRole: post.author?.role || '',
    authorPrincipal: '', // server overrides
    date: post.date || new Date().toISOString().slice(0, 10),
    readMin: BigInt(post.readMin ?? 1),
    excerpt: post.excerpt || '',
    hero: post.hero || 'roaster',
    pinned: !!post.pinned,
    body: JSON.stringify(post.body || []),
    canister: post.canister || MAINNET_INDEX,
    block: BigInt(post.block ?? 0),
    burned: BigInt(0),
    tips: BigInt(0),
    comments: BigInt(0),
    timestampCreated: BigInt(0),
    timestampUpdated: BigInt(0),
  };
}

// Forum slug helpers (server enforces the f- prefix; we mirror it client-side
// so URLs read cleaner: `/forums/my-thread` not `/forums/f-my-thread`).
export const FORUM_PREFIX = 'f-';
export function forumSlug(s) {
  if (!s) return '';
  return s.startsWith(FORUM_PREFIX) ? s : FORUM_PREFIX + s;
}
export function stripForumPrefix(s) {
  if (!s) return '';
  return s.startsWith(FORUM_PREFIX) ? s.slice(FORUM_PREFIX.length) : s;
}
export function isForumSlug(s) {
  return !!s && s.startsWith(FORUM_PREFIX);
}

// ---------- Public API: Posts ----------

// Internal bookkeeping posts (e.g. the moderation overlay) must never appear
// in any public listing. Filter by category client-side regardless of how the
// canister's list endpoints slice categories.
const INTERNAL_CATS = new Set(['moderation']);
const isPublicPost = (p) => !INTERNAL_CATS.has(p.cat);

export async function listPosts() {
  const a = actor();
  if (!a) return SEED_POSTS;
  try {
    const out = await a.listDevLogPosts();
    if (!out || out.length === 0) return SEED_POSTS;
    return out.map(canisterToPost).filter(isPublicPost);
  } catch (e) {
    console.warn('[devlog] listPosts failed, using seed', e);
    return SEED_POSTS;
  }
}

export async function getPost(slug) {
  const a = actor();
  const fallback = () => SEED_POSTS.find((p) => p.slug === slug) || null;
  if (!a) return fallback();
  try {
    const out = await a.getPost(slug);
    if (!out || out.length === 0) return fallback();
    const post = canisterToPost(out[0]);
    // Internal bookkeeping posts (moderation overlay) are not viewable pages.
    if (!isPublicPost(post)) return fallback();
    return post;
  } catch (e) {
    console.warn('[devlog] getPost failed, using seed', e);
    return fallback();
  }
}

export async function listForumPosts() {
  const a = actor();
  if (!a) return [];
  try {
    const out = await a.listForumPosts();
    return out.map(canisterToPost).filter(isPublicPost);
  } catch (e) {
    console.warn('[devlog] listForumPosts failed', e);
    return [];
  }
}

export async function getForumPost(slugNoPrefix) {
  return getPost(forumSlug(slugNoPrefix));
}

export async function upsertForumPost(post) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in with Internet Identity to post.' };
  try {
    const input = frontendToCanisterPost({ ...post, slug: forumSlug(post.slug), pinned: false });
    const res = await a.postForumEntry(input);
    if ('ok' in res) return { ok: canisterToPost(res.ok) };
    return { err: res.err };
  } catch (e) {
    console.warn('[devlog] postForumEntry failed', e);
    return { err: String(e?.message || e) };
  }
}

export async function deleteForumPost(slugWithOrWithoutPrefix) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin.' };
  try {
    const res = await a.deleteForumPost(forumSlug(slugWithOrWithoutPrefix));
    if ('ok' in res) return { ok: true };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// Admin-only — publish / edit a curated dev-log post.
export async function upsertPost(post) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in with Internet Identity to publish.' };
  try {
    const res = await a.upsertPost(frontendToCanisterPost(post));
    if ('ok' in res) return { ok: canisterToPost(res.ok) };
    return { err: res.err };
  } catch (e) {
    console.warn('[devlog] upsertPost failed', e);
    return { err: String(e?.message || e) };
  }
}

// Admin-only — permanently remove a curated dev-log post.
export async function deletePost(slug) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin.' };
  try {
    const res = await a.deletePost(slug);
    if ('ok' in res) return { ok: true };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// ---------- Moderation overlay ----------
// Comments on the index canister are append-only — there is no edit/delete/
// hide method. Moderation therefore lives in an ADMIN-OWNED overlay post
// (slug MOD_SLUG, category 'moderation', filtered from every listing above):
// its body holds the list of hidden comment keys, and pages apply it at
// render time. Writing the overlay goes through `upsertPost`, which the
// canister admin-gates — so only real admins can hide/unhide, and each change
// is an on-chain, signed update.

const MOD_SLUG = 'mod-overlay';
export const modKey = (slug, commentId) => `${slug}#${commentId}`;

export async function getModeration() {
  const a = actor();
  const empty = { hiddenComments: [] };
  if (!a) return empty;
  try {
    const out = await a.getPost(MOD_SLUG);
    if (!out || out.length === 0) return empty;
    let body = [];
    try { body = JSON.parse(out[0].body || '[]'); } catch { body = []; }
    const mod = Array.isArray(body) ? body.find((b) => b && b.kind === 'mod') : null;
    return { hiddenComments: Array.isArray(mod?.hiddenComments) ? mod.hiddenComments : [] };
  } catch (e) {
    console.warn('[devlog] getModeration failed', e);
    return empty;
  }
}

export async function saveModeration({ hiddenComments = [] } = {}) {
  return upsertPost({
    slug: MOD_SLUG,
    title: 'Moderation overlay (internal)',
    cat: 'moderation',
    author: { name: 'moderation', role: 'system', hue: 0 },
    readMin: 1,
    excerpt: 'Internal moderation state — not a public post.',
    hero: 'roaster',
    pinned: false,
    body: [{ kind: 'mod', hiddenComments }],
  });
}

// Convenience: toggle one comment's hidden state and persist.
export async function setCommentHidden(slug, commentId, hidden) {
  const cur = await getModeration();
  const key = modKey(slug, commentId);
  const set = new Set(cur.hiddenComments);
  if (hidden) set.add(key); else set.delete(key);
  const res = await saveModeration({ hiddenComments: [...set] });
  if (res.err) return { err: res.err };
  return { ok: [...set] };
}

// ---------- Public API: Stats (admin analytics) ----------

export async function appStats() {
  const a = actor();
  if (!a) return null;
  try {
    const s = await a.appStats();
    return {
      posts: Number(s.posts),
      comments: Number(s.comments),
      burns: Number(s.burns),
      orders: Number(s.orders),
      products: Number(s.products),
    };
  } catch (e) {
    console.warn('[devlog] appStats failed', e);
    return null;
  }
}

export async function totalBurnedAll() {
  const a = actor();
  if (!a) return null;
  try {
    return Number(await a.totalBurned());
  } catch (e) {
    console.warn('[devlog] totalBurned failed', e);
    return null;
  }
}

// ---------- Public API: Comments ----------

export async function listComments(slug) {
  const a = actor();
  if (!a) return slug ? SEED_COMMENTS : [];
  try {
    const raw = await a.listComments(slug);
    return raw.map((c) => ({
      id: Number(c.id),
      author: { name: c.authorName, role: c.authorRole, hue: Number(c.authorHue) },
      poster: c.poster,
      date: new Date(Number(BigInt(c.timestamp) / 1_000_000n)).toLocaleString(),
      burned: Number(c.burned),
      stake: Number(c.stake),
      parentId: Number(c.parentId),
      text: c.text,
    }));
  } catch (e) {
    console.warn('[devlog] listComments failed, using seed', e);
    return SEED_COMMENTS;
  }
}

export async function postComment(slug, author, text, parentId = 0) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in with Internet Identity to comment.' };
  try {
    const res = await a.postComment(
      slug,
      author?.name || '',
      BigInt(author?.hue ?? 24),
      author?.role || 'member',
      text,
      BigInt(parentId)
    );
    if ('ok' in res) {
      return {
        ok: {
          id: Number(res.ok.id),
          slug: res.ok.slug,
          author: { name: res.ok.authorName, role: res.ok.authorRole, hue: Number(res.ok.authorHue) },
          poster: res.ok.poster,
          text: res.ok.text,
          burned: Number(res.ok.burned),
          stake: Number(res.ok.stake),
          parentId: Number(res.ok.parentId),
        },
      };
    }
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// ---------- Public API: Burns ----------

export async function burnTip(slug, amount, blockIndex = 0) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in to burn $nanas.' };
  try {
    const res = await a.recordBurn(slug, BigInt(amount), BigInt(blockIndex));
    if ('ok' in res) {
      return {
        ok: {
          id: Number(res.ok.id),
          slug: res.ok.slug,
          amount: Number(res.ok.amount),
          block: Number(res.ok.block),
          caller: res.ok.caller,
        },
      };
    }
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// ---------- Public API: Leaderboard ----------

export async function getLeaderboard(limit = 50) {
  const a = actor();
  if (!a) return [];
  try {
    const rows = await a.getLeaderboard(BigInt(limit));
    return rows.map((r, i) => ({
      rank: i + 1,
      principal: r.principal,
      burned: Number(r.totalBurned),
      burnCount: Number(r.burnCount),
    }));
  } catch (e) {
    console.warn('[devlog] getLeaderboard failed', e);
    return [];
  }
}

export async function listBurns(slug) {
  const a = actor();
  if (!a) return [];
  try {
    const raw = await a.listBurns(slug);
    return raw.map((b) => ({
      id: Number(b.id),
      slug: b.slug,
      amount: Number(b.amount),
      block: Number(b.block),
      caller: b.caller,
      timestamp: Number(b.timestamp),
    }));
  } catch (e) {
    console.warn('[devlog] listBurns failed', e);
    return [];
  }
}

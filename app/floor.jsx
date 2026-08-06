/* ── Floor language (OFFICE_AS_INTERFACE §4) ──────────────────────────────
   Pure helpers that translate runtime events into the office's physical
   vocabulary. The mapping is the ANIMATION API: one table, every backend.
   Kept import-free so scripts/test_floor.py can run this file verbatim.

   §4's binding rules apply to everything here:
   - honest   — a prop visit only plays while that tool is REALLY running;
                the snag line never claims anything but what happened.
   - cheap    — these return strings/classnames for CSS the floor already
                has (away placards, bubbles); no new animation tech.       */

/* Which prop a tool call walks the coworker to. Search wins over storage
   (VAULT_SEARCH is a bookshelf trip, not a cabinet one); anything we can't
   place honestly stays at the desk with the tool chip. */
function toolProp(name) {
  const n = String(name || '').toUpperCase();
  if (!n) return null;
  if (/SEARCH|LIBRARY|RESEARCH/.test(n)) return 'bookshelf';
  if (/WEB|HTTP|FETCH|URL|BROWSE/.test(n)) return 'phone';
  if (/VAULT|FILE|DIR|MEMORY|NOTE/.test(n)) return 'cabinet';
  return null;
}

/* What the placard says while they're away from the desk. Office words
   only (§6): the action, never the tool. */
const PROP_PLACARD = {
  cabinet:   'at the filing cabinet',
  bookshelf: 'at the bookshelf',
  phone:     'on the phone',
};

/* What a coworker says when a run fails (§4 error row, §7 "no raw error
   dumps — every failure is one honest sentence plus try again / ask
   differently / pick another coworker").

   Driving a real failed run through the floor showed this was still a log
   line wearing a speech bubble: it said

     "hit a snag — OpenRouter 503: error : openrouter: no API key configured"

   — an HTTP status, a doubled "error :", a provider name, and "API key",
   which §6 bans outright. The cause was recognisable and the fix was
   actionable, and the bubble said neither.

   SNAG_CAUSES maps only failures we can identify with confidence. Anything
   unrecognised falls through to the old cleaned first line: a wrong-but-
   confident diagnosis is worse than a vague honest one. */
const SNAG_CAUSES = [
  [/no api key|api[- ]?key (?:not|isn'?t) |missing api key|unauthor|invalid bearer|\b401\b/i,
   "that brain isn't signed in yet — add it in Settings, or give this to someone else"],
  [/\b429\b|rate.?limit|too many requests/i,
   'that brain is rate-limited right now — worth trying again in a minute'],
  [/insufficient|quota|billing|payment required|\b402\b/i,
   "that brain's account is out of credit — top it up or pick another coworker"],
  [/econnrefused|connection refused|enotfound|failed to fetch|network error|dns/i,
   "couldn't reach that brain — it looks offline from here"],
  [/timed? ?out|etimedout|\b504\b/i,
   'that took too long, so I stopped waiting — try again or ask for less at once'],
  [/\b5\d\d\b|internal server error|service unavailable/i,
   "that brain's service is having trouble — not something you did"],
];

/* Just the cause, as a clause: "that brain isn't signed in yet — …".

   Surfaces that already supply their own subject and verb (an escalation
   headline naming the coworker, a card that says "blocked by") need this
   half without the "hit a snag" spine. They must NOT get it by stripping
   the prefix off snagSentence — that is exactly how the inbox ended up
   printing "Kenji that brain isn't signed in yet", a sentence with no
   verb. One classifier, two shapes, no regex surgery at the call site. */
function snagCause(raw) {
  const text = String(raw || '');
  for (const [re, sentence] of SNAG_CAUSES) {
    if (re.test(text)) return sentence;
  }
  const first = text.split('\n')[0]
    .replace(/https?:\/\/\S+/g, '')            // URLs are noise in a bubble
    .replace(/[{}[\]"\\]/g, ' ')               // JSON shrapnel
    .replace(/\s+/g, ' ')
    .trim();
  const line = first || 'something went wrong on the last run';
  return line.length > 90 ? line.slice(0, 89).trimEnd() + '…' : line;
}

function snagSentence(raw) {
  return 'hit a snag — ' + snagCause(raw);
}

/* Which props stand in a coworker's room. Driven by `agent.tools` — the
   capability the boss ACTUALLY granted at hire — so a room furnishes to
   what its occupant can really do, and the §4 walk destinations exist in
   the room the walk happens in.

   Honesty note: this is capability, never achievement. A cabinet means
   "may open the vault", not "has filed a lot" — the papers pile and the
   out-tray are the earned counters, and they already read real numbers.
   An agent with no declared tools still gets a shelf: a bare office would
   read as broken, and a shelf claims nothing. Capped at two so the room
   stays legible at ×2 scale. */
const KIT_RULES = [
  [/^(vault|files?|fs|disk|memory)$/i, 'cabinet'],
  [/^(web|email|mail|http|browse|slack)$/i, 'phone'],
  [/^(search|library|research|db|index)$/i, 'bookshelf'],
];

function deskKit(tools) {
  const list = Array.isArray(tools) ? tools : [];
  const out = [];
  for (const t of list) {
    for (const [re, prop] of KIT_RULES) {
      if (re.test(String(t)) && out.indexOf(prop) === -1) out.push(prop);
    }
  }
  if (!out.length) out.push('bookshelf');
  return out.slice(0, 2);
}

/* ── The wire between the runtime and the floor ───────────────────────────
   Six events carry every beat the office plays. They were raw string
   literals at ~30 sites across 10 files, and a typo in one is a SILENTLY
   dead beat: nothing throws, no warning appears, the animation simply
   never plays. (`cafresohq:coffee` was added that way — by hand, twice,
   in two files.) One table now, and the names are checked.

   Guarded for headless: scripts/test_floor.py runs this file verbatim
   under node, where there is no window. */
const FLOOR_EVENT = {
  tool:     'cafresohq:agentTool',       // { agentId, name, phase: start|done }
  screen:   'cafresohq:agentScreen',     // { agentId, text, phase }
  artifact: 'cafresohq:artifact',        // { agentId }
  walkIn:   'cafresohq:walkIn',          // { id, color }
  coffee:   'cafresohq:coffee',          // { agentId }
  activity: 'cafresohq:agentActivity',   // { agentId, agentName, color, kind }
};

/* Every floor beat is ABOUT a coworker: with no id the office has no room
   to play it in and drops the event on the floor (literally). Catching
   that at the emitter turns a silent no-op into one warning at the site
   that got it wrong, which is the whole point of routing through here. */
function floorEmit(kind, detail) {
  const name = FLOOR_EVENT[kind];
  if (!name) throw new Error('unknown floor event: ' + kind);
  const d = detail || {};
  if (!d.agentId && !d.id) {
    if (typeof console !== 'undefined' && console.warn) {
      console.warn(`[floor] ${kind} dropped — no agentId; the office cannot place it`);
    }
    return false;
  }
  if (typeof window === 'undefined' || !window.dispatchEvent) return false;
  try { window.dispatchEvent(new CustomEvent(name, { detail: d })); return true; }
  catch (_e) { return false; }
}

/* Subscribe; returns the unsubscribe so effects can just return it. */
function floorOn(kind, handler) {
  const name = FLOOR_EVENT[kind];
  if (!name) throw new Error('unknown floor event: ' + kind);
  if (typeof window === 'undefined' || !window.addEventListener) return () => {};
  window.addEventListener(name, handler);
  return () => window.removeEventListener(name, handler);
}

export { deskKit, FLOOR_EVENT, floorEmit, floorOn, PROP_PLACARD, snagCause, snagSentence, toolProp };

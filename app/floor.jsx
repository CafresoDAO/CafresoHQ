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

/* ── One vocabulary for a tool visit ──────────────────────────────────────
   §6's table has a binding row: `tool call` → "shown as the action itself:
   reading files, searching". FOUR surfaces were breaking it, each with its
   own hand-rolled string:

     desk bubble    🔍 memory_read: facts/france.md
     activity row   memory_read("facts/france.md")
     chat echo      📡 MEMORY_READ("facts/france.md") →
     delivery note  - Read facts/france.md         ← the only honest one

   The first three print the tool's internal name on the floor, in the most
   prominent place a coworker has (their own speech bubble). One table now,
   and the tenses differ only because the surfaces do: a bubble describes
   what is happening NOW, a log and a filed note describe what happened.

   Same taxonomy and same order as toolProp above — search before web,
   because WEB_SEARCH contains both words and is a trip to the bookshelf. */
/* Ordered: the VERB patterns run before the NOUN ones, because the table
   used to key on the noun alone and so described every write as a read.
   MEMORY_WRITE and FILE_WRITE both came out "Opened notes/x.md" — the
   coworker saved something and the floor said they looked at it — and
   EXPORT_PPTX fell through to the default as "Checked deck.pptx" for work
   that produced a file.

   The default's reasoning is right and stays: an unknown tool gets a modest
   verb rather than a confident wrong one. But "Opened" for a write is not
   claiming less, it is claiming something else, and it costs the boss the
   one bit that matters — whether anything changed. */
/* `fail` is the third tense, and it is not decoration. A tool can fail
   WITHOUT raising — a missing file, a path that isn't a directory, a
   command that exits non-zero all answer normally, with the explanation as
   the result, because the coworker needs that text to try something else.
   Every surface here used to read "there is a result" as "it worked", and
   caption it in the past tense. Watched live 2026-08-13: a DIR_LIST of a
   path that did not exist rendered as

     📁 Opened ./site
     Not a directory: ./site

   — the office asserting success in its own voice, one line above its own
   evidence to the contrary. The boss scanning headers (which is what
   headers are FOR) reads that as a directory that was opened. */
const VISIT_WORDS = [
  [/SEARCH|LIBRARY|RESEARCH/,    { now: 'searching for', past: 'Looked up', fail: "Couldn't look up", icon: '🔎' }],
  [/PUBLISH/,                    { now: 'publishing',    past: 'Published', fail: "Couldn't publish",  icon: '🌍' }],
  [/EXPORT|GENERATE/,            { now: 'making',        past: 'Made',      fail: "Couldn't make",     icon: '🖨' }],
  [/WRITE|APPEND|SAVE|NEW|CREATE/, { now: 'saving',      past: 'Saved',     fail: "Couldn't save",     icon: '📝' }],
  [/WEB|HTTP|FETCH|URL|BROWSE/,  { now: 'reading',       past: 'Read',      fail: "Couldn't read",     icon: '🌐' }],
  [/VAULT|FILE|DIR|MEMORY|NOTE/, { now: 'opening',       past: 'Opened',    fail: "Couldn't open",     icon: '📁' }],
];
/* Anything we don't recognise still gets an ACTION, never the tool's name.
   "Checked X" claims less than a wrong-but-confident verb would. */
const VISIT_DEFAULT = { now: 'checking', past: 'Checked', fail: "Couldn't check", icon: '🗒' };
/* One icon for every failed trip, whatever the prop. The verb is the honest
   part, but a boss skims icons first, and six different icons for six ways
   of not working is six chances to miss that nothing happened. */
const VISIT_FAIL_ICON = '⚠';

function visitWords(name) {
  const n = String(name || '').toUpperCase();
  for (const [re, words] of VISIT_WORDS) if (re.test(n)) return words;
  return VISIT_DEFAULT;
}

/* What they visited, said plainly. The scheme is plumbing to a reader who
   can see it's a web address, and quotes around it are machine syntax. */
function visitSubject(arg, cap) {
  const s = String(arg || '').trim().replace(/^https?:\/\//i, '').replace(/\s+/g, ' ');
  const max = cap || 88;
  return s.length > max ? s.slice(0, max - 1).trimEnd() + '…' : s;
}

/* The one-liner each surface composes from. `tense` is 'now' for a live
   bubble, 'past' for a log line or a filed note. Returns null when there's
   no subject to name — a visit with no argument has nothing honest to say
   beyond the walk the sprite is already doing. */
function visitLine(name, arg, tense, cap) {
  const subject = visitSubject(arg, cap);
  if (!subject) return null;
  const w = visitWords(name);
  const verb = tense === 'now' ? w.now : tense === 'fail' ? w.fail : w.past;
  return `${verb} ${subject}`;
}

/* Some tools take no argument at all — MEMORY_LIST is "show me everything
   on the shelf". `visitLine` returns null for those (a filed-note line
   reading "Opened" with no target is useless), and the live surfaces used
   to fall back to "checked something", which was measured on a real run
   and says nothing.

   But the office DOES know something: which prop they walked to. So the
   fallback is the placard the floor already shows above their empty desk —
   the same words, in the same voice, for the same trip. */
function visitPlace(name, tense) {
  const prop = toolProp(name);
  /* A failed trip must not borrow the placard: "the bookshelf" reads as a
     place they got to. Say plainly that they didn't. */
  if (tense === 'fail') return "couldn't do that";
  if (prop && PROP_PLACARD[prop]) return PROP_PLACARD[prop];
  return tense === 'now' ? 'looking something up' : 'looked something up';
}

/* A visit, as structured data for the UI to render — never as text.
   Capped here rather than at each render site so one long page fetch can't
   push the coworker's actual answer off the screen. */
const VISIT_RESULT_CAP = 600;

function toVisit(ev) {
  if (!ev || !ev.name) return null;
  const tense = ev.failed ? 'fail' : 'past';
  const head = visitLine(ev.name, ev.arg, tense, 60) || visitPlace(ev.name, tense);
  const raw = String(ev.result === undefined || ev.result === null ? '' : ev.result);
  const body = raw.length > VISIT_RESULT_CAP
    ? raw.slice(0, VISIT_RESULT_CAP).trimEnd() + '\n…'
    : raw;
  return {
    icon: ev.failed ? VISIT_FAIL_ICON : visitWords(ev.name).icon,
    head, body: body.trim(), at: ev.at || null, failed: !!ev.failed,
  };
}

/* Attach a visit to the message currently streaming. One helper because
   five call sites need it, and five hand-rolled copies is how the office
   ends up describing the same trip five ways (it already did, four times,
   before `visitLine`). */
function attachVisit(setChat, msgId, ev) {
  const visit = toVisit(ev);
  if (!visit || !setChat || !msgId) return false;
  setChat(prev => prev.map(m => m.id === msgId
    ? Object.assign({}, m, { visits: (m.visits || []).concat([visit]) })
    : m));
  return true;
}

/* ── The office's voice is not the coworker's to borrow ───────────────────
   Caught live, and it is the worst thing found on this floor so far. Asked
   a local model to check its memory, the chat came back:

     📡 MEMORY_READ("facts/france.md") →
     Found note on French capitals in memory!
     [Vault path: Research/capitals-of-europe.md]

     📁 Opened facts/france.md
     (no memory at "facts/france.md")

   The second block is the office reporting what really happened. The FIRST
   is the model writing a tool visit that never occurred, in the office's
   own format, complete with an invented result and an invented vault path.
   To the boss the two are the same kind of line, and one of them is a
   fabricated fact attributed to their own filing cabinet.

   It learned the format from us: every past visit is stored in the chat
   message text, and that text goes straight back as conversation history.
   So the fix is at the source — the office's report of its own actions
   never re-enters the model's context as something the model said.

   Only the HEAD line goes. The result body underneath stays: it is real
   information the model legitimately needs, and stripping it would make
   the next turn dumber to no purpose. What's removed is the TEMPLATE.

   The legacy `📡 NAME("arg") →` shape is matched too, because histories
   written before the office changed its wording still carry it — and it is
   the exact shape the forgery above imitated. */
const _VISIT_VERBS = (() => {
  const words = VISIT_WORDS.map(([, w]) => w).concat([VISIT_DEFAULT]);
  const all = [];
  /* `fail` belongs here for the same reason past and now do: it is office
     voice, so a coworker must not be able to type it and have it render as
     the office reporting. A forged failure is as damaging as a forged
     success — it blames the tools for work they never declined to do. */
  for (const w of words) for (const v of [w.past, w.now, w.fail]) if (v && all.indexOf(v) === -1) all.push(v);
  return all;
})();
const _VISIT_ICONS = VISIT_WORDS.map(([, w]) => w.icon).concat([VISIT_DEFAULT.icon, VISIT_FAIL_ICON]);

function _officeVoiceRe() {
  const icons = _VISIT_ICONS.map(i => i.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const verbs = _VISIT_VERBS.map(v => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  return new RegExp(`^[ \\t]*(?:📡[^\\n]*→|(?:${icons})[ \\t]+(?:${verbs})\\b[^\\n]*)[ \\t]*$`, 'gm');
}

function stripOfficeVoice(text) {
  return String(text || '').replace(_officeVoiceRe(), '').replace(/\n{3,}/g, '\n\n').trim();
}

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
  /* Every browser words a dead connection differently, and this pattern
     originally spoke only Chrome. `network error` (with a space) does NOT
     match Firefox's `NetworkError when attempting to fetch resource`, and
     nothing here matched Safari's terse `Load failed` — so on two of the
     three major engines a plain offline failure fell straight past the
     classifier into the raw-first-line fallback, on EVERY surface that uses
     it, not just one. Caught by unplugging the network under a real vault
     delete and reading the toast: "NetworkError when attempting to fetch
     resource." reached the boss verbatim, which is the §7 leak this table
     exists to stop. `networkerror` is written unspaced on purpose. */
  [/econnrefused|connection refused|enotfound|failed to fetch|network ?error|load failed|dns/i,
   "couldn't reach that brain — it looks offline from here"],
  /* "did not start responding" is how a cold LOCAL model reads: the driver
     gives up before the weights finish loading. Caught live — a first call
     to a freshly-woken Ollama produced `backend did not start responding
     within 20s`, which matched nothing here and so fell through to the raw
     first line, putting the §6-banned word "backend" straight into the
     floor bubble. Its own sentence, because "warming up" is the actionable
     part and "try again" really does work the second time (it did). */
  [/did ?n[o']?t start responding|did ?n[o']?t respond|not responding/i,
   "that brain didn't answer in time — it may still be warming up, so try again in a moment"],
  [/timed? ?out|etimedout|\b504\b/i,
   'that took too long, so I stopped waiting — try again or ask for less at once'],
  [/\b5\d\d\b|internal server error|service unavailable/i,
   "that brain's service is having trouble — not something you did"],
  /* Model-not-installed. Caught live by pointing a coworker at
     `ollama:model-that-does-not-exist`: the raw line "Ollama 404: model …
     not found" fell through the table and put a vendor name and an HTTP
     code on the floor bubble, which is exactly the raw dump §7 forbids.

     It earns its own sentence rather than folding into the 404-ish
     network case, because the cure is completely different — nothing is
     offline and retrying will never help; the brain this coworker was
     hired with simply is not on the machine. That is also the single most
     likely failure for the audience §08 names: a non-guru picks a model
     they do not have. Placed AFTER the 5xx rule so a genuine server error
     still wins, and it does not match a bare "404" alone — "not found"
     or "no such model" has to be there too, or an unrelated 404 would be
     mis-diagnosed with confidence, which this table's own header warns
     is worse than a vague honest answer.

     The character budget between "model" and "not found" is 60, not the
     20 the first cut used: the real string is
     `Ollama 404: model "model-that-does-not-exist" not found`, and the
     quoted name alone is 28 characters. The regex read correctly and
     missed the only case it was written for — found by unit-testing the
     classifier against the VERBATIM error rather than a paraphrase. */
  [/(?:\b404\b[^\n]{0,40})?(?:model[^\n]{0,60}(?:not found|does ?n[o']?t exist)|no such model|unknown model|pull the model)/i,
   "that brain isn't installed on this machine — pick another coworker, or install it and try again"],
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
  return cleanCause(text);
}

/* The sanitiser WITHOUT the diagnosis — snagCause's own fallback, given a
   name so surfaces whose subject is not a brain can use it.

   Every sentence in SNAG_CAUSES says "that brain", because the table was
   written for coworker dispatch. Point it at a failure whose subject is
   something else and it answers confidently and wrongly: a failed probe of
   the office's OWN backend came back "couldn't reach that brain — it looks
   offline from here", which names the wrong thing and sends the boss to
   check the wrong place. (Same shape as the open note about file saves
   reporting a brain outage.) Routing those surfaces through snagCause trades
   a raw dump for a confident misdiagnosis, which is the worse of the two.

   So: use snagCause where a brain really is the subject, and cleanCause
   where it is not. This still satisfies §7's "no raw error dumps" — URLs,
   JSON shrapnel and multi-line stacks are stripped and the line is capped —
   it just declines to name a cause it cannot identify, which is the same
   call as the graph panel's "unformed". */
/* ── The same knowledge, worded for the OFFICE ────────────────────────────
   Splitting snagCause and cleanCause fixed the misattribution but threw away
   something useful: the patterns themselves are right, it is only the NOUN
   that was wrong. A vault delete that fails offline is not "couldn't reach
   that brain", but neither is it nothing — "the office isn't answering" is
   both true and actionable, and the office is what actually failed.

   Found by census after the settings probe: TWELVE call sites were passing
   non-brain failures through snagCause — every file operation and publish in
   views/projects.jsx, all three vault paths, app/storage.jsx, the delivery
   share. Some of that was mine, from earlier the same day: widening the
   connectivity pattern so an offline vault delete stopped leaking
   "NetworkError when attempting to fetch resource" verbatim ALSO made it
   claim a brain was offline. One fix, two subjects, and I only checked one.

   hq-runtime.jsx already had this lesson written down for BROWSER_FETCH —
   "a page is not a brain", snagCause applied and then taken back out. It was
   true there, true here, and nobody had generalised it.

   Three shapes now, one classifier: snagCause when a brain really is the
   subject, officeCause when the office is, cleanCause when nothing can be
   said with confidence. */
const OFFICE_CAUSES = [
  [/econnrefused|connection refused|enotfound|failed to fetch|network ?error|load failed|dns/i,
   "the office isn't answering — check it's still running"],
  [/timed? ?out|etimedout|\b504\b/i,
   'that took too long, so I stopped waiting — try again'],
  [/\b5\d\d\b|internal server error|service unavailable/i,
   'the office ran into trouble doing that — not something you did'],
  [/\b40[34]\b|not found|no such file|enoent/i,
   "the office couldn't find that — it may have been moved or renamed"],
  [/eacces|permission denied|\b403\b/i,
   "the office isn't allowed to touch that file"],
  [/enospc|no space left/i,
   'this machine is out of disk space'],
];

function officeCause(raw) {
  const text = String(raw || '');
  for (const [re, sentence] of OFFICE_CAUSES) {
    if (re.test(text)) return sentence;
  }
  return cleanCause(text);
}

function cleanCause(raw) {
  const first = String(raw || '').split('\n')[0]
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

/* The third shape: the clause standing alone as its own sentence, for
   surfaces where the speaker is already obvious because the bubble IS
   them — the coworker's error bubble and the CEO's.

   snagSentence is the INBOX shape. Those rows render "NAME + text", so
   "Kenji hit a snag — that brain isn't signed in yet" needs the verb to
   have a spine. Put the same string in a bubble the CEO is speaking and
   the subject vanishes: "⚠ hit a snag — couldn't reach that brain — it
   looks offline from here", a log line with two dashes in it, which is
   what the front door said until this was written down.

   It exists as a function for the reason the other two do: chatErrorText
   was already capitalising the clause by hand, and a second call site
   copying that expression is exactly how these three shapes drifted apart
   the first time. */
function snagOpener(raw) {
  const c = snagCause(raw);
  return c.charAt(0).toUpperCase() + c.slice(1);
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

/* One shape for a tool line filed into the activity feed, so the call sites
   can't drift on tense the way they did — both wrote the PAST tense from the
   `start` phase, which put "saved report.md" in the feed before the save had
   been attempted, and left it there unchanged when the save failed.

   Call this on `done` only: the tense is chosen from the outcome, and the
   outcome does not exist yet at `start`. */
function toolActivity(agent, ev, extra) {
  const tense = ev && ev.failed ? 'fail' : 'past';
  const line = visitLine(ev.name, ev.arg, tense, 40) || visitPlace(ev.name, tense);
  return {
    agentId: agent && agent.id, agentName: agent && agent.name,
    color: agent && agent.color, action: 'tool',
    text: String(line || '').toLowerCase(),
    ...(extra || {}),
  };
}

export { attachVisit, cleanCause, deskKit, FLOOR_EVENT, floorEmit, floorOn, PROP_PLACARD, officeCause, snagCause, snagOpener, snagSentence, stripOfficeVoice, toolActivity, toolProp, toVisit, visitLine, visitPlace, visitSubject, visitWords };

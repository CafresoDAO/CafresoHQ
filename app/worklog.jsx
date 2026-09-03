/* ── Is anyone actually on this? (OFFICE_AS_INTERFACE §4/§5) ──────────────
   The task board could not answer the first question a boss asks about an
   in-progress job. Measured on a live floor: a task sat in DOING for a whole
   session with nobody working on it, and its card was pixel-identical to one
   picked up a second earlier. An office where jobs rot invisibly in "in
   progress" is not an operating business.

   Two facts fix that, and both must be honest:

   1. WHEN it started. `startedAt`, stamped on the way into `doing` and
      cleared on the way out.
   2. WHETHER anyone is on it NOW. §4 is binding here: `agent.status` is the
      only thing that answers "is this coworker working right now". Not the
      task's own status, not the desk bubble, not a timer.

   Kept import-free so scripts/test_worklog.py can run this file verbatim. */

/* The `startedAt` invariant, in one place — there are seven sites that write
   a task status, and an invariant enforced at six of them is not one.

   Only stamped when ABSENT: re-entering `doing` mid-run (a reassignment, a
   drag onto the same column) must not restart the clock, or a job that has
   been sitting two hours would report itself fresh every time it was
   touched. Cleared on the way out so a re-opened task can't inherit a stale
   age from a previous life.

   `completedAt`/`completedBy` get the same treatment, for the same reason —
   and belong here rather than at each call site for a reason `startedAt`
   didn't have to worry about: the fix that taught every agent-completion
   path to stamp them (app.jsx, "of the three sites that put a task into
   done, only one stamped") verified itself with a wiring check that greps
   app.jsx/features.jsx for the literal text `applyStatus(...,'done'`. The
   Task Board's own column drag — `onMoveTask` in app.jsx, `applyStatus(t,
   status)` with `status` a variable — has never once matched that literal
   and was never one of the three sites anyone counted.

   Measured: drag a parked card (one whose run came back without a
   deliverable — `result` holds the reply text, `completedAt`/`completedBy`
   both correctly null per that same fix) straight from DOING to the DONE
   column. The card's `t.result` block renders `finished` from `t.status`
   alone, so it flips to "✓ finished" — and, with nothing here stamping
   `completedAt`, stays timeless forever, the exact bare line the
   agent-completion fix was written to stop. No agent did this, so no name
   is owed — `completedBy` is left to the caller, same as it always was —
   but WHEN is owed, because the boss just did it and the field exists to
   say so.

   Symmetric with `startedAt`: only stamped when absent, so re-dropping an
   already-done card on DONE doesn't refresh its finish time; cleared on the
   way out (`completedBy` with it — a name with no timestamp behind it is a
   worse answer than no name) so a card reopened via a manual drag, and not
   just via a fresh run, can't go on crediting whoever finished its last
   life. */
function applyStatus(task, status, now) {
  const next = Object.assign({}, task, { status });
  if (status === 'doing') {
    if (!next.startedAt) next.startedAt = (now || Date.now());
  } else if (next.startedAt) {
    delete next.startedAt;
  }
  if (status === 'done') {
    if (!next.completedAt) next.completedAt = (now || Date.now());
  } else {
    if (next.completedAt) delete next.completedAt;
    if (next.completedBy) delete next.completedBy;
  }
  return next;
}

/* WORKING statuses — the floor's own vocabulary for a coworker mid-run.
   Anything else (idle, away, stuck) means nobody is at the keyboard. */
const WORKING = ['active', 'busy'];

/* A card in `doing` whose run has already ENDED, waiting on the boss.

   #86 said a parked snag is not work in flight, and every surface that
   counts running jobs has had to know it since. They each worked it out
   themselves — the load-time scrub, the "is this stream this card's"
   check, the card's own worklog line above — and on 2026-08-16 the
   workflow list turned out never to have learned it: a two-step pipeline
   whose first step stopped part-way read `0/2 done · 1 in progress`,
   because `status === 'doing'` was the whole test. The pipeline was not
   in progress. It was stopped, and would stay stopped until the boss
   restarted that step.

   `blockedReason` is written by the run-end path and by a coworker's
   `[TASK_BLOCKED]`, and cleared by every path that moves the card on — a
   progress note, a completion, a fresh START. A mid-run `[TASK_BLOCKED]`
   therefore reads as parked while the stream is technically still open,
   and that is the office's settled reading, not a gap: worklogLine says
   "hit a snag" on the same card, and a coworker who announces they are
   stuck on this job has stopped moving it whatever the socket is doing.

   Named here so the fourth surface that needs the answer reads it rather
   than deriving a fourth copy. */
function isParked(task) {
  return !!(task && task.status === 'doing' && task.blockedReason);
}

/* True when a job is in progress and no one is currently working on it.

   Deliberately does NOT try to prove the agent is on THIS task specifically
   — nothing in the model links a run to a task id, and inventing that link
   would be the kind of confident-but-wrong claim §4 exists to prevent. What
   it says is exactly what it knows: this job is open, and its owner is not
   working. Unassigned counts too — an owner-less job in DOING is the purest
   case of nobody being on it. */
function isStalled(task, owner) {
  if (!task || task.status !== 'doing') return false;
  if (!owner) return true;
  return WORKING.indexOf(String(owner.status)) === -1;
}

/* How long it has been in `doing`, or null when we never stamped it —
   tasks that predate `startedAt` must say nothing rather than guess from
   `createdAt`, which is when the job was WRITTEN DOWN, not when it started.
   A silent card beats a card claiming a made-up two hours. */
function sittingFor(task, now) {
  if (!task || !task.startedAt) return null;
  const ms = (now || Date.now()) - task.startedAt;
  return ms >= 0 ? ms : null;
}

const MIN = 60000, HOUR = 3600000, DAY = 86400000;

/* Office words, coarse on purpose: the boss is deciding whether to chase
   this, not timing a lap. */
function durationLabel(ms) {
  if (ms === null || ms === undefined || ms < 0) return null;
  if (ms < MIN) return 'just now';
  if (ms < HOUR) return `${Math.floor(ms / MIN)}m`;
  if (ms < DAY) {
    const h = Math.floor(ms / HOUR), m = Math.floor((ms % HOUR) / MIN);
    return m ? `${h}h ${m}m` : `${h}h`;
  }
  const d = Math.floor(ms / DAY);
  return d === 1 ? '1 day' : `${d} days`;
}

/* The one line the card shows. Returns null when there is nothing true and
   useful to say, so callers can render nothing rather than an empty badge.

   The wording separates the two cases because they need different moves
   from the boss: someone IS on it (wait), or nobody is (start it, or close
   it). It never says "stuck" — that word belongs to a coworker who tried
   and snagged (§5), and a job nobody picked up has not failed at anything. */
/* The blocked branch comes FIRST, and it is the one case where this line is
   allowed the word the comment above reserves.

   A coworker can say `[TASK_BLOCKED: id: reason]` mid-run. The office stored
   the reason on the task and showed it in a toast, and the toast is gone in
   seconds — after which the card sat in DOING looking exactly like a job in
   flight. Worse than looking neutral: `agent.status` is about the COWORKER,
   not the task, so the moment that coworker was dispatched to anything else
   this line read "on it · 12m" over a job they had explicitly given up on.
   A missing answer became a wrong one.

   "hit a snag" and not "nobody's on this", because the two need different
   moves from the boss. Nobody-on-this means start it or close it. This means
   somebody tried, and there is a reason underneath worth reading. */
function worklogLine(task, owner, now) {
  if (!task || task.status !== 'doing') return null;
  const age = durationLabel(sittingFor(task, now));
  if (task.blockedReason) return age ? `hit a snag · ${age}` : 'hit a snag';
  if (!isStalled(task, owner)) return age ? `on it · ${age}` : 'on it';
  return age ? `nobody's on this · ${age}` : "nobody's on this";
}

/* A card line, cut where a reader can tell it was cut.

   Both honesty lines on a card — the snag reason and the note explaining a
   card sitting in the inbox — were rendered `.slice(0, 140)`, a hard cut at
   a character count. Seen on screen 2026-08-16, both at once:

     ✋ they did as much as they can in one go and stopped there. Running
        it again starts from the brief and carries nothing over, so a
        narrower bri
     ↩ waiting on "Alpha probe one three one" — that step has not
        delivered yet, so this one has nothing to work from. Finish it and
        this starts on

   §7 says every honest sentence needs a way forward, and in both of these
   the way forward is the last clause — which is precisely the part a cap
   eats. "Finish it and this starts on" is not a shorter version of the
   sentence; it is a sentence that stops before saying anything.

   240 because that is already the office's number for the longest thing
   that can land in one of these fields (a coworker's `[TASK_BLOCKED]`
   reason is cut to 240 on the way in), so every sentence the office writes
   itself now arrives whole. Longer than that still gets cut — a card is a
   card — but on a word, with the ellipsis that says so, and the caller
   hands the untruncated text to the hover. */
function cardNote(text, cap) {
  const s = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
  const n = cap || 240;
  if (s.length <= n) return s;
  const cut = s.slice(0, n - 1);
  const sp = cut.lastIndexOf(' ');
  /* Only back up to a word boundary when there is one worth backing up to
     — a 200-character URL has no spaces, and losing most of the line to
     find one would be worse than the cut. */
  return (sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:.—-]+$/, '') + '…';
}

/* When a job finished. `completedAt` and `completedBy` were both stamped on
   the record by the done handler and read by nothing, so a finished card
   could not say who finished it or when — the DONE column was a wall of
   titles with no history behind any of them.

   Returns null rather than guessing when the stamp is missing: tasks that
   predate `completedAt` must say nothing, for the same reason `sittingFor`
   refuses to fall back to `createdAt`. "just now" already reads as a time,
   so it does not take the "ago". */
function finishedLabel(task, now) {
  if (!task || !task.completedAt) return null;
  const label = durationLabel((now || Date.now()) - task.completedAt);
  if (!label) return null;
  return label === 'just now' ? 'just now' : `${label} ago`;
}

export { applyStatus, cardNote, durationLabel, finishedLabel, isParked, isStalled, sittingFor, worklogLine, WORKING };

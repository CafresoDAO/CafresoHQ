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
   age from a previous life. */
function applyStatus(task, status, now) {
  const next = Object.assign({}, task, { status });
  if (status === 'doing') {
    if (!next.startedAt) next.startedAt = (now || Date.now());
  } else if (next.startedAt) {
    delete next.startedAt;
  }
  return next;
}

/* WORKING statuses — the floor's own vocabulary for a coworker mid-run.
   Anything else (idle, away, stuck) means nobody is at the keyboard. */
const WORKING = ['active', 'busy'];

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

export { applyStatus, durationLabel, finishedLabel, isStalled, sittingFor, worklogLine, WORKING };

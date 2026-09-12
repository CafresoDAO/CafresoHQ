/* ── Experience ledger (OFFICE_AS_INTERFACE §5) ───────────────────────────
   Each completed job appends one entry here. The ledger is APPEND-ONLY on
   purpose: in Phase B these numbers are attachment and legibility ("Mira's
   done all my briefs"); in Phase C the same per-agent, per-task-type history
   becomes the on-chain résumé ledger for marketplace agents. Entries are
   never rewritten, re-keyed or decremented — anything derived (jobs, streak,
   affinity) is computed from the log, so the log stays the truth.

   What counts as a job: a TASK completion (dropped on a desk, or closed via
   a [TASK_DONE:…] marker in chat) and a MISSION that ran its schedule. A
   chat reply or a DM is not a job, same as it is not an artifact (§3.6) —
   the legacy `agent.tasksDone` counter counted those, which is why the
   roster no longer displays it.

   Outcomes: 'done' or 'snag' (a failed run — resets the streak). A run the
   USER stopped is not recorded at all; walking over to someone's desk and
   taking the folder back is not their failure.

   Entry: { at, agentId, kind, outcome, taskId?, title? }               */

/* `agent.tasksDone` is RETIRED, not merely unused. Three sites still
   incremented it after this ledger replaced it, and nothing anywhere read
   it back — a counter whose only surviving property was that it was
   wrong, sitting in the agent object waiting to look authoritative to
   whoever needed a jobs number next. The writes are gone; stale values on
   already-persisted coworkers are harmless because no surface reads them.
   If you want jobs completed, it is `xpStats(experience, agentId)`. */

/* Streak length at which a card calls it "on fire" (🔥). One number, read
   by both twin surfaces (the roster card in views/core.jsx and the
   Performance-review panel in ui/panels.jsx) so the same `xp.streak` value
   earns the same badge everywhere.

   Before this constant existed, each file hardcoded its own threshold —
   the roster card fired at `>= 3` (documented live: "Jobs 3 🔥" in
   OFFICE_AS_INTERFACE #155), the panel at `>= 2` — an inconsistency present
   since both were introduced in the same commit (76b8070) and never
   reconciled. A coworker sitting at streak 2 read as "just delivering,
   nothing special" on the roster tile and "2 🔥 — on a hot streak" the
   moment the boss opened their Performance review, for the identical fact
   about the identical coworker. Measured live: hired Llama, seeded the
   ledger with two 'done' entries via /hq/state/experience, and the roster
   card showed "JOBS 2" with no flame while the panel opened on the same
   card showed "CURRENT STREAK 2 🔥". */
const XP_HOT_STREAK = 3;

/* Kind → [singular, plural]. Kinds mirror the starter cards
   (modals/starter.jsx) plus the two host-minted ones. Unknown kinds are
   preserved verbatim in the ledger (Phase C forward-compat) and label as
   plain jobs. */
const XP_KIND_LABEL = {
  brief:   ['research brief', 'research briefs'],
  draft:   ['draft', 'drafts'],
  page:    ['page', 'pages'],
  mission: ['night shift', 'night shifts'],
  task:    ['job', 'jobs'],
  /* A colleague's question answered mid-run (ASK_COWORKER, #430). Not a
     starter kind — nothing is filed under it from a card — but it is work
     the coworker did for the team, and two of them are an affinity. */
  help:    ['assist', 'assists'],
};

/* The task-type a task earns XP under: its starter card if it came from
   one, else a generic job. */
function taskKind(task) {
  const s = task && task.starter;
  return (s && s !== 'task' && s !== 'mission' && XP_KIND_LABEL[s]) ? s : 'task';
}

/* Append one entry. Returns the ledger unchanged when the entry is
   malformed, or when this job's completion is still STANDING — a job
   completes once, which makes every double-fire path safe (an agent
   re-emitting [TASK_DONE:…], a mission's self-complete racing its deadline
   sweep).

   "Standing" is the whole of it, and it used to say "ever". A task that is
   completed, re-opened (the board lets a done card go back to a column —
   see `applyStatus`'s own note about a re-opened task's stale age) and then
   snagged could never be completed AGAIN: the retry's 'done' matched a
   completion from days earlier and went on the floor. Two things then stuck
   forever, both of them wrong and both of them read as current:

     • the retry's coworker got no credit — no job, no streak, nothing on
       the résumé ledger for work they actually delivered; and
     • `xpLastAttempt` reads this job's NEWEST entry, so with the success
       dropped the newest one stayed the snag. The inbox card kept warning
       "Mira hit a snag on this" and the workflow panel kept counting the
       step as "1 failed — needs you" on a step that had since succeeded —
       against modals/collab.jsx's promise, in that file's own words, that
       it "clears itself the moment a retry succeeds".

   So: scan back to this job's newest entry only. A 'done' standing there is
   a double-fire and is dropped exactly as before; a 'snag' there means the
   job really was re-attempted, and a re-attempt that succeeded is a
   completion the log has never recorded. */
function xpRecord(ledger, { agentId, kind, outcome, taskId, title, at } = {}) {
  const prev = Array.isArray(ledger) ? ledger : [];
  if (!agentId || (outcome !== 'done' && outcome !== 'snag')) return prev;
  if (outcome === 'done' && taskId) {
    for (let i = prev.length - 1; i >= 0; i--) {
      const e = prev[i];
      if (!e || e.taskId !== taskId) continue;
      if (e.outcome === 'done') return prev;   // completion still stands
      break;                                   // snagged since — this one is real
    }
  }
  const entry = { at: at || Date.now(), agentId, kind: String(kind || 'task'), outcome };
  if (taskId) entry.taskId = taskId;
  if (title) entry.title = String(title).slice(0, 80);
  return [...prev, entry];
}

/* "12 research briefs" */
function xpKindLabel(kind, n) {
  const l = XP_KIND_LABEL[kind] || XP_KIND_LABEL.task;
  return `${n} ${n === 1 ? l[0] : l[1]}`;
}

/* Everything a card shows, derived in one pass:
     jobs    — completed, ever
     snags   — failed runs, ever
     streak  — consecutive completions since the last snag
     byKind  — { kind: doneCount }
     affinity— { kind, count } for the strongest REAL specialty, or null.
               Generic tasks aren't a specialty, and one of something isn't
               an affinity yet — the label only appears once it's earned. */
function xpStats(ledger, agentId) {
  const mine = (Array.isArray(ledger) ? ledger : [])
    .filter(e => e && e.agentId === agentId);
  let jobs = 0, snags = 0;
  const byKind = {};
  for (const e of mine) {
    if (e.outcome === 'done') { jobs++; byKind[e.kind] = (byKind[e.kind] || 0) + 1; }
    else snags++;
  }
  let streak = 0;
  for (let i = mine.length - 1; i >= 0; i--) {
    if (mine[i].outcome !== 'done') break;
    streak++;
  }
  let affinity = null;
  for (const kind of Object.keys(byKind)) {
    if (kind === 'task') continue;
    if (byKind[kind] >= 2 && (!affinity || byKind[kind] > affinity.count)) {
      affinity = { kind, count: byKind[kind] };
    }
  }
  return { jobs, snags, streak, byKind, affinity,
           lastAt: mine.length ? (mine[mine.length - 1].at || 0) : 0 };
}

/* The one-line specialty string for a card ("12 research briefs"), or ''
   when there's nothing honest to claim. */
function xpAffinityText(stats) {
  return (stats && stats.affinity)
    ? xpKindLabel(stats.affinity.kind, stats.affinity.count)
    : '';
}

/* What happened the LAST time someone tried this task, or null.

   A snagged task goes back to the inbox with assignedTo cleared, which is
   right — it must stay re-delegatable — but the card came back looking
   untouched. The system knew Kenji had already tried it and failed (the
   attention row, his room, this ledger all said so); the one surface where
   you decide what to do next said nothing, so the obvious next move was to
   hand it straight back to the coworker it had just defeated.

   Derived, never stored — same rule as the rest of §5. It reports a fact
   ("Kenji hit a snag on this"), never a recommendation: whether to retry,
   reword, or reassign is the boss's call, and we don't have the standing
   to guess. */
function xpLastAttempt(ledger, taskId, agents) {
  if (!taskId) return null;
  const rows = (Array.isArray(ledger) ? ledger : []).filter(e => e && e.taskId === taskId);
  if (!rows.length) return null;
  const last = rows.reduce((a, b) => ((b.at || 0) >= (a.at || 0) ? b : a));
  const who = (Array.isArray(agents) ? agents : []).find(a => a && a.id === last.agentId);
  return {
    agentId: last.agentId,
    // A coworker who has since been let go leaves the fact intact but
    // nameless — better than inventing a name or dropping the history.
    name: who ? who.name : null,
    outcome: last.outcome,
    at: last.at || 0,
  };
}

/* That fact as one line of office English, or '' when there is nothing
   worth saying (no attempt, or the last one succeeded — a finished task
   isn't sitting in the inbox needing a warning). */
function xpLastAttemptText(attempt) {
  if (!attempt || attempt.outcome === 'done') return '';
  const who = attempt.name || 'someone since let go';
  return `${who} hit a snag on this`;
}

export { taskKind, xpAffinityText, xpKindLabel, xpLastAttempt, xpLastAttemptText, xpRecord, xpStats, XP_HOT_STREAK, XP_KIND_LABEL };

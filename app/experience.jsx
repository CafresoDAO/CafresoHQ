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
};

/* The task-type a task earns XP under: its starter card if it came from
   one, else a generic job. */
function taskKind(task) {
  const s = task && task.starter;
  return (s && s !== 'task' && s !== 'mission' && XP_KIND_LABEL[s]) ? s : 'task';
}

/* Append one entry. Returns the ledger unchanged when the entry is
   malformed, or when this job already has a 'done' — a job completes once,
   which makes every double-fire path safe (an agent re-emitting
   [TASK_DONE:…], a mission's self-complete racing its deadline sweep). */
function xpRecord(ledger, { agentId, kind, outcome, taskId, title, at } = {}) {
  const prev = Array.isArray(ledger) ? ledger : [];
  if (!agentId || (outcome !== 'done' && outcome !== 'snag')) return prev;
  if (outcome === 'done' && taskId &&
      prev.some(e => e && e.taskId === taskId && e.outcome === 'done')) return prev;
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

export { taskKind, xpAffinityText, xpKindLabel, xpRecord, xpStats, XP_KIND_LABEL };

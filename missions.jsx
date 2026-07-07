/* ==========================================================================
   CafresoHQ — research missions

   A "mission" is a long-running, scheduled loop that hands an agent a
   research prompt every N minutes for up to D hours. Each iteration uses
   the agent's normal tool stack ([SEARCH:], [VAULT_NEW:], [VAULT_READ:])
   so over time a corpus of focused notes accumulates in the configured
   vault folder.

   The mission state is persisted to localStorage so a reload picks up
   in-progress missions; the loop itself is a chain of setTimeouts owned
   by the running browser tab. If the tab closes, the loop pauses; on
   reopen the user can resume.
   ========================================================================== */

const { useState: useSM, useEffect: useEMission, useRef: useRMission } = React;
const { Modal: OcModalM } = window.CafresoHQModals;

const MIN = 60_000;
const HOUR = 60 * MIN;

const DURATION_PRESETS = [
  { label: '15 min',  ms: 15 * MIN },
  { label: '30 min',  ms: 30 * MIN },
  { label: '1 hour',  ms: 1 * HOUR },
  { label: '2 hours', ms: 2 * HOUR },
  { label: '4 hours', ms: 4 * HOUR },
];

const INTERVAL_PRESETS = [
  { label: 'every 1 min',  ms: 1 * MIN },
  { label: 'every 3 min',  ms: 3 * MIN },
  { label: 'every 5 min',  ms: 5 * MIN },
  { label: 'every 10 min', ms: 10 * MIN },
  { label: 'every 20 min', ms: 20 * MIN },
];

/* Slugify a topic into a vault-friendly folder name. */
function topicSlug(topic) {
  return String(topic || '').trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'untitled';
}

/* Build the per-iteration prompt for a project-study mission. The agent
   reads project files, understands architecture, and writes structured
   notes about how the project works into the Obsidian vault. */
function buildProjectStudyPrompt(mission, agent, notesIndex, fileTree) {
  const elapsedMin = Math.round((Date.now() - mission.startedAt) / MIN);
  const remainingMin = Math.max(0, Math.round((mission.startedAt + mission.durationMs - Date.now()) / MIN));
  const folder = mission.vaultFolder;
  const totalIters = Math.max(1, Math.round(mission.durationMs / mission.intervalMs));
  const notesList = (notesIndex && notesIndex.length)
    ? notesIndex.slice(0, 20).map(n => `  - ${n.path}${n.title ? ` (${n.title})` : ''}`).join('\n')
    : '  (none yet)';
  const treeList = (fileTree && fileTree.length)
    ? fileTree.slice(0, 80).map(f => `  ${f.isDir ? '📁' : '  '} ${f.name}${f.size ? ` (${f.size})` : ''}`).join('\n')
    : '  (could not list files)';

  const lines = [
    `You are studying a software project to build comprehensive documentation in Obsidian.`,
    ``,
    `PROJECT: ${mission.projectName}`,
    `PATH: ${mission.projectPath}`,
    `ITERATION: ${mission.iterations + 1} of ~${totalIters} planned`,
    `TIME: ${elapsedMin}m elapsed · ${remainingMin}m remaining`,
    `VAULT FOLDER: ${folder}/`,
    ``,
    `Project file tree (top-level):`,
    treeList,
    ``,
    `Notes already written under ${folder}/:`,
    notesList,
    ``,
    `=== YOUR JOB THIS ITERATION ===`,
    `Study ONE specific aspect of this project. Read 1-3 files to understand how something works, then write a focused note about it.`,
    ``,
    `Suggested note topics (pick whichever hasn't been covered yet):`,
    `  • Project overview — what it is, what it does, tech stack`,
    `  • Architecture — how the codebase is organized, key directories`,
    `  • Entry points — main files, how the app starts/runs`,
    `  • Key components — major modules, classes, or functions and what they do`,
    `  • Data flow — how data moves through the system`,
    `  • Configuration — env vars, config files, settings`,
    `  • Dependencies — key libraries/frameworks and why they're used`,
    `  • API / endpoints — routes, handlers, request/response shapes`,
    `  • State management — how state is stored, updated, persisted`,
    `  • Build & deploy — how to build, test, run, deploy`,
    `  • Patterns & conventions — code style, naming, recurring patterns`,
    `  • Edge cases & gotchas — tricky parts, workarounds, known issues`,
    ``,
    `Available actions:`,
    `  • [FILE_READ: <file path>] — read a project file to understand it`,
    `  • [VAULT_READ: <path>] — review what you've already written`,
    `  • [VAULT_NEW: ${folder}/<descriptive-slug>.md]\\n# <title>\\n\\n<focused note>\\n[/VAULT_NEW] — write a new note`,
    `  • [VAULT_APPEND: <path>]\\n<content>\\n[/VAULT_APPEND] — add to an existing note`,
    ``,
    `Rules:`,
    `  - Read 1-3 project files, then write ONE focused note. Don't try to document everything at once.`,
    `  - Use frontmatter: ---\\ntags: [project-study, ${mission.projectName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}]\\n---`,
    `  - Wikilink to other notes you've written ([[other-note]]) to build a connected knowledge graph.`,
    `  - Include code snippets with \`\`\` fences when they clarify how something works.`,
    `  - Focus on the WHY and HOW, not just listing what exists. Explain design decisions if apparent.`,
    `  - End your reply with: "Documented X. Next iteration could explore Y."`,
  ];

  if (mission.allowSelfComplete) {
    lines.push(
      `  - ONLY if you've thoroughly documented ALL major aspects AND completed at least ${Math.floor(totalIters * 0.6)} iterations, write a final ${folder}/_index.md (table of contents linking all notes) and emit [MISSION_COMPLETE].`
    );
  } else {
    lines.push(
      `  - Do NOT try to "complete" early. Go DEEPER: add code examples, edge cases, sequence diagrams (mermaid), comparison tables, configuration reference, or troubleshooting guides.`
    );
  }
  return lines.join('\n');
}

/* Build the per-iteration research prompt. The agent sees what it's
   already written + what time/iteration we're on, and is asked to do
   ONE focused action this turn — emphasis on ONE so the work spreads
   across the full duration of the mission rather than getting crammed
   into iteration 1. */
function buildResearchPrompt(mission, agent, notesIndex) {
  const elapsedMin = Math.round((Date.now() - mission.startedAt) / MIN);
  const remainingMin = Math.max(0, Math.round((mission.startedAt + mission.durationMs - Date.now()) / MIN));
  const folder = mission.vaultFolder;
  const totalIters = Math.max(1, Math.round(mission.durationMs / mission.intervalMs));
  const notesList = (notesIndex && notesIndex.length)
    ? notesIndex.slice(0, 20).map(n => `  - ${n.path}${n.title ? ` (${n.title})` : ''}`).join('\n')
    : '  (none yet)';

  const lines = [
    `You are on a long-running research mission. The host runs you on a fixed schedule; pacing matters.`,
    ``,
    `TOPIC: ${mission.topic}`,
    `ITERATION: ${mission.iterations + 1} of ~${totalIters} planned`,
    `TIME: ${elapsedMin}m elapsed · ${remainingMin}m remaining`,
    `VAULT FOLDER: ${folder}/`,
    ``,
    `Notes already written under ${folder}/:`,
    notesList,
    ``,
    `=== YOUR JOB THIS ITERATION ===`,
    `Do EXACTLY ONE new search-and-write cycle. Pick a single angle you haven't covered yet, search for it, and write a focused note. Do not try to cover the whole topic — there are ~${totalIters} iterations planned, so leave plenty for future runs.`,
    ``,
    `Available actions (use ONE, max two):`,
    `  • [SEARCH: <specific query>] — query the web for a NEW angle. Be specific.`,
    `  • [VAULT_READ: <path>] — review what you've already written.`,
    `  • [VAULT_NEW: ${folder}/<descriptive-slug>.md]\\n# <title>\\n\\n<focused note>\\n[/VAULT_NEW] — write a new focused note`,
    `  • [VAULT_APPEND: <path>]\\n<content>\\n[/VAULT_APPEND] — extend an existing note`,
    ``,
    `Rules:`,
    `  - ONE search → ONE note. Don't chain multiple searches in a single iteration.`,
    `  - Don't repeat searches you've already run. Don't re-write notes you've already written.`,
    `  - Use frontmatter (---\\ntags: [research]\\n---) on new notes so they integrate with Obsidian.`,
    `  - Wikilink to other notes you've written ([[other-note]]) to build the graph.`,
    `  - End your reply with a plain-text status line: "Wrote X. Next iteration could explore Y."`,
  ];

  if (mission.allowSelfComplete) {
    lines.push(
      `  - ONLY if you've genuinely exhausted ALL new angles AND completed at least ${Math.floor(totalIters * 0.6)} iterations, write a final ${folder}/_index.md and emit [MISSION_COMPLETE]. Otherwise keep going.`
    );
  } else {
    lines.push(
      `  - Do NOT try to "complete" the mission early. The boss has set a fixed schedule; the time budget is the only stop condition. If you feel you've covered the obvious angles, dig DEEPER on the existing ones (case studies, code examples, edge cases, common pitfalls, comparison tables, monitoring/operations) instead of declaring done.`
    );
  }
  return lines.join('\n');
}

/* Match an iteration's response for a self-declared completion signal.
   Only honored when the mission was started with allowSelfComplete=true.
   Belt-and-suspenders against the agent emitting the marker even when
   we asked it not to. */
function isMissionComplete(text) {
  return /\[\s*MISSION_COMPLETE\s*\]/i.test(String(text || ''));
}

/* ==========================================================================
   Mission runner

   Single-iteration: build prompt, stream agent, read returned tool events,
   note new files written, advance state. Errors don't kill the mission;
   3 in a row triggers an auto-pause.
   ========================================================================== */
async function runMissionIteration(ctx) {
  const { mission, agent, setMissions, setChat, appendJournal, onUpdateAgent, pulseGraph, signal } = ctx;
  const startedThisRun = Date.now();

  /* Read the current vault index for this folder so the agent knows
     what's already there. Cheap call (just file list). */
  let notesIndex = [];
  try {
    const all = await window.CafresoHQClient.vaultList();
    const prefix = mission.vaultFolder + '/';
    notesIndex = all
      .filter(f => f.path.startsWith(prefix))
      .sort((a, b) => (b.mtime || 0) - (a.mtime || 0))
      .map(f => ({ path: f.path, title: f.title }));
  } catch (_e) {}

  /* For project-study missions, also fetch the project file tree so the
     agent knows what files are available to read. */
  let fileTree = [];
  if (mission.type === 'project-study' && mission.projectPath) {
    try {
      const res = await fetch('/tools/exec', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ tool: 'DIR_LIST', arg: mission.projectPath }),
      });
      const data = await res.json();
      if (data.ok) {
        fileTree = String(data.result || '').split('\n').filter(Boolean).map(line => {
          const isDir = line.endsWith('/') || line.endsWith('\\');
          const name = line.replace(/[\\/]+$/, '');
          return { name, isDir };
        });
      }
    } catch (_e) {}
  }

  const prompt = mission.type === 'project-study'
    ? buildProjectStudyPrompt(mission, agent, notesIndex, fileTree)
    : buildResearchPrompt(mission, agent, notesIndex);

  /* Insert a marker message into chat (Research thread) so the user can
     scroll the mission timeline separately from team chatter and direct
     chat. Each mission iteration is its own message; they all share the
     'research' thread so the user can read the whole research feed. */
  const msgId = HQ.uid('m');
  setChat(prev => [...prev, {
    id: msgId,
    from: 'agent',
    name: `${agent.name} · iter ${mission.iterations + 1} · ${mission.topic.slice(0, 40)}${mission.topic.length > 40 ? '…' : ''}`,
    text: '', streaming: true,
    thread: 'research',
    missionId: mission.id,
  }]);

  const flush = HQ.throttleTokens(setChat, msgId);
  let buf = '';
  let usedTokens = 0;
  let writesThisIter = [];

  try {
    await HQ.agentStream(agent, prompt, tok => { buf += tok; flush(tok); }, {
      onUsage: u => { usedTokens = u.total || 0; },
      onHint: flush.note,
      onTool: ev => {
        if (ev.phase === 'done') {
          if (ev.name === 'VAULT_NEW' || ev.name === 'VAULT_APPEND') {
            writesThisIter.push({ name: ev.name, path: String(ev.arg || '').trim(), at: Date.now() });
          }
          if (ev.name === 'FILE_READ') {
            writesThisIter.push({ name: 'FILE_READ', path: String(ev.arg || '').trim(), at: Date.now() });
          }
          pulseGraph && pulseGraph(ev);
        } else if (ev.phase === 'start') {
          pulseGraph && pulseGraph(ev);
        }
      },
      // No peers — missions are solo work, no DM noise.
      peers: [],
      // Per-iteration budget: 4 hops + 2048 max_tokens. 4 hops fits one
      // SEARCH + one VAULT_NEW with room for a follow-up search if needed,
      // but stops a single iteration from devouring the whole topic in one
      // go (which used to leave nothing for the remaining iterations).
      maxTokens: 2048,
      maxToolHops: 4,
      signal,
    });
    flush.flushNow();
  } catch (err) {
    const aborted = err && err.name === 'AbortError';
    flush.cancel();
    if (aborted) {
      // Stop / pause / unmount path. Don't count this against the error
      // streak — the user (or app shutdown) deliberately killed it.
      setChat(prev => prev.map(m => m.id === msgId
        ? { ...m, text: ((m.text || '') + ' …(stopped)'), streaming: false }
        : m));
      return { ok: false, aborted: true };
    }
    setChat(prev => prev.map(m => m.id === msgId
      ? { ...m, text: `⚠ Mission iteration failed: ${err.message}`, error: true, streaming: false }
      : m));
    setMissions(prev => prev.map(x => x.id === mission.id
      ? { ...x, errors: (x.errors || 0) + 1, lastError: err.message }
      : x));
    return { ok: false };
  }

  setChat(prev => prev.map(m => m.id === msgId ? { ...m, streaming: false } : m));

  const cleaned = HQ.cleanHarmony(buf);
  /* Self-completion is OFF by default. When a mission has it enabled, we
     also require the agent to have actually run a meaningful number of
     iterations — at least 60% of the planned schedule — before honoring
     the marker. Otherwise an over-eager model can collapse a 1-hour
     research session into iteration 1. */
  const totalPlanned = Math.max(1, Math.round(mission.durationMs / mission.intervalMs));
  const minBeforeComplete = Math.floor(totalPlanned * 0.6);
  const completed = mission.allowSelfComplete
    && isMissionComplete(cleaned)
    && (mission.iterations + 1) >= minBeforeComplete;

  /* Update agent stats + journal so the mission's work shows up in the
     usual surfaces too. */
  onUpdateAgent(agent.id, {
    status: 'active', mood: 'done',
    recent: cleaned.slice(0, 140) || `mission iter ${mission.iterations + 1}`,
    tokens: (agent.tokens || 0) + usedTokens,
    tasksDone: (agent.tasksDone || 0) + 1,
    task: 'on mission',
  });
  if (cleaned.trim()) {
    appendJournal(agent.id, cleaned, `mission · ${mission.topic.slice(0, 40)}`);
  }

  setMissions(prev => prev.map(x => x.id === mission.id ? {
    ...x,
    iterations: x.iterations + 1,
    lastIterationAt: startedThisRun,
    lastAction: cleaned.slice(0, 160),
    notesWritten: [...(x.notesWritten || []), ...writesThisIter],
    tokensUsed: (x.tokensUsed || 0) + usedTokens,
    errors: 0, // streak reset on success
    status: completed ? 'done' : x.status,
  } : x));

  return { ok: true, completed };
}

/* ==========================================================================
   Live mission loop. One per running mission. Owned by the host App.

   The loop is a chain of setTimeouts, so iterations never overlap and the
   user can stop cleanly via clearTimeout. We hold the timer id in a ref
   keyed by mission id.
   ========================================================================== */
function useMissionRunner(missions, setMissions, ctx) {
  const timersRef = useRMission({});    // { missionId: timeoutId }
  const runningRef = useRMission({});   // { missionId: true } guards against double-fires
  const abortersRef = useRMission({});  // { missionId: AbortController } — lets stop/pause kill in-flight fetches

  /* Inject setMissions into the ctx so runMissionIteration (and the runner's
     own status updates) can see it. Earlier this wasn't threaded through and
     iterations failed to record their results — leaving mission state
     frozen and no follow-up iteration ever scheduled. */
  const ctxWithSetters = { ...ctx, setMissions };

  useEMission(() => {
    /* Cancel timers + abort in-flight streams for missions that have left
       running state (paused, done, or removed). Without the abort, hitting
       STOP mid-iteration only stops the NEXT iteration from being scheduled
       — the current fetch keeps draining tokens until the model finishes. */
    for (const id of Object.keys(timersRef.current)) {
      const m = missions.find(x => x.id === id);
      if (!m || m.status !== 'running') {
        clearTimeout(timersRef.current[id]);
        delete timersRef.current[id];
      }
    }
    for (const id of Object.keys(abortersRef.current)) {
      const m = missions.find(x => x.id === id);
      if (!m || m.status !== 'running') {
        try { abortersRef.current[id].abort(); } catch (_e) {}
        delete abortersRef.current[id];
      }
    }

    /* Schedule each running mission. Don't reschedule if a timer is
       already pending for it. */
    for (const m of missions) {
      if (m.status !== 'running') continue;
      if (timersRef.current[m.id]) continue;

      /* Time-budget check: stop if we've blown past the duration. */
      const deadline = m.startedAt + m.durationMs;
      if (Date.now() >= deadline) {
        setMissions(prev => prev.map(x => x.id === m.id ? { ...x, status: 'done' } : x));
        continue;
      }

      /* Three errors in a row → auto-pause so we don't burn cycles on
         a busted backend. */
      if ((m.errors || 0) >= 3) {
        setMissions(prev => prev.map(x => x.id === m.id ? { ...x, status: 'paused', lastError: x.lastError || 'too many errors' } : x));
        continue;
      }

      /* First iteration runs ~1s after start so the modal can render
         and the user sees activity. Subsequent iterations honor interval. */
      const fireIn = m.iterations === 0 ? 1000 : m.intervalMs;

      timersRef.current[m.id] = setTimeout(async () => {
        delete timersRef.current[m.id];
        if (runningRef.current[m.id]) return;
        runningRef.current[m.id] = true;
        const controller = new AbortController();
        abortersRef.current[m.id] = controller;
        try {
          /* Re-read the latest mission state in case user paused while we
             were waiting. */
          const latest = (ctxWithSetters.missionsRef && ctxWithSetters.missionsRef.current
            ? ctxWithSetters.missionsRef.current
            : missions).find(x => x.id === m.id);
          if (!latest || latest.status !== 'running') return;
          const agent = ctxWithSetters.agentsRef.current.find(a => a.id === latest.agentId);
          if (!agent) {
            setMissions(prev => prev.map(x => x.id === m.id ? { ...x, status: 'error', lastError: 'agent removed' } : x));
            return;
          }
          await runMissionIteration({ ...ctxWithSetters, mission: latest, agent, signal: controller.signal });
        } catch (err) {
          /* Bug-of-bugs: anything thrown by runMissionIteration after the
             agentStream try/catch (e.g., a missing dependency) used to
             vanish into an unhandled rejection and freeze the mission.
             Now we surface it explicitly. AbortError is intentional and
             shouldn't count against the error streak. */
          if (err && err.name === 'AbortError') return;
          console.error('[mission] iteration error:', err);
          setMissions(prev => prev.map(x => x.id === m.id ? { ...x,
            errors: (x.errors || 0) + 1,
            lastError: err && err.message ? err.message : String(err),
          } : x));
        } finally {
          runningRef.current[m.id] = false;
          if (abortersRef.current[m.id] === controller) delete abortersRef.current[m.id];
        }
      }, fireIn);
    }
  }, [missions]);

  /* Unmount: clear all timers + abort all in-flight fetches so a tab
     navigation doesn't leak streams that keep draining the API quota. */
  useEMission(() => () => {
    for (const id of Object.keys(timersRef.current)) clearTimeout(timersRef.current[id]);
    for (const id of Object.keys(abortersRef.current)) {
      try { abortersRef.current[id].abort(); } catch (_e) {}
    }
    timersRef.current = {};
    abortersRef.current = {};
  }, []);
}

/* ==========================================================================
   Night Shift (Sprint 4 MVP-1) — server-side scheduled missions.

   Unlike the browser loop above, these run inside serve.py (night_runner.py)
   on a restricted tool subset (vault/read/search/fetch — no wallet, publish,
   or shell), so they keep working after the tab closes. This section is the
   scheduling UI: create schedules, list them, show the run history the
   Gazette also ingests.
   ========================================================================== */
const nsBase = () => {
  try { return window.CafresoHQClient.backendBase() || ''; } catch (_e) { return ''; }
};
const nsFetch = (path, opts) =>
  fetch(nsBase() + path, { credentials: 'include', ...(opts || {}) }).then(r => r.json());

/* Next occurrence of 2:00 AM local — the canonical "tonight". */
function nextTwoAm() {
  const d = new Date();
  d.setHours(2, 0, 0, 0);
  if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
  return d;
}
const toLocalInput = (d) => {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

function NightShiftSection({ agents }) {
  const [schedules, setSchedules] = useSM([]);
  const [running, setRunning] = useSM([]);
  const [runs, setRuns] = useSM([]);
  const [reachable, setReachable] = useSM(true);
  const [topic, setTopic] = useSM('');
  const [agentId, setAgentId] = useSM(() => (agents.find(a => (a.tools || []).includes('vault')) || agents[0] || {}).id || '');
  const [folder, setFolder] = useSM('');
  const [startStr, setStartStr] = useSM(() => toLocalInput(nextTwoAm()));
  const [recurrence, setRecurrence] = useSM('once');
  const [duration, setDuration] = useSM(1 * HOUR);
  const [interval, setNsInterval] = useSM(10 * MIN);
  const [msg, setMsg] = useSM('');

  const load = async () => {
    try {
      const [s, r] = await Promise.all([nsFetch('/missions/scheduled'), nsFetch('/missions/runs')]);
      setSchedules(s.schedules || []); setRunning(s.running || []);
      setRuns((r.runs || []).slice(-5).reverse());
      setReachable(true);
    } catch (_e) { setReachable(false); }
  };
  useEMission(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, []);

  const schedule = async (startAtMs) => {
    const ag = agents.find(a => a.id === agentId);
    if (!topic.trim() || !ag) { setMsg('topic + agent required'); return; }
    setMsg('');
    try {
      const res = await nsFetch('/missions/schedule', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          topic: topic.trim(), agentId: ag.id, agentName: ag.name,
          vaultFolder: folder.trim() || `Research/${topicSlug(topic)}`,
          startAt: startAtMs, recurrence, durationMs: duration, intervalMs: interval,
        }),
      });
      if (res.error) { setMsg(res.error); return; }
      setTopic(''); setMsg('Scheduled 🌙 — runs even with this tab closed.');
      load();
    } catch (e) { setMsg(String(e.message || e)); }
  };
  const cancel = async (id) => {
    try { await fetch(nsBase() + `/missions/scheduled/${id}`, { method: 'DELETE', credentials: 'include' }); load(); }
    catch (_e) {}
  };

  const fmtT = (ms) => ms ? new Date(ms).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
  if (!reachable) {
    return (
      <div style={{ marginTop: 14 }}>
        <div className="missions-section-title">🌙 NIGHT SHIFT</div>
        <div className="hint">Container backend unreachable — night shift needs a running HQ container.</div>
      </div>
    );
  }
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ borderTop: '1px dashed var(--ink-3)', margin: '14px 0' }} />
      <div className="missions-section-title">🌙 NIGHT SHIFT · runs in the container — close the laptop, work continues</div>

      {schedules.length > 0 && (
        <div className="missions-list" style={{ marginTop: 8 }}>
          {schedules.map(s => (
            <div key={s.id} className="mission-card status-running">
              <div className="mc-head">
                <div className="mc-title">🌙 {s.topic}</div>
                <span className="mc-status">{running.includes(s.id) ? 'RUNNING NOW' : s.enabled ? 'SCHEDULED' : 'DONE'}</span>
              </div>
              <div className="mc-meta">
                <span><b>{s.agentName || s.agentId}</b> · {s.vaultFolder}/</span>
                <span>{s.recurrence === 'daily' ? 'daily' : 'once'} · {Math.round(s.durationMs / MIN)}m @ {Math.round(s.intervalMs / MIN)}m</span>
                <span>{s.enabled ? `next: ${fmtT(s.nextRunAt)}` : `last: ${fmtT(s.lastRunAt)}`}</span>
              </div>
              <div className="mc-actions">
                <button className="px-btn danger" style={{ fontSize: 9 }} onClick={() => cancel(s.id)}>✕ CANCEL</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="form-grid" style={{ marginTop: 8 }}>
        <div className="form-row full">
          <label>TOPIC</label>
          <input value={topic} onChange={e => setTopic(e.target.value)} placeholder="what should get researched overnight?" />
        </div>
        <div className="form-row">
          <label>AGENT</label>
          <select value={agentId} onChange={e => setAgentId(e.target.value)}>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name} · {a.role}</option>)}
          </select>
        </div>
        <div className="form-row">
          <label>VAULT FOLDER</label>
          <input value={folder} onChange={e => setFolder(e.target.value)} placeholder={`Research/${topicSlug(topic) || '<topic>'}`} />
        </div>
        <div className="form-row">
          <label>STARTS</label>
          <input type="datetime-local" value={startStr} onChange={e => setStartStr(e.target.value)} />
          <span className="hint">defaults to tonight 2:00 AM</span>
        </div>
        <div className="form-row">
          <label>REPEAT</label>
          <select value={recurrence} onChange={e => setRecurrence(e.target.value)}>
            <option value="once">once</option>
            <option value="daily">every night</option>
          </select>
        </div>
        <div className="form-row">
          <label>DURATION</label>
          <select value={duration} onChange={e => setDuration(parseInt(e.target.value))}>
            {DURATION_PRESETS.filter(p => p.ms >= 30 * MIN).map(p => <option key={p.label} value={p.ms}>{p.label}</option>)}
          </select>
        </div>
        <div className="form-row">
          <label>INTERVAL</label>
          <select value={interval} onChange={e => setNsInterval(parseInt(e.target.value))}>
            {[5, 10, 20].map(m => <option key={m} value={m * MIN}>every {m} min</option>)}
          </select>
          <span className="hint">{Math.round(duration / interval)} iterations · night tools only (no wallet/publish/shell)</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
        <button className="px-btn primary" style={{ fontSize: 9 }}
          onClick={() => schedule(new Date(startStr).getTime() || 0)}>🌙 SCHEDULE</button>
        <button className="px-btn secondary" style={{ fontSize: 9 }}
          onClick={() => schedule(0)} title="starts within ~30s on the next scheduler scan">▶ RUN NOW</button>
        {msg && <span className="hint">{msg}</span>}
      </div>

      {runs.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="missions-section-title">RECENT NIGHT RUNS</div>
          {runs.map(r => (
            <div key={r.id} className="hint" style={{ marginTop: 3 }}>
              {r.lastError ? '⚠' : '✓'} {fmtT(r.startedAt)} · <b>{r.agentName || r.agentId}</b> · {r.topic.slice(0, 40)} ·
              {' '}{r.iterations} iter · {(r.writes || []).length} note{(r.writes || []).length === 1 ? '' : 's'}
              {r.lastError ? ` · ${String(r.lastError).slice(0, 60)}` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ==========================================================================
   UI: MissionsModal — start a mission + show live progress on active ones
   ========================================================================== */
function MissionsModal({ open, onClose, agents, missions, onStart, onStop, onResume, onClear, projects }) {
  const [mode, setMode] = useSM('research'); // 'research' | 'project-study'
  const [topic, setTopic] = useSM('');
  const [projectId, setProjectId] = useSM('');
  const [agentId, setAgentId] = useSM(() => agents.find(a => (a.tools||[]).includes('web') && (a.tools||[]).includes('vault'))?.id || agents[0]?.id || '');
  const [duration, setDuration] = useSM(2 * HOUR);
  const [interval, setInterval_] = useSM(5 * MIN);
  const [folder, setFolder] = useSM('');
  const [allowSelfComplete, setAllowSelfComplete] = useSM(false);
  // A project is studyable if it has a local filesystem path — that's true for
  // both folder-added projects (source 'local') and cloned GitHub repos
  // (source 'github:<url>'), since the agent reads files via the container's
  // DIR_LIST/FILE_READ on `projectPath`. NOTE: the old check `p.type === 'local'`
  // never matched — projects carry `source`, not `type`, so this list was always
  // empty and the STUDY PROJECT dropdown never populated.
  const localProjects = (projects || []).filter(p => p && p.path);
  const selectedProject = localProjects.find(p => p.id === projectId);
  /* Elevated agents are locked out of missions unless the operator explicitly
     authorizes unattended computer access. Resets whenever the picked agent
     changes so authorization can't silently carry over to a new pick. */
  const [elevatedAuth, setElevatedAuth] = useSM(false);
  useEMission(() => { setElevatedAuth(false); }, [agentId]);
  const selectedAgent = agents.find(a => a.id === agentId);
  const isElevated = !!(selectedAgent && selectedAgent.elevated);
  /* Tick once per second so the next-iteration countdown ticks live while
     this modal is open. We don't need the tick when closed. */
  const [, setTick] = useSM(0);
  useEMission(() => {
    if (!open) return;
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, [open]);

  if (!open) return null;

  const fmtTime = (ms) => {
    if (ms < MIN) return Math.round(ms / 1000) + 's';
    if (ms < HOUR) return Math.round(ms / MIN) + 'm';
    return (ms / HOUR).toFixed(1).replace(/\.0$/, '') + 'h';
  };
  const fmtRemaining = (m) => {
    const left = m.startedAt + m.durationMs - Date.now();
    return left > 0 ? fmtTime(left) + ' left' : 'time up';
  };
  const submit = () => {
    if (isElevated && !elevatedAuth) return;
    if (mode === 'project-study') {
      if (!projectId || !agentId) return;
      const proj = localProjects.find(p => p.id === projectId);
      if (!proj) return;
      const projSlug = topicSlug(proj.name);
      const folderClean = (folder.trim() || `Projects/${projSlug}`).replace(/^\/+|\/+$/g, '');
      onStart({
        id: 'msn_' + Math.random().toString(36).slice(2, 9),
        type: 'project-study',
        agentId,
        topic: `Study: ${proj.name}`,
        projectId: proj.id,
        projectName: proj.name,
        projectPath: proj.path,
        vaultFolder: folderClean,
        startedAt: Date.now(),
        durationMs: duration,
        intervalMs: interval,
        iterations: 0,
        status: 'running',
        lastAction: '',
        notesWritten: [],
        tokensUsed: 0,
        errors: 0,
        allowSelfComplete,
        elevatedAuthorized: isElevated ? true : false,
      });
      setProjectId('');
      setFolder('');
      setElevatedAuth(false);
    } else {
      if (!topic.trim() || !agentId) return;
      const folderClean = (folder.trim() || `Research/${topicSlug(topic)}`).replace(/^\/+|\/+$/g, '');
      onStart({
        id: 'msn_' + Math.random().toString(36).slice(2, 9),
        type: 'research',
        agentId,
        topic: topic.trim(),
        vaultFolder: folderClean,
        startedAt: Date.now(),
        durationMs: duration,
        intervalMs: interval,
        iterations: 0,
        status: 'running',
        lastAction: '',
        notesWritten: [],
        tokensUsed: 0,
        errors: 0,
        allowSelfComplete,
        elevatedAuthorized: isElevated ? true : false,
      });
      setTopic('');
      setElevatedAuth(false);
    }
  };

  const hasVaultAndWeb = (a) => {
    const t = new Set(a.tools || []);
    return t.has('web') && t.has('vault');
  };
  const hasVault = (a) => (a.tools || []).includes('vault');
  const canDoMode = (a) => mode === 'project-study' ? hasVault(a) : hasVaultAndWeb(a);

  return (
    <OcModalM
      open={open}
      onClose={onClose}
      title="🔬 RESEARCH"
      subtitle="long-running research or project study → vault notes"
      size="lg"
    >

          {/* --- Active missions list --- */}
          {missions.length > 0 && (
            <div className="missions-active">
              <div className="missions-section-title">ACTIVE RESEARCH · {missions.filter(m=>m.status==='running').length} running · {missions.length} total</div>
              <div className="missions-list">
                {missions.map(m => {
                  const ag = agents.find(a => a.id === m.agentId);
                  const writes = (m.notesWritten || []).length;
                  /* "next iteration in" countdown: anchored to the last
                     iteration's completion time + intervalMs. If we
                     haven't run any yet, anchor to startedAt. */
                  let nextLabel = '';
                  if (m.status === 'running') {
                    const anchor = m.lastIterationAt || m.startedAt;
                    const next = anchor + m.intervalMs;
                    const ago = m.lastIterationAt ? Math.max(0, Date.now() - m.lastIterationAt) : null;
                    const dt = next - Date.now();
                    if (m.iterations === 0) {
                      nextLabel = 'first iteration starting…';
                    } else if (dt <= 0) {
                      nextLabel = 'next iteration any moment now…';
                    } else {
                      nextLabel = `next in ${fmtTime(dt)}` + (ago !== null ? ` · last ran ${fmtTime(ago)} ago` : '');
                    }
                  }
                  return (
                    <div key={m.id} className={`mission-card status-${m.status}`}>
                      <div className="mc-head">
                        {ag && <Sprite data={ag.color} scale={1.5}/>}
                        <div className="mc-title">
                          {m.type === 'project-study' && <span style={{fontSize:9,opacity:0.7,marginRight:4}}>📂</span>}
                          {m.topic}
                        </div>
                        <span className={`mc-status status-${m.status}`}>{m.status.toUpperCase()}</span>
                      </div>
                      <div className="mc-meta">
                        <span><b>{ag ? ag.name : '(unknown)'}</b> · {m.vaultFolder}/</span>
                        <span>iter {m.iterations} · {writes} note{writes===1?'':'s'} · {(m.tokensUsed||0).toLocaleString()} tok</span>
                        <span>
                          {m.status === 'running' ? fmtRemaining(m) :
                           m.status === 'paused' ? 'paused' :
                           m.status === 'done' ? 'completed' :
                           'error'}
                        </span>
                      </div>
                      {nextLabel && <div className="mc-next">⏳ {nextLabel}</div>}
                      {m.lastAction && <div className="mc-last">last: {m.lastAction.slice(0, 200)}{m.lastAction.length > 200 ? '…' : ''}</div>}
                      {m.lastError && <div className="mc-err">⚠ {m.lastError.slice(0, 200)}</div>}
                      <div className="mc-actions">
                        {m.status === 'running' && <button className="px-btn danger" style={{fontSize:9}} onClick={()=>onStop(m.id)}>■ STOP</button>}
                        {m.status === 'paused' && <button className="px-btn primary" style={{fontSize:9}} onClick={()=>onResume(m.id)}>▶ RESUME</button>}
                        {(m.status === 'done' || m.status === 'paused' || m.status === 'error') && (
                          <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>onClear(m.id)}>CLEAR</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{borderTop:'1px dashed var(--ink-3)', margin:'14px 0'}}/>
            </div>
          )}

          {/* --- Start form --- */}
          <div className="missions-section-title">START A NEW MISSION</div>
          <div style={{display:'flex',gap:4,marginTop:8,marginBottom:12}}>
            <button className={`px-btn ${mode==='research'?'primary':'secondary'}`} style={{fontSize:8,flex:1}}
              onClick={()=>setMode('research')}>🔬 RESEARCH</button>
            <button className={`px-btn ${mode==='project-study'?'primary':'secondary'}`} style={{fontSize:8,flex:1}}
              onClick={()=>setMode('project-study')}>📂 STUDY PROJECT</button>
          </div>
          <div className="form-grid">
            {mode === 'research' ? (
              <div className="form-row full">
                <label>TOPIC</label>
                <input value={topic} onChange={e=>setTopic(e.target.value)}
                  placeholder="e.g. Internet Computer Protocol token economics" autoFocus/>
                <span className="hint">be specific — vague topics lead to vague notes</span>
              </div>
            ) : (
              <div className="form-row full">
                <label>PROJECT</label>
                <select value={projectId} onChange={e=>setProjectId(e.target.value)}>
                  <option value="">— select a local project —</option>
                  {localProjects.map(p => (
                    <option key={p.id} value={p.id}>{p.name} — {p.path}</option>
                  ))}
                </select>
                <span className="hint">
                  {localProjects.length === 0
                    ? 'no local projects added yet — add one in the Projects tab first'
                    : 'agent will read project files and write structured notes about how it works'}
                </span>
              </div>
            )}
            <div className="form-row">
              <label>AGENT</label>
              <select value={agentId} onChange={e=>setAgentId(e.target.value)}>
                {agents.map(a => (
                  <option key={a.id} value={a.id} disabled={!canDoMode(a)}>
                    {a.elevated ? '🛡 ' : ''}{a.name} · {a.role}{!canDoMode(a) ? (mode === 'project-study' ? ' (needs Vault tool)' : ' (needs Web + Vault tools)') : ''}
                  </option>
                ))}
              </select>
              <span className="hint">{mode === 'project-study' ? 'must have Vault Notes tool enabled' : 'must have Web Search and Vault Notes tools enabled'}</span>
            </div>
            <div className="form-row">
              <label>VAULT FOLDER</label>
              <input value={folder} onChange={e=>setFolder(e.target.value)}
                placeholder={mode === 'project-study'
                  ? `Projects/${selectedProject ? topicSlug(selectedProject.name) : '<project>'}`
                  : `Research/${topicSlug(topic) || '<topic>'}`}/>
              <span className="hint">all notes get written here; defaults to {mode === 'project-study' ? 'Projects' : 'Research'}/&lt;slug&gt;</span>
            </div>
            <div className="form-row">
              <label>DURATION</label>
              <select value={duration} onChange={e=>setDuration(parseInt(e.target.value))}>
                {DURATION_PRESETS.map(p => <option key={p.label} value={p.ms}>{p.label}</option>)}
              </select>
            </div>
            <div className="form-row">
              <label>INTERVAL</label>
              <select value={interval} onChange={e=>setInterval_(parseInt(e.target.value))}>
                {INTERVAL_PRESETS.map(p => <option key={p.label} value={p.ms}>{p.label}</option>)}
              </select>
              <span className="hint">{Math.round(duration / interval)} iterations total</span>
            </div>
            <div className="form-row full">
              <label>EARLY STOP</label>
              <label style={{display:'flex',alignItems:'center',gap:8,fontFamily:'VT323',fontSize:16,cursor:'pointer'}}>
                <input type="checkbox" checked={allowSelfComplete} onChange={e=>setAllowSelfComplete(e.target.checked)}/>
                Allow agent to declare the mission complete before time is up
              </label>
              <span className="hint">
                {allowSelfComplete
                  ? `agent may emit [MISSION_COMPLETE] after ~${Math.floor((duration/interval) * 0.6)} iterations if all angles feel covered`
                  : `agent runs until time elapses; deeper coverage instead of finishing early`}
              </span>
            </div>
            {isElevated && (
              <div className="form-row full elevated-opt on">
                <label style={{color:'#c44'}}>🛡 ELEVATED</label>
                <label style={{display:'flex',alignItems:'flex-start',gap:8,fontFamily:'VT323',fontSize:16,cursor:'pointer',lineHeight:1.3}}>
                  <input type="checkbox" checked={elevatedAuth} onChange={e=>setElevatedAuth(e.target.checked)} style={{marginTop:3}}/>
                  <span>
                    <b style={{color:'#c44'}}>Authorize {selectedAgent.name} for unattended computer access</b><br/>
                    <span className="hint" style={{display:'block',marginTop:2}}>
                      This mission runs for {fmtTime(duration)} ({Math.round(duration/interval)} iterations). During that window
                      {' '}<b>{selectedAgent.name}</b> may read/write files and run shell commands on this computer without per-action approval.
                      Only check this if you trust the topic + the agent's prompt.
                    </span>
                  </span>
                </label>
              </div>
            )}
          </div>
          <div className="hint" style={{marginTop: 'var(--sp-5)'}}>
            ⚠ <strong>Keep this tab open</strong> — this loop runs in the browser. Closing the tab stops the mission.
            Prevent your laptop from sleeping for the duration. Each iteration uses real LLM tokens — pin a strong model
            (claudecode:sonnet / claude-haiku / llama-3.3-70b) on the agent for best results.
            For work that should continue with the tab CLOSED, schedule a 🌙 Night Shift below instead.
          </div>

          <NightShiftSection agents={agents} />
          {/* Footer is now rendered by the Modal shell — but in this design the
              start button + summary live near the form, so we keep them inline. */}
          <div style={{
            display:'flex',
            alignItems:'center',
            justifyContent:'flex-end',
            gap:'var(--sp-4)',
            marginTop:'var(--sp-5)',
            paddingTop:'var(--sp-4)',
            borderTop:'1px dashed var(--rule)',
          }}>
            <div className="hint" style={{marginRight:'auto'}}>{
              mode === 'project-study'
                ? (projectId ? `${Math.round(duration / interval)} iterations × file reads + vault writes${isElevated ? ' · 🛡 elevated agent' : ''}` : 'select a project to start')
                : (topic.trim() ? `${Math.round(duration / interval)} iterations × ~3 LLM calls each${isElevated ? ' · 🛡 elevated agent' : ''}` : 'enter a topic to start')
            }</div>
            <button className="px-btn primary" onClick={submit}
              disabled={mode === 'project-study' ? (!projectId || !agentId || (isElevated && !elevatedAuth)) : (!topic.trim() || !agentId || (isElevated && !elevatedAuth))}
              title={isElevated && !elevatedAuth ? 'Tick the elevated authorization checkbox first' : ''}>
              {mode === 'project-study' ? '▶ START STUDY' : '▶ START RESEARCH'}
            </button>
          </div>
    </OcModalM>
  );
}

window.CafresoHQMissions = {
  MissionsModal, useMissionRunner, runMissionIteration, MIN, HOUR,
};

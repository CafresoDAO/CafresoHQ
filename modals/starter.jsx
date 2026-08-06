import { Sprite } from '../sprites.jsx';
import { Modal } from './base.jsx';
const { useState: useStateS, useEffect: useEffectS, useRef: useRefS } = React;

/* ── Starter tasks (OFFICE_AS_INTERFACE §3 step 4) ────────────────────────
   The beat right after the first hire: three real outcomes instead of a
   blank prompt box. Each card asks for exactly ONE thing — the subject —
   and turns it into a normal task, dispatched down the same path as
   dragging a card onto a desk. Nothing here is a special case: what the
   coworker receives is a task brief like any other.

   Copy follows the jargon table (§6) — assignments and deliverables, never
   prompts or tokens. Honesty rule: `build` adapts to what the coworker can
   actually DO. Filing to the cabinet is only promised when they hold vault
   access; otherwise the deliverable comes back in the reply, which is a
   real outcome we can always keep. */
const STARTER_TASKS = [
  {
    key: 'brief',
    icon: '🔎',
    name: 'Research brief',
    outcome: 'A short, sourced brief you can act on.',
    ask: 'What should they look into?',
    placeholder: 'how small teams price a new product',
    title: (s) => `Research brief: ${s}`,
    build: (s, { canFile, filePath }) => [
      `Write a short research brief on: ${s}`,
      '',
      'Structure it as a one-paragraph summary, then 3–5 key findings as',
      "bullets, then a short honest note on what you're unsure about.",
      'Say where each finding came from — if you searched, name the source;',
      'if it came from what you already know, say so plainly. Never invent a',
      'citation.',
      canFile
        ? `Save the finished brief to ${filePath('Research', s, 'md')}, then reply with a 2-sentence summary and the path.`
        : 'Deliver the brief itself in your reply — it is the deliverable, so keep it tight and finished.',
    ].join('\n'),
  },
  {
    key: 'draft',
    icon: '✍️',
    name: 'First draft',
    outcome: 'Real sentences you can edit — not an outline.',
    ask: 'What should they draft?',
    placeholder: 'a warm intro email to a new client',
    title: (s) => `First draft: ${s}`,
    build: (s, { canFile, filePath }) => [
      `Write a first draft of: ${s}`,
      '',
      'Write it for real — full sentences, a clear structure, no placeholder',
      'text and no "[insert here]" gaps. Where you need an assumption to keep',
      'moving, make a sensible one and list your assumptions at the end.',
      canFile
        ? `Save the draft to ${filePath('Drafts', s, 'md')}, then reply with a 2-sentence summary and the path.`
        : 'Put the draft itself in your reply — it is the deliverable.',
    ].join('\n'),
  },
  {
    key: 'page',
    icon: '🌐',
    name: 'Simple page',
    outcome: 'One web page, finished and ready to open.',
    ask: 'What should the page be for?',
    placeholder: 'a one-page site for my dog-walking business',
    title: (s) => `Simple page: ${s}`,
    build: (s, { canFile, filePath }) => [
      `Build a simple web page for: ${s}`,
      '',
      'One self-contained HTML file: inline CSS, no external stylesheets,',
      'fonts, or script libraries — it has to render with no network. Make it',
      'look finished rather than a wireframe: real copy, a sensible layout,',
      'and readable on a phone.',
      canFile
        ? `Save it to ${filePath('Sites', s, 'html')}, then reply with one sentence about what you built and the path.`
        : 'Put the complete HTML in your reply, in one code block.',
    ].join('\n'),
  },
];

/* Vault-relative path for a deliverable: Research/how-small-teams-price.md */
function filePath(folder, subject, ext) {
  const slug = String(subject).toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'note';
  return `${folder}/${slug}.${ext}`;
}

/* Whether this coworker can actually file into the boss's cabinet. Front-desk
   hires claim ['web'] or ['files','shell','web'] — none claim 'vault' — so the
   honest default is "deliver it in the reply". */
function canFileToVault(agent) {
  return !!(agent && (agent.tools || []).includes('vault'));
}

/* Build the real task object a starter card produces. Exported so the task
   board's empty state and the first-run sheet mint identical tasks. */
function buildStarterTask(starter, subject, agent) {
  const s = String(subject || '').trim();
  if (!s) return null;
  return {
    id: 'tk_' + Math.random().toString(36).slice(2, 7),
    title: starter.title(s).slice(0, 120),
    detail: starter.build(s, { canFile: canFileToVault(agent), filePath }),
    assignedTo: null,
    status: 'inbox',
    priority: 'med',
    createdAt: Date.now(),
    starter: starter.key,      // provenance: which card produced this task
  };
}

/* ── <StarterCards> ───────────────────────────────────────────────────────
   The card row itself, shared by the first-run sheet and the task board's
   empty inbox. Picking a card expands it into a single subject field;
   submitting calls onPick(starter, subject). The host decides what happens
   next — the sheet dispatches to the new hire, the board files it to the
   inbox for the user to drag. */
function StarterCards({ onPick, who = '', compact = false }) {
  const [picked, setPicked] = useStateS(null);
  const [subject, setSubject] = useStateS('');
  const inputRef = useRefS(null);

  useEffectS(() => {
    if (picked && inputRef.current) inputRef.current.focus();
  }, [picked]);

  const active = STARTER_TASKS.find(s => s.key === picked) || null;
  const submit = () => {
    if (!active || !subject.trim()) return;
    onPick(active, subject.trim());
    setPicked(null); setSubject('');
  };

  return (
    <div className={'starter-wrap' + (compact ? ' is-compact' : '')}>
      <div className="starter-row">
        {STARTER_TASKS.map(s => (
          <button
            key={s.key}
            type="button"
            className={'starter-card' + (picked === s.key ? ' is-picked' : '')}
            onClick={() => { setPicked(p => (p === s.key ? null : s.key)); setSubject(''); }}
            aria-pressed={picked === s.key}
          >
            <span className="starter-icon" aria-hidden="true">{s.icon}</span>
            <span className="starter-name">{s.name}</span>
            <span className="starter-outcome">{s.outcome}</span>
          </button>
        ))}
      </div>
      {active && (
        <div className="starter-fill">
          <label className="starter-ask" htmlFor="starter-subject">
            {who ? active.ask.replace('they', who) : active.ask}
          </label>
          <div className="starter-input-row">
            <input
              id="starter-subject"
              ref={inputRef}
              className="oc-input sz-sm"
              value={subject}
              placeholder={active.placeholder}
              onChange={e => setSubject(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit(); }}
              autoComplete="off"
            />
            <button
              type="button"
              className="px-btn primary"
              style={{ fontSize: 'var(--text-10)' }}
              onClick={submit}
              disabled={!subject.trim()}
            >START →</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── <StarterTasksModal> ──────────────────────────────────────────────────
   First-run beat 4: opens once, a moment after the first coworker walks in.
   Skipping is one click and never nags — free text still exists, it just
   isn't the star (OFFICE_AS_INTERFACE §3.4 / §7). */
function StarterTasksModal({ open, agent, onClose, onStart }) {
  if (!open || !agent) return null;
  const who = agent.name || 'they';
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="FIRST ASSIGNMENT"
      subtitle={`${who} is at a desk · pick something real to start on`}
      size="md"
      footer={
        <button className="px-btn ghost" style={{ fontSize: 'var(--text-10)' }} onClick={onClose}>
          Skip — I'll ask in my own words
        </button>
      }
    >
      <div className="starter-head">
        <Sprite data={agent.color} scale={3} />
        <div className="starter-head-note">
          <strong>{who}</strong> is ready. Pick one and watch it happen on the
          floor — you can always ask for something else in chat.
        </div>
      </div>
      <StarterCards who={who} onPick={(starter, subject) => {
        const task = buildStarterTask(starter, subject, agent);
        if (task) onStart(task, agent);
      }} />
    </Modal>
  );
}

export { STARTER_TASKS, StarterCards, StarterTasksModal, buildStarterTask };

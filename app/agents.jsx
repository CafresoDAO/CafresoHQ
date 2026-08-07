function downgradeElevatedModel(model, settings) {
  if (!model) return { model: 'haiku', swapped: false, why: '' };
  const m = /^(cafresohq|codex):(.+)$/.exec(model);
  if (!m) return { model, swapped: false, why: '' };
  const proto = m[1], tail = m[2];
  let swap = null;
  let why = '';
  if (proto === 'cafresohq') {
    swap = 'claudecode:' + tail;
    why = 'CafresoHQ elevated provider is elevation-only';
  } else if (proto === 'codex') {
    const ocaTail = tail.startsWith('oca/') ? tail : 'oca/' + tail;
    swap = 'oca:' + ocaTail;
    why = 'Codex CLI is elevation-only';
  }
  if (!swap) {
    if (settings && settings.anthropicKey) swap = 'anthropic:' + settings.anthropicModel;
    else if (settings && settings.claudecodeModel) swap = 'claudecode:' + settings.claudecodeModel;
    else swap = 'haiku';
    why = (why || 'a model that only runs with file and shell access') + '; falling back to user default';
  }
  return { model: swap, swapped: true, why };
}

/* ─────────────────────────────────────────────────────────────────────
   Agent capability inference (Phase 2 of comms refactor)

   Agents can declare an explicit `capabilities: [...]` array. When they
   don't, we infer a reasonable starting set from the role name so the
   `/who-can <skill>` palette command works for everyone out of the box,
   not just newly-onboarded agents. Map is intentionally generous — we'd
   rather over-suggest than under-suggest, since the boss makes the final
   call about who to actually hand off to.
   ───────────────────────────────────────────────────────────────────── */
const ROLE_CAPABILITY_MAP = [
  // [keyword in role (lowercase), capabilities[]]
  ['code',        ['code-review','fix','debug','refactor','test']],
  ['gremlin',     ['code-review','fix','debug','refactor','test']],
  ['engineer',    ['code-review','fix','debug','refactor','test','deployment']],
  ['research',    ['research','summary','analysis','citation']],
  ['goblin',      ['research','summary','analysis']],
  ['analyst',     ['research','analysis','metrics']],
  ['growth',      ['marketing','copy','metrics','outreach']],
  ['hunter',      ['research','outreach','prospecting']],
  ['marketer',    ['marketing','copy','launch']],
  ['docs',        ['docs','writing','organization','editing']],
  ['archivist',   ['docs','organization','retrieval']],
  ['writer',      ['writing','copy','editing']],
  ['designer',    ['design','ux','copy','review']],
  ['ux',          ['ux','design','review']],
  ['ops',         ['deployment','infra','automation']],
  ['devops',      ['deployment','infra','automation','monitoring']],
  ['pm',          ['planning','triage','spec']],
  ['product',     ['planning','triage','spec','review']],
  ['chief',       ['planning','review','synthesis']],
  ['lead',        ['planning','review','synthesis']],
];
function agentCapabilities(agent) {
  if (!agent) return [];
  if (Array.isArray(agent.capabilities) && agent.capabilities.length) {
    return agent.capabilities.map(c => String(c).toLowerCase());
  }
  const role = String(agent.role || '').toLowerCase();
  const caps = new Set(['general']);
  for (const [kw, list] of ROLE_CAPABILITY_MAP) {
    if (role.includes(kw)) for (const c of list) caps.add(c);
  }
  // Elevated agents get computer-access capabilities by default.
  if (agent.elevated) {
    for (const c of ['shell','file','deployment','review']) caps.add(c);
  }
  return [...caps];
}
/* `/who-can <skill>` resolver — returns agents matching ANY token in the
   query (so "code review" matches both 'code-review' and split tokens).
   Used by the palette command + future routing helpers. */
function whoCan(agents, queryRaw) {
  const q = String(queryRaw || '').toLowerCase().trim();
  if (!q) return [];
  const tokens = q.split(/[\s,]+/).filter(Boolean);
  const match = (cap) => {
    const c = cap.toLowerCase();
    return tokens.some(t =>
      c === t || c.startsWith(t) || c.includes(t) || t.includes(c));
  };
  return (agents || []).map(a => {
    const caps = agentCapabilities(a);
    const hits = caps.filter(match);
    return { agent: a, capabilities: caps, matches: hits };
  }).filter(r => r.matches.length > 0)
    .sort((a, b) => b.matches.length - a.matches.length);
}

/* The HQ topbar's ecosystem switcher is now the shared <cafreso-ecobar> web
   component (cafreso-ecobar.jsx) — used by HQ, the SvelteKit frontend, and
   Minegold from one definition. The old React-only EcosystemNav + ECOSYSTEM_APPS
   that lived here were removed to keep a single source of truth. */

/* ─────────────────────────────────────────────────────────────────────
   AppGlobalCommands — registers always-available palette commands.
   Lives inside <CommandPaletteProvider> (so useCommands works) and
   gets fresh callbacks whenever its props change. Doesn't render
   anything visible; it's purely a registration component.
   ───────────────────────────────────────────────────────────────────── */

export { downgradeElevatedModel, whoCan };

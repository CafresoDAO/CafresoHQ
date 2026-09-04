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
    /* There is no 'oca:' provider — parseModelId()'s prefix table and
       stream()'s dispatch in claude-client.jsx both stop at 'codex:' and
       neither one recognizes 'oca'. Naming it here used to send a
       downgraded helper's model straight through as a bare, unroutable
       string ("oca:oca/gpt-5.5"), silently falling back to whatever
       provider Settings had picked with a model id that provider had never
       heard of. Leaving `swap` unset here routes through the settings
       fallback below instead, which only ever names providers `stream()`
       actually dispatches. */
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

   Skills are inferred from the job title so `/who-can <skill>` works for
   everyone out of the box. The map is intentionally generous — we'd rather
   over-suggest than under-suggest, since the boss makes the final call
   about who to hand off to.

   That generosity is only defensible if the boss can SEE what they are
   choosing between, which until 2026-08-16 they could not: `whoCan`
   returned a coworker with nothing ticked on their card in the same shape,
   and the same ordering, as one holding the tool. Two coworkers both
   titled Research, one with Web Search and one with no grants at all, came
   back as an identical pair of bullets. So a hit now carries the
   coworker's REAL reach beside the guess — see `reachOf`.

   There used to be a first branch here reading an explicit
   `capabilities: [...]` array off the agent. Nothing in the product has
   ever written that field — not the hire form, not the Roster card (which
   patches model, temperature, tools, toolFormat and elevated), not the
   backend, not a template — so the branch was dead and its only living
   effect was to make the dead-end toast's advice, "set capabilities on an
   existing agent", sound like it named something. Removed with the advice.
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
  const role = String(agent.role || '').toLowerCase();
  const caps = new Set(['general']);
  for (const [kw, list] of ROLE_CAPABILITY_MAP) {
    if (role.includes(kw)) for (const c of list) caps.add(c);
  }
  /* Elevated coworkers get computer-access skill words. Unlike the two
     TOOL ids of the same spelling that #117 removed, these are the boss's
     own search terms and they match a door that really is printed on the
     card — "File & shell access". A boss typing "shell" should find the
     coworker who has it. */
  if (agent.elevated) {
    for (const c of ['shell','file','deployment','review']) caps.add(c);
  }
  return [...caps];
}

/* `/who-can <skill>` resolver — returns agents matching ANY token in the
   query (so "code review" matches both 'code-review' and split tokens).

   `reachOf` answers "what can this coworker actually reach", and is
   INJECTED rather than imported for the same reason app/cast.jsx states
   about its own facts: this file is import-free and runs verbatim under
   node in the suite, so it asserts what it was told rather than going to
   look. The caller passes the product's one answer to that question —
   `grantedTools(a.tools, HQ.capabilityFacts(a))`, the same pair the
   coworker card, the inspect panel and the candidate shelf all use — and
   `/who-can` stops being a fourth surface describing a coworker's reach in
   its own words.

   Omit it and `reach` is ABSENT on every hit, not empty. That is cast.jsx's
   rule and it matters here too: "we did not look" must never render as
   "they have nothing". */
function whoCan(agents, queryRaw, reachOf) {
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
    const r = { agent: a, capabilities: caps, matches: hits };
    if (typeof reachOf === 'function') {
      /* A reader that throws leaves the fact absent rather than empty —
         the boss gets the guess with no claim about reach, which is what
         we actually know at that point. */
      try { r.reach = reachOf(a); } catch (_e) {}
    }
    return r;
  }).filter(r => r.matches.length > 0)
    /* Ties on skill-word count break toward the coworker who can actually
       do it. Ordering is the only part of a "generous" list the boss reads
       as a recommendation, so it is the part that has to be earned. Left
       untouched when reach is absent. */
    .sort((a, b) => (b.matches.length - a.matches.length)
                 || (reachCount(b) - reachCount(a)));
}
function reachCount(hit) {
  return (hit && hit.reach && hit.reach.granted) ? hit.reach.granted.length : 0;
}

/* The bullet the palette prints, so the sentence the boss reads is testable
   without a toast. Reach absent → no suffix at all; reach present and empty
   → say so, because "nothing ticked" is the fact that makes the whole list
   worth showing. */
function whoCanLine(hit) {
  const head = `• ${hit.agent.name} (${hit.agent.role}): ${hit.matches.join(', ')}`;
  if (!hit.reach) return head;
  const can = (hit.reach.granted || []).map(g => g.say);
  if (can.length) return `${head} — can ${can.join(', ')}`;
  const locked = (hit.reach.locked || []).map(l => l.unlock).filter(Boolean);
  if (locked.length) return `${head} — nothing switched on yet; could ${locked.join(', ')}`;
  return `${head} — nothing ticked on their card yet`;
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

export { downgradeElevatedModel, whoCan, whoCanLine };

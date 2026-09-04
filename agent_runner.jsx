import { CafresoHQClient } from './claude-client.jsx';
import { officeStamp } from './app/artifacts.jsx';
/* ==========================================================================
   CafresoHQ — Agent Runner Shim
   --------------------------------------------------------------------------
   Bridges UI-fired graph actions (right-click, multi-select, ghost-edge
   confirmations, cluster labeling) into actual LLM work via the existing
   CafresoHQClient.stream() API.

   Listens for:
     - 'cafresohq:agentAction' { kind, nodeId|nodeIds, agentId?, ...extra }

   Emits, while running:
     - 'cafresohq:agentActivity' { nodeId, agentId, agentName, color, kind }

   Some actions write artifacts to the vault. Summaries can also return
   directly to the floating chat window via responseMode: 'chat'.

   The runner picks an agent the user hired if `agentId` is provided. Otherwise
   it falls back to the CafresoHQClient's currently configured provider/model.
   ========================================================================== */

let CafresoHQAgentRunner;

(function () {
  if (typeof window === 'undefined') return;
  if (window.__cafresohqAgentRunnerInstalled) return; // idempotent
  window.__cafresohqAgentRunnerInstalled = true;

  /* Look up an agent by id from the live app state. The host app should
     register its current agents list via setAgents() so the runner can
     pick the right model. */
  let _agents = [];
  let _addMemoryFn = null; // optional hook to push runner notes to the agent's memory
  CafresoHQAgentRunner = {
    setAgents(list) { _agents = Array.isArray(list) ? list : []; },
    getAgents()    { return _agents.slice(); },
    setAddMemoryFn(fn) { _addMemoryFn = typeof fn === 'function' ? fn : null; },
  };

  function findAgent(id) {
    if (!id) return null;
    return _agents.find(a => a.id === id) || null;
  }

  function emitActivity(nodeId, agent, kind) {
    try {
      window.dispatchEvent(new CustomEvent('cafresohq:agentActivity', {
        detail: {
          nodeId,
          agentId: agent ? agent.id : null,
          agentName: agent ? agent.name : 'Agent',
          color: (agent && agent.color && (agent.color.body || agent.color.shirt)) || '#7db5b5',
          kind,
        },
      }));
    } catch (_) {}
  }

  function emitChatResponse({ text, nodeId, agent, kind }) {
    try {
      window.dispatchEvent(new CustomEvent('cafresohq:agentChatResponse', {
        detail: {
          text, nodeId, kind: kind || 'summarize',
          agentId: agent ? agent.id : null,
          agentName: agent ? agent.name : 'Graph Agent',
          agentRole: agent ? agent.role : 'summarizer',
        },
      }));
    } catch (_) {}
  }

  /* Read with activity overlay. */
  async function readWithBeacon(path, agent) {
    emitActivity(path, agent, 'read');
    try { return await CafresoHQClient.vaultRead(path); }
    catch (_) { return ''; }
  }

  /* Run a single chat call, return the full text. We emit a "thinking"
     activity ping at start and a "write" ping when finished writing. */
  async function ask({ system, prompt, agent }) {
    let text = '';
    const opts = {
      system,
      messages: [{ role: 'user', content: prompt }],
      onToken: (delta) => { text += delta; },
      maxTokens: 1024,
    };
    if (agent && agent.model)    opts.model    = agent.model;
    if (agent && agent.elevated) opts.elevated = true;
    if (agent && agent.name)     opts.agentName = agent.name;
    await CafresoHQClient.stream(opts);
    return text.trim();
  }

  /* Sanitize a path slug for filenames. */
  function slug(s) {
    return (s || 'note')
      .replace(/\.md$/, '')
      .replace(/[\\/:*?"<>|]/g, '_')
      .slice(0, 80);
  }

  /* Is something already filed at this path? A generated note may never
     replace a note the boss (or another agent) already wrote, so the answer
     has to be conservative: only a genuine "there is nothing here" clears
     the way. Any other failure — offline, 502, a bridge refusal — leaves
     the answer unknown, and unknown is not permission to overwrite. */
  async function pathTaken(path) {
    try { await CafresoHQClient.vaultRead(path); return true; }
    catch (e) { return !/not found|404/i.test((e && e.message) || ''); }
  }

  /* ----- Action handlers ------------------------------------------------ */

  async function handleSummarize({ nodeId, includeNeighbors, agent, responseMode }) {
    if (!nodeId) return;
    const own = await readWithBeacon(nodeId, agent);
    let neighbors = [];
    if (includeNeighbors) {
      // Use the graph's adjacency: ask the CafresoHQGraph API.
      const g = (window.CafresoHQGraph && window.CafresoHQGraph._lastGraph) || null;
      if (g && g.edges) {
        for (const e of g.edges) {
          const s = e.source.id || e.source, t = e.target.id || e.target;
          if (s === nodeId) neighbors.push(t);
          else if (t === nodeId) neighbors.push(s);
        }
      }
      neighbors = [...new Set(neighbors)].slice(0, 6);
    }
    const neighborBodies = await Promise.all(neighbors.map(async id => {
      const body = await readWithBeacon(id, agent);
      return { id, body: body.slice(0, 1500) };
    }));

    const system = `You are a focused note-summarizer for an Obsidian vault. ` +
      `Summaries are concise (3-6 bullets), faithful to the source, and use the ` +
      `same vocabulary as the note. Cite linked notes inline as [[Title]].`;
    const prompt =
      `Summarize the following note. ${includeNeighbors && neighborBodies.length ? 'Also weave in the linked notes as context.' : ''}\n\n` +
      `=== ${nodeId} ===\n${own.slice(0, 4000)}\n` +
      neighborBodies.map(n => `\n=== Linked: ${n.id} ===\n${n.body}`).join('') +
      `\n\nReturn only the summary in markdown bullets.`;

    const summary = await ask({ system, prompt, agent });
    if (responseMode === 'chat') {
      emitChatResponse({ text: summary, nodeId, agent, kind: 'summarize' });
      return;
    }
    const ts = officeStamp();   // the boss's clock — see officeStamp
    const path = `Summaries/${slug(nodeId.split('/').pop())}-summary.md`;
    const out =
      `---\nsource: "[[${nodeId}]]"\ngenerated: ${ts}\nagent: ${agent ? agent.name : 'auto'}\n---\n\n` +
      `# Summary of ${nodeId.split('/').pop().replace(/\.md$/, '')}\n\n` +
      summary + '\n\n' +
      `## Source\n[[${nodeId}]]\n` +
      (neighborBodies.length
        ? `\n## Linked context\n${neighborBodies.map(n => `- [[${n.id}]]`).join('\n')}\n`
        : '');
    emitActivity(path, agent, 'write');
    await CafresoHQClient.vaultWrite(path, out, 'write');
    if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) await window.CafresoHQGraph.refresh();
  }

  async function handleSuggestTags({ nodeId, agent }) {
    if (!nodeId) return;
    const own = await readWithBeacon(nodeId, agent);
    const system = `Suggest 3-7 lowercase tags for a note in an Obsidian vault. ` +
      `Output only a JSON array of strings, e.g. ["#project","#design","#research"].`;
    const prompt = `Note path: ${nodeId}\n\n${own.slice(0, 4000)}`;
    const raw = await ask({ system, prompt, agent });
    let tags = [];
    try {
      const m = raw.match(/\[[\s\S]*\]/);
      tags = m ? JSON.parse(m[0]) : [];
    } catch (_) {}
    if (!Array.isArray(tags) || tags.length === 0) tags = [raw.split(/\s+/).slice(0,5).join(' ')];
    const path = `Suggestions/${slug(nodeId.split('/').pop())}-tags.md`;
    const out =
      `---\nsource: "[[${nodeId}]]"\ngenerated: ${officeStamp()}\n---\n\n` +
      `# Suggested tags for ${nodeId.split('/').pop()}\n\n` +
      tags.map(t => `- ${t}`).join('\n') + '\n\n' +
      `## Source\n[[${nodeId}]]\n`;
    emitActivity(path, agent, 'write');
    await CafresoHQClient.vaultWrite(path, out, 'write');
    if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) await window.CafresoHQGraph.refresh();
  }

  async function handleFindMissingLinks({ nodeId, agent }) {
    if (!nodeId) return;
    const own = await readWithBeacon(nodeId, agent);
    // Build candidate list from the graph's other titles.
    const g = (window.CafresoHQGraph && window.CafresoHQGraph._lastGraph) || null;
    const candidates = (g && g.nodes ? g.nodes : [])
      .filter(n => n.id !== nodeId)
      .map(n => n.title || n.id)
      .slice(0, 200);
    const system = `Identify which notes in the candidate list this note SHOULD link to ` +
      `but currently doesn't. Output a JSON array of titles, e.g. ["Project Helios","API Design"]. ` +
      `Only include titles from the candidate list. Be conservative.`;
    const prompt =
      `=== Note ${nodeId} ===\n${own.slice(0, 4000)}\n\n` +
      `=== Candidate titles ===\n${candidates.join('\n')}`;
    const raw = await ask({ system, prompt, agent });
    let suggestions = [];
    try {
      const m = raw.match(/\[[\s\S]*\]/);
      suggestions = m ? JSON.parse(m[0]) : [];
    } catch (_) {}
    const path = `Suggestions/${slug(nodeId.split('/').pop())}-missing-links.md`;
    const out =
      `---\nsource: "[[${nodeId}]]"\ngenerated: ${officeStamp()}\n---\n\n` +
      `# Suggested links from ${nodeId.split('/').pop()}\n\n` +
      (suggestions.length ? suggestions.map(t => `- [[${t}]]`).join('\n') : '_No suggestions._') + '\n\n' +
      `## Source\n[[${nodeId}]]\n`;
    emitActivity(path, agent, 'write');
    await CafresoHQClient.vaultWrite(path, out, 'write');
    if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) await window.CafresoHQGraph.refresh();
  }

  async function handleGenerateChild({ nodeId, agent }) {
    if (!nodeId) return;
    const own = await readWithBeacon(nodeId, agent);
    const system = `Propose ONE child note that elaborates a sub-topic of the parent. ` +
      `Output strictly:\nTITLE: <title>\n---\n<markdown body>\n` +
      `The body must include "Parent: [[${nodeId}]]" near the top.`;
    const prompt = `=== Parent note ${nodeId} ===\n${own.slice(0, 4000)}`;
    const raw = await ask({ system, prompt, agent });
    const m = raw.match(/TITLE:\s*(.+?)\n[-]{3,}\n([\s\S]+)/);
    const title = (m && m[1].trim()) || `${nodeId.split('/').pop().replace(/\.md$/,'')} - child`;
    const body  = (m && m[2].trim()) || raw;
    const folder = nodeId.split('/').slice(0, -1).join('/') || 'Inbox';
    const base = slug(title);
    /* The title is the model's, the folder is the parent's — so a child
       titled like an existing sibling (or like the parent itself, which is
       exactly what a model that echoes the parent's name produces) used to
       resolve onto a note that was already there, and vaultWrite REPLACES.
       The boss's note was gone, silently, with a green write in its place.
       Step to a free filename instead; if there isn't one, refuse and let
       the runner's error path say so rather than overwrite. */
    let path = '';
    for (let n = 1; n <= 20; n++) {
      const candidate = `${folder}/${base}${n === 1 ? '' : `-${n}`}.md`;
      if (!(await pathTaken(candidate))) { path = candidate; break; }
    }
    if (!path) throw new Error(`no free filename for "${title}" in ${folder} — the child note was not written (nothing was overwritten)`);
    emitActivity(path, agent, 'write');
    await CafresoHQClient.vaultWrite(path, `# ${title}\n\nParent: [[${nodeId}]]\n\n${body}\n`, 'write');
    // Also link from the parent — to the file that was actually written,
    // which is not `title` once the name had to be stepped.
    try {
      const parentBody = await CafresoHQClient.vaultRead(nodeId);
      const linkText = `[[${path.split('/').pop().replace(/\.md$/, '')}]]`;
      if (!parentBody.includes(linkText)) {
        await CafresoHQClient.vaultWrite(nodeId, parentBody.replace(/\s*$/, '\n\n') + linkText + '\n', 'write');
      }
    } catch (_) {}
    if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) await window.CafresoHQGraph.refresh();
  }

  async function handleExplainConnections({ nodeId, agent }) {
    if (!nodeId) return;
    const own = await readWithBeacon(nodeId, agent);
    const g = (window.CafresoHQGraph && window.CafresoHQGraph._lastGraph) || null;
    const links = [];
    if (g && g.edges) {
      for (const e of g.edges) {
        const s = e.source.id || e.source, t = e.target.id || e.target;
        if (s === nodeId) links.push(t);
        else if (t === nodeId) links.push(s);
      }
    }
    const linkBodies = await Promise.all(links.slice(0, 6).map(async id => ({
      id, body: (await readWithBeacon(id, agent)).slice(0, 1200),
    })));
    const system = `Explain in 4-8 sentences how this note relates to each linked note. ` +
      `Reference each link by [[Title]]. Be specific, not generic.`;
    const prompt =
      `=== Note ${nodeId} ===\n${own.slice(0, 3500)}\n\n` +
      linkBodies.map(l => `=== Linked: ${l.id} ===\n${l.body}`).join('\n\n');
    const explanation = await ask({ system, prompt, agent });
    const path = `Summaries/${slug(nodeId.split('/').pop())}-connections.md`;
    const out =
      `---\nsource: "[[${nodeId}]]"\ngenerated: ${officeStamp()}\n---\n\n` +
      `# How [[${nodeId}]] connects\n\n${explanation}\n`;
    emitActivity(path, agent, 'write');
    await CafresoHQClient.vaultWrite(path, out, 'write');
    if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) await window.CafresoHQGraph.refresh();
  }

  async function handleLabelClusters({ clusters, agent }) {
    if (!clusters || !clusters.length) return;
    const system = `For each cluster, return a 1-3 word label that captures the unifying theme. ` +
      `Output JSON: {"<idx>": "<label>"}.`;
    const prompt = clusters.map(c =>
      `Cluster ${c.idx} (${c.size} notes, tags ${c.tags.slice(0,8).join(' ')}):\n` +
      c.titles.slice(0, 12).map(t => `- ${t}`).join('\n')
    ).join('\n\n');
    const raw = await ask({ system, prompt, agent });
    let labels = {};
    try {
      const m = raw.match(/\{[\s\S]*\}/);
      labels = m ? JSON.parse(m[0]) : {};
    } catch (_) {}
    if (Object.keys(labels).length) {
      // Hand back to the GraphView to display.
      try {
        window.dispatchEvent(new CustomEvent('cafresohq:clusterLabelsResolved', { detail: { labels } }));
      } catch (_) {}
    }
  }

  async function handleBatchMission({ nodeIds, agent }) {
    if (!nodeIds || !nodeIds.length) return;
    // Run a summarize-each in series. For very large batches the user can
    // stop the page mid-run.
    for (const id of nodeIds.slice(0, 12)) {
      try { await handleSummarize({ nodeId: id, includeNeighbors: false, agent }); }
      catch (_) {}
    }
  }

  /* ----- Dispatcher ----------------------------------------------------- */

  async function dispatch(detail) {
    const agent = findAgent(detail.agentId);
    try {
      switch (detail.kind) {
        case 'summarize':           return await handleSummarize({ ...detail, agent });
        case 'suggestTags':         return await handleSuggestTags({ ...detail, agent });
        case 'findMissingLinks':    return await handleFindMissingLinks({ ...detail, agent });
        case 'generateChild':       return await handleGenerateChild({ ...detail, agent });
        case 'explainConnections':  return await handleExplainConnections({ ...detail, agent });
        case 'labelClusters':       return await handleLabelClusters({ ...detail, agent });
        case 'mission':             return await handleSummarize({ nodeId: detail.nodeId, includeNeighbors: true, agent });
        case 'batchMission':        return await handleBatchMission({ ...detail, agent });
        default: console.warn('[agent_runner] unknown action kind:', detail.kind);
      }
    } catch (err) {
      console.error('[agent_runner] action failed:', detail.kind, err);
      window.dispatchEvent(new CustomEvent('cafresohq:agentRunnerError', {
        detail: { kind: detail.kind, message: err && err.message || String(err) },
      }));
    }
  }

  window.addEventListener('cafresohq:agentAction', (e) => {
    const detail = e && e.detail;
    if (!detail || !detail.kind) return;
    /* Fire-and-forget — UI already shows a status toast. */
    dispatch(detail);
  });

  /* No monkey-patching here anymore: GraphView maintains
     window.CafresoHQGraph._lastGraph itself (set on mount and on every
     refresh), so the 200ms-forever polling wrapper this file used to install
     was redundant — action handlers read the registry lazily below. */

  console.info('[agent_runner] installed — listening for cafresohq:agentAction');
})();

export { CafresoHQAgentRunner };

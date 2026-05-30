/* ==========================================================================
   CafresoAI — real backend client
   Dispatches streaming chat to:
     - Hermes Agent (DEFAULT — OpenAI-compatible via /hermes/v1 proxy, SSE)
     - Anthropic Messages API (browser-direct, stream SSE)
     - LM Studio / Ollama (OpenAI-compatible /v1/chat/completions, SSE)
     - Claude Code / Openclaw / Codex CLIs, Google Gemini
   Settings persisted in localStorage. window.OpenclawClient is the surface.
   ========================================================================== */

// Derive the API path prefix from the current page URL.
// When loaded at https://hq.cafreso.com/u/<slug>/hq.html (Caddy gateway):
//   _API_BASE = '/u/<slug>'  →  fetch(_API_BASE + '/terminal/status')
//   resolves to https://hq.cafreso.com/u/<slug>/terminal/status
//   Caddy handle_path strips the prefix and proxies /terminal/status to the container.
// When loaded directly at http://ip:8787/hq.html or http://localhost:8787/hq.html:
//   _API_BASE = ''  →  fetch('' + '/terminal/status') = fetch(_API_BASE + '/terminal/status')  ✓
const _API_BASE = window.location.pathname.replace(/\/[^/]*$/, '');
window._API_BASE = _API_BASE;   // expose for views.jsx / app.jsx

const LS_KEY = 'openclaw_client_v1';

const ANTHROPIC_MODELS = [
  'claude-opus-4-7',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
];

const GEMINI_MODELS = [
  'gemini-3.1-pro-preview',
  'gemini-2.5-pro',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
  'gemini-2.5-flash',
];

/* Claude Code (Pro/Max subscription) — invoked via subprocess on the proxy.
   Models match what the `claude` CLI accepts via --model. */
const CLAUDECODE_MODELS = [
  'claude-sonnet-4-5',
  'claude-opus-4-5',
  'claude-haiku-4-5',
  'sonnet',  // CLI shorthand
  'opus',
  'haiku',
];

/* OpenClaw (elevated) — same Claude Code CLI but with file/shell tools
   enabled. Server-side allowlist governs paths and tool names; the
   client just picks a model. Same accepted IDs as CLAUDECODE_MODELS. */
const OPENCLAW_MODELS = CLAUDECODE_MODELS;

/* Codex CLI elevated agent — talks directly to OpenAI (model_provider=openai)
   via OPENAI_API_KEY (BYOK / operator env). Models are real OpenAI ids. */
const CODEX_MODELS = [
  'gpt-4.1',
  'gpt-4.1-mini',
  'gpt-4o',
  'gpt-4o-mini',
  'o3',
  'o4-mini',
];

/* Hermes Agent (Nous Research) — the DEFAULT runtime. serve.py proxies
   /hermes/v1 → the per-container `hermes gateway` OpenAI-compatible API
   server (127.0.0.1:8642), injecting the Bearer API_SERVER_KEY server-side
   so the key never reaches the browser. The single advertised model id is
   'hermes-agent' — the gateway routes to whatever LLM backend is configured
   in ~/.hermes/config.yaml, and runs the full agent toolset server-side. */
const HERMES_MODELS = [
  'hermes-agent',
];

const DEFAULTS = {
  provider: 'hermes',
  /* Hermes Agent (default). Same-origin proxy at /hermes/v1 → serve.py →
     the container's `hermes gateway` API server. No browser-side key:
     serve.py injects API_SERVER_KEY. Override hermesUrl only when bypassing
     the proxy (direct dev access to a local gateway on :8642). */
  hermesUrl: '/hermes/v1',
  hermesModel: 'hermes-agent',
  anthropicKey: '',
  anthropicModel: 'claude-haiku-4-5-20251001',
  lmstudioUrl: '/lmstudio/v1',
  lmstudioModel: '',
  ollamaUrl: '/ollama/v1',
  ollamaModel: '',
  claudecodeModel: 'sonnet',
  codexModel: 'gpt-4.1',
  googleModel: 'gemini-3.1-pro-preview',
  googleKey: '',
  maxTokens: 1024,
  braveKey: '',
  braveEnabled: false,
  /* Sub-agent model selection (Phase 3+):
     - 'inherit' (default): transient sub-agents use the same model as the
       agent that spawned them (cheapest cognitive load — no model-mixing).
     - any provider-prefixed id (e.g. 'anthropic:claude-haiku-4-5-20251001'):
       all sub-agents use that pinned model regardless of spawner.
     A spawning agent can override per-spawn with [SPAWN_SUBAGENT: role | model:<id>]
     syntax — that always wins over this setting. */
  subagentModel: 'inherit',
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch (_e) { return { ...DEFAULTS }; }
}
function saveSettings(s) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(s)); }
  catch (err) {
    console.warn('[openclaw] saveSettings failed:', err);
    try { window.dispatchEvent(new CustomEvent('openclaw:storage-error', { detail: { key: LS_KEY, error: err } })); } catch (_e) {}
  }
}

let _settings = loadSettings();
const _listeners = new Set();
function getSettings() { return { ..._settings }; }
function setSettings(patch) {
  _settings = { ..._settings, ...patch };
  saveSettings(_settings);
  _listeners.forEach(f => { try { f(_settings); } catch (_e) {} });
}
function onSettingsChange(fn) { _listeners.add(fn); return () => _listeners.delete(fn); }

/* Anthropic requires alternating user/assistant and must start with user. */
function normalizeMessages(msgs) {
  const out = [];
  for (const m of msgs) {
    if (!m.content || !String(m.content).trim()) continue;
    if (out.length && out[out.length - 1].role === m.role) {
      out[out.length - 1].content += '\n\n' + m.content;
    } else {
      out.push({ role: m.role, content: m.content });
    }
  }
  while (out.length && out[0].role !== 'user') out.shift();
  return out;
}

async function parseSSE(stream, onLine) {
  const reader = stream.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let event = 'message';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).replace(/\r$/, '');
      buf = buf.slice(idx + 1);
      if (line === '') { event = 'message'; continue; }
      if (line.startsWith('event:')) { event = line.slice(6).trim(); }
      else if (line.startsWith('data:')) { onLine(event, line.slice(5).trim()); }
    }
  }
}

async function streamAnthropic({ system, messages, model, temperature, maxTokens, onToken, onUsage, signal }) {
  const s = _settings;
  if (!s.anthropicKey) throw new Error('No Anthropic API key — open Settings → API');
  const body = {
    model: model || s.anthropicModel,
    max_tokens: maxTokens || s.maxTokens || 1024,
    messages: normalizeMessages(messages),
    stream: true,
  };
  if (system) body.system = system;
  if (typeof temperature === 'number') body.temperature = temperature;
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST', signal,
    headers: {
      'content-type': 'application/json',
      'x-api-key': s.anthropicKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Anthropic ${res.status}: ${t.slice(0, 400)}`);
  }
  let inputTokens = 0;
  let outputTokens = 0;
  await parseSSE(res.body, (event, data) => {
    try {
      const j = JSON.parse(data);
      if (event === 'content_block_delta' && j.delta && j.delta.type === 'text_delta' && j.delta.text) {
        onToken(j.delta.text);
      } else if (event === 'message_start' && j.message && j.message.usage) {
        inputTokens = j.message.usage.input_tokens || 0;
      } else if (event === 'message_delta' && j.usage) {
        outputTokens = j.usage.output_tokens || outputTokens;
      } else if (event === 'message_stop' && onUsage) {
        onUsage({ input: inputTokens, output: outputTokens, total: inputTokens + outputTokens });
      }
    } catch (_e) {}
  });
  if (onUsage && (inputTokens || outputTokens)) {
    onUsage({ input: inputTokens, output: outputTokens, total: inputTokens + outputTokens });
  }
}

/* Shared OpenAI-compatible streaming. Used by both LM Studio and Ollama.
   noStreamOptions: suppress `stream_options` for backends that
   reject that field with InvalidParameter. */
async function streamOpenAICompat({ base, label, system, messages, model, temperature, maxTokens, onToken, onUsage, signal, defaultModel, apiKey, requireKey, extraHeaders, noStreamOptions }) {
  const root = (base || '').replace(/\/+$/, '');
  if (!root) throw new Error(`No ${label} URL set — open Settings → API`);
  if (requireKey && !apiKey) throw new Error(`No ${label} API key set — open Settings → API`);
  const msgs = [];
  if (system) msgs.push({ role: 'system', content: system });
  for (const m of messages) if (m.content && String(m.content).trim()) msgs.push(m);
  const body = {
    model: model || defaultModel || 'local-model',
    messages: msgs,
    stream: true,
    max_tokens: maxTokens || _settings.maxTokens || 1024,
  };
  if (!noStreamOptions) body.stream_options = { include_usage: true };
  if (typeof temperature === 'number') body.temperature = temperature;
  /* Build headers: content-type always, Bearer auth when a key is given,
     plus any provider-specific extras (e.g. organization headers later). */
  const headers = { 'content-type': 'application/json' };
  if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;
  if (extraHeaders) Object.assign(headers, extraHeaders);
  const res = await fetch(root + '/chat/completions', {
    method: 'POST', signal,
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${label} ${res.status}: ${t.slice(0, 400)}`);
  }
  /* Reasoning models (nemotron, deepseek-r1, etc.) emit thinking into
     `delta.reasoning_content` and final answer into `delta.content`.
     Surface both so the user sees something while the model thinks. */
  let inReasoning = false;
  await parseSSE(res.body, (_event, data) => {
    if (!data || data === '[DONE]') return;
    try {
      const j = JSON.parse(data);
      const delta = j.choices && j.choices[0] && j.choices[0].delta;
      if (delta) {
        if (delta.reasoning_content) {
          if (!inReasoning) { onToken('💭 '); inReasoning = true; }
          onToken(delta.reasoning_content);
        }
        if (delta.content) {
          if (inReasoning) { onToken('\n\n'); inReasoning = false; }
          onToken(delta.content);
        }
      }
      if (j.usage && onUsage) {
        onUsage({
          input: j.usage.prompt_tokens || 0,
          output: j.usage.completion_tokens || 0,
          total: j.usage.total_tokens || 0,
        });
      }
    } catch (_e) {}
  });
}

function streamLMStudio(opts) {
  return streamOpenAICompat({
    ...opts,
    base: _settings.lmstudioUrl,
    label: 'LM Studio',
    defaultModel: _settings.lmstudioModel,
  });
}

function streamOllama(opts) {
  return streamOpenAICompat({
    ...opts,
    base: _settings.ollamaUrl,
    label: 'Ollama',
    defaultModel: _settings.ollamaModel,
  });
}

/* Hermes Agent (DEFAULT) — OpenAI-compatible chat completions through the
   same-origin /hermes/v1 proxy. serve.py injects the Bearer API_SERVER_KEY
   server-side and meters the `usage` object, so no key is needed here.
   noStreamOptions: the gateway runs a full agent and may reject the
   `stream_options` field; per-request token usage is captured server-side
   at the proxy boundary (see serve.py _hermes_proxy), so the browser
   doesn't depend on include_usage. Tool-progress (`hermes.tool.progress`)
   SSE events are ignored by parseSSE's data-only path and surfaced
   separately by the console embed (Phase 3). */
function streamHermes(opts) {
  return streamOpenAICompat({
    ...opts,
    base: _API_BASE + (_settings.hermesUrl || '/hermes/v1'),
    requireKey: false,      // Auth handled server-side via API_SERVER_KEY env var
    noStreamOptions: true,  // gateway may reject stream_options; metering is server-side
    label: 'Hermes',
    defaultModel: _settings.hermesModel || 'hermes-agent',
  });
}

/* Liveness/model probe for the Hermes gateway via the proxy. Mirrors the
   shape returned by claudecodeStatus()/codexStatus() so the UI can gate on
   `.configured`. */
async function hermesStatus() {
  try {
    const base = _API_BASE + (_settings.hermesUrl || '/hermes/v1');
    const r = await fetch(base.replace(/\/+$/, '') + '/models');
    if (!r.ok) return { configured: false, models: [] };
    const data = await r.json().catch(() => ({}));
    const models = Array.isArray(data && data.data) ? data.data.map(m => m.id) : [];
    return { configured: true, models };
  } catch (_e) { return { configured: false, models: [] }; }
}

/* Claude Code (Pro/Max subscription) — proxy spawns the local `claude` CLI
   and translates its stream-json output into the OpenAI-compat SSE shape,
   so we can reuse parseSSE here. */
async function streamClaudeCode({ system, messages, model, temperature, maxTokens, onToken, onUsage, signal, cwd }) {
  const body = {
    system,
    messages,
    model: model || _settings.claudecodeModel,
    maxTokens: maxTokens || _settings.maxTokens || 1024,
    temperature, // honored if the CLI passes it through; harmless otherwise
  };
  if (cwd) body.cwd = cwd;
  const res = await fetch(_API_BASE + '/claudecode/stream', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Claude Code ${res.status}: ${t.slice(0, 400)}`);
  }
  await parseSSE(res.body, (_event, data) => {
    if (!data || data === '[DONE]') return;
    try {
      const j = JSON.parse(data);
      const tok = j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
      if (tok) onToken(tok);
      if (j.usage && onUsage) {
        onUsage({
          input: j.usage.prompt_tokens || 0,
          output: j.usage.completion_tokens || 0,
          total: j.usage.total_tokens || 0,
        });
      }
    } catch (_e) {}
  });
}

/* Same as streamClaudeCode but hits /openclaw/stream — proxy spawns the
   CLI with file/shell tools enabled and a server-side path/tool allowlist.
   Used for ELEVATED agents only. The agent name is forwarded so the
   server-side audit log records who's making the call. */
async function streamOpenclaw({ system, messages, model, temperature, maxTokens, agentName, elevated, onToken, onUsage, signal, cwd }) {
  /* The elevated flag is set by mock-data.jsx from agent.elevated. It's a
     belt-and-suspenders check: the UI already prevents picking an
     openclaw: model on a non-elevated agent, but if that ever fails, a
     runtime refusal here keeps a non-elevated agent from getting
     computer access. */
  if (!elevated) {
    throw new Error('CafresoAI elevated provider requires the agent to be elevated. Toggle 🛡 in Settings first.');
  }
  const body = {
    system,
    messages,
    model: model || _settings.claudecodeModel,
    maxTokens: maxTokens || _settings.maxTokens || 1024,
    temperature,
    agentName: agentName || 'elevated-agent',
  };
  if (cwd) body.cwd = cwd;
  const res = await fetch(_API_BASE + '/openclaw/stream', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`CafresoAI ${res.status}: ${t.slice(0, 400)}`);
  }
  await parseSSE(res.body, (_event, data) => {
    if (!data || data === '[DONE]') return;
    try {
      const j = JSON.parse(data);
      const tok = j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
      if (tok) onToken(tok);
      if (j.usage && onUsage) {
        onUsage({
          input: j.usage.prompt_tokens || 0,
          output: j.usage.completion_tokens || 0,
          total: j.usage.total_tokens || 0,
        });
      }
    } catch (_e) {}
  });
}

async function openclawStatus() {
  try {
    const r = await fetch(_API_BASE + '/openclaw/status');
    if (!r.ok) return { configured: false };
    return await r.json();
  } catch (_e) { return { configured: false }; }
}

/* Same SSE wire format as streamOpenclaw but hits /codex/stream — the
   server spawns `codex exec --json` and maps Codex JSONL events to the
   same SSE shape. Auth comes from ~/.codex/config.toml; no key is passed. */
async function streamCodex({ system, messages, model, temperature, maxTokens, agentName, elevated, onToken, onUsage, signal, cwd }) {
  if (!elevated) {
    throw new Error('Codex provider requires the agent to be elevated. Toggle 🛡 in Settings first.');
  }
  const s = _settings;
  const body = {
    system,
    messages,
    model: model || s.codexModel || '',
    agentName: agentName || 'elevated-agent',
  };
  if (cwd) body.cwd = cwd;
  const res = await fetch(_API_BASE + '/codex/stream', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Codex ${res.status}: ${t.slice(0, 400)}`);
  }
  await parseSSE(res.body, (_event, data) => {
    if (!data || data === '[DONE]') return;
    try {
      const j = JSON.parse(data);
      const tok = j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
      if (tok) onToken(tok);
      if (j.usage && onUsage) {
        onUsage({
          input: j.usage.prompt_tokens || 0,
          output: j.usage.completion_tokens || 0,
          total: j.usage.total_tokens || 0,
        });
      }
    } catch (_e) {}
  });
}

async function codexStatus() {
  try {
    const r = await fetch(_API_BASE + '/codex/status');
    if (!r.ok) return { configured: false, binary: '', override: '', allowedDirs: [], badDirs: [] };
    return await r.json();
  } catch (_e) { return { configured: false, binary: '', override: '', allowedDirs: [], badDirs: [] }; }
}

/* Provider-prefixed model IDs (e.g. "ollama:gpt-oss:20b") let each agent
   pin a backend regardless of the global provider toggle. Bare ids fall
   back to whatever provider the user picked in Settings. */
function parseModelId(id) {
  if (!id) return { provider: null, model: null };
  for (const p of ['hermes:', 'anthropic:', 'lmstudio:', 'ollama:', 'claudecode:', 'openclaw:', 'codex:', 'google:']) {
    if (id.startsWith(p)) return { provider: p.slice(0, -1), model: id.slice(p.length) };
  }
  return { provider: null, model: id };
}

async function stream(opts) {
  if (!opts.onToken) throw new Error('stream() requires onToken');
  const { provider: pinned, model: bareModel } = parseModelId(opts.model);
  const provider = pinned || _settings.provider;
  const next = { ...opts, model: bareModel || undefined };
  if (provider === 'hermes')     return streamHermes(next);
  if (provider === 'anthropic')  return streamAnthropic(next);
  if (provider === 'claudecode') return streamClaudeCode(next);
  if (provider === 'openclaw')   return streamOpenclaw(next);
  if (provider === 'codex')      return streamCodex(next);
  if (provider === 'google')     return streamGoogle(next);
  if (provider === 'ollama')     return streamOllama(next);
  return streamLMStudio(next);
}

async function streamGoogle({ system, messages, model, temperature, maxTokens, onToken, onUsage, signal }) {
  const s = _settings;
  if (!s.googleKey) throw new Error('No Google API key — open Settings → API');

  const mdl = model || s.googleModel;

  const contents = normalizeMessages(messages).map(m => ({
    role: m.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: m.content }],
  }));

  const body = { contents };
  if (system) body.systemInstruction = { parts: [{ text: system }] };

  const generationConfig = {};
  generationConfig.maxOutputTokens = maxTokens || s.maxTokens || 1024;
  if (typeof temperature === 'number') generationConfig.temperature = temperature;
  body.generationConfig = generationConfig;

  const res = await fetch(
    'https://generativelanguage.googleapis.com/v1beta/models/' + mdl + ':streamGenerateContent?alt=sse',
    {
      method: 'POST', signal,
      headers: {
        'content-type': 'application/json',
        'x-goog-api-key': s.googleKey,
      },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Google ${res.status}: ${t.slice(0, 400)}`);
  }

  let inputTokens = 0;
  let outputTokens = 0;
  await parseSSE(res.body, (event, data) => {
    try {
      const j = JSON.parse(data);
      if (j.candidates && j.candidates[0] && j.candidates[0].content && j.candidates[0].content.parts) {
        onToken(j.candidates[0].content.parts[0].text);
      }
      if (j.usageMetadata) {
        inputTokens = j.usageMetadata.promptTokenCount || inputTokens;
        outputTokens = j.usageMetadata.candidatesTokenCount || outputTokens;
        if (onUsage) {
          onUsage({ input: inputTokens, output: outputTokens, total: inputTokens + outputTokens });
        }
      }
    } catch (_e) {}
  });
  if (onUsage && (inputTokens || outputTokens)) {
    onUsage({ input: inputTokens, output: outputTokens, total: inputTokens + outputTokens });
  }
}


async function listLMStudioModels() {
  const s = _settings;
  const base = (s.lmstudioUrl || '').replace(/\/+$/, '');
  if (!base) return [];
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3000);
  try {
    const r = await fetch(base + '/models', { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) return [];
    const j = await r.json();
    return (j.data || []).map(m => m.id).filter(Boolean);
  } catch (_e) { clearTimeout(timer); return []; }
}

/* Same-origin proxy at /ollama/* is set up by serve.py. */
const OLLAMA_BASE = '/ollama';

async function listOllamaModels() {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3000);
  try {
    const r = await fetch(OLLAMA_BASE + '/api/tags', { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) return [];
    const j = await r.json();
    return (j.models || []).map(m => ({
      name: m.name,
      size: m.size,
      parameter_size: m.details && m.details.parameter_size,
      quantization: m.details && m.details.quantization_level,
    })).filter(m => m.name);
  } catch (_e) { clearTimeout(timer); return []; }
}

async function lmStudioModelDetails() {
  const s = _settings;
  const base = (s.lmstudioUrl || '').replace(/\/+$/, '');
  if (!base) return [];
  // /v1/models is OpenAI-compatible; LM Studio's richer /api/v0/models lives at the root.
  // Derive the root from the configured base by stripping a trailing /v1.
  const root = base.replace(/\/v\d+$/, '');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3000);
  try {
    const r = await fetch(root + '/api/v0/models', { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) {
      const ids = await listLMStudioModels();
      return ids.map(id => ({ id }));
    }
    const j = await r.json();
    return (j.data || []).map(m => ({
      id: m.id,
      type: m.type,
      state: m.state,
      arch: m.arch,
      quantization: m.quantization,
      max_context_length: m.max_context_length,
    })).filter(m => m.id);
  } catch (_e) {
    clearTimeout(timer);
    const ids = await listLMStudioModels();
    return ids.map(id => ({ id }));
  }
}

async function localRegistry() {
  const [lmstudio, ollama] = await Promise.all([
    lmStudioModelDetails(),
    listOllamaModels(),
  ]);
  return { lmstudio, ollama };
}

function formatRegistry(reg) {
  if (!reg) return '';
  const lines = ['Local model registry (live snapshot, fetched just now):'];
  if (reg.lmstudio && reg.lmstudio.length) {
    lines.push(`  LM Studio (${_settings.lmstudioUrl}):`);
    for (const m of reg.lmstudio) {
      const tags = [m.type, m.state, m.quantization].filter(Boolean).join(', ');
      lines.push(`    - ${m.id}${tags ? ` [${tags}]` : ''}`);
    }
  } else {
    lines.push('  LM Studio: unreachable or no models');
  }
  if (reg.ollama && reg.ollama.length) {
    lines.push(`  Ollama (${_settings.ollamaUrl}):`);
    for (const m of reg.ollama) {
      const tags = [m.parameter_size, m.quantization].filter(Boolean).join(', ');
      lines.push(`    - ${m.name}${tags ? ` [${tags}]` : ''}`);
    }
  } else {
    lines.push('  Ollama: unreachable or no models');
  }
  lines.push('Treat this list as authoritative. If the user asks about a model not listed here, say it is not currently available — do not guess which backend hosts it.');
  return lines.join('\n');
}

async function claudecodeStatus() {
  const r = await fetch(_API_BASE + '/claudecode/status');
  return r.ok ? r.json() : { configured: false, binary: '', override: '' };
}
async function claudecodeConfigure(binary) {
  const r = await fetch(_API_BASE + '/claudecode/configure', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ binary: binary || '' }),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function claudecodeProbe() {
  try {
    const s = await claudecodeStatus();
    if (!s.configured) return { ok: false, detail: 'claude CLI not found on proxy machine' };
    return { ok: true, detail: s.binary };
  } catch (e) { return { ok: false, detail: e.message }; }
}

async function codexConfigure(binary) {
  const r = await fetch(_API_BASE + '/codex/configure', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ binary: binary || '' }),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function codexProbe() {
  try {
    const s = await codexStatus();
    if (!s.configured) return { ok: false, detail: 'codex CLI not found or allowed dirs invalid on proxy machine' };
    return { ok: true, detail: s.binary };
  } catch (e) { return { ok: false, detail: e.message }; }
}

async function probe() {
  const s = _settings;
  if (s.provider === 'hermes') {
    const h = await hermesStatus();
    if (h.configured) return { ok: true, detail: h.models.length ? `${h.models.length} model(s)` : 'gateway up' };
    return { ok: false, detail: 'gateway unreachable — is `hermes gateway` running with API_SERVER_ENABLED?' };
  }
  if (s.provider === 'claudecode') return claudecodeProbe();
  if (s.provider === 'codex') return codexProbe();
  if (s.provider === 'anthropic') {
    if (!s.anthropicKey) return { ok: false, detail: 'no key' };
    try {
      const r = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-api-key': s.anthropicKey,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
        },
        body: JSON.stringify({
          model: s.anthropicModel,
          max_tokens: 1,
          messages: [{ role: 'user', content: 'hi' }],
        }),
      });
      if (r.ok) return { ok: true, detail: 'key works' };
      const t = await r.text();
      return { ok: false, detail: `${r.status}: ${t.slice(0, 120)}` };
    } catch (e) { return { ok: false, detail: e.message }; }
  }
  if (s.provider === 'ollama') {
    const models = await listOllamaModels();
    if (models.length) return { ok: true, detail: `${models.length} model(s) loaded` };
    return { ok: false, detail: 'no models or unreachable' };
  }
  const models = await listLMStudioModels();
  if (models.length) return { ok: true, detail: `${models.length} model(s) loaded` };
  return { ok: false, detail: 'no models or unreachable' };
}

/* Build a grouped, prefixed list for model-picker UIs.
   Returns: [{ label, provider, options: [{ id, label }] }, ...] */
async function localModelOptions() {
  const groups = [];
  // Hermes Agent (default runtime) — surface first; only if the gateway's
  // API server is reachable through the proxy.
  try {
    const h = await hermesStatus();
    if (h.configured) {
      const opts = (h.models.length ? h.models : HERMES_MODELS)
        .map(m => ({ id: 'hermes:' + m, label: m }));
      groups.push({
        label: 'Hermes Agent (default · Nous Research)',
        provider: 'hermes',
        options: opts,
      });
    }
  } catch (_e) {}
  groups.push({
    label: 'Anthropic (Claude API · credits)',
    provider: 'anthropic',
    options: ANTHROPIC_MODELS.map(m => ({ id: 'anthropic:' + m, label: m })),
  });
  // Claude Code (Pro/Max subscription) — only surface if the proxy can find
  // the CLI. Otherwise picking it would just error every call.
  try {
    const cc = await claudecodeStatus();
    if (cc.configured) {
      groups.push({
        label: 'Anthropic (Pro/Max via Claude Code CLI)',
        provider: 'claudecode',
        options: CLAUDECODE_MODELS.map(m => ({ id: 'claudecode:' + m, label: m })),
      });
      groups.push({
        label: 'CafresoAI · elevated (Claude Code + tools)',
        provider: 'openclaw',
        options: OPENCLAW_MODELS.map(m => ({ id: 'openclaw:' + m, label: m })),
      });
    }
  } catch (_e) {}

  // Codex CLI — only surface if the proxy can find the codex binary.
  try {
    const cx = await codexStatus();
    if (cx.configured) {
      groups.push({
        label: 'Codex · elevated (OpenAI Codex CLI + tools)',
        provider: 'codex',
        options: CODEX_MODELS.map(m => ({ id: 'codex:' + m, label: m })),
      });
    }
  } catch (_e) {}

  groups.push({
    label: 'Google (Gemini API · credits)',
    provider: 'google',
    options: GEMINI_MODELS.map(m => ({ id: 'google:' + m, label: m })),
  });

  const [lm, ol] = await Promise.all([
    lmStudioModelDetails().catch(() => []),
    listOllamaModels().catch(() => []),
  ]);
  if (lm.length) {
    groups.push({
      label: 'LM Studio (local)',
      provider: 'lmstudio',
      options: lm.map(m => ({
        id: 'lmstudio:' + m.id,
        label: m.id + (m.state === 'loaded' ? ' ✓' : ''),
      })),
    });
  }
  if (ol.length) {
    groups.push({
      label: 'Ollama (local)',
      provider: 'ollama',
      options: ol.map(m => ({
        id: 'ollama:' + m.name,
        label: m.name + (m.parameter_size ? ` (${m.parameter_size})` : ''),
      })),
    });
  }
  return groups;
}

/* ---- Brave Web Search ---- */
async function braveSearch(query, { count = 6, signal } = {}) {
  const s = _settings;
  if (!s.braveKey) throw new Error('No Brave key — open Settings → API → Tools');
  const params = new URLSearchParams({ q: query, count: String(count), safesearch: 'moderate' });
  const r = await fetch(_API_BASE + '/brave/search?' + params.toString(), {
    headers: { 'X-Brave-Key': s.braveKey },
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`Brave ${r.status}: ${t.slice(0, 200)}`);
  }
  const j = await r.json();
  const web = (j.web && j.web.results) || [];
  return web.slice(0, count).map(w => ({
    title: w.title,
    url: w.url,
    description: (w.description || '').replace(/<[^>]+>/g, ''),
  }));
}

async function braveProbe() {
  try {
    const results = await braveSearch('hello world', { count: 1 });
    return { ok: true, detail: results.length ? `key works · ${results[0].title.slice(0,40)}` : 'key works' };
  } catch (e) { return { ok: false, detail: e.message }; }
}

/* ---- Markdown Vault (local filesystem, optional Obsidian REST plugin) ---- */
async function vaultStatus() {
  const r = await fetch(_API_BASE + '/vault/status');
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultDiscover() {
  const r = await fetch(_API_BASE + '/vault/discover');
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
/* Configure accepts a partial patch: any subset of {backend, root, restUrl, restKey}.
   For back-compat, passing a string is treated as setting the FS root. */
async function vaultConfigure(patchOrRoot) {
  const body = typeof patchOrRoot === 'string'
    ? { root: patchOrRoot }
    : (patchOrRoot || {});
  const r = await fetch(_API_BASE + '/vault/configure', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultGraph() {
  const r = await fetch(_API_BASE + '/vault/graph');
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultOpenInObsidian(path) {
  const r = await fetch(_API_BASE + '/vault/open', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultList() {
  const r = await fetch(_API_BASE + '/vault/list');
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  const j = await r.json();
  return j.files || [];
}
async function vaultRead(path) {
  const r = await fetch(_API_BASE + '/vault/note?path=' + encodeURIComponent(path));
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.text();
}
async function vaultWrite(path, content, mode = 'write') {
  const r = await fetch(_API_BASE + '/vault/note?path=' + encodeURIComponent(path) + '&mode=' + mode, {
    method: 'PUT', headers: { 'content-type': 'text/markdown' },
    body: content,
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultDelete(path) {
  const r = await fetch(_API_BASE + '/vault/note?path=' + encodeURIComponent(path), { method: 'DELETE' });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  return r.json();
}
async function vaultSearch(query, { limit = 10 } = {}) {
  const r = await fetch(_API_BASE + '/vault/search?q=' + encodeURIComponent(query) + '&limit=' + limit);
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`);
  }
  const j = await r.json();
  return j.hits || [];
}
async function vaultProbe() {
  try {
    const s = await vaultStatus();
    if (!s.configured) return { ok: false, detail: 'no vault directory configured' };
    if (!s.exists) return { ok: false, detail: `path not found: ${s.root}` };
    const files = await vaultList();
    return { ok: true, detail: `${files.length} note${files.length===1?'':'s'} · ${s.root}` };
  } catch (e) { return { ok: false, detail: e.message }; }
}

// ── CryptoVault: AES-256-GCM encrypted at-rest storage for agent API keys ────
//
// Keys are encrypted with a random device key (AES-256-GCM) stored separately
// in localStorage. Each stored key is prefixed with a 12-byte random IV so
// every write produces a distinct ciphertext.
//
// vetKeys upgrade path (ICP):
//   Replace _vaultDeviceKey() with a call to vetkd_encrypted_key from the IC
//   management canister, using the authenticated II principal as the identity.
//   The derivation produces transport key material that the client decrypts
//   into a raw AES-256 key — the rest of this vault (encrypt/decrypt) stays
//   identical. Upgrading means decryption requires an IC round-trip tied to
//   the user's hardware-backed II credential, so reading localStorage alone
//   can no longer expose the plaintext key.
//
//   Rough upgrade shape (using @dfinity/vetkeys):
//     import { VetAesGcmKey } from '@dfinity/vetkeys';
//     const vetKey = await VetAesGcmKey.fromCanister(agent, canisterId, derivationPath);
//     // then replace crypto.subtle.generateKey / importKey with vetKey.asCryptoKey()

const _VAULT_DEVICE_KEY  = 'cafresoai_device_key_v1';   // raw AES key, base64
const _VAULT_AGENT_STORE = 'cafresoai_agent_keys_v1';   // encrypted key blob map

let _vaultCryptoKey = null; // CryptoKey — cached in memory for the session

async function _vaultDeviceKey() {
  if (_vaultCryptoKey) return _vaultCryptoKey;
  const stored = localStorage.getItem(_VAULT_DEVICE_KEY);
  if (stored) {
    const raw = Uint8Array.from(atob(stored), c => c.charCodeAt(0));
    _vaultCryptoKey = await crypto.subtle.importKey(
      'raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']
    );
  } else {
    _vaultCryptoKey = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']
    );
    const exported = await crypto.subtle.exportKey('raw', _vaultCryptoKey);
    localStorage.setItem(_VAULT_DEVICE_KEY,
      btoa(String.fromCharCode(...new Uint8Array(exported))));
  }
  return _vaultCryptoKey;
}

async function _vaultEncrypt(plaintext) {
  const key = await _vaultDeviceKey();
  const iv  = crypto.getRandomValues(new Uint8Array(12));
  const enc = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv }, key, new TextEncoder().encode(plaintext)
  );
  const buf = new Uint8Array(12 + enc.byteLength);
  buf.set(iv);
  buf.set(new Uint8Array(enc), 12);
  return btoa(String.fromCharCode(...buf));
}

async function _vaultDecrypt(b64) {
  try {
    const key  = await _vaultDeviceKey();
    const buf  = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: buf.slice(0, 12) }, key, buf.slice(12)
    );
    return new TextDecoder().decode(plain);
  } catch (_) { return ''; }
}

function _vaultLoad() {
  try { return JSON.parse(localStorage.getItem(_VAULT_AGENT_STORE) || '{}'); }
  catch (_) { return {}; }
}

/** Encrypt and persist an agent API key. provider: 'anthropic' | 'openai' */
async function setAgentKey(provider, plaintext) {
  const store = _vaultLoad();
  if (!plaintext) { delete store[provider]; }
  else            { store[provider] = await _vaultEncrypt(plaintext); }
  try { localStorage.setItem(_VAULT_AGENT_STORE, JSON.stringify(store)); }
  catch (_) {}
}

/** Decrypt and return a stored agent API key, or '' if not set. */
async function getAgentKey(provider) {
  const store = _vaultLoad();
  return store[provider] ? _vaultDecrypt(store[provider]) : '';
}

/** True if a key for this provider is stored (without decrypting). */
function hasAgentKey(provider) {
  return !!_vaultLoad()[provider];
}

async function terminalStatus() {
  try {
    const r = await fetch(_API_BASE + '/terminal/status');
    if (!r.ok) return { claude: false, codex: false };
    return await r.json();
  } catch (_e) { return { claude: false, codex: false }; }
}

async function terminalStream({ messages, cli, cwd, model, projectName, sessionId, projectId, authMethod, onData, signal }) {
  // authMethod: 'subscription' — use the CLI's own OAuth login (Pro/Max plan)
  //             'apikey'       — decrypt stored BYOK key and send it
  // Default to 'subscription' for claude, 'apikey' for codex.
  const provider = cli === 'claude' ? 'anthropic' : 'openai';
  const useSubscription = (authMethod || (cli === 'claude' ? 'subscription' : 'apikey')) === 'subscription';

  // sessionId + projectId let the backend tie this stream to a long-running
  // orchestrator session so subsequent calls can resume context (e.g. CLI
  // working directory, tool state, agent memory) instead of starting fresh.
  const payload = { messages, cli, cwd, model, projectName, sessionId, projectId };
  if (useSubscription) {
    // Tell the server explicitly: don't inject any API key — let the CLI
    // authenticate via its own OAuth / subscription credentials.
    payload.authMethod = 'subscription';
  } else {
    const agentKey = await getAgentKey(provider);
    if (agentKey) payload[cli === 'claude' ? 'claudeKey' : 'codexKey'] = agentKey;
  }

  const res = await fetch(_API_BASE + '/terminal/stream', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Terminal ${res.status}: ${t.slice(0, 400)}`);
  }
  await parseSSE(res.body, (_event, data) => {
    if (!data || data === '[DONE]') return;
    try {
      const j = JSON.parse(data);
      const delta = j.choices && j.choices[0] && j.choices[0].delta;
      if (delta && delta.content) onData(delta.content, delta.type || 'text');
    } catch (_e) {}
  });
}

async function spawnTerminal({ cli, cwd }) {
  const params = new URLSearchParams({ cli, cwd });
  const r = await fetch(`${_API_BASE}/terminal/spawn?${params}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* ── Export / generate (real binary deliverables to the vault) ────────────
   Each calls a serve.py endpoint that renders the markdown / prompt and
   writes the resulting .pptx / .docx / .pdf / image / video into the vault. */
async function exportPptx(path, content) {
  const r = await fetch(_API_BASE + '/export/pptx', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
async function exportDocx(path, content) {
  const r = await fetch(_API_BASE + '/export/docx', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
async function exportPdf(path, content) {
  const r = await fetch(_API_BASE + '/export/pdf', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* Read media provider/model from settings. Falls back to OpenAI/dall-e-3. */
function _mediaConfig(kind /* 'image' | 'video' */) {
  const s = (typeof getSettings === 'function') ? getSettings() : (window.OpenclawClient && window.OpenclawClient.getSettings ? window.OpenclawClient.getSettings() : {});
  const provider = (kind === 'video' ? s.videoProvider : s.imageProvider) || 'openai';
  const model = (kind === 'video' ? s.videoModel : s.imageModel) || (kind === 'video' ? '' : 'dall-e-3');
  return { provider, model };
}

async function generateImage(path, prompt, opts = {}) {
  const cfg = _mediaConfig('image');
  const provider = opts.provider || cfg.provider;
  const model = opts.model || cfg.model;
  // Decrypt provider's API key from the on-device vault (best-effort).
  // Local providers (a1111, comfyui) don't need a key — they hit a local URL.
  let apiKey = '';
  try {
    if (provider === 'openai')  apiKey = await getAgentKey('openai')  || '';
    if (provider === 'google')  apiKey = await getAgentKey('google')  || '';
    if (provider === 'fal')     apiKey = await getAgentKey('fal')     || '';
  } catch (_e) {}
  // Resolve baseUrl for local providers from settings.
  const s = (typeof getSettings === 'function') ? getSettings() : {};
  let baseUrl = opts.baseUrl;
  if (!baseUrl) {
    if (provider === 'a1111')   baseUrl = s.a1111Url   || 'http://127.0.0.1:7860';
    if (provider === 'comfyui') baseUrl = s.comfyUrl   || 'http://127.0.0.1:8188';
  }
  const r = await fetch(_API_BASE + '/generate/image', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, prompt, provider, model, size: opts.size, apiKey, baseUrl, workflow: opts.workflow }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function generateVideo(path, prompt, opts = {}) {
  const cfg = _mediaConfig('video');
  const provider = opts.provider || cfg.provider;
  const model = opts.model || cfg.model;
  let apiKey = '';
  try {
    if (provider === 'openai')  apiKey = await getAgentKey('openai')  || '';
    if (provider === 'google')  apiKey = await getAgentKey('google')  || '';
    if (provider === 'fal')     apiKey = await getAgentKey('fal')     || '';
  } catch (_e) {}
  const s = (typeof getSettings === 'function') ? getSettings() : {};
  let baseUrl = opts.baseUrl;
  if (!baseUrl && provider === 'comfyui') baseUrl = s.comfyUrl || 'http://127.0.0.1:8188';
  const r = await fetch(_API_BASE + '/generate/video', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, prompt, provider, model, duration: opts.duration, apiKey, baseUrl, workflow: opts.workflow }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function vaultUpload(files) {
  const fd = new FormData();
  for (const f of files) fd.append('file', f, f.name);
  const r = await fetch(_API_BASE + '/vault/upload', { method: 'POST', body: fd });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function vaultOciStatus() {
  const r = await fetch(_API_BASE + '/vault/oci/status');
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function vaultOciList() {
  const r = await fetch(_API_BASE + '/vault/oci/list');
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function vaultOciSync(direction = 'push') {
  const r = await fetch(_API_BASE + '/vault/oci/sync', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ direction }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function toolExec(tool, arg, { body = '', signal, cwd } = {}) {
  const payload = { tool, arg, body };
  if (cwd) payload.cwd = cwd;
  const r = await fetch(_API_BASE + '/tools/exec', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || 'tool error');
  return j.result;
}

/* Clone a GitHub repo into the first allowed dir.
   url can be 'owner/repo' or a full https URL.
   Returns { path, name, url } on success. */
async function cloneRepo({ url, name, depth = 1 } = {}) {
  const r = await fetch(_API_BASE + '/projects/clone', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ url, name, depth }),
  });
  const j = await r.json();
  if (!j.ok) {
    const err = new Error(j.error || `clone failed (${r.status})`);
    err.detail = j.stderr || '';
    throw err;
  }
  return j;
}

/* ── VaultBridge — postMessage client to the SvelteKit parent shell ──────────
   When the HQ app runs inside ai.cafreso.com/app (iframe), the SvelteKit
   parent holds the vetKeys master key and can decrypt vault blobs on demand.
   VaultBridge proxies vault operations as postMessages to the parent.

   VaultBridge.isAvailable() returns false when the HQ app is opened standalone
   (not iframed inside the shell), allowing graceful fallback to the local API. */
(function () {
  const _pending = new Map();

  function _req(type, data) {
    return new Promise((resolve, reject) => {
      const reqId = Math.random().toString(36).slice(2, 10);
      const timer = setTimeout(() => {
        _pending.delete(reqId);
        reject(new Error('VaultBridge timeout: ' + type));
      }, 20000);
      _pending.set(reqId, { resolve, reject, timer });
      window.parent.postMessage({ type, reqId, ...data }, '*');
    });
  }

  window.addEventListener('message', function (e) {
    if (e.source !== window.parent) return;
    const { type, reqId } = e.data || {};
    if (!reqId || !_pending.has(reqId)) return;
    const { resolve, reject, timer } = _pending.get(reqId);
    clearTimeout(timer);
    _pending.delete(reqId);
    if (type === 'vault:error') {
      const err = new Error(e.data.message || 'vault error');
      err.code = e.data.code;
      reject(err);
    } else {
      resolve(e.data);
    }
  });

  window.VaultBridge = {
    /** True when running inside the SvelteKit shell iframe. */
    isAvailable() {
      try { return window.parent !== window; } catch { return false; }
    },
    /** Returns the decrypted file index: [{id, name, size, mimeType, isBinary, updatedAt}] */
    list() { return _req('vault:list', {}).then(r => r.files || []); },
    /** Decrypt and return the text content of a file by blob ID. */
    read(id) { return _req('vault:read', { id }).then(r => r.content); },
    /** Encrypt and save updated text content for an existing file. */
    write(id, content) { return _req('vault:write', { id, content }); },
    /** Create a new text file in the vault. Returns the metadata entry. */
    create(name, content) { return _req('vault:create', { name, content }).then(r => r.meta); },
    /** Delete a vault file by blob ID. */
    remove(id) { return _req('vault:delete', { id }); },
  };
})();

window.OpenclawClient = {
  getSettings, setSettings, onSettingsChange,
  stream, listLMStudioModels, probe,
  listOllamaModels, lmStudioModelDetails, localRegistry, formatRegistry,
  localModelOptions, parseModelId,
  braveSearch, braveProbe,
  vaultStatus, vaultConfigure, vaultList, vaultRead, vaultWrite, vaultDelete, vaultSearch, vaultProbe,
  vaultDiscover, vaultGraph, vaultOpenInObsidian,
  vaultUpload, vaultOciStatus, vaultOciList, vaultOciSync,
  terminalStatus, terminalStream, spawnTerminal,
  exportPptx, exportDocx, exportPdf, generateImage, generateVideo,
  setAgentKey, getAgentKey, hasAgentKey,
  claudecodeStatus, claudecodeConfigure, claudecodeProbe,
  codexConfigure, codexProbe,
  hermesStatus,
  openclawStatus, codexStatus, toolExec, cloneRepo,
  ANTHROPIC_MODELS, CLAUDECODE_MODELS, OPENCLAW_MODELS, CODEX_MODELS, GEMINI_MODELS, HERMES_MODELS,
};

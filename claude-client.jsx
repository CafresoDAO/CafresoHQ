/* ==========================================================================
   CafresoHQ — real backend client
   Dispatches streaming chat to:
     - Hermes Agent (DEFAULT — OpenAI-compatible via /hermes/v1 proxy, SSE)
     - Anthropic Messages API (browser-direct, stream SSE)
     - LM Studio / Ollama (OpenAI-compatible /v1/chat/completions, SSE)
     - Claude Code / CafresoHQ / Codex CLIs, Google Gemini
   Settings persisted in localStorage. window.CafresoHQClient is the surface.
   ========================================================================== */

// ── API base resolution ─────────────────────────────────────────────────────
// Precedence:
//   1. ?api=<base>  — injected by the shell when the UI is served cross-origin
//      from an ICP canister (e.g. ?api=https://hq.cafreso.com/u/<slug>). This is
//      the frontend/backend-split path: UI on the canister, API in the container.
//   2. A pre-set window._API_BASE (shell may inject it inline before this loads).
//   3. Derive from the page path (same-origin):
//      · https://hq.cafreso.com/u/<slug>/hq.html → '/u/<slug>' (Caddy strips it)
//      · http://localhost:8787/hq.html           → '' (direct, same-origin)
// When no override is present, behavior is identical to before (zero regression).
(function () {
  var injected = null;
  try {
    var qp = new URLSearchParams(window.location.search).get('api');
    if (qp) injected = qp;
  } catch (_e) {}
  if (injected == null && typeof window._API_BASE === 'string' && window._API_BASE_OVERRIDE) {
    injected = window._API_BASE;
  }
  // Validate an absolute injected base before adopting it. The credentialed
  // fetch wrapper sends the hq_session cookie to this origin, so a crafted
  // ?api=https://evil.example link must NOT be able to redirect API traffic.
  // Allowed: our gateway, *.cafreso.com over https, and loopback for dev.
  if (injected != null && /^https?:\/\//i.test(String(injected))) {
    var okOrigin = false;
    try {
      var u = new URL(String(injected));
      var host = u.hostname.toLowerCase();
      okOrigin =
        (u.protocol === 'https:' &&
          (host === 'cafreso.com' || host.endsWith('.cafreso.com'))) ||
        host === 'localhost' || host === '127.0.0.1' ||
        u.origin === window.location.origin;
    } catch (_e) { okOrigin = false; }
    if (!okOrigin) {
      try { console.warn('[hq] ignoring untrusted ?api= origin:', injected); } catch (_e) {}
      injected = null;
    }
  }
  window._API_BASE = (injected != null)
    ? String(injected).replace(/\/$/, '')
    : window.location.pathname.replace(/\/[^/]*$/, '');
})();
const _API_BASE = window._API_BASE;   // exposed for views.jsx / app.jsx

// ── Credentialed fetch for cross-origin (canister UI → container API) ─────────
// When the UI is on a different origin than the API, the browser won't send the
// hq_session cookie unless the request opts in with credentials:'include'. We
// install a scoped wrapper that adds it ONLY for requests whose resolved origin
// matches the API origin — third-party requests (unpkg/fonts/CDNs) and the React
// runtime are untouched, and same-origin requests are unaffected (cookies
// already flow there, so adding the flag is a harmless no-op). This centralizes
// the cross-origin credential behavior without editing every call site.
(function () {
  if (window.__cafresoApiFetchInstalled) return;
  window.__cafresoApiFetchInstalled = true;
  var _origFetch = window.fetch.bind(window);
  function apiOrigin() {
    var b = window._API_BASE || '';
    try { return /^https?:\/\//.test(b) ? new URL(b).origin : window.location.origin; }
    catch (_e) { return window.location.origin; }
  }
  function withCreds(init) {
    init = init || {};
    if (init.credentials == null) init = Object.assign({}, init, { credentials: 'include' });
    return init;
  }
  // Default timeout for API-origin requests that don't bring their own
  // AbortSignal: fail in 45s instead of spinning forever when the container
  // hangs. Streaming / long-running endpoints are exempt — aborting a fetch
  // also kills an in-progress body read, so those manage their own lifecycle.
  var NO_TIMEOUT = /(chat\/completions|\/stream|\/messages\b|\/pty|\/install\b|\/export|\/clone|generate)/;
  function withTimeout(url, init) {
    if ((init && init.signal) || NO_TIMEOUT.test(url)) return init;
    if (typeof AbortController === 'undefined') return init;
    var ctrl = new AbortController();
    setTimeout(function () {
      try { ctrl.abort(new DOMException('request timed out (45s)', 'TimeoutError')); }
      catch (_e) { try { ctrl.abort(); } catch (_e2) {} }
    }, 45000);
    return Object.assign({}, init || {}, { signal: ctrl.signal });
  }
  // Explicit helper for code that wants to be unambiguous.
  window.apiFetch = function (input, init) {
    var url = (typeof input === 'string') ? input : (input && input.url) || '';
    return _origFetch(input, withTimeout(url, withCreds(init)));
  };
  // Session-expiry detection: a 401 from the API origin means the hq_session
  // cookie died mid-use. Without this, every feature just silently hangs or
  // errors — the app looked frozen. Fire one event; the shell shows recovery
  // UI, and an embedding parent (ai.cafreso.com /hq/app) can re-mint + reload.
  var _expiredFired = false;
  function noteAuthFailure(resp) {
    if (_expiredFired || !resp || resp.status !== 401) return resp;
    _expiredFired = true;
    try { window.dispatchEvent(new CustomEvent('hq:session-expired')); } catch (_e) {}
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'hq:session-expired' }, '*');
      }
    } catch (_e) {}
    return resp;
  }
  window.fetch = function (input, init) {
    var isApi = false;
    try {
      var url = (typeof input === 'string') ? input : (input && input.url) || '';
      if (new URL(url, window.location.href).origin === apiOrigin()) {
        isApi = true;
        init = withTimeout(url, withCreds(init));
      }
    } catch (_e) {}
    var p = _origFetch(input, init);
    return isApi ? p.then(noteAuthFailure) : p;
  };
})();

const LS_KEY = 'cafresohq_client_v1';

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

/* CafresoHQ (elevated) — same Claude Code CLI but with file/shell tools
   enabled. Server-side allowlist governs paths and tool names; the
   client just picks a model. Same accepted IDs as CLAUDECODE_MODELS. */
const CAFRESOHQ_MODELS = CLAUDECODE_MODELS;

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
  /* User's personal OpenRouter key (free at https://openrouter.ai/keys).
     Stored here so the onboarding/Settings UI can re-display + re-submit it.
     The authoritative copy lives server-side in the container's
     ~/.hermes/.env (OPENROUTER_API_KEY), set via hermesSetOpenRouterKey() →
     serve.py /hermes/openrouter-key. The browser copy is convenience only. */
  openrouterKey: '',
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
    console.warn('[cafresohq] saveSettings failed:', err);
    try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: LS_KEY, error: err } })); } catch (_e) {}
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

/* Is the active provider actually usable (does the user have what it needs)?
   Drives the onboarding "no API key" nudge. Provider-aware so local/CLI backends
   (which need no browser key) don't trigger a false warning. */
function hasUsableKey(s) {
  s = s || _settings;
  switch (s.provider || 'hermes') {
    case 'anthropic':  return !!s.anthropicKey;
    case 'google':     return !!s.googleKey;
    case 'lmstudio':   return !!s.lmstudioModel;   // local — "ready" = a model picked
    case 'ollama':     return !!s.ollamaModel;
    case 'claudecode':                              // CLI-backed, no key entered in the UI
    case 'codex':      return true;
    case 'hermes':                                  // default — needs the user's OpenRouter key
    case 'openrouter':
    default:           return !!s.openrouterKey;
  }
}

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

/* Hermes capability mode: 'lite' (trimmed system prompt — fits free tiers like
   Groq free) vs 'full' (rich toolset prompt — best with BYOK / paid keys for
   heavier workloads). Backed by serve.py /hermes/capability. */
async function hermesGetCapability() {
  try {
    const r = await fetch(_API_BASE + '/hermes/capability');
    if (!r.ok) return 'lite';
    const d = await r.json().catch(() => ({}));
    return d.mode === 'full' ? 'full' : 'lite';
  } catch (_e) { return 'lite'; }
}

async function hermesSetCapability(mode) {
  const want = mode === 'full' ? 'full' : 'lite';
  const r = await fetch(_API_BASE + '/hermes/capability', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ mode: want }),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    throw new Error(`capability ${r.status}: ${t.slice(0, 160)}`);
  }
  return r.json();
}

/* Hermes model quick-switch: read the current model + curated presets, or set a
   new one (rewrites config.yaml model.default + restarts the gateway). Presets
   are OpenRouter free open-weights ids verified to accept Hermes' large prompt. */
async function hermesGetModel() {
  try {
    const r = await fetch(_API_BASE + '/hermes/model');
    if (!r.ok) return { model: '', presets: [] };
    return await r.json();
  } catch (_e) { return { model: '', presets: [] }; }
}

async function hermesSetModel(model) {
  const r = await fetch(_API_BASE + '/hermes/model', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    throw new Error(`model ${r.status}: ${t.slice(0, 160)}`);
  }
  return r.json();
}

/* Persist the user's personal free OpenRouter key.
   The production path writes it into the container's ~/.hermes/.env
   (OPENROUTER_API_KEY) and restarts the gateway, via a serve.py endpoint
   POST /hermes/openrouter-key {key}. Until that endpoint ships, this still
   stores the key in browser settings so the onboarding flow is complete and
   the value survives reloads; { serverStored:false } signals the caller that
   only the local copy was saved. Always saves locally first. */
/* Which browser-settings field holds the key for each Hermes backend. Stored
   per-provider so switching back and forth doesn't lose a key, and so the key
   can be RE-PUSHED to a freshly-recreated container (which loses ~/.hermes). */
const HERMES_PROVIDER_KEY_FIELD = {
  openrouter: 'openrouterKey',
  gemini: 'geminiKey',
  groq: 'groqKey',
};

/* Set the Hermes backend provider + its free key. Persists locally (per-provider
   field + active backend) AND pushes to the container, which rewrites config.yaml
   to that provider and restarts the gateway. Reliability path from the research:
   the user can move off OpenRouter :free (20 RPM / 50 RPD) to Gemini direct
   (≈15 RPM / 1500 RPD) or Groq with their own free key. */
async function hermesSetProvider(provider, key, model) {
  const prov = (provider || 'openrouter').toLowerCase();
  const field = HERMES_PROVIDER_KEY_FIELD[prov] || 'openrouterKey';
  const trimmed = String(key || '').trim();
  // persist locally so it survives reload AND container recreate (re-push)
  setSettings({ hermesBackend: prov, [field]: trimmed });
  if (!trimmed) return { ok: true, serverStored: false, detail: 'cleared' };
  try {
    const r = await fetch(_API_BASE + '/hermes/provider', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ provider: prov, key: trimmed, model: model || '' }),
    });
    if (r.ok) {
      const d = await r.json().catch(() => ({}));
      return { ok: true, serverStored: true, ...d };
    }
    // Old container without /hermes/provider (pre-overhaul image): fall back to
    // the legacy OpenRouter-only endpoint so existing OpenRouter users don't
    // regress before the new image rolls out. (Gemini/Groq need the new image.)
    if (r.status === 404 && prov === 'openrouter') {
      try {
        const r2 = await fetch(_API_BASE + '/hermes/openrouter-key', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ key: trimmed }),
        });
        if (r2.ok) { const d = await r2.json().catch(() => ({})); return { ok: true, serverStored: true, ...d }; }
      } catch (_e) {}
    }
    const t = await r.text().catch(() => '');
    return { ok: true, serverStored: false, detail: `server ${r.status}: ${t.slice(0, 120)}` };
  } catch (e) {
    return { ok: true, serverStored: false, detail: 'offline — saved locally' };
  }
}

/* Read the container's CURRENT backend + whether it has a key. Used on load to
   decide whether to re-push the saved key after a recreate. */
async function hermesGetProvider() {
  try {
    const r = await fetch(_API_BASE + '/hermes/provider');
    if (!r.ok) return { provider: 'openrouter', model: '', configured: false };
    return await r.json();
  } catch (_e) { return { provider: 'openrouter', model: '', configured: false }; }
}

/* The 'keys vanish on recreate' fix: if the freshly-provisioned container has no
   provider key, silently re-apply the one saved in this browser. Best-effort —
   never throws, never blocks startup. */
async function hermesEnsureProvider() {
  try {
    const cur = await hermesGetProvider();
    if (cur && cur.configured) return { restored: false, configured: true };
    const s = getSettings();
    const prov = (s.hermesBackend || 'openrouter').toLowerCase();
    const field = HERMES_PROVIDER_KEY_FIELD[prov] || 'openrouterKey';
    const key = (s[field] || '').trim();
    if (!key) return { restored: false, configured: false };
    await hermesSetProvider(prov, key, '');
    return { restored: true, provider: prov };
  } catch (_e) { return { restored: false, error: true }; }
}

/* Back-compat wrapper — the old OpenRouter-only entry point. */
async function hermesSetOpenRouterKey(key) {
  return hermesSetProvider('openrouter', key, '');
}

/* Hermes agent-config portability: download the container's config (no keys)
   as a JSON envelope, or apply one — also accepts a raw ~/.hermes/config.yaml
   so existing Hermes users can bring their setup to HQ in one step. */
async function hermesExportConfig() {
  const r = await fetch(_API_BASE + '/hermes/config/export');
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
async function hermesImportConfig(text) {
  let payload;
  try {
    const parsed = JSON.parse(text);
    // our export envelope
    payload = { config_yaml: parsed.config_yaml || '', capability: parsed.capability || '' };
  } catch (_e) {
    // raw config.yaml
    payload = { config_yaml: String(text || '') };
  }
  const r = await fetch(_API_BASE + '/hermes/config/import', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* Agent fleet status + on-demand install. The HQ ships with Hermes (default,
   always installed); Claude Code and Codex can be added on demand via `npm i -g`,
   which the backend runs synchronously — so agentsInstall() can take 30-60 s. */
async function agentsStatus() {
  try {
    const r = await fetch(_API_BASE + '/agents');
    if (!r.ok) return { agents: [] };
    return await r.json();
  } catch (_e) { return { agents: [] }; }
}

async function agentsInstall(agent) {
  const r = await fetch(_API_BASE + '/agents/install', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ agent }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 202) {
    throw new Error(d.error || `install ${r.status}`);
  }
  if (d.error) throw new Error(d.error);
  // New backend: 202 + background job → poll status until it settles. The
  // promise still resolves with the final result, so callers are unchanged.
  // Old backend: a 200 with the final result lands in the return below.
  if (r.status === 202) {
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
      await new Promise(res => setTimeout(res, 3000));
      let s;
      try {
        const sr = await fetch(_API_BASE + '/agents/install/status?agent=' + encodeURIComponent(agent));
        s = await sr.json().catch(() => ({}));
      } catch (_e) { continue; }   // transient — keep polling
      if (s.status === 'done') return s;
      if (s.status === 'error') throw new Error(s.error || 'install failed');
    }
    throw new Error('install still running after 10 minutes — check Settings → Code Agents later');
  }
  return d;
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

/* Same as streamClaudeCode but hits /cafresohq/stream — proxy spawns the
   CLI with file/shell tools enabled and a server-side path/tool allowlist.
   Used for ELEVATED agents only. The agent name is forwarded so the
   server-side audit log records who's making the call. */
async function streamCafresoHQ({ system, messages, model, temperature, maxTokens, agentName, elevated, onToken, onUsage, signal, cwd }) {
  /* The elevated flag is set by hq-runtime.jsx from agent.elevated. It's a
     belt-and-suspenders check: the UI already prevents picking an
     cafresohq: model on a non-elevated agent, but if that ever fails, a
     runtime refusal here keeps a non-elevated agent from getting
     computer access. */
  if (!elevated) {
    throw new Error('CafresoHQ elevated provider requires the agent to be elevated. Toggle 🛡 in Settings first.');
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
  const res = await fetch(_API_BASE + '/cafresohq/stream', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`CafresoHQ ${res.status}: ${t.slice(0, 400)}`);
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

async function cafresohqStatus() {
  try {
    const r = await fetch(_API_BASE + '/cafresohq/status');
    if (!r.ok) return { configured: false };
    return await r.json();
  } catch (_e) { return { configured: false }; }
}

/* Same SSE wire format as streamCafresoHQ but hits /codex/stream — the
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
  for (const p of ['hermes:', 'anthropic:', 'lmstudio:', 'ollama:', 'claudecode:', 'cafresohq:', 'codex:', 'google:']) {
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
  if (provider === 'cafresohq')   return streamCafresoHQ(next);
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
        label: 'CafresoHQ · elevated (Claude Code + tools)',
        provider: 'cafresohq',
        options: CAFRESOHQ_MODELS.map(m => ({ id: 'cafresohq:' + m, label: m })),
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
async function vaultRename(from, to) {
  const r = await fetch(_API_BASE + '/vault/rename', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ from, to }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
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

const _VAULT_DEVICE_KEY  = 'cafresohq_device_key_v1';   // raw AES key, base64
const _VAULT_AGENT_STORE = 'cafresohq_agent_keys_v1';   // encrypted key blob map

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
  // authMethod: 'subscription' — use the CLI's own OAuth / login credentials
  //             'apikey'       — decrypt stored BYOK key and send it
  // Default to 'subscription' for claude/gemini (CLI login), 'apikey' for codex.
  const provider = cli === 'claude' ? 'anthropic' : cli === 'gemini' ? 'google' : 'openai';
  const defaultAuth = (cli === 'claude' || cli === 'gemini') ? 'subscription' : 'apikey';
  const useSubscription = (authMethod || defaultAuth) === 'subscription';

  // sessionId + projectId let the backend tie this stream to a long-running
  // orchestrator session so subsequent calls can resume context (e.g. CLI
  // working directory, tool state, agent memory) instead of starting fresh.
  const payload = { messages, cli, cwd, model, projectName, sessionId, projectId };
  if (useSubscription) {
    // Tell the server explicitly: don't inject any API key — let the CLI
    // authenticate via its own OAuth / login credentials.
    payload.authMethod = 'subscription';
  } else {
    const agentKey = await getAgentKey(provider);
    const keyField = cli === 'claude' ? 'claudeKey' : cli === 'gemini' ? 'geminiKey' : 'codexKey';
    if (agentKey) payload[keyField] = agentKey;
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
  const s = (typeof getSettings === 'function') ? getSettings() : (window.CafresoHQClient && window.CafresoHQClient.getSettings ? window.CafresoHQClient.getSettings() : {});
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

/* Drop files into a project's working directory so agents (FILE_READ /
   DIR_LIST) and the preview pane can use them. dirPath is the project's path
   (?path=); omitting it lands in the server's first allowed dir. */
async function fsUpload(dirPath, files) {
  const fd = new FormData();
  for (const f of files) fd.append('file', f, f.name);
  const qs = dirPath ? ('?path=' + encodeURIComponent(dirPath)) : '';
  const r = await fetch(_API_BASE + '/fs/upload' + qs, { method: 'POST', body: fd });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* Working-tree file manager — mkdir / rename(move) / delete. Each is guarded
   server-side by the same allowed-dirs whitelist as FILE_WRITE. */
async function _fsMutate(route, body) {
  const r = await fetch(_API_BASE + route, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
function fsMkdir(path)      { return _fsMutate('/fs/mkdir', { path }); }
function fsRename(from, to) { return _fsMutate('/fs/rename', { from, to }); }
function fsDelete(path)     { return _fsMutate('/fs/delete', { path }); }

/* Read a text file's FULL content + conflict metadata (mtime/hash) in one GET.
   The Workspace editor uses this instead of FILE_READ so it gets the whole file
   (FILE_READ truncates at 8000) and the headers conflict-safety needs. */
async function fsReadText(path) {
  const r = await fetch(_API_BASE + '/fs/file?path=' + encodeURIComponent(path), { cache: 'no-store' });
  if (!r.ok) { let j = {}; try { j = await r.json(); } catch (_e) {} throw new Error(j.error || `HTTP ${r.status}`); }
  const content = await r.text();
  return { content, mtime: r.headers.get('X-File-Mtime') || '', hash: r.headers.get('X-File-Hash') || '' };
}
/* Cheap stat for the pre-save conflict check — {ok, mtime, hash, size}, no body. */
async function fsStat(path) {
  const r = await fetch(_API_BASE + '/fs/stat?path=' + encodeURIComponent(path), { cache: 'no-store' });
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

/* Is the backend (per-user container via the gateway) actually reachable?
   Probes _API_BASE + /health. On the asset canister WITHOUT a ?api gateway,
   _API_BASE is the canister origin which has no /health → false → the UI knows
   it's running backend-less (no vault/graph/chat/terminal). */
async function backendHealth() {
  try {
    const r = await fetch(_API_BASE + '/health', { cache: 'no-store', credentials: 'include' });
    return r.ok;
  } catch (_e) { return false; }
}
/** The resolved backend base URL (gateway when cross-origin, '' when same-origin). */
function backendBase() { return _API_BASE || ''; }

window.CafresoHQClient = {
  getSettings, setSettings, onSettingsChange, hasUsableKey, backendHealth, backendBase,
  stream, listLMStudioModels, probe,
  listOllamaModels, lmStudioModelDetails, localRegistry, formatRegistry,
  localModelOptions, parseModelId,
  braveSearch, braveProbe,
  vaultStatus, vaultConfigure, vaultList, vaultRead, vaultWrite, vaultDelete, vaultRename, vaultSearch, vaultProbe,
  vaultDiscover, vaultGraph, vaultOpenInObsidian,
  vaultUpload, vaultOciStatus, vaultOciList, vaultOciSync,
  terminalStatus, terminalStream, spawnTerminal,
  exportPptx, exportDocx, exportPdf, generateImage, generateVideo,
  setAgentKey, getAgentKey, hasAgentKey,
  claudecodeStatus, claudecodeConfigure, claudecodeProbe,
  codexConfigure, codexProbe,
  hermesStatus, hermesGetCapability, hermesSetCapability, hermesGetModel, hermesSetModel,
  hermesSetOpenRouterKey, hermesSetProvider, hermesGetProvider, hermesEnsureProvider,
  hermesExportConfig, hermesImportConfig,
  agentsStatus, agentsInstall,
  cafresohqStatus, codexStatus, toolExec, cloneRepo, fsUpload, fsMkdir, fsRename, fsDelete, fsReadText, fsStat,
  ANTHROPIC_MODELS, CLAUDECODE_MODELS, CAFRESOHQ_MODELS, CODEX_MODELS, GEMINI_MODELS, HERMES_MODELS,
};

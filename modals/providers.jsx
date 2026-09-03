import { ModelPicker } from './base.jsx';
import { HQ } from '../hq-runtime.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
import { useSettingsStore } from './base.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

/* Mobile keyboards (iOS Safari especially) auto-capitalize the first
   character typed into a plain text field even with autocapitalize "off"
   honored inconsistently across versions — "https://" silently becomes
   "Https://", which fails to resolve with zero visible sign anything's
   wrong (the field looks identical). The scheme is case-insensitive per
   spec, so lowercasing it here is always safe; nothing after the scheme is
   touched — host/path can be genuinely case-sensitive, and a token/key
   value must never go through this at all. Same defect, same fix as the
   2026-07-22 Workspaces/Fleet Settings page fix — that one never reached
   this file's URL fields (VaultTab's REST URL, MediaTab's local-provider
   base URLs), which is the actual Settings modal a boss uses day to day. */
function normalizeUrlScheme(v) {
  return (v || '').replace(/^(https?):\/\//i, (_, s) => s.toLowerCase() + '://');
}
/* Every URL/token/path field below gets these four — belt for the scheme
   normalizer above, suspenders for the fields (folder paths, API keys)
   the normalizer can't safely touch at all: autocapitalize/autocorrect off
   so the mobile keyboard never mangles the first character in the first
   place, autocomplete off so a browser/password-manager suggestion can't
   silently overwrite a real key, spellcheck off so nothing gets a red
   squiggle (or a tap-to-replace) under a token. */
const NO_MANGLE_PROPS = { autoCapitalize: 'off', autoCorrect: 'off', autoComplete: 'off', spellCheck: false };
const HBACKENDS = {
  openrouter: { label: 'OpenRouter', field: 'openrouterKey', ph: 'sk-or-v1-…',
                link: 'https://openrouter.ai/keys', linkText: 'openrouter.ai/keys',
                note: 'free open-weights · no per-request size cap' },
  gemini:     { label: 'Google Gemini', field: 'geminiKey', ph: 'AIza…',
                link: 'https://aistudio.google.com/apikey', linkText: 'aistudio.google.com/apikey',
                note: 'most reliable free tier · ~15/min · 1500/day (Flash)' },
  groq:       { label: 'Groq', field: 'groqKey', ph: 'gsk_…',
                link: 'https://console.groq.com/keys', linkText: 'console.groq.com/keys',
                note: 'fastest free tier · use Lite capability (free size limits)' },
  // Local backends: your own hardware, so no key — configured by a URL instead.
  // Both write `provider: lmstudio` server-side (hermes has no ollama provider).
  lmstudio:   { label: 'LM Studio', local: true, urlField: 'hermesLmUrl',
                ph: 'http://localhost:1234/v1',
                note: 'your own GPU · no key, no quota, no per-token cost' },
  ollama:     { label: 'Ollama', local: true, urlField: 'hermesOlUrl',
                ph: 'http://localhost:11434/v1',
                note: 'your own GPU · OpenAI-compatible endpoint' },
};

function ApiTab() {
  const C = CafresoHQClient;
  const [s, update] = useSettingsStore();
  const [probing, setProbing] = useStateM(false);
  const [probeResult, setProbeResult] = useStateM(null);
  const [lmModels, setLmModels] = useStateM([]);
  const [olModels, setOlModels] = useStateM([]);
  // Hermes capability: 'lite' vs 'full' system-prompt size. Backed by serve.py
  // /hermes/capability (rewrites config.yaml + restarts gateway).
  const [capMode, setCapMode] = useStateM('lite');
  const [capBusy, setCapBusy] = useStateM(false);
  // Hermes model quick-switch: current model + curated free presets (incl. Nemotron 120B).
  const [hModel, setHModel] = useStateM('');
  const [hPresets, setHPresets] = useStateM([]);
  const [hBusy, setHBusy] = useStateM(false);
  useEffectM(() => {
    if (C && C.hermesGetCapability) C.hermesGetCapability().then(setCapMode).catch(()=>{});
    if (C && C.hermesGetModel) C.hermesGetModel().then(r => { setHModel(r.model || ''); setHPresets(r.presets || []); }).catch(()=>{});
  }, []);
  const changeCap = async (mode) => {
    if (mode === capMode || capBusy) return;
    const prev = capMode; setCapMode(mode); setCapBusy(true);
    try { await C.hermesSetCapability(mode); }
    catch (e) { setCapMode(prev); setProbeResult({ ok:false, detail:'capability: ' + e.message }); }
    finally { setCapBusy(false); }
  };
  const changeModel = async (model) => {
    if (!model || model === hModel || hBusy) return;
    const prev = hModel; setHModel(model); setHBusy(true);
    try { await C.hermesSetModel(model); }
    catch (e) { setHModel(prev); setProbeResult({ ok:false, detail:'model: ' + e.message }); }
    finally { setHBusy(false); }
  };

  // Hermes backend service (which free LLM powers Hermes). Init from the saved
  // preference, then reconcile with whatever the container actually has live.
  const [hBackend, setHBackend] = useStateM(s.hermesBackend || 'openrouter');
  const [keyBusy, setKeyBusy] = useStateM(false);
  useEffectM(() => {
    if (C && C.hermesGetProvider) C.hermesGetProvider()
      .then(r => { if (r && r.configured && HBACKENDS[r.provider]) setHBackend(r.provider); })
      .catch(() => {});
  }, []);
  const changeBackend = (prov) => {
    if (!HBACKENDS[prov]) return;
    setHBackend(prov); update({ hermesBackend: prov });
  };
  const saveKey = async (prov, val) => {
    const meta = HBACKENDS[prov]; if (!meta) return;
    if (val === (s[meta.field] || '')) return;
    setKeyBusy(true); setProbeResult(null);
    try {
      let r = { serverStored: false };
      if (C && C.hermesSetProvider) r = await C.hermesSetProvider(prov, val, '');
      else update({ [meta.field]: val, hermesBackend: prov });
      if (!val) setProbeResult({ ok: true, detail: `${meta.label} key cleared` });
      else if (r && r.serverStored) setProbeResult({ ok: true, detail: `${meta.label} applied · gateway reloading (~15s)` });
      else setProbeResult({ ok: false, detail: (r && r.detail) || 'saved locally only' });
    } catch (e) { setProbeResult({ ok: false, detail: e.message }); }
    finally { setKeyBusy(false); }
  };

  // ── local Hermes backend (LM Studio / Ollama in the CONTAINER) ─────────────
  // Separate from the browser-side lmstudio/ollama settings below: this one is
  // what the agents, night shifts and the search worker actually run on.
  const [hbModels, setHbModels] = useStateM(null);   // null = not probed yet
  const hbMeta = HBACKENDS[hBackend] || {};
  const hbUrl = (hbMeta.local && (s[hbMeta.urlField] || hbMeta.ph)) || '';
  useEffectM(() => {
    if (!hbMeta.local || !C || !C.hermesLocalModels) { setHbModels(null); return; }
    C.hermesLocalModels(hbUrl).then(r => setHbModels(r.models || []))
      .catch(() => setHbModels([]));
  }, [hBackend, hbUrl]);
  const saveLocalBackend = async (prov, url, model) => {
    const meta = HBACKENDS[prov]; if (!meta) return;
    setKeyBusy(true); setProbeResult(null);
    try {
      update({ [meta.urlField]: url, hermesBackend: prov });
      const r = await C.hermesSetProvider(prov, '', model || '', url);
      if (r && r.serverStored) {
        setProbeResult({ ok: true, detail: `${meta.label} applied · gateway reloading (~15s)` });
        if (r.model) setHModel(r.model);
      } else {
        setProbeResult({ ok: false, detail: (r && r.detail) || 'could not apply' });
      }
    } catch (e) { setProbeResult({ ok: false, detail: e.message }); }
    finally { setKeyBusy(false); }
  };

  useEffectM(() => {
    if (s.provider === 'lmstudio') {
      CafresoHQClient.listLMStudioModels().then(setLmModels).catch(() => setLmModels([]));
    } else if (s.provider === 'ollama') {
      CafresoHQClient.listOllamaModels().then(ms => setOlModels(ms.map(m => m.name))).catch(() => setOlModels([]));
    }
  }, [s.provider, s.lmstudioUrl, s.ollamaUrl]);

  const runProbe = async () => {
    setProbing(true); setProbeResult(null);
    try {
      const r = await CafresoHQClient.probe();
      setProbeResult(r);
      if (s.provider === 'lmstudio') {
        setLmModels(await CafresoHQClient.listLMStudioModels());
      } else if (s.provider === 'ollama') {
        const ms = await CafresoHQClient.listOllamaModels();
        setOlModels(ms.map(m => m.name));
      } else if (s.provider === 'google') { // Add this block for Google models
        // No specific model listing needed here as it's done in claude-client.jsx
      }
    } catch (e) { setProbeResult({ ok:false, detail: e.message }); }
    setProbing(false);
  };

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>PROVIDER</h4>
        <div className="row-knob">
          {/* THIS browser's brain. Distinct from the Hermes brain below, which
              is what the container runs — wanting LM Studio here and OpenRouter
              in the container (or vice versa) is legitimate, so they don't merge. */}
          <div><div className="lbl">Brain (this browser)</div><div className="sub">what the UI on this machine talks to directly</div></div>
          <select value={s.provider} onChange={e=>update({provider:e.target.value})}>
            <option value="lmstudio">LM Studio (local)</option>
            <option value="ollama">Ollama (local)</option>
            <option value="anthropic">Anthropic — API credits</option>
            <option value="google">Google (Gemini) — API credits</option>
            <option value="claudecode">Anthropic — Pro/Max (via Claude Code)</option>
            <option value="hermes">Hermes (default · runs in your office)</option>
            <option value="codex">OpenAI Codex CLI (local + tools)</option>
          </select>
          <span className="hint" style={{maxWidth:240}}>fallback for agents whose model isn't pinned</span>
        </div>
        {/* Cloud presets only — a local backend gets its own model row below,
            driven by what that box actually has LOADED. */}
        {s.provider === 'hermes' && !hbMeta.local && (
          <div className="row-knob">
            <div>
              <div className="lbl">Model</div>
              <div className="sub">
                {hBusy ? 'Switching model… (~10s)'
                  : 'Free open-weights running in your office · switch anytime'}
              </div>
            </div>
            <select value={hPresets.some(p=>p.id===hModel) ? hModel : ''}
                    disabled={hBusy} onChange={e=>changeModel(e.target.value)}>
              {!hPresets.some(p=>p.id===hModel) && hModel &&
                <option value="">{hModel} (custom)</option>}
              {hPresets.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
        )}
        {s.provider === 'hermes' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Hermes brain (runs in your office)</div>
              <div className="sub">{HBACKENDS[hBackend]
                ? HBACKENDS[hBackend].note + ' · runs your agents, night shifts and search worker'
                : 'free LLM behind Hermes'}</div>
            </div>
            <select value={hBackend} disabled={keyBusy} onChange={e=>changeBackend(e.target.value)}>
              <option value="openrouter">OpenRouter (default)</option>
              <option value="gemini">Google Gemini (most reliable free)</option>
              <option value="groq">Groq (fastest free)</option>
              <option value="lmstudio">LM Studio (your own GPU)</option>
              <option value="ollama">Ollama (your own GPU)</option>
            </select>
          </div>
        )}
        {s.provider === 'hermes' && hbMeta.local && (
          <div className="row-knob">
            <div>
              <div className="lbl">{hbMeta.label} endpoint</div>
              <div className="sub">
                {keyBusy ? 'applying · gateway reloading (~15s)…'
                  : 'where your office reaches it — must be a private or localhost address'}
              </div>
            </div>
            <input type="text" key={'u' + hBackend} placeholder={hbMeta.ph}
              autoComplete="off" spellCheck={false} style={{width:200}} disabled={keyBusy}
              defaultValue={s[hbMeta.urlField] || hbMeta.ph}
              onBlur={e => saveLocalBackend(hBackend, e.target.value.trim(), hModel)}/>
          </div>
        )}
        {s.provider === 'hermes' && hbMeta.local && (
          <div className="row-knob">
            <div>
              <div className="lbl">Model</div>
              <div className="sub">
                {hbModels === null ? 'checking what your backend has…'
                  : hbModels.length === 0
                    ? "couldn't reach that endpoint — you can still type a model id"
                    : 'a model must be LOADED to answer; unloaded ones fail or stall on first use'}
              </div>
            </div>
            {hbModels && hbModels.length ? (
              <select value={hModel} disabled={keyBusy || hBusy}
                      onChange={e => saveLocalBackend(hBackend, hbUrl, e.target.value)}>
                {!hbModels.some(m => m.id === hModel) && hModel && (
                  <option value={hModel}>{hModel} (not on this backend)</option>
                )}
                {hbModels.map(m => (
                  <option key={m.id} value={m.id}>
                    {(m.loaded === true ? '● ' : m.loaded === false ? '○ ' : '') + m.id}
                    {m.loaded === false ? ' — not loaded' : ''}
                  </option>
                ))}
              </select>
            ) : (
              <input type="text" key={'m' + hBackend} placeholder="model id"
                autoComplete="off" spellCheck={false} style={{width:200}} disabled={keyBusy}
                defaultValue={hModel}
                onBlur={e => saveLocalBackend(hBackend, hbUrl, e.target.value.trim())}/>
            )}
          </div>
        )}
        {s.provider === 'hermes' && HBACKENDS[hBackend] && !hbMeta.local && (
          <div className="row-knob">
            <div>
              <div className="lbl">{HBACKENDS[hBackend].label} key</div>
              <div className="sub">
                {keyBusy ? 'applying key · gateway reloading (~15s)…' : (
                  <>your free personal key · get one at{' '}
                  <a href={HBACKENDS[hBackend].link} target="_blank" rel="noopener noreferrer"
                     style={{color:'var(--accent-rose, #c45)', textDecoration:'underline'}}>
                    {HBACKENDS[hBackend].linkText}
                  </a></>
                )}
              </div>
            </div>
            <input type="password" key={hBackend} placeholder={HBACKENDS[hBackend].ph}
              autoComplete="off" spellCheck={false} style={{width:200}} disabled={keyBusy}
              defaultValue={s[HBACKENDS[hBackend].field] || ''}
              onBlur={e => saveKey(hBackend, e.target.value.trim())}/>
          </div>
        )}
        {s.provider === 'hermes' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Agent capability</div>
              <div className="sub">
                {capBusy ? 'Reloading agent… (~10s)'
                  : capMode === 'full'
                    ? 'Full toolset in every prompt — needs a larger/paid key (free tiers will 413).'
                    : 'Lite: trimmed prompt that fits free tiers (e.g. Groq free). Tools load on demand.'}
              </div>
            </div>
            <select value={capMode} disabled={capBusy} onChange={e=>changeCap(e.target.value)}>
              <option value="lite">Lite — free-tier safe</option>
              <option value="full">Full — BYOK / heavy</option>
            </select>
          </div>
        )}
        <div className="row-knob">
          <div><div className="lbl">Max tokens per reply</div><div className="sub">caps response length</div></div>
          <input type="number" min="64" max="8192" step="64" style={{width:90}}
            value={s.maxTokens} onChange={e=>update({maxTokens: parseInt(e.target.value)||1024})}/>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Connection test</div>
            <div className="sub">
              {probing ? 'probing…'
                : probeResult ? (probeResult.ok ? `✓ ${probeResult.detail}` : `✕ ${probeResult.detail}`)
                : 'verifies keys/URL work'}
            </div>
          </div>
          <button className="px-btn secondary" onClick={runProbe} disabled={probing}>
            {probing ? '…' : 'TEST'}
          </button>
        </div>
      </div>

      {/* Sub-agent panel — controls the model used by transient sub-agents
          spawned via [SPAWN_SUBAGENT]. Default 'inherit' uses the spawner's
          model. Pinning a small/cheap model here is useful when sub-agents
          are doing high-volume one-shot tasks (e.g. summaries) and you
          don't want to burn the parent's premium model on each. */}
      <div className="cb-panel">
        <h4>HELPER MODEL</h4>
        <div className="row-knob">
          <div>
            <div className="lbl">Helper brain</div>
            <div className="sub">
              {s.subagentModel === 'inherit'
                ? 'Helpers inherit the model of whoever brought them in.'
                : `All helpers pinned to: ${s.subagentModel}`}
            </div>
          </div>
          {s.subagentModel === 'inherit' ? (
            <button className="px-btn secondary"
                    onClick={() => update({ subagentModel: CafresoHQClient.getSettings().anthropicModel ? 'anthropic:' + CafresoHQClient.getSettings().anthropicModel : 'inherit' })}>
              PIN A MODEL…
            </button>
          ) : (
            <button className="px-btn secondary"
                    onClick={() => update({ subagentModel: 'inherit' })}>
              RESET TO INHERIT
            </button>
          )}
        </div>
        {s.subagentModel !== 'inherit' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Pinned model</div>
              <div className="sub">used for every one-shot helper</div>
            </div>
            <ModelPicker value={s.subagentModel}
                         onChange={(id) => update({ subagentModel: id || 'inherit' })} />
          </div>
        )}
        <div className="row-knob">
          <div>
            <div className="lbl">Per-spawn override</div>
            <div className="sub">
              Spawning agents can override this with
              <code style={{margin:'0 4px'}}>[SPAWN_SUBAGENT: role | model:&lt;id&gt;]</code>
              syntax — that always wins.
            </div>
          </div>
          <span className="hint" style={{maxWidth:240}}>e.g. <code>[SPAWN_SUBAGENT: code-reviewer | model:claudecode:sonnet]</code></span>
        </div>
      </div>

      {s.provider === 'claudecode' && <ClaudeCodePanel s={s} update={update} />}
      {s.provider === 'codex' && <CodexPanel s={s} update={update} />}

      {/* These two used to be written out here, each gated on
          `s.provider`, and they are the same two fields BrowserKeysTab now
          renders in Settings → Connections. One definition rather than two:
          this component is unmounted, so a second copy would drift without
          anyone noticing — which is most of how it got into this state. The
          provider gate is gone with them; see the note on BrowserKeysTab
          for why that gate was asking a question nothing can answer. */}
      <BrowserKeysTab />

      {s.provider === 'lmstudio' && (
        <div className="cb-panel">
          <h4>LM STUDIO</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>BASE URL</label>
            <input placeholder="/lmstudio/v1"
              value={s.lmstudioUrl} onChange={e=>update({lmstudioUrl: e.target.value})}/>
            <span className="hint">OpenAI-compatible endpoint root (use the /lmstudio/v1 proxy to avoid CORS)</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            {lmModels.length ? (
              <select value={s.lmstudioModel} onChange={e=>update({lmstudioModel: e.target.value})}>
                <option value="">— server default —</option>
                {lmModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input placeholder="auto-detect via TEST, or type a model id"
                value={s.lmstudioModel} onChange={e=>update({lmstudioModel: e.target.value})}/>
            )}
            <span className="hint">{lmModels.length ? `${lmModels.length} loaded` : 'hit TEST to list loaded models'}</span>
          </div>
        </div>
      )}

      {s.provider === 'ollama' && (
        <div className="cb-panel">
          <h4>OLLAMA</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>BASE URL</label>
            <input placeholder="/ollama/v1"
              value={s.ollamaUrl} onChange={e=>update({ollamaUrl: e.target.value})}/>
            <span className="hint">OpenAI-compatible endpoint (use the /ollama/v1 proxy to avoid CORS)</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            {olModels.length ? (
              <select value={s.ollamaModel} onChange={e=>update({ollamaModel: e.target.value})}>
                <option value="">— server default —</option>
                {olModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input placeholder="auto-detect via TEST, or type a model id"
                value={s.ollamaModel} onChange={e=>update({ollamaModel: e.target.value})}/>
            )}
            <span className="hint">{olModels.length ? `${olModels.length} loaded` : 'hit TEST to list loaded models'}</span>
          </div>
        </div>
      )}


      <BraveTab />
      <VaultTab />
    </div>
  );
}

function ClaudeCodePanel({ s, update }) {
  const [status, setStatus] = useStateM({ configured: false, binary: '', override: '' });
  const [draft, setDraft] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);

  const refresh = async () => {
    try {
      const st = await CafresoHQClient.claudecodeStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await CafresoHQClient.claudecodeConfigure(draft.trim());
      await refresh();
      setMsg({ ok: true, text: draft.trim() ? 'override saved' : 'cleared (using PATH)' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  return (
    <div className="cb-panel">
      <h4>🟣 CLAUDE CODE (PRO / MAX)</h4>
      <div className="hint" style={{marginBottom:10}}>
        Routes calls through your locally-installed <code>claude</code> CLI, which is already
        authenticated against your Pro/Max subscription. Each call spawns a subprocess on the
        proxy machine, so requests are slightly slower than direct API but use your subscription
        instead of API credits. Tool use inside Claude Code is disabled so CafresoHQ's own
        tool loop stays in charge.
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">CLI status</div>
          <div className="sub">
            {status.configured
              ? <>✓ found at <code>{status.binary}</code></>
              : '✕ claude binary not found on the proxy machine'}
            {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
          </div>
        </div>
      </div>
      <div className="form-row" style={{marginBottom:8,marginTop:6}}>
        <label>OVERRIDE PATH</label>
        <input placeholder="(blank = look up `claude` on PATH)"
          value={draft} onChange={e=>setDraft(e.target.value)}/>
        <span className="hint">absolute path to a different claude binary; leave blank to auto-detect</span>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Default model</div><div className="sub">used when an agent hasn't pinned one</div></div>
        <select value={s.claudecodeModel} onChange={e=>update({claudecodeModel: e.target.value})}>
          {CafresoHQClient.CLAUDECODE_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless CAFRESOHQ_CLAUDE_BIN env var</div></div>
        <button className="px-btn secondary" onClick={save} disabled={busy}>{busy ? '…' : 'SAVE'}</button>
      </div>
    </div>
  );
}

function CodexPanel({ s, update }) {
  const [status, setStatus] = useStateM({ configured: false, binary: '', override: '', allowedDirs: [], badDirs: [] });
  const [draft, setDraft] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);

  const refresh = async () => {
    try {
      const st = await CafresoHQClient.codexStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await CafresoHQClient.codexConfigure(draft.trim());
      await refresh();
      setMsg({ ok: true, text: draft.trim() ? 'override saved' : 'cleared (using PATH)' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  return (
    <div className="cb-panel">
      <h4>CODEX CLI</h4>
      <div className="hint" style={{marginBottom:10}}>
        Routes calls through your locally-installed <code>codex</code> CLI using the profiles in
        <code> ~/.codex/config.toml</code>. Pick a default profile-backed model below; agent-specific
        pins still override it.
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">CLI status</div>
          <div className="sub">
            {status.configured
              ? <>found at <code>{status.binary}</code></>
              : 'codex binary not found on the proxy machine'}
            {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
          </div>
          {!!status.badDirs?.length && (
            <div className="sub" style={{color:'var(--warning, #c97b2a)', marginTop:4}}>
              invalid CAFRESOHQ_ALLOWED_DIRS: {status.badDirs.join(', ')}
            </div>
          )}
        </div>
      </div>
      <div className="form-row" style={{marginBottom:8,marginTop:6}}>
        <label>OVERRIDE PATH</label>
        <input placeholder="(blank = look up `codex` on PATH)"
          value={draft} onChange={e=>setDraft(e.target.value)}/>
        <span className="hint">absolute path to a different codex binary; leave blank to auto-detect</span>
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">Default model</div>
          <div className="sub">maps to a profile in <code>~/.codex/config.toml</code></div>
        </div>
        <select value={s.codexModel} onChange={e=>update({codexModel: e.target.value})}>
          {CafresoHQClient.CODEX_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless CAFRESOHQ_CODEX_BIN env var</div></div>
        <button className="px-btn secondary" onClick={save} disabled={busy}>{busy ? '...' : 'SAVE'}</button>
      </div>
    </div>
  );
}

export function VaultTab() {
  const [status, setStatus] = useStateM({
    configured: false, backend: 'fs', root: '', defaultRoot: '', restUrl: '', restKey: '',
    fsExists: false, restReachable: false, restDetail: '', unavailable: false, error: '',
  });
  const [draftRoot, setDraftRoot] = useStateM('');
  const [draftUrl, setDraftUrl] = useStateM('');
  const [draftKey, setDraftKey] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);
  const [files, setFiles] = useStateM(null);

  const refresh = async () => {
    try {
      const s = await CafresoHQClient.vaultStatus();
      setStatus({ ...s, unavailable: false, error: '' });
      setDraftRoot(s.root || '');
      setDraftUrl(s.restUrl || '');
      // We never get the actual key back from the server; only the masked sentinel.
      if (!draftKey) setDraftKey('');
      if (s.configured) {
        try { setFiles(await CafresoHQClient.vaultList()); } catch (_e) { setFiles(null); }
      } else { setFiles(null); }
    } catch (e) {
      const message = e.message || 'CafresoHQ bridge is not reachable.';
      setStatus({
        configured: false, backend: 'fs', root: draftRoot || '', defaultRoot: '', restUrl: draftUrl || '', restKey: '',
        fsExists: false, restReachable: false, restDetail: '', unavailable: true, error: message,
      });
      setFiles(null);
      setMsg({ ok: false, text: message });
    }
  };
  useEffectM(() => { refresh(); }, []);

  const cleanLocalRoot = (value) => (value || '').trim().replace(/^["']+|["']+$/g, '');

  const setBackend = async (backend) => {
    setBusy(true); setMsg(null);
    try {
      await CafresoHQClient.vaultConfigure({ backend });
      HQ.clearVaultReadyCache();
      await refresh();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const saveFs = async () => {
    const root = cleanLocalRoot(draftRoot);
    setBusy(true); setMsg(null);
    try {
      await CafresoHQClient.vaultConfigure({ backend: 'fs', root });
      HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: root ? 'configured' : 'cleared' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const useCafresoHQVault = async () => {
    const root = status.defaultRoot || draftRoot.trim();
    if (!root) return;
    setBusy(true); setMsg(null);
    try {
      setDraftRoot(root);
      await CafresoHQClient.vaultConfigure({ backend: 'fs', root });
      HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'using the CafresoHQ Library' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const detectObsidianVault = async () => {
    setBusy(true); setMsg(null);
    try {
      const found = await CafresoHQClient.vaultDiscover();
      const vaults = found.vaults || [];
      const pick = vaults.find(v => v.exists) || vaults[0];
      if (!pick) {
        setMsg({ ok: false, text: 'no Obsidian vaults found' });
      } else if (!pick.exists) {
        setMsg({ ok: false, text: `found ${pick.name}, but path is missing` });
      } else {
        setDraftRoot(pick.path);
        await CafresoHQClient.vaultConfigure({ backend: 'fs', root: pick.path });
        HQ.clearVaultReadyCache();
        await refresh();
        setMsg({ ok: true, text: `using ${pick.name}` });
      }
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const saveRest = async () => {
    setBusy(true); setMsg(null);
    try {
      const patch = { restUrl: normalizeUrlScheme(draftUrl.trim()) };
      if (draftKey.trim()) patch.restKey = draftKey.trim();
      await CafresoHQClient.vaultConfigure(patch);
      setDraftKey(''); // clear the in-memory draft so we don't redisplay
      HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'saved' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  /* Three backends write notes, and this screen used to know two. `isRest`
     was the whole model, so `!isRest` meant "local folder" — and on a fleet
     office running the oci backend that lit LOCAL DIRECTORY as the SELECTED
     storage, showed a local path with a green "✓ N notes indexed" tick
     beside it, and rendered USE APP VAULT / DETECT OBSIDIAN / SAVE. Each of
     those three posts {backend:'fs'}. Measured against a provisioned office
     (bucket cafresohq-fleet-vault): one click moved the vault to a
     container-local folder, /vault/status still answered configured:true, so
     nothing anywhere warned — and POST /vault/configure {"backend":"oci"}
     answered `bad backend: oci`, so there was no way back short of
     restarting the container. Every honesty sentence the office says about
     an unreachable vault ("check Connections") points here. */
  const isRest = status.backend === 'rest';
  const isOci = status.backend === 'oci';
  const isFs = !isRest && !isOci;
  /* Whether this office HAS fleet storage, which is not the same question as
     whether it is using it — `ociBucket` comes back from /vault/status
     whenever the container was provisioned with one, on any active backend.
     The chip has to key off this and not off isOci, or the way back closes
     behind the boss the moment they press LOCAL DIRECTORY: the control that
     returns them would be the one control the new state stops rendering. */
  const hasFleetStorage = isOci || !!status.ociBucket;

  return (
    <div className="cb-panel">
      <h4>LIBRARY</h4>
      <div className="row-knob">
        <div><div className="lbl">Storage</div><div className="sub">CafresoHQ works with a plain Markdown folder; Obsidian is optional</div></div>
        <div style={{display:'flex',gap:6,flexWrap:'wrap',justifyContent:'flex-end'}}>
          {/* Shown only on an office that HAS fleet storage: this is not a
              backend a boss can pick into existence, and a chip offering it
              on a laptop would be the same wrong door in the other
              direction. The server refuses it there too. */}
          {hasFleetStorage && (
            <button className={`px-btn ${isOci?'primary':'secondary'}`} style={{fontSize:9}}
              onClick={()=>setBackend('oci')} disabled={busy}>FLEET STORAGE</button>
          )}
          <button className={`px-btn ${isFs?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('fs')} disabled={busy}>LOCAL DIRECTORY</button>
          <button className={`px-btn ${isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('rest')} disabled={busy}>OBSIDIAN REST</button>
        </div>
      </div>

      {isOci && (<>
        <div className="row-knob" style={{marginTop:6}}>
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.ociBucket
                ? `✓ object storage · bucket ${status.ociBucket} · ${files?.length ?? '…'} file${files?.length === 1 ? '' : 's'} indexed`
                : '✕ no bucket named — this office was provisioned without one'}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
        </div>
        {/* §7: the honest sentence is "you cannot set this here", and it is
            only honest if it also says where it IS set. No field, because
            there is nothing on this screen that could supply credentials —
            the container authenticates as itself. The two buttons above
            still work: leaving fleet storage for a local folder is a real
            choice, it just has to be one the boss makes on purpose. */}
        <div className="hint" style={{marginTop:8}}>
          This office files its notes into its fleet's object storage, set when the
          office was set up (<code>OCI_VAULT_NAMESPACE</code>, <code>OCI_VAULT_BUCKET</code>,
          optional <code>OCI_VAULT_PREFIX</code>) — not from this screen, and not by
          pasting a key: this office signs its own requests.
          {/* Names the control, not a direction. The first draft said
              "switching to a local directory below" and the row of three
              buttons is above this paragraph — a sentence that sends the
              boss looking the wrong way is a small wrong door, and this
              panel exists because of a large one. */}
          {' '}{status.ociBucket
            ? 'Pressing LOCAL DIRECTORY above moves future notes off the bucket; the notes already in it stay where they are.'
            : 'Until a bucket is named, notes have nowhere to land — whoever sets this fleet up names it.'}
        </div>
      </>)}

      {isFs && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>LIBRARY FOLDER</label>
          <input placeholder={status.defaultRoot || 'C:/Users/you/Documents/cafresohq/hq-state/vault'}
            {...NO_MANGLE_PROPS}
            value={draftRoot} onChange={e=>setDraftRoot(e.target.value)}/>
          <span className="hint">absolute path to a Markdown folder; the default lives inside CafresoHQ under <code>hq-state/vault</code></span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.fsExists
                ? `✓ ${files?.length ?? '…'} file${files?.length === 1 ? '' : 's'} indexed`
                : (draftRoot ? `path not yet saved` : 'not configured')}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
          <div style={{display:'flex',gap:6,flexWrap:'wrap',justifyContent:'flex-end'}}>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={useCafresoHQVault} disabled={busy}>{busy ? '...' : 'USE APP LIBRARY'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={detectObsidianVault} disabled={busy}>{busy ? '...' : 'DETECT OBSIDIAN'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={saveFs} disabled={busy}>{busy ? '...' : 'SAVE'}</button>
          </div>
        </div>
      </>)}

      {isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>REST URL</label>
          <input placeholder="https://127.0.0.1:27124"
            {...NO_MANGLE_PROPS}
            value={draftUrl} onChange={e=>setDraftUrl(e.target.value)}/>
          <span className="hint">optional Obsidian Local REST API endpoint (HTTPS, self-signed cert OK via proxy)</span>
        </div>
        <div className="form-row" style={{marginBottom:8}}>
          <label>API KEY</label>
          <input type="password" placeholder={status.restKey ? '•••• (saved — type to replace)' : 'paste from Obsidian → Local REST API settings'}
            {...NO_MANGLE_PROPS}
            value={draftKey} onChange={e=>setDraftKey(e.target.value)}/>
          <span className="hint">optional; stored only on this proxy server (in memory); never logged</span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.restReachable
                ? `✓ plugin reachable · ${files?.length ?? '…'} file${files?.length === 1 ? '' : 's'} indexed`
                : (status.restDetail ? `✕ ${status.restDetail}` : 'not yet tested')}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
          <button className="px-btn secondary" onClick={saveRest} disabled={busy}>{busy ? '…' : 'SAVE'}</button>
        </div>
        <div className="hint" style={{marginTop:8}}>
          Obsidian REST is optional. It unlocks plugin-mediated file access and open-in-Obsidian.
          Install the <em>Local REST API</em> community plugin in Obsidian, copy its API key, and paste above.
        </div>
      </>)}

      <div className="hint" style={{marginTop:8,fontSize:11}}>
        Agents whose role includes the <strong>Library</strong> tool can search/read/append/create Markdown notes
        {isOci ? ' from this office’s fleet storage' : ' from the local directory'}.
        {/* The tip named two backends' env vars and the office runs on
            three; on a fleet container it was a list of settings that do
            nothing here. */}
        {isOci
          ? <> Tip: <code>CAFRESOHQ_VAULT_BACKEND=oci</code> with <code>OCI_VAULT_NAMESPACE</code> / <code>OCI_VAULT_BUCKET</code> selects fleet storage when the office starts.</>
          : <> Tip: pass <code>CAFRESOHQ_VAULT</code> to override the app Library, or <code>CAFRESOHQ_OBSIDIAN_URL</code> / <code>CAFRESOHQ_OBSIDIAN_KEY</code> for optional Obsidian REST.</>}
      </div>
    </div>
  );
}

/* ── Media generation (Settings -> Media) ────────────────────────────────
   GENERATE_IMAGE/GENERATE_VIDEO are real, tested tools (exporters.py
   _generate_image/_generate_video: 5 image providers, 4 video providers,
   clean structured errors on every branch) gated in hq-runtime.jsx's
   toolsForAgent purely on `s.imageProvider`/`s.videoProvider` being truthy
   — and until this tab, NOTHING anywhere ever wrote those two settings
   keys. See docs/OFFICE_AS_INTERFACE.md, "GENERATE_IMAGE/GENERATE_VIDEO
   are fully built and completely unreachable" (2026-08-12).

   Cloud keys reuse the SAME encrypted vault as terminal sessions
   (CafresoHQClient.setAgentKey/getAgentKey, claude-client.jsx) —
   generateImage/generateVideo already call getAgentKey('openai'|'google'
   |'fal'), so a shared provider (e.g. fal for both image and video) only
   asks for a key once. Local providers (a1111, comfyui) take a base URL
   instead, in plain settings — no secret involved, same shape as the
   LM Studio/Ollama URL fields above. */
const IMAGE_PROVIDERS = [
  { id: 'openai',  label: 'OpenAI (DALL·E)',        kind: 'key', keyId: 'openai',
    modelPh: 'dall-e-3' },
  { id: 'google',  label: 'Google (Gemini/Imagen)',  kind: 'key', keyId: 'google',
    modelPh: 'gemini-2.5-flash-image-preview' },
  { id: 'fal',     label: 'fal.ai',                  kind: 'key', keyId: 'fal',
    modelPh: 'fal-ai/flux/schnell' },
  { id: 'a1111',   label: 'Automatic1111 (local)',   kind: 'url', urlField: 'a1111Url',
    ph: 'http://127.0.0.1:7860', modelPh: '(server default)' },
  { id: 'comfyui', label: 'ComfyUI (local)',         kind: 'url', urlField: 'comfyUrl',
    ph: 'http://127.0.0.1:8188', modelPh: '(server default)' },
];
const VIDEO_PROVIDERS = [
  { id: 'fal',     label: 'fal.ai',                          kind: 'key', keyId: 'fal',
    modelPh: 'fal-ai/bytedance/seedance/v1/lite/text-to-video' },
  { id: 'openai',  label: 'OpenAI (Sora — gated, returns an error)', kind: 'key', keyId: 'openai',
    modelPh: '—' },
  { id: 'google',  label: 'Google (Veo — not wired, returns an error)', kind: 'key', keyId: 'google',
    modelPh: '—' },
  { id: 'comfyui', label: 'ComfyUI (local, needs a workflow)', kind: 'url', urlField: 'comfyUrl',
    ph: 'http://127.0.0.1:8188', modelPh: '(provider-specific — required)' },
];
const MEDIA_KEY_META = {
  openai: { label: 'OpenAI', ph: 'sk-…',
    link: 'https://platform.openai.com/api-keys', linkText: 'platform.openai.com/api-keys' },
  google: { label: 'Google', ph: 'AIza…',
    link: 'https://aistudio.google.com/apikey', linkText: 'aistudio.google.com/apikey' },
  fal:    { label: 'fal.ai', ph: 'key_id:key_secret',
    link: 'https://fal.ai/dashboard/keys', linkText: 'fal.ai/dashboard/keys' },
};

/* Write-only key field: the vault never hands the plaintext back to a
   caller that isn't about to use it immediately, so this row can only show
   "saved" / "not set", never the value itself. Mirrors VaultTab's REST API
   KEY field (same never-redisplay rule), but backed by setAgentKey/
   getAgentKey instead of vaultConfigure. */
function MediaKeyRow({ keyId }) {
  const meta = MEDIA_KEY_META[keyId];
  const [has, setHas] = useStateM(() => CafresoHQClient.hasAgentKey(keyId));
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM('');

  // hasAgentKey() is synchronous against local-device presence only; chain
  // keychain hydration finishes async shortly after module load, so confirm
  // with the real (awaited) getter once mounted rather than trusting the
  // synchronous snapshot forever.
  useEffectM(() => {
    let live = true;
    CafresoHQClient.getAgentKey(keyId).then(v => { if (live) setHas(!!v); }).catch(() => {});
    return () => { live = false; };
  }, [keyId]);

  const save = async (e) => {
    const val = e.target.value.trim();
    if (!val) return;
    e.target.value = '';
    setBusy(true); setMsg('');
    try {
      await CafresoHQClient.setAgentKey(keyId, val);
      setHas(true);
      setMsg('✓ saved');
    } catch (err) { setMsg(err.message || 'save failed'); }
    setBusy(false);
  };

  return (
    <div className="form-row" style={{ marginBottom: 8 }}>
      <label>{meta.label} KEY</label>
      <input type="password" placeholder={has ? '•••• (saved — type to replace)' : meta.ph}
        {...NO_MANGLE_PROPS} disabled={busy} onBlur={save} />
      <span className="hint">
        {msg || <>get one at{' '}
          <a href={meta.link} target="_blank" rel="noopener noreferrer"
             style={{ color: 'var(--accent-rose, #c45)', textDecoration: 'underline' }}>
            {meta.linkText}
          </a></>}
        {' '}· shared with any other media provider that uses the same key
      </span>
    </div>
  );
}

export function MediaTab() {
  const [s, update] = useSettingsStore();
  const imgMeta = IMAGE_PROVIDERS.find(p => p.id === s.imageProvider);
  const vidMeta = VIDEO_PROVIDERS.find(p => p.id === s.videoProvider);
  // One row per distinct key provider actually in play, so a shared
  // provider (e.g. fal for both image and video) asks for a key once.
  const keyIds = [...new Set([imgMeta, vidMeta].filter(p => p && p.kind === 'key').map(p => p.keyId))];

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>IMAGE GENERATION</h4>
        {/* Was: "Coworkers get the GENERATE_IMAGE tool once a provider is
            set here". Two problems, both fixed 2026-08-15. §6: it handed
            the boss a raw tool name. And it was simply untrue — it was
            describing a one-key gate that was itself the defect, since
            picking a provider here used to hand the tool to every
            coworker in the office including the ones whose Image Gen box
            was never ticked. Two switches, two screens, and this is the
            screen that has to say so, because the other one is a checkbox
            with no room for a sentence.

            The label reads IMAGE PROVIDER rather than PROVIDER because the
            coworker card promises "once you pick an image provider" —
            scripts/test_a_card_names_the_switch.py pins card copy to a
            control that is printed, and until now that pin had to be
            loosened to the single word "provider" to pass. */}
        <div className="sub" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          Two things have to be on before a coworker can make images: an image
          provider here, and their <strong>Image Gen</strong> box, on their own
          card in Settings → Roster. Leaving this off keeps image making out of
          the whole office's reach.
        </div>
        <div className="form-row" style={{ marginBottom: 8 }}>
          <label>IMAGE PROVIDER</label>
          <select value={s.imageProvider || ''} onChange={e => update({ imageProvider: e.target.value })}>
            <option value="">— off —</option>
            {IMAGE_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </div>
        {imgMeta && (
          <div className="form-row" style={{ marginBottom: imgMeta.kind === 'url' ? 8 : 0 }}>
            <label>MODEL</label>
            <input placeholder={imgMeta.modelPh} value={s.imageModel || ''}
              onChange={e => update({ imageModel: e.target.value })} />
            <span className="hint">blank uses your office's default model for this provider</span>
          </div>
        )}
        {imgMeta && imgMeta.kind === 'url' && (
          <div className="form-row">
            <label>BASE URL</label>
            <input placeholder={imgMeta.ph} value={s[imgMeta.urlField] || ''}
              {...NO_MANGLE_PROPS}
              onChange={e => update({ [imgMeta.urlField]: normalizeUrlScheme(e.target.value) })} />
            <span className="hint">where your local {imgMeta.label.split(' ')[0]} server listens</span>
          </div>
        )}
      </div>

      <div className="cb-panel">
        <h4>VIDEO GENERATION</h4>
        <div className="sub" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          fal.ai is the only provider that can succeed on just an API key today —
          OpenAI's Sora and Google's Veo APIs are still gated, so those branches
          return a clean error instead of a video.
        </div>
        <div className="form-row" style={{ marginBottom: 8 }}>
          {/* Same claim as image: the Image Gen box is the one door for both
              kinds of media, because there is no 'video' id in
              TOOLS_CATALOG to give video a box of its own. */}
          <label>VIDEO PROVIDER</label>
          <select value={s.videoProvider || ''} onChange={e => update({ videoProvider: e.target.value })}>
            <option value="">— off —</option>
            {VIDEO_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </div>
        {vidMeta && (
          <div className="form-row" style={{ marginBottom: vidMeta.kind === 'url' ? 8 : 0 }}>
            <label>MODEL</label>
            <input placeholder={vidMeta.modelPh} value={s.videoModel || ''}
              onChange={e => update({ videoModel: e.target.value })} />
            <span className="hint">blank uses your office's default model for this provider</span>
          </div>
        )}
        {vidMeta && vidMeta.kind === 'url' && (
          <div className="form-row">
            <label>BASE URL</label>
            <input placeholder={vidMeta.ph} value={s[vidMeta.urlField] || ''}
              {...NO_MANGLE_PROPS}
              onChange={e => update({ [vidMeta.urlField]: normalizeUrlScheme(e.target.value) })} />
            <span className="hint">ComfyUI video needs a workflow JSON supplied per-call; this only sets where to reach it</span>
          </div>
        )}
      </div>

      {keyIds.length > 0 && (
        <div className="cb-panel">
          <h4>PROVIDER KEYS</h4>
          <div className="sub" style={{ lineHeight: 1.6, marginBottom: 8 }}>
            Stored in this browser's encrypted key vault — the same one used for
            terminal sessions. Never sent anywhere but the provider's own API.
          </div>
          {keyIds.map(id => <MediaKeyRow key={id} keyId={id} />)}
        </div>
      )}

      {!imgMeta && !vidMeta && (
        <div className="cb-panel">
          <div className="muted">Pick an image or video provider above to give coworkers the media-generation tool.</div>
        </div>
      )}
    </div>
  );
}

/* BROWSER-SIDE BRAINS — the fourth and last panel rescued out of ApiTab.
   These two keys were the ones with real consequences still attached.

   `localModelOptions()` appends "Anthropic (Claude API · credits)" and
   "Google (Gemini API · credits)" to EVERY brain picker, unconditionally.
   The manual hire form defaults to `anthropic:claude-haiku-…`. It correctly
   notices the brain is not signed in and says so — "they can be hired, but
   can't work until you add it in Settings → Connections" — and Connections
   had no Anthropic or Google field, because the only ones ever written sat
   in a component nothing imports. Measured on a fresh office: the warning
   fires, the boss follows it, and the room it names is empty. A failure
   sentence with a route out that loops back to itself is the §7 rule
   failing in the shape it was written to prevent.

   Not gated on `s.provider`, unlike the panels these came from. That toggle
   lives in the same unmounted component, so it has been pinned at its
   default of 'hermes' for as long as the tab has been gone — which means
   those panels were dead twice over. It is also the wrong question now:
   `parseModelId` lets any agent pin `anthropic:…` regardless of the global
   provider, and that is how brains are actually chosen. What makes this
   panel relevant is that a coworker somewhere is pinned to one of these.

   Not the same thing as CLOUD KEYS above, and the distinction is the whole
   reason this panel is allowed to be a form at all. Those keys go to the
   gateway and the panel deliberately refuses to accept them in the browser
   — "keys never reach the browser" is a posture, not a gap. These two are
   read only by `streamAnthropic`/`streamGoogle`, which call api.anthropic.com
   and generativelanguage.googleapis.com straight from this tab with the key
   as a request header. It never touches the Cafreso server, so there is no
   posture to fight; it lives in localStorage, and the hint says so. */
export function BrowserKeysTab() {
  const [s, update] = useSettingsStore();
  const C = CafresoHQClient;
  const rows = [
    { id: 'anthropic', h: '🧠 ANTHROPIC (CLAUDE API)', ph: 'sk-ant-…',
      keyField: 'anthropicKey', modelField: 'anthropicModel',
      models: C.ANTHROPIC_MODELS,
      where: 'console.anthropic.com/settings/keys',
      link: 'https://console.anthropic.com/settings/keys' },
    { id: 'google', h: '🧠 GOOGLE (GEMINI API)', ph: 'AIza…',
      keyField: 'googleKey', modelField: 'googleModel',
      models: C.GEMINI_MODELS,
      where: 'aistudio.google.com/apikey',
      link: 'https://aistudio.google.com/apikey' },
  ];
  return (
    <>
      {rows.map(r => (
        <div className="cb-panel" key={r.id}>
          <h4>{r.h}</h4>
          <div className="form-row" style={{ marginBottom: 8 }}>
            <label>API KEY</label>
            <input type="password" placeholder={r.ph} value={s[r.keyField] || ''}
              {...NO_MANGLE_PROPS}
              onChange={e => update({ [r.keyField]: e.target.value })} />
            {/* Where to get one, the same way SELF_HOST_PROVIDERS does it in
                the CLOUD KEYS panel — a boss who has got this far because a
                hire warning sent them here does not necessarily have a key
                yet, and "add it in Settings" is only half an instruction. */}
            <span className="hint">
              stays in this browser · get one at{' '}
              <a href={r.link} target="_blank" rel="noreferrer">{r.where}</a>
            </span>
          </div>
          <div className="form-row">
            <label>DEFAULT MODEL</label>
            <select value={s[r.modelField] || ''}
                    onChange={e => update({ [r.modelField]: e.target.value })}>
              {r.models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            {/* Says what it is actually for. The old copy read "used for the
                CEO and any helper without a brain of their own", which was
                written when `s.provider` still selected one global brain. A
                coworker pinned to `anthropic:claude-opus-…` carries its model
                in the id and never consults this. */}
            <span className="hint">for coworkers pinned to this provider without a model in their brain id</span>
          </div>
        </div>
      ))}
    </>
  );
}

/* Self-sufficient, the same shape MediaTab and VaultTab already have: it
   reads the settings store itself instead of taking `s`/`update` from a
   parent. That prop pair was the reason this panel could only live inside
   the one component in this file that holds the store — the component
   nothing mounts. Settings → Connections has no such store to hand down,
   and a snapshot passed as a prop would toggle the switch without ever
   re-rendering it. */
export function BraveTab() {
  const [s, update] = useSettingsStore();
  const [probing, setProbing] = useStateM(false);
  const [result, setResult] = useStateM(null);
  const test = async () => {
    setProbing(true); setResult(null);
    try { setResult(await CafresoHQClient.braveProbe()); }
    catch (e) { setResult({ ok:false, detail: e.message }); }
    setProbing(false);
  };
  return (
    <div className="cb-panel">
      <h4>🔍 BRAVE WEB SEARCH</h4>
      <div className="row-knob">
        <div><div className="lbl">Enable web search tool</div><div className="sub">agents with the WEB tool can call <code>[SEARCH: query]</code></div></div>
        <div className={`pxswitch ${s.braveEnabled?'on':''}`} onClick={()=>update({braveEnabled: !s.braveEnabled})}><div className="nub"/></div>
      </div>
      <div className="form-row" style={{marginBottom:8}}>
        <label>API KEY</label>
        <input type="password" placeholder="BSA-…"
          {...NO_MANGLE_PROPS}
          value={s.braveKey} onChange={e=>update({braveKey: e.target.value})}/>
        <span className="hint">stored in this browser's localStorage; sent to /brave/search on this proxy only</span>
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">Connection test</div>
          <div className="sub">
            {probing ? 'probing…' : result ? (result.ok ? `✓ ${result.detail}` : `✕ ${result.detail}`) : 'verifies key works'}
          </div>
        </div>
        <button className="px-btn secondary" onClick={test} disabled={probing || !s.braveKey}>
          {probing ? '…' : 'TEST'}
        </button>
      </div>
    </div>
  );
}


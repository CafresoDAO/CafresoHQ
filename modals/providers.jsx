import { ModelPicker } from './base.jsx';
import { HQ } from '../hq-runtime.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
import { useSettingsStore } from './base.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;
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

      {s.provider === 'anthropic' && (
        <div className="cb-panel">
          <h4>ANTHROPIC</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>API KEY</label>
            <input type="password" placeholder="sk-ant-…"
              value={s.anthropicKey} onChange={e=>update({anthropicKey: e.target.value})}/>
            <span className="hint">stored in this browser's localStorage only</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            <select value={s.anthropicModel} onChange={e=>update({anthropicModel: e.target.value})}>
              {CafresoHQClient.ANTHROPIC_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <span className="hint">used for the CEO and any helper without a brain of their own</span>
          </div>
        </div>
      )}

      {s.provider === 'google' && (
        <div className="cb-panel">
          <h4>GOOGLE (GEMINI)</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>API KEY</label>
            <input type="password" placeholder="AIza…"
              value={s.googleKey} onChange={e=>update({googleKey: e.target.value})}/>
            <span className="hint">stored in this browser's localStorage only</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            <select value={s.googleModel} onChange={e=>update({googleModel: e.target.value})}>
              {CafresoHQClient.GEMINI_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <span className="hint">used for the CEO and any helper without a brain of their own</span>
          </div>
        </div>
      )}

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


      <BraveTab s={s} update={update} />
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
      setMsg({ ok: true, text: 'using CafresoHQ vault' });
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
      const patch = { restUrl: draftUrl.trim() };
      if (draftKey.trim()) patch.restKey = draftKey.trim();
      await CafresoHQClient.vaultConfigure(patch);
      setDraftKey(''); // clear the in-memory draft so we don't redisplay
      HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'saved' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const isRest = status.backend === 'rest';

  return (
    <div className="cb-panel">
      <h4>MARKDOWN VAULT</h4>
      <div className="row-knob">
        <div><div className="lbl">Storage</div><div className="sub">CafresoHQ works with a plain Markdown folder; Obsidian is optional</div></div>
        <div style={{display:'flex',gap:6}}>
          <button className={`px-btn ${!isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('fs')} disabled={busy}>LOCAL DIRECTORY</button>
          <button className={`px-btn ${isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('rest')} disabled={busy}>OBSIDIAN REST</button>
        </div>
      </div>

      {!isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>VAULT DIRECTORY</label>
          <input placeholder={status.defaultRoot || 'C:/Users/you/Documents/cafresohq/hq-state/vault'}
            value={draftRoot} onChange={e=>setDraftRoot(e.target.value)}/>
          <span className="hint">absolute path to a Markdown folder; the default lives inside CafresoHQ under <code>hq-state/vault</code></span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.fsExists
                ? `✓ ${files?.length ?? '…'} note${files?.length === 1 ? '' : 's'} indexed`
                : (draftRoot ? `path not yet saved` : 'not configured')}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
          <div style={{display:'flex',gap:6,flexWrap:'wrap',justifyContent:'flex-end'}}>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={useCafresoHQVault} disabled={busy}>{busy ? '...' : 'USE APP VAULT'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={detectObsidianVault} disabled={busy}>{busy ? '...' : 'DETECT OBSIDIAN'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={saveFs} disabled={busy}>{busy ? '...' : 'SAVE'}</button>
          </div>
        </div>
      </>)}

      {isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>REST URL</label>
          <input placeholder="https://127.0.0.1:27124"
            value={draftUrl} onChange={e=>setDraftUrl(e.target.value)}/>
          <span className="hint">optional Obsidian Local REST API endpoint (HTTPS, self-signed cert OK via proxy)</span>
        </div>
        <div className="form-row" style={{marginBottom:8}}>
          <label>API KEY</label>
          <input type="password" placeholder={status.restKey ? '•••• (saved — type to replace)' : 'paste from Obsidian → Local REST API settings'}
            value={draftKey} onChange={e=>setDraftKey(e.target.value)}/>
          <span className="hint">optional; stored only on this proxy server (in memory); never logged</span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.restReachable
                ? `✓ plugin reachable · ${files?.length ?? '…'} note${files?.length === 1 ? '' : 's'} indexed`
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
        Agents whose role includes the <strong>Vault Notes</strong> tool can search/read/append/create Markdown notes from the local directory.
        Tip: pass <code>CAFRESOHQ_VAULT</code> to override the app vault, or <code>CAFRESOHQ_OBSIDIAN_URL</code> / <code>CAFRESOHQ_OBSIDIAN_KEY</code> for optional Obsidian REST.
      </div>
    </div>
  );
}

function BraveTab({ s, update }) {
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


import { ProjectTerminal } from './terminal.jsx';
import { ideLangFromPath } from './ide.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
import { officeCause, repoCause } from '../app/floor.jsx';
import { FilePreview, IDEEditor, LocalTree, ideFileIcon, previewKind } from './ide.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;
function WorkspaceView({ projects, setProjects, agents = [], tasks, onAddTask, onSwitchView }) {
  const LS = (k, d) => { try { const v = localStorage.getItem('ws:' + k); return v == null ? d : JSON.parse(v); } catch (_e) { return d; } };
  const LSset = (k, v) => { try { localStorage.setItem('ws:' + k, JSON.stringify(v)); } catch (_e) {} };
  const baseName = (p) => String(p || '').split(/[\/\\]/).pop();
  const shortPath = (p) => { const s = String(p || '').split(/[\/\\]/).filter(Boolean); return s.slice(-2).join('/'); };
  const joinPath = (dir, name) => { const d = String(dir || ''); const sep = (d.includes('\\') && !d.includes('/')) ? '\\' : '/'; return d.replace(/[\/\\]+$/, '') + sep + name; };
  const isUnder = (p, base) => p === base || p.startsWith(base + '/') || p.startsWith(base + '\\');
  const toast = (k, m) => { if (window.cafresohqToast && window.cafresohqToast[k]) window.cafresohqToast[k](m); };
  /* §7: "every failure is one honest sentence". These toasts used to
     concatenate a raw `e.message` — "Save failed: NetworkError when
     attempting to fetch resource." — on Projects, which is onboarding step 5
     and has a button on the Getting Started checklist, so it is core path and
     gets no part of the desktop-mode/settings exemption in §6. Same helper
     and same reasoning as views/vault.jsx; snagCAUSE because these messages
     bring their own subject and verb. */
  const snag = (what, e) => toast('error', `${what} — ${officeCause((e && e.message) || String(e))}`);
  const C = CafresoHQClient;

  const [mode, setMode] = useSV(() => LS('mode', 'workspace'));
  /* Same never-silently-drop-edits contract as openPath: flipping to Classic
     unmounts the editor, so confirm first if the open file has unsaved changes. */
  const flipMode = async (m) => {
    if (m === mode) return;
    const cur = openFileRef.current;
    if (cur && cur.dirty && !(await window.hqConfirm('Discard unsaved changes to ' + baseName(cur.path) + '?', { okLabel: 'Discard', danger: true }))) return;
    setMode(m); LSset('mode', m);
  };
  /* Same commit step as ProjectsView's — the best-effort mkdir carries the
     same reasoning as there: the first-time boss typing a fresh path has no
     existing folder, and without this the FILES pane's first render is
     "Not a directory: …". An existing path just returns `existed: true`. */
  const commitProject = async ({ name, path, source }) => {
    if (source === 'local' && C && C.fsMkdir) {
      try { await C.fsMkdir(path); } catch (_e) { /* surfaces as the tree's not-a-directory state */ }
    }
    const id = 'p_' + Math.random().toString(36).slice(2, 8);
    setProjects && setProjects(prev => [...(prev || []), { id, name, path, source }]);
    setSelectedId(id);
    setShowAdd(false);
    toast('success', `Added project "${name}"`);
  };
  const _isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;
  const [mobilePane, setMobilePane] = useSV('files');   // mobile pane-switcher: files | editor | terminal | agents
  const [selectedId, setSelectedId] = useSV(() => LS('selid', (projects[0] && projects[0].id) || null));
  const project = projects.find(p => p.id === selectedId) || projects[0] || null;
  React.useEffect(() => { if (project) LSset('selid', project.id); }, [project && project.id]);

  const [openFile, setOpenFile] = useSV(null);   // {path, content, mtime, hash, dirty, binary}
  const [previewMode, setPreviewMode] = useSV(false);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [conflict, setConflict] = useSV(false);
  const [treeNonce, setTreeNonce] = useSV(0);
  const [previewNonce, setPreviewNonce] = useSV(0);
  const [followAgent, setFollowAgent] = useSV(() => LS('follow', false));
  const [agentStatus, setAgentStatus] = useSV('idle');   // idle | working
  const [ledger, setLedger] = useSV([]);
  const [pulse, setPulse] = useSV(() => new Set());      // paths the agent just touched
  /* termOpen now means "Terminal tab active" (was: drawer expanded).
     Default false — land on the editor, hop to the terminal deliberately.
     termMounted latches true on first activation: the terminal stays mounted
     after that (PTY survives tab hops) but is never spun up for users who
     don't open it. */
  const [termOpen, setTermOpen] = useSV(() => LS('term', false));
  const [termMounted, setTermMounted] = useSV(() => LS('term', false));
  const [fileDrag, setFileDrag] = useSV(false);
  /* Workspace mode's own Add-Project modal. Before this, creating a project
     was Classic-only, so the empty state's "Create your first project"
     button could only flip modes — a boss clicked a button named after the
     thing they wanted and got a different screen with ANOTHER empty state
     ("Click + ADD"). Watched live on a fresh office at onboarding step 5. */
  const [showAdd, setShowAdd] = useSV(false);
  const uploadRef = React.useRef(null);
  const uploadDirRef = React.useRef(null);

  const openFileRef = React.useRef(null); React.useEffect(() => { openFileRef.current = openFile; }, [openFile]);
  const followRef = React.useRef(false); React.useEffect(() => { followRef.current = followAgent; }, [followAgent]);
  /* The agent-tool listener below is mounted once ([] deps) and needs the
     CURRENT project to resolve the paths coworkers report. Same ref pattern
     as the two above. */
  const projectRef = React.useRef(null); React.useEffect(() => { projectRef.current = project; }, [project && project.id, project && project.path]);
  const pulseTimers = React.useRef({});
  const idleTimer = React.useRef(null);

  /* ── open a file into the deck (full content + conflict metadata) ── */
  const openPath = async (path, opts) => {
    const cur = openFileRef.current;
    // Never silently drop unsaved edits when switching files. Auto-opens
    // (Follow along) skip; user-initiated opens confirm first.
    if (cur && cur.dirty && cur.path !== path) {
      if (opts && opts.auto) return;
      if (!(await window.hqConfirm('Discard unsaved changes to ' + baseName(cur.path) + '?', { okLabel: 'Discard', danger: true }))) return;
    }
    setErr(null); setConflict(false);
    const kind = previewKind(path);
    const binary = kind === 'image' || kind === 'pdf';
    if (binary) { setOpenFile({ path, content: '', binary: true }); setPreviewMode(true); return; }
    setBusy(true);
    try {
      const r = await C.fsReadText(path);
      setOpenFile({ path, content: r.content, mtime: r.mtime, hash: r.hash, dirty: false, binary: false });
      setPreviewMode(false);
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };
  const onEdit = (val) => setOpenFile(f => f ? { ...f, content: val, dirty: true } : f);

  /* ── conflict-safe save: re-stat before writing, never silently clobber ── */
  const save = async (force) => {
    const f = openFileRef.current; if (!f) return;
    setBusy(true); setErr(null);
    try {
      if (!force && f.hash) {
        try { const st = await C.fsStat(f.path); if (st && st.hash && st.hash !== f.hash) { setConflict(true); setBusy(false); return; } } catch (_e) {}
      }
      await C.toolExec('FILE_WRITE', f.path, { body: f.content });
      let nh = f.hash, nm = f.mtime;
      try { const st2 = await C.fsStat(f.path); if (st2 && st2.ok) { nh = st2.hash; nm = st2.mtime; } } catch (_e) {}
      setOpenFile(o => (o && o.path === f.path) ? { ...o, hash: nh, mtime: nm, dirty: false } : o);
      setConflict(false); setTreeNonce(n => n + 1);
      toast('success', 'Saved ' + baseName(f.path));
    } catch (e) { setErr(e.message || String(e)); snag("Couldn't save that file", e); }
    setBusy(false);
  };
  const reloadOpen = async (path) => {
    try { const r = await C.fsReadText(path); setOpenFile(o => (o && o.path === path) ? { ...o, content: r.content, mtime: r.mtime, hash: r.hash, dirty: false } : o); setPreviewNonce(n => n + 1); } catch (_e) {}
  };

  /* ── live presence / ledger / status pip helpers ── */
  const markPulse = (path) => {
    if (!path) return;
    setPulse(prev => { const n = new Set(prev); n.add(path); return n; });
    clearTimeout(pulseTimers.current[path]);
    pulseTimers.current[path] = setTimeout(() => setPulse(prev => { const n = new Set(prev); n.delete(path); return n; }), 2600);
  };
  const addLedger = (verb, name, arg) => setLedger(prev => [{ id: Math.random().toString(36).slice(2, 9), verb, name, path: arg, label: shortPath(arg), kind: verb }, ...prev].slice(0, 40));
  const bumpIdle = () => { clearTimeout(idleTimer.current); idleTimer.current = setTimeout(() => setAgentStatus('idle'), 3500); };

  /* A coworker reports the path they were GIVEN — "index.html" — because that
     is what they typed in the marker, and the runtime resolves it server-side
     against the project's working directory. Every path in this pane is
     absolute: the tree lists absolute paths, so `openFile.path` is absolute
     too. Comparing the two silently matched nothing, and all three live
     "watch them work" behaviours below were dead for the ordinary case of a
     coworker writing inside their own project:

       · the tree pulse highlighted a path that isn't in the tree,
       · Follow along called fsReadText('index.html') — which fails, and the
         error renders only inside the editor pane, so with no file open the
         failure was invisible: the checkbox promised "auto-open whatever
         file they are writing" and silently did nothing,
       · and the `cur.path === arg` branch — the one that reloads the file
         you are LOOKING AT when a coworker rewrites it, or raises the
         conflict banner if you have unsaved edits — could never be true.

     Measured live 2026-08-13: with index.html open and the file changed
     underneath, the runtime's own relative-arg event left the editor showing
     stale content with no banner; the identical event carrying the absolute
     path reloaded it instantly. Resolve here, at the one place that knows
     the project root. FILE_* only — vault and export args are vault-relative
     and have nothing to do with this tree. */
  const resolveInProject = (p) => {
    const s = String(p || '').trim();
    if (!s || s.startsWith('/') || /^[A-Za-z]:[\\/]/.test(s)) return s;
    const base = projectRef.current && projectRef.current.path;
    return base ? joinPath(base, s) : s;
  };

  /* ── the agent event bus: the heart of co-habitation ── */
  React.useEffect(() => {
    const onAgentTool = (e) => {
      const d = e.detail || {}; const name = d.name, phase = d.phase;
      const arg = (name === 'FILE_WRITE' || name === 'FILE_READ')
        ? resolveInProject(d.arg)
        : String(d.arg || '').trim();
      setAgentStatus('working'); bumpIdle();
      if (phase === 'start') { markPulse(arg); return; }
      if (phase !== 'done') return;
      /* A tool that failed did not do the thing. The ledger is the boss's
         record of what their coworkers actually did to this folder, and a
         failed write filed as "wrote index.html" is a claim the file
         changed — it did not, and the tree pulse and follow-along that
         follow would chase a file that was never written. The chat bubble
         reports the failure with its own ⚠ card; this pane stays quiet
         rather than filing a success. The presence pip set above stays as
         it is — they ARE still working, the attempt just didn't land. */
      if (d.failed) return;
      const isWrite = name === 'FILE_WRITE';
      const isVault = name === 'VAULT_NEW' || name === 'VAULT_APPEND';
      const isExport = name && name.indexOf('EXPORT') === 0;
      const isBash = name === 'BASH';
      if (isWrite || isVault || isExport) {
        markPulse(arg); setTreeNonce(n => n + 1);
        addLedger(isExport ? 'exported' : 'wrote', name, arg);
        const cur = openFileRef.current;
        if (isWrite && cur && cur.path === arg) {
          if (cur.dirty) setConflict(true);   // surface banner — do not clobber
          else reloadOpen(arg);               // clean buffer → silent reload + preview chase
        } else if (isWrite && followRef.current) {
          /* Follow along means EVERY file they write, code included. The old
             gate here was `previewKind(arg) !== 'code'`, which skipped .js,
             .py, .css, .json — i.e. nearly everything a coworker writes in a
             code workspace — while the checkbox promised "Auto-open whatever
             file they are writing". Measured live: a .md write followed, the
             very next .js write did not, and the stage silently kept showing
             the stale file. openPath's own `auto` branch is what protects
             unsaved edits (it returns early on a dirty buffer); the kind
             check never protected anything. */
          openPath(arg, { auto: true });
        }
      } else if (isBash) {
        addLedger('ran', name, arg);
      }
    };
    window.addEventListener('cafresohq:agentTool', onAgentTool);
    return () => window.removeEventListener('cafresohq:agentTool', onAgentTool);
  }, []);

  /* Clear pending presence/idle timers on unmount (no setState-after-unmount). */
  React.useEffect(() => () => {
    try { Object.values(pulseTimers.current).forEach(clearTimeout); clearTimeout(idleTimer.current); } catch (_e) {}
  }, []);

  /* ── file-manager actions (same backbone as the classic Projects view) ── */
  const fsOK = () => (C && C.fsMkdir) ? C : null;
  const newFolder = async () => {
    if (!project || !fsOK()) { toast('error', 'Working with files needs a newer HQ — update and restart.'); return; }
    const name = ((await window.hqPrompt('New folder name:')) || '').trim(); if (!name || /[\/\\]/.test(name)) return;
    try { await C.fsMkdir(joinPath(project.path, name)); setTreeNonce(n => n + 1); toast('success', `Created "${name}"`); } catch (e) { snag("Couldn't make that folder", e); }
  };
  const renameEntry = async (entry) => {
    if (!fsOK()) return;
    const next = ((await window.hqPrompt('Rename to:', { value: entry.name, okLabel: 'Rename' })) || '').trim(); if (!next || next === entry.name || /[\/\\]/.test(next)) return;
    const to = entry.path.slice(0, Math.max(0, entry.path.length - entry.name.length)) + next;
    try { await C.fsRename(entry.path, to); setTreeNonce(n => n + 1); if (openFileRef.current && isUnder(openFileRef.current.path, entry.path)) setOpenFile(o => ({ ...o, path: to + o.path.slice(entry.path.length) })); toast('success', `Renamed to "${next}"`); } catch (e) { snag("Couldn't rename that", e); }
  };
  const deleteEntry = async (entry) => {
    if (!fsOK()) return;
    if (!(await window.hqConfirm(`Delete ${entry.isDir ? 'folder' : 'file'} "${entry.name}"?` + (entry.isDir ? '\n\nThis removes everything inside it.' : '') + '\n\nThis cannot be undone.', { danger: true }))) return;
    try { await C.fsDelete(entry.path); setTreeNonce(n => n + 1); if (openFileRef.current && isUnder(openFileRef.current.path, entry.path)) setOpenFile(null); toast('success', `Deleted "${entry.name}"`); } catch (e) { snag("Couldn't delete that", e); }
  };
  const doUpload = async (fileList, dir) => {
    setFileDrag(false);
    if (!project) return; const files = Array.from(fileList || []).filter(Boolean); if (!files.length) return;
    if (!C || !C.fsUpload) { toast('error', 'Uploading needs a newer HQ — update and restart.'); return; }
    try { const res = await C.fsUpload(dir || project.path, files); setTreeNonce(n => n + 1); toast('success', `Shared ${res.count || files.length} file${(res.count || files.length) === 1 ? '' : 's'}`); const f0 = res.uploaded && res.uploaded[0]; if (f0 && f0.path) openPath(f0.path); } catch (e) { snag("Couldn't share those files", e); }
  };
  const uploadTo = (entry, files) => { if (files && files.length) { doUpload(files, entry.path); return; } uploadDirRef.current = entry.path; if (uploadRef.current) uploadRef.current.click(); };
  const triggerUpload = () => { uploadDirRef.current = null; if (uploadRef.current) uploadRef.current.click(); };
  const openChat = () => { if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true); window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'project:' + project.id })); };

  /* Put a coworker on this project — or take them off. Workspace is the
     DEFAULT mode and had no assignment control at all: the roster of
     checkboxes lived only in Classic, so a boss who never found the mode
     toggle could not staff a project. The pane it was missing from is
     literally titled "Coworkers · working together", and its one control
     (TALK ↗) stays disabled until somebody is assigned — so the empty
     state offered a disabled button and no way to un-disable it.
     Assignment is not a nicety here: it is what creates the project room,
     what makes a message fan out to the team, and what gives this pane
     anyone to report on. */
  const toggleAgent = (agentId) => {
    if (!project) return;
    setProjects && setProjects(prev => prev.map(p => {
      if (p.id !== project.id) return p;
      const cur = Array.isArray(p.agentIds) ? p.agentIds : [];
      return { ...p, agentIds: cur.includes(agentId) ? cur.filter(id => id !== agentId) : [...cur, agentId] };
    }));
  };
  const onLedgerClick = (l) => { if (l.kind === 'ran') { setTermOpen(true); setTermMounted(true); LSset('term', true); return; } if (l.path) openPath(l.path); };

  const statusLabel = agentStatus === 'working' ? 'coworker working…' : 'coworker standing by';

  /* ── pane bodies, reused by the desktop grid AND the mobile pane-switcher.
     Defined as functions so they're only evaluated when a project exists. ── */
  const filesPane = () => (
    <div className="ws-pane ws-files">
      <div className="ws-pane-hd">📁 Files<div className="ws-hd-acts"><button onClick={newFolder} title="New folder">＋</button><button onClick={triggerUpload} title="Upload files">⬆</button></div></div>
      <div className={'ws-tree' + (fileDrag ? ' drag' : '')}
        onDragOver={e => { e.preventDefault(); setFileDrag(true); }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setFileDrag(false); }}
        onDrop={e => { e.preventDefault(); if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) doUpload(e.dataTransfer.files, null); else setFileDrag(false); }}>
        <LocalTree path={project.path} refreshNonce={treeNonce} onSelectFile={p => { openPath(p); if (_isMobile) setMobilePane('editor'); }} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} pulsePaths={pulse} />
      </div>
      <input ref={uploadRef} type="file" multiple style={{ display: 'none' }} onChange={e => { doUpload(e.target.files, uploadDirRef.current); e.target.value = ''; uploadDirRef.current = null; }} />
    </div>
  );
  const [pubMsg, setPubMsg] = useSV(null);
  const canPublish = () => {
    try { return !!CafresoHQClient.getSettings().icpServices?.publish; } catch (_e) { return false; }
  };
  const publishOpen = async () => {
    if (!openFile) return;
    setPubMsg('Publishing…');
    try {
      const r = await CafresoHQClient.publishSite(openFile.path);
      setPubMsg(r.url);
      try { await navigator.clipboard.writeText(r.url); } catch (_e) {}
    } catch (e) { setPubMsg('Publish failed — ' + officeCause((e && e.message) || String(e))); }
  };

  const editorPane = () => (
    <div className="ws-editorwrap">
      {openFile ? (
        <>
          <div className="ws-tabs">
            <span className="ws-tab on">{ideFileIcon ? ideFileIcon(openFile.path) : '📄'} <span className="nm">{baseName(openFile.path)}</span>{openFile.dirty ? <span className="dirty">•</span> : ''}</span>
            {!openFile.binary && <div className="ws-seg ws-cpseg"><button className={!previewMode ? 'on' : ''} onClick={() => setPreviewMode(false)}>Code</button><button className={previewMode ? 'on' : ''} onClick={() => setPreviewMode(true)}>Preview</button></div>}
            {!openFile.binary && openFile.dirty && <button className="ws-save" onClick={() => save(false)} disabled={busy}>Save</button>}
            {!openFile.binary && /\.html?$/i.test(openFile.path || '') && canPublish() &&
              <button className="ws-save" title="Publish this site + drop a clickable .url link into the project" onClick={publishOpen}>🚀 Publish</button>}
          </div>
          {conflict && (
            <div className="ws-conflict">⚠ Your coworker changed this file while you had edits.
              <button onClick={() => { setConflict(false); openPath(openFile.path); }}>Reload</button>
              <button onClick={() => save(true)}>Keep mine</button>
            </div>
          )}
          {pubMsg && (
            <div className="ws-conflict" style={{ background: 'var(--paper-2,#f0e9d8)' }}>
              {/^https?:/.test(pubMsg)
                ? <>Published — link copied. <a href={pubMsg} target="_blank" rel="noopener noreferrer">{pubMsg}</a></>
                : pubMsg}
              <button onClick={() => setPubMsg(null)}>✕</button>
            </div>
          )}
          {err && <div className="ws-err">{officeCause(err)}</div>}
          <div className="ws-stage">
            {previewMode ? <FilePreview file={openFile} nonce={previewNonce} /> : <IDEEditor value={openFile.content} onChange={onEdit} path={openFile.path} />}
          </div>
        </>
      ) : (
        <div className="ws-stage-empty">{_isMobile ? 'Tap a file in the Files tab — or watch your coworkers build one.' : 'Open a file from the tree — or watch your coworkers build one.'}<br /><span className="dim">Code · Preview · live as it's written</span></div>
      )}
    </div>
  );
  const agentPane = () => (
    <div className="ws-pane ws-agent">
      <div className="ws-pane-hd">Coworkers · working together<div className="ws-hd-acts"><button className="ws-talk" disabled={(project.agentIds || []).length === 0} onClick={openChat} title="Open this project's room, where the team works together">TALK ↗</button></div></div>
      <div className="ws-crew">
        {agents.length === 0
          ? <div className="ws-crew-empty">No coworkers hired yet — visit Team to hire one.</div>
          : agents.map(a => {
              const on = (project.agentIds || []).includes(a.id);
              return (
                <button
                  key={a.id}
                  className={'ws-crew-chip' + (on ? ' on' : '')}
                  onClick={() => toggleAgent(a.id)}
                  title={on
                    ? `${a.name} is on this project — click to take them off`
                    : `Put ${a.name} on this project${a.elevated ? ' (has file and shell access)' : ''}`}
                >
                  <span className="tick">{on ? '✓' : '+'}</span>{a.name}
                </button>
              );
            })}
      </div>
      <div className="ws-ledger">
        {ledger.length === 0 && <div className="ws-led-empty">{(project.agentIds || []).length === 0
          ? 'Nobody is on this project yet — add a coworker above and they share this folder & shell with you.'
          : 'Your coworkers share this folder & shell. Their writes, runs, and exports appear here as they work — click any line to jump to it.'}</div>}
        {ledger.map(l => (
          <div key={l.id} className={'ws-led k-' + l.kind} onClick={() => onLedgerClick(l)} title={l.path}>
            <span className="v">{l.kind}</span><span className="lb">{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="ws-root">
      <div className="ws-topbar">
        <div className="ws-seg ws-modeseg">
          <button className={mode === 'workspace' ? 'on' : ''} onClick={() => flipMode('workspace')} title="Unified Workspace — files, editor, terminal and your coworkers on one screen">Workspace</button>
          <button className={mode === 'classic' ? 'on' : ''} onClick={() => flipMode('classic')} title="The original Projects view">Classic</button>
        </div>
        {mode === 'workspace' && project && (
          <>
            <select className="ws-projsel" value={project.id} onChange={e => setSelectedId(e.target.value)}>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <span className="ws-env" title={project.path}><span className="ico">⬡</span> {project.source === 'github' ? 'repo' : 'local'} · {shortPath(project.path) || project.path}</span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
              <label className="ws-follow" title="Auto-open whatever file they are writing"><input type="checkbox" checked={followAgent} onChange={e => { setFollowAgent(e.target.checked); LSset('follow', e.target.checked); }} /> Follow along</label>
              <span className={'ws-pip ' + agentStatus}><span className="dot" />{statusLabel}</span>
            </div>
          </>
        )}
      </div>

      {mode === 'classic' ? (
        <div className="ws-classic"><ProjectsView projects={projects} setProjects={setProjects} tasks={tasks} agents={agents} onAddTask={onAddTask} onSwitchView={onSwitchView} /></div>
      ) : !project ? (
        /* This is where the onboarding checklist's "New Project →" lands,
           and it used to read "No project yet — switch to [Classic] to
           create one." Measured on a fresh office: step 5 of 6 was the only
           step left, its own button brought the boss here, and the screen
           answered with the name of a mode. "Classic" means nothing to
           someone who has been in the building for four minutes, and the
           sentence describes the app's internal shape instead of offering
           the thing they came for.

           First rewrite renamed the CTA but kept the mode flip — so the
           button said "Create your first project" and delivered a SECOND
           empty state ("Click + ADD") in a view the boss never asked for.
           A button does the thing it is named after: this one opens the
           Add-Project dialog right here, and the committed project lands
           selected in this same Workspace view. */
        <div className="ws-noproj">
          <div className="ws-noproj-copy">
            No projects yet. A project is a folder your coworkers can build
            in — docs, pages, code — and you can watch them work in it.
          </div>
          <button className="px-btn primary" onClick={() => setShowAdd(true)}>
            Create your first project
          </button>
        </div>
      ) : _isMobile ? (
        <>
          <div className="ws-mbody">
            <div className="ws-mpane" style={{ display: mobilePane === 'files' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column', overflow: 'hidden' }}>{filesPane()}</div>
            <div className="ws-mpane" style={{ display: mobilePane === 'editor' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column', overflow: 'hidden' }}>{editorPane()}</div>
            {/* Terminal stays mounted (visibility/height toggle) so xterm can size when shown. */}
            <div className="ws-mpane ws-mterm" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, visibility: mobilePane === 'terminal' ? 'visible' : 'hidden', height: mobilePane === 'terminal' ? undefined : 0, flex: mobilePane === 'terminal' ? 1 : undefined, pointerEvents: mobilePane === 'terminal' ? 'auto' : 'none' }}>
              <ProjectTerminal project={project} visible={mobilePane === 'terminal'} />
            </div>
            <div className="ws-mpane" style={{ display: mobilePane === 'agents' ? 'flex' : 'none', flex: 1, minHeight: 0, flexDirection: 'column', overflow: 'hidden' }}>{agentPane()}</div>
          </div>
          <div className="ws-mtabs">
            {[['files', '📁', 'Files'], ['editor', '📄', 'Editor'], ['terminal', '⌁', 'Terminal'], ['agents', '🤖', 'Agents']].map(([k, ic, lbl]) => (
              <button key={k} className={mobilePane === k ? 'on' : ''} onClick={() => setMobilePane(k)}>
                <span className="mi">{ic}{k === 'agents' && agentStatus === 'working' && <span className="mbadge" />}</span><span className="ml">{lbl}</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="ws-body">
          {filesPane()}
          {/* Center deck: Editor and Terminal are PEER TABS you hop between,
              not a stacked bottom drawer — opening the terminal no longer
              shrinks the editor, and both stay mounted (display toggle) so
              the PTY and editor state survive the hop. */}
          <div className="ws-center">
            <div className="ws-ctabs" role="tablist">
              <button className={'ws-ctab' + (!termOpen ? ' on' : '')} role="tab" aria-selected={!termOpen}
                onClick={() => { setTermOpen(false); LSset('term', false); }}>
                📄 Editor{openFile && openFile.dirty ? <span className="dirty">•</span> : null}
              </button>
              <button className={'ws-ctab' + (termOpen ? ' on' : '')} role="tab" aria-selected={!!termOpen}
                onClick={() => { setTermOpen(true); setTermMounted(true); LSset('term', true); }}>
                ⌁ Terminal
              </button>
            </div>
            <div className="ws-cstage" style={{ display: termOpen ? 'none' : 'flex' }}>{editorPane()}</div>
            <div className="ws-cstage" style={{ display: termOpen ? 'flex' : 'none' }}>
              {(termOpen || termMounted) && <ProjectTerminal project={project} visible={!!termOpen} />}
            </div>
          </div>
          {agentPane()}
        </div>
      )}
      {/* Portaled to <body> (see AddProjectModal) so the floating window's
          stacking context can't bury it — the same trap the Classic view
          hit with the Job Postings book. */}
      {showAdd ? (
        <AddProjectModal
          prefillName=""
          onClose={() => setShowAdd(false)}
          onCommit={commitProject}
        />
      ) : null}
    </div>
  );
}

function ProjectsView({ projects, setProjects, onSave, agents = [], onSwitchView }) {
  const [selected, setSelected] = useSV(null);
  const [openFile, setOpenFile] = useSV(null);
  const [previewMode, setPreviewMode] = useSV(false);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [rightTab, setRightTab] = useSV('files');
  const [openedTerminals, setOpenedTerminals] = React.useState([]);
  /* File-drop / upload into the selected project's working dir. treeNonce
     forces LocalTree to re-list after an upload; fileDragHover drives the
     drop-zone highlight. */
  const [treeNonce, setTreeNonce] = useSV(0);
  const [fileDragHover, setFileDragHover] = useSV(false);
  const [uploadTargetDir, setUploadTargetDir] = useSV(null);  // subfolder target for 📤 picker
  const uploadInputRef = React.useRef(null);

  React.useEffect(() => {
    if (rightTab === 'terminal' && selected) {
      setOpenedTerminals(prev =>
        prev.includes(selected) ? prev : [...prev, selected]
      );
    }
  }, [rightTab, selected]);

  /* Toggle assignment of an agent to the current project. The dynamic
     project tab in ChatPanel keys off `agentIds`, so flipping this is
     all that's needed to make the per-project room appear / disappear. */
  const toggleAgent = (agentId) => {
    if (!selected) return;
    setProjects(prev => prev.map(p => {
      if (p.id !== selected) return p;
      const cur = Array.isArray(p.agentIds) ? p.agentIds : [];
      const next = cur.includes(agentId) ? cur.filter(id => id !== agentId) : [...cur, agentId];
      return { ...p, agentIds: next };
    }));
  };
  /* Drag-drop state for the project list — visual hint when a folder is being
     dragged over the panel. The actual OS-path can't be inferred from the
     drop event (browser security), so we only use the drop as a trigger to
     open the "new project" prompt with the folder name pre-filled. */
  const [dragHover, setDragHover] = useSV(false);

  const project = projects.find(p => p.id === selected);

  const [showAdd, setShowAdd] = useSV(false);
  const [addPrefill, setAddPrefill] = useSV('');

  const _isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;
  const [mobileStep, setMobileStep] = useSV(_isMobile ? 'list' : null);
  const [mobileDetailTab, setMobileDetailTab] = useSV('files');

  /* Inline rename state — keyed by project id so multiple cards don't
     collide. Stays null when no project is being renamed. */
  const [renamingId, setRenamingId] = useSV(null);
  const [renameDraft, setRenameDraft] = useSV('');

  const beginRename = (p) => {
    setRenamingId(p.id);
    setRenameDraft(p.name || '');
  };
  const commitRename = () => {
    const draft = String(renameDraft || '').trim();
    if (!renamingId) return;
    if (!draft) { setRenamingId(null); return; }
    setProjects(prev => prev.map(p => p.id === renamingId ? { ...p, name: draft } : p));
    if (window.cafresohqToast) window.cafresohqToast.success(`Project renamed to "${draft}"`);
    setRenamingId(null);
  };
  const cancelRename = () => { setRenamingId(null); setRenameDraft(''); };

  /* Delete a project. Confirms because this also wipes the per-project
     chat thread (those messages are scoped via thread:'project:<id>')
     and orphans any tasks that referenced it. We don't cascade-delete
     tasks — those stay in the boss's task list and can be reassigned. */
  const deleteProject = async (p) => {
    if (!p) return;
    const assignees = (p.agentIds || []).length;
    const msg = `Delete project "${p.name}"?` +
      (assignees > 0 ? `\n\n${assignees} agent${assignees === 1 ? '' : 's'} ${assignees === 1 ? 'is' : 'are'} currently assigned. Their assignments will be cleared.` : '') +
      `\n\nThis cannot be undone.`;
    if (!(await window.hqConfirm(msg, { danger: true }))) return;
    setProjects(prev => (prev || []).filter(x => x.id !== p.id));
    // Drop its keep-alive terminal mount too, or the PTY stays connected to a
    // project that no longer exists (and the list grows forever).
    setOpenedTerminals(prev => prev.filter(id => id !== p.id));
    if (selected === p.id) { setSelected(null); setOpenFile(null); }
    if (window.cafresohqToast) window.cafresohqToast.info(`Deleted project "${p.name}"`);
  };

  /* Add a new project — opens the AddProjectModal. */
  const addProject = (suggestedName) => {
    setAddPrefill(suggestedName || '');
    setShowAdd(true);
  };

  /* Final commit step shared by Local-folder and GitHub-clone tabs.
     GitHub-clone's path always exists (cloneRepo creates it server-side),
     but "Local folder" — the path the onboarding flow's "Create your
     first project" actually funnels a brand-new boss into — accepted any
     typed path with no such guarantee. A first-time boss following that
     copy has no existing empty-projects folder lying around, so the
     FILES pane's very first render read "Not a directory: /tmp/…" with
     no path forward other than discovering the unrelated "+ Folder"
     button already does `mkdir(parents=True)` as a side effect. Best-
     effort create it here too — same call "+ Folder" already makes, so
     an existing path (the "point at my existing repo" case this tab's
     own copy also describes) just gets `existed: true` back and nothing
     changes for it. */
  const commitProject = async ({ name, path, source }) => {
    if (source === 'local' && CafresoHQClient && CafresoHQClient.fsMkdir) {
      try { await CafresoHQClient.fsMkdir(path); } catch (_e) { /* falls back to today's "not a directory" state */ }
    }
    const id = 'p_' + Math.random().toString(36).slice(2, 8);
    setProjects && setProjects(prev => [...(prev || []), { id, name, path, source }]);
    setSelected(id);
    setShowAdd(false);
    if (window.cafresohqToast) window.cafresohqToast.success(`Added project "${name}"`);
  };

  const onDropFolder = (e) => {
    e.preventDefault();
    setDragHover(false);
    if (!setProjects) return;
    /* Extract a suggested folder name from the first dropped item. */
    const items = e.dataTransfer && e.dataTransfer.items;
    let suggestedName = '';
    if (items && items.length) {
      try {
        const entry = items[0].webkitGetAsEntry && items[0].webkitGetAsEntry();
        if (entry && entry.isDirectory && entry.name) suggestedName = entry.name;
      } catch (_) {}
    }
    if (!suggestedName && e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      suggestedName = e.dataTransfer.files[0].name;
    }
    addProject(suggestedName);
  };

  const readFile = async (path) => {
    setBusy(true); setErr(null);
    const kind = previewKind(path);
    const isBinary = kind === 'image' || kind === 'pdf';
    setPreviewMode(isBinary);   // binary auto-previews; text lands in the editor
    if (isBinary) {
      // Not text — don't FILE_READ; the preview pane streams it from /fs/file.
      setOpenFile({ path, content: '', dirty: false, binary: true });
      setBusy(false);
      return;
    }
    try {
      const text = await CafresoHQClient.toolExec('FILE_READ', path);
      setOpenFile({
        path,
        content: typeof text === 'string' ? text : String(text || ''),
        dirty: false,
      });
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };

  const saveFile = async () => {
    if (!openFile) return;
    setBusy(true); setErr(null);
    try {
      await CafresoHQClient.toolExec('FILE_WRITE', openFile.path, { body: openFile.content });
      setOpenFile({ ...openFile, dirty: false });
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };

  /* Join a dir + name using whichever separator the dir already uses (so
     Windows paths stay Windows paths). */
  const joinPath = (dir, name) => {
    const d = String(dir || '');
    const sep = (d.includes('\\') && !d.includes('/')) ? '\\' : '/';
    return d.replace(/[\/\\]+$/, '') + sep + name;
  };
  /* Is `p` the path `base` itself, or a descendant of it? Separator-bounded so
     /proj/foobar is NOT treated as living under /proj/foo. */
  const isUnder = (p, base) => p === base || p.startsWith(base + '/') || p.startsWith(base + '\\');
  const toast = (kind, msg) => { if (window.cafresohqToast && window.cafresohqToast[kind]) window.cafresohqToast[kind](msg); };
  /* §7: "every failure is one honest sentence". These toasts used to
     concatenate a raw `e.message` — "Save failed: NetworkError when
     attempting to fetch resource." — on Projects, which is onboarding step 5
     and has a button on the Getting Started checklist, so it is core path and
     gets no part of the desktop-mode/settings exemption in §6. Same helper
     and same reasoning as views/vault.jsx; snagCAUSE because these messages
     bring their own subject and verb. */
  const snag = (what, e) => toast('error', `${what} — ${officeCause((e && e.message) || String(e))}`);

  /* Upload (drop or picker) files into a working dir so assigned agents can
     read them and the preview pane can render them. targetDir defaults to the
     project root; a folder row's 📤 / drop passes a subfolder. After a
     successful upload we refresh the tree and auto-open the first file. */
  const uploadFiles = async (fileList, targetDir) => {
    setFileDragHover(false);  // a folder-row drop stops propagation to the panel zone
    if (!project || !project.path) {
      toast('info', 'Select a project first to share files with it.');
      return;
    }
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;
    if (!CafresoHQClient || !CafresoHQClient.fsUpload) {
      setErr('Uploading needs a newer HQ (one that serves /fs/upload) — update and restart.');
      toast('error', 'Uploading is unavailable — this HQ needs updating.');
      return;
    }
    const dir = targetDir || project.path;
    setBusy(true); setErr(null);
    try {
      const res = await CafresoHQClient.fsUpload(dir, files);
      setTreeNonce(n => n + 1);
      const n = (res && res.count) || files.length;
      const where = dir === project.path ? project.name : ('…/' + dir.split(/[\/\\]/).pop());
      toast('success', `Shared ${n} file${n === 1 ? '' : 's'} with ${where}`);
      const first = res && res.uploaded && res.uploaded[0];
      if (first && first.path) readFile(first.path);
    } catch (e) {
      setErr(e.message || String(e));
      snag("Couldn't share those files", e);
    }
    setBusy(false);
  };

  /* ── File-manager actions over the working tree (new folder / rename /
     delete / upload-into-subfolder). Each refreshes the tree on success. ── */
  const fsClient = () => (CafresoHQClient && CafresoHQClient.fsMkdir) ? CafresoHQClient : null;

  const newFolder = async () => {
    if (!project || !project.path) return;
    if (!fsClient()) { toast('error', 'Working with files needs a newer HQ — update and restart.'); return; }
    const name = ((await window.hqPrompt('New folder name:')) || '').trim();
    if (!name) return;
    if (/[\/\\]/.test(name)) { toast('error', 'Folder name can\'t contain slashes.'); return; }
    setBusy(true); setErr(null);
    try {
      await fsClient().fsMkdir(joinPath(project.path, name));
      setTreeNonce(n => n + 1);
      toast('success', `Created folder "${name}"`);
    } catch (e) { setErr(e.message || String(e)); snag("Couldn't make that folder", e); }
    setBusy(false);
  };

  const renameEntry = async (entry) => {
    if (!fsClient()) { toast('error', 'Working with files needs a newer HQ — update and restart.'); return; }
    const cur = entry.name;
    const next = ((await window.hqPrompt('Rename to:', { value: cur, okLabel: 'Rename' })) || '').trim();
    if (!next || next === cur) return;
    if (/[\/\\]/.test(next)) { toast('error', 'Name can\'t contain slashes.'); return; }
    const parent = entry.path.slice(0, Math.max(0, entry.path.length - cur.length));
    const to = parent + next;
    setBusy(true); setErr(null);
    try {
      await fsClient().fsRename(entry.path, to);
      setTreeNonce(n => n + 1);
      // Keep the editor's path live — including when a *folder* with the open
      // file inside it was renamed (else the next Save writes a ghost copy at
      // the old path). Rebase the open file's path prefix onto the new name.
      if (openFile && openFile.path && isUnder(openFile.path, entry.path)) {
        setOpenFile({ ...openFile, path: to + openFile.path.slice(entry.path.length) });
      }
      toast('success', `Renamed to "${next}"`);
    } catch (e) { setErr(e.message || String(e)); snag("Couldn't rename that", e); }
    setBusy(false);
  };

  const deleteEntry = async (entry) => {
    if (!fsClient()) { toast('error', 'Working with files needs a newer HQ — update and restart.'); return; }
    const what = entry.isDir ? 'folder' : 'file';
    const msg = `Delete ${what} "${entry.name}"?` + (entry.isDir ? '\n\nThis removes everything inside it.' : '') + '\n\nThis cannot be undone.';
    if (!(await window.hqConfirm(msg, { danger: true }))) return;
    setBusy(true); setErr(null);
    try {
      await fsClient().fsDelete(entry.path);
      setTreeNonce(n => n + 1);
      if (openFile && openFile.path && isUnder(openFile.path, entry.path)) setOpenFile(null);
      toast('success', `Deleted "${entry.name}"`);
    } catch (e) { setErr(e.message || String(e)); snag("Couldn't delete that", e); }
    setBusy(false);
  };

  /* 📤 on a folder (no files) opens the picker targeting that folder; a drop
     passes its files straight through. */
  const uploadTo = (entry, files) => {
    if (files && files.length) { uploadFiles(files, entry.path); return; }
    setUploadTargetDir(entry.path);
    if (uploadInputRef.current) uploadInputRef.current.click();
  };

  /* ── Mobile drill-down navigation ── */
  if (_isMobile) {
    return (
      <div className="view-projects" style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'}}>
        {/* Mobile back nav bar */}
        {mobileStep !== 'list' && (
          <div className="proj-mobile-back" style={{
            display:'flex',alignItems:'center',gap:10,
            padding:'10px 14px',
            borderBottom:'2px solid var(--accent-sun)',
            background:'var(--paper-2)',
            minHeight:48,
          }}>
            <button
              className="px-btn ghost"
              style={{fontSize:13,padding:'6px 12px',minWidth:44,minHeight:44,color:'var(--accent-sun)',fontWeight:700}}
              onClick={() => {
                if (mobileStep === 'editor') { setOpenFile(null); setMobileStep('detail'); }
                else { setSelected(null); setOpenFile(null); setMobileStep('list'); }
              }}
            >← Back</button>
            <span style={{fontFamily:"'Press Start 2P',monospace",fontSize:10,letterSpacing:'0.08em',color:'var(--ink)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
              {mobileStep === 'editor' ? (openFile ? openFile.path.split(/[\\/]/).pop() : 'Editor') : (project ? project.name : 'Files')}
            </span>
          </div>
        )}

        {/* Step: project list */}
        {mobileStep === 'list' && (
          <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'auto'}}>
            <div className="proj-section-head" style={{display:'flex',alignItems:'center',gap:'var(--sp-3)',padding:'12px'}}>
              <span style={{flex:1,fontFamily:"'Press Start 2P',monospace",fontSize:11}}>🗂 PROJECTS · {projects.length}</span>
              <button
                onClick={() => addProject('')}
                style={{
                  background:'var(--accent-sun)',border:'none',
                  borderRadius:6,fontSize:12,fontWeight:700,
                  padding:'8px 16px',color:'var(--ink)',cursor:'pointer',
                  minHeight:44,
                }}
              >+ ADD</button>
            </div>
            {projects.length === 0 && (
              <div style={{padding:24,textAlign:'center',opacity:0.6}}>
                No projects yet. Tap + ADD to create one.
              </div>
            )}
            {projects.map(p => (
              <div
                key={p.id}
                style={{
                  padding:'16px 16px',
                  margin:'6px 10px',
                  borderRadius:10,
                  cursor:'pointer',
                  display:'flex',alignItems:'center',gap:12,
                  background: selected === p.id ? 'var(--accent-sun-10, rgba(218,165,32,0.12))' : 'var(--paper-2)',
                  border: selected === p.id ? '1.5px solid var(--accent-sun)' : '1.5px solid var(--rule)',
                  transition:'background 0.15s, border-color 0.15s',
                  minHeight:56,
                }}
                onClick={() => { setSelected(p.id); setOpenFile(null); setMobileStep('detail'); }}
              >
                <span style={{fontSize:24,width:36,height:36,display:'flex',alignItems:'center',justifyContent:'center',borderRadius:8,background:'var(--accent-sun-10, rgba(218,165,32,0.1))'}}>📁</span>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:700,fontSize:15,marginBottom:3,color:'var(--ink)'}}>{p.name}</div>
                  {p.path && <div style={{fontSize:11,opacity:0.5,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.path}</div>}
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); deleteProject(p); }}
                  title={`Delete "${p.name}"`}
                  aria-label={`Delete project ${p.name}`}
                  style={{
                    width:36,height:36,display:'grid',placeItems:'center',
                    background:'transparent',border:'1px solid var(--rule)',
                    borderRadius:8,cursor:'pointer',fontSize:14,
                    color:'var(--brand-coffee-3, #7a6f63)',
                    flexShrink:0,
                    transition:'background .12s, color .12s, border-color .12s',
                  }}
                  onMouseEnter={(e)=>{ e.currentTarget.style.background='rgba(232,92,86,0.1)'; e.currentTarget.style.color='var(--brand-cart-badge, #E85C56)'; e.currentTarget.style.borderColor='var(--brand-cart-badge, #E85C56)'; }}
                  onMouseLeave={(e)=>{ e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--brand-coffee-3, #7a6f63)'; e.currentTarget.style.borderColor='var(--rule)'; }}
                >🗑</button>
                <span style={{fontSize:20,color:'var(--accent-sun)',opacity:0.6}}>›</span>
              </div>
            ))}
          </div>
        )}

        {/* Step: project detail — files / terminal / agents */}
        {mobileStep === 'detail' && project && (
          <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>
            {/* Mobile sub-tabs: Files | Terminal | Agents */}
            <div style={{
              display:'flex', borderBottom:'1px solid var(--rule)',
              background:'var(--paper-2)', flexShrink:0,
              overflowX:'auto', WebkitOverflowScrolling:'touch',
            }}>
              {[['files','📄 Files'],['terminal','⚡ Terminal'],['agents','👥 Agents']].map(([t,label]) => (
                <button key={t}
                  onClick={() => setMobileDetailTab(t)}
                  style={{
                    background:'none', border:'none', cursor:'pointer',
                    padding:'10px 16px', fontSize:11, fontWeight:700,
                    fontFamily:"'JetBrains Mono',monospace",
                    color: mobileDetailTab === t ? '#7c6bff' : 'var(--ink-3)',
                    borderBottom: mobileDetailTab === t ? '2px solid #7c6bff' : '2px solid transparent',
                    whiteSpace:'nowrap', minHeight:44, flexShrink:0,
                  }}
                >{label}</button>
              ))}
            </div>

            {mobileDetailTab === 'files' && (
              <div style={{flex:1,overflow:'auto',display:'flex',flexDirection:'column'}}>
                <div style={{display:'flex',justifyContent:'flex-end',gap:6,padding:'6px 8px',borderBottom:'1px solid var(--rule)'}}>
                  <button
                    className="px-btn ghost"
                    style={{fontSize:11,padding:'4px 10px'}}
                    title="New folder in this project"
                    onClick={newFolder}
                  >＋ Folder</button>
                  <button
                    className="px-btn ghost"
                    style={{fontSize:11,padding:'4px 10px'}}
                    title="Upload files to share with the team on this project"
                    onClick={() => { setUploadTargetDir(null); if (uploadInputRef.current) uploadInputRef.current.click(); }}
                  >⬆ Share file</button>
                </div>
                <input ref={uploadInputRef} type="file" multiple style={{display:'none'}}
                  onChange={(e) => { uploadFiles(e.target.files, uploadTargetDir); e.target.value = ''; setUploadTargetDir(null); }} />
                <div style={{flex:1,overflow:'auto'}}>
                  <LocalTree path={project.path} refreshNonce={treeNonce} onSelectFile={(path) => { readFile(path); setMobileStep('editor'); }} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} />
                </div>
              </div>
            )}

            {/* Terminal — always mounted once the detail view opens, hidden when inactive.
                Using visibility+height:0 instead of display:none so xterm.js
                ResizeObserver can still measure the element when it becomes visible. */}
            <div style={{
              flex: mobileDetailTab === 'terminal' ? 1 : undefined,
              overflow: 'hidden', display: 'flex', flexDirection: 'column',
              visibility: mobileDetailTab === 'terminal' ? 'visible' : 'hidden',
              height: mobileDetailTab === 'terminal' ? undefined : 0,
              pointerEvents: mobileDetailTab === 'terminal' ? 'auto' : 'none',
            }}>
              <ProjectTerminal project={project} visible={mobileStep === 'detail' && mobileDetailTab === 'terminal'} />
            </div>

            {mobileDetailTab === 'agents' && (
              <div style={{flex:1,overflow:'auto',padding:'12px 14px'}}>
                <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}>
                  <span style={{fontFamily:"'Press Start 2P',monospace",fontSize:10,letterSpacing:'0.05em'}}>👥 ASSIGNED · {(project.agentIds || []).length}</span>
                  {(project.agentIds || []).length > 0 && onSwitchView && (
                    <button className="px-btn primary" style={{fontSize:10,padding:'8px 16px',marginLeft:'auto',minHeight:36}} onClick={() => onSwitchView('chat')}>TALK ›</button>
                  )}
                </div>
                <div style={{display:'flex',flexDirection:'column',gap:6}}>
                  {agents.map(a => {
                    const assigned = (project.agentIds || []).includes(a.id);
                    return (
                      <label key={a.id} style={{display:'flex',alignItems:'center',gap:10,padding:'10px 8px',fontSize:14,cursor:'pointer',borderRadius:8,background: assigned ? 'var(--accent-sun-10, rgba(218,165,32,0.1))' : 'transparent',border: assigned ? '1px solid var(--accent-sun)' : '1px solid transparent',transition:'all 0.15s',minHeight:44}}>
                        <input type="checkbox" checked={assigned} onChange={() => toggleAgent(a.id)} style={{width:22,height:22,accentColor:'var(--accent-sun)'}} />
                        <span style={{fontWeight:assigned ? 700 : 400}}>{a.name}</span>
                        {a.role && <span style={{fontSize:11,opacity:0.5}}>· {a.role}</span>}
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: file editor */}
        {mobileStep === 'editor' && openFile && (
          <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0}}>
            <div className="proj-edit-head ide-edit-head" style={{flexWrap:'wrap',gap:6,padding:'8px 10px'}}>
              <span className="ide-tab" style={{flex:'1 1 auto',minWidth:0}}>
                <span className="ide-tab-icon">{ideFileIcon(openFile.path)}</span>
                <span className="ide-tab-name" style={{overflow:'hidden',textOverflow:'ellipsis'}}>{openFile.path.split(/[\\/]/).pop()}</span>
                {openFile.dirty && <span className="ide-tab-dot">●</span>}
              </span>
              {err && <span className="proj-edit-err">{officeCause(err)}</span>}
              <span style={{display:'inline-flex', gap:2}}>
                <button className={`px-btn ${!previewMode ? 'primary' : 'secondary'}`} style={{fontSize:10, padding:'5px 10px'}} onClick={() => setPreviewMode(false)}>Code</button>
                <button className={`px-btn ${previewMode ? 'primary' : 'secondary'}`} style={{fontSize:10, padding:'5px 10px'}} onClick={() => setPreviewMode(true)}>Preview</button>
              </span>
              <button className="px-btn primary" style={{fontSize:11,padding:'6px 14px'}} onClick={saveFile} disabled={!openFile.dirty || busy}>
                {busy ? 'Saving…' : openFile.dirty ? 'Save' : 'Saved'}
              </button>
            </div>
            {previewMode
              ? <FilePreview file={openFile} />
              : <IDEEditor
                  value={openFile.content}
                  onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}
                  path={openFile.path}
                />}
          </div>
        )}

        {showAdd ? (
          <AddProjectModal
            prefillName={addPrefill}
            onClose={() => setShowAdd(false)}
            onCommit={commitProject}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="view-projects">
      <div className="section-title">
        🗂 PROJECTS
        <span className="tag">{projects.length} {projects.length === 1 ? 'project' : 'projects'}</span>
      </div>
      <div style={{display: 'flex', gap: 0, height: 'calc(100% - 48px)', overflow: 'hidden'}}>
        {/* Left: project list */}
        <div
          style={{
            width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column',
            borderRight: '1px solid var(--rule)', overflow: 'hidden',
            background: dragHover ? 'rgba(240, 198, 116, 0.15)' : 'transparent',
            outline: dragHover ? '2px dashed var(--accent-sun)' : 'none',
            outlineOffset: '-4px',
            transition: 'background var(--motion-fast) var(--ease-out)',
          }}
          onDragOver={(e) => { e.preventDefault(); setDragHover(true); }}
          onDragLeave={() => setDragHover(false)}
          onDrop={onDropFolder}
        >
          <div className="proj-section-head" style={{display:'flex',alignItems:'center',gap:'var(--sp-3)'}}>
            <span style={{flex:1}}>PROJECTS · {projects.length}</span>
            <button
              onClick={() => addProject('')}
              title="Add a new project (drop a folder here too)"
              style={{
                background: 'var(--paper)', border: '1.5px solid var(--ink)',
                borderRadius: 'var(--radius-2)',
                fontSize: 'var(--text-9)', fontWeight: 700,
                padding: 'var(--sp-1) var(--sp-3)',
                color: 'var(--ink)', cursor: 'pointer',
              }}
            >+ ADD</button>
          </div>
          <div style={{overflowY: 'auto', flex: 1, padding: '4px 0'}}>
            {projects.length === 0 && (
              <div className="proj-empty-msg">
                No projects yet.<br/>
                <span style={{fontSize:'var(--text-9)',opacity:0.7}}>Click + ADD or drop a folder here.</span>
              </div>
            )}
            {projects.map(p => (
              <div
                key={p.id}
                className={'tree-row proj-list-row' + (selected === p.id ? ' active' : '')}
                style={{cursor: 'pointer', padding: '8px 12px', flexDirection: 'column', alignItems: 'flex-start', gap: 1, position: 'relative'}}
                onClick={() => { if (renamingId !== p.id) { setSelected(p.id); setOpenFile(null); setRightTab('files'); } }}
                title={p.path}
              >
                {renamingId === p.id ? (
                  <input
                    autoFocus
                    value={renameDraft}
                    onChange={e => setRenameDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
                      else if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
                    }}
                    onBlur={commitRename}
                    onClick={e => e.stopPropagation()}
                    style={{
                      width: '100%', fontFamily: 'VT323', fontSize: 16,
                      padding: '2px 4px', border: '2px solid var(--ink)',
                      background: 'var(--paper)', color: 'var(--ink)',
                    }}
                  />
                ) : (
                  <div className="proj-list-name">{p.name}</div>
                )}
                {p.path && renamingId !== p.id && <div className="proj-list-path">{p.path}</div>}
                {/* Hover-only row actions — visible only when this row is
                    the active selection so the list stays clean. The
                    renaming UI takes precedence so these don't overlap. */}
                {selected === p.id && renamingId !== p.id && (
                  <div className="proj-row-actions" style={{
                    position: 'absolute', top: 4, right: 4,
                    display: 'flex', gap: 2,
                  }}>
                    <button
                      title="Rename project"
                      onClick={(e) => { e.stopPropagation(); beginRename(p); }}
                      style={{
                        fontSize: 9, padding: '2px 5px',
                        border: '1px solid var(--rule)', borderRadius: 3,
                        background: 'var(--paper)', color: 'var(--ink)',
                        cursor: 'pointer',
                      }}
                    >✎</button>
                    <button
                      title="Delete project"
                      onClick={(e) => { e.stopPropagation(); deleteProject(p); }}
                      style={{
                        fontSize: 9, padding: '2px 5px',
                        border: '1px solid var(--rule)', borderRadius: 3,
                        background: 'var(--paper)', color: 'var(--ink-3, #b85a4a)',
                        cursor: 'pointer',
                      }}
                    >✕</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Middle: file tree + agent assignment panel */}
        {project ? (
          <div style={{width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--rule)', overflow: 'hidden'}}>
            <div className="proj-section-head" title={project.path} style={{display:'flex',alignItems:'center',gap:'var(--sp-2)'}}>
              <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{project.name}</span>
              <button
                className="px-btn ghost"
                style={{fontSize:9,padding:'2px 7px',flexShrink:0}}
                title="New folder in this project"
                onClick={newFolder}
              >＋ Folder</button>
              <button
                className="px-btn ghost"
                style={{fontSize:9,padding:'2px 7px',flexShrink:0}}
                title="Upload files to this project — share them with whoever is assigned"
                onClick={() => { setUploadTargetDir(null); if (uploadInputRef.current) uploadInputRef.current.click(); }}
              >⬆ Share</button>
            </div>
            <input ref={uploadInputRef} type="file" multiple style={{display:'none'}}
              onChange={(e) => { uploadFiles(e.target.files, uploadTargetDir); e.target.value = ''; setUploadTargetDir(null); }} />
            <div
              style={{overflowY:'auto', flex:1, padding:'4px 0', position:'relative',
                      background: fileDragHover ? 'rgba(240, 198, 116, 0.15)' : 'transparent',
                      outline: fileDragHover ? '2px dashed var(--accent-sun)' : 'none', outlineOffset:'-2px',
                      transition:'background var(--motion-fast) var(--ease-out)'}}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setFileDragHover(true); }}
              onDragLeave={(e) => {
                e.preventDefault();
                // Ignore leaves that just cross onto a child tree row — only
                // clear when the drag actually exits the container (no strobe).
                if (!e.currentTarget.contains(e.relatedTarget)) setFileDragHover(false);
              }}
              onDrop={(e) => {
                e.preventDefault(); e.stopPropagation(); setFileDragHover(false);
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
              }}
            >
              <LocalTree path={project.path} onSelectFile={readFile} refreshNonce={treeNonce} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} />
              {fileDragHover && (
                <div style={{position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center',
                             pointerEvents:'none', fontSize:11, fontWeight:600, color:'var(--accent-sun)',
                             textShadow:'0 1px 2px var(--paper)'}}>Drop to share with the team</div>
              )}
            </div>
            {/* Agent assignment — assigning at least one agent reveals a
                "📁 <project name>" room in the chat panel's thread tabs.
                Sending a message in that room fans out to all assigned
                agents, with all their replies streamed inline. */}
            <div className="proj-agents-panel">
              <div className="proj-agents-head">
                <span>👥 ASSIGNED · {(project.agentIds || []).length}</span>
                <button
                  className="proj-talk-btn"
                  style={{width: 'auto', margin: 0, padding: '2px 8px', fontSize: 9}}
                  disabled={(project.agentIds || []).length === 0}
                  onClick={() => {
                    /* Open the floating chat window (Projects view uses it)
                       and switch its active thread to this project's room.
                       Cross-component event lets ChatPanel set itself
                       without us lifting state. */
                    if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true);
                    window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'project:' + project.id }));
                  }}
                  title="Open this project's chat room, where the team talks"
                >TALK ↗</button>
              </div>
              <div className="proj-agents-list">
                {agents.length === 0 && (
                  <div style={{fontSize: 10, opacity: 0.5, padding: '6px'}}>
                    No coworkers hired yet — go to Team to hire someone.
                  </div>
                )}
                {agents.map(a => {
                  const checked = (project.agentIds || []).includes(a.id);
                  return (
                    <div
                      key={a.id}
                      className={'proj-agents-row' + (checked ? ' checked' : '')}
                      onClick={() => toggleAgent(a.id)}
                      title={`${a.role}${a.elevated ? ' · has file and shell access' : ''}`}
                    >
                      <span className={'proj-agents-checkbox' + (checked ? ' checked' : '')}>
                        {checked ? '✓' : ''}
                      </span>
                      <span style={{flex: 1, fontWeight: 600}}>{a.name}</span>
                      <span style={{fontSize: 9, opacity: 0.6}}>{a.elevated ? '🛡' : '👤'}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div style={{width: 260, flexShrink: 0, borderRight: '1px solid var(--rule)'}}>
            <div className="proj-empty-msg">Select a project to browse its files.</div>
          </div>
        )}

        {/* Right: [FILES] [TERMINAL] tab bar + content */}
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden'}}>
          {project && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 0,
              borderBottom: '1px solid var(--rule)', flexShrink: 0,
              background: 'var(--paper)',
            }}>
              {['files', 'terminal'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: '6px 16px', fontSize: 10, fontWeight: 700,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: rightTab === tab ? '#7c6bff' : 'var(--ink-dim)',
                    borderBottom: rightTab === tab ? '2px solid #7c6bff' : '2px solid transparent',
                    letterSpacing: 1, textTransform: 'uppercase',
                  }}
                >
                  {tab === 'files' ? '📄 FILES' : '⚡ TERMINAL'}
                </button>
              ))}
            </div>
          )}
          {/* Persistent terminal sessions — stay mounted so PTY + chat survive tab/project switches */}
          {openedTerminals.map(pid => {
            const p = projects.find(x => x.id === pid);
            if (!p) return null;
            const active = rightTab === 'terminal' && selected === pid;
            return (
              <div key={pid} style={{flex: 1, overflow: 'hidden', display: active ? undefined : 'none'}}>
                <ProjectTerminal project={p} visible={active} />
              </div>
            );
          })}

          {/* Files / empty states — only when terminal is not active */}
          {!(rightTab === 'terminal' && project) && (
            rightTab === 'files' && openFile ? (
              <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0}}>
                <div className="proj-edit-head ide-edit-head">
                  <span className="ide-tab">
                    <span className="ide-tab-icon">{ideFileIcon(openFile.path)}</span>
                    <span className="ide-tab-name">{openFile.path.split(/[\\/]/).pop()}</span>
                    {openFile.dirty && <span className="ide-tab-dot" title="unsaved changes">●</span>}
                  </span>
                  <span className="ide-tab-path">{openFile.path}</span>
                  {err && <span className="proj-edit-err">{officeCause(err)}</span>}
                  <span style={{flex:1}}/>
                  <span style={{display:'inline-flex', gap:2, marginRight:8}}>
                    <button className={`px-btn ${!previewMode ? 'primary' : 'secondary'}`} style={{fontSize:9, padding:'3px 9px'}} onClick={() => setPreviewMode(false)}>Code</button>
                    <button className={`px-btn ${previewMode ? 'primary' : 'secondary'}`} style={{fontSize:9, padding:'3px 9px'}} onClick={() => setPreviewMode(true)} title="Render this file (HTML, PDF, image, markdown…)">Preview</button>
                  </span>
                  {!previewMode && (
                    <span className="ide-stats">
                      {openFile.content.split('\n').length} ln · {openFile.content.length} ch · {ideLangFromPath(openFile.path).toUpperCase()}
                    </span>
                  )}
                  <button className="px-btn primary" style={{fontSize: 10, padding: '3px 10px'}} onClick={saveFile} disabled={!openFile.dirty || busy}>
                    {busy ? 'Saving…' : openFile.dirty ? 'Save' : 'Saved'}
                  </button>
                </div>
                {previewMode
                  ? <FilePreview file={openFile} />
                  : <IDEEditor
                      value={openFile.content}
                      onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}
                      path={openFile.path}
                    />}
              </div>
            ) : project ? (
              <div style={{flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                <div className="proj-empty-msg" style={{textAlign: 'center'}}>
                  <div style={{fontSize: 24, marginBottom: 8, opacity: 0.4}}>📄</div>
                  Select a file to edit, or switch to Terminal to run a CLI agent.
                </div>
              </div>
            ) : null
          )}
        </div>
      </div>
      {showAdd ? (
        <AddProjectModal
          prefillName={addPrefill}
          onClose={() => setShowAdd(false)}
          onCommit={commitProject}
        />
      ) : null}
    </div>
  );
}

/* ---------------- Add Project modal ---------------- */
/* ── File-system browser popup ────────────────────────────────────────────── */
function FileBrowserModal({ initialPath, onSelect, onClose }) {
  const [curPath,  setCurPath]  = useSV('');
  const [parent,   setParent]   = useSV(null);
  const [entries,  setEntries]  = useSV([]);
  const [loading,  setLoading]  = useSV(false);
  const [err,      setErr]      = useSV(null);

  const browse = (p) => {
    setLoading(true); setErr(null);
    const qs = p ? `?path=${encodeURIComponent(p)}` : '';
    fetch(`${window._API_BASE || ''}/fs/browse${qs}`)
      .then(r => r.json())
      .then(j => {
        if (j.error) throw new Error(j.error);
        setCurPath(j.path);
        setParent(j.parent);
        setEntries(j.entries || []);
      })
      .catch(e => setErr(e.message || String(e)))
      .finally(() => setLoading(false));
  };

  React.useEffect(() => { browse(initialPath || ''); }, []);

  return (
    <div className="backdrop" onClick={onClose} style={{ zIndex: 2000 }}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--paper)', border: '2px solid var(--rule)',
          borderRadius: 10, width: 'min(520px, 96vw)', maxHeight: '80vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 8px 48px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 14px', borderBottom: '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}>
          <span style={{ fontWeight: 700, fontSize: 11, flex: 1 }}>📁 BROWSE FOLDERS</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--ink-dim)' }}>✕</button>
        </div>

        {/* Path breadcrumb + Up */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 12px', borderBottom: '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}>
          <button
            onClick={() => parent && browse(parent)}
            disabled={!parent || loading}
            style={{
              background: 'none', border: '1px solid var(--rule)', borderRadius: 4,
              padding: '2px 8px', fontSize: 10, cursor: parent ? 'pointer' : 'default',
              color: parent ? 'var(--ink)' : 'var(--ink-dim)',
            }}
          >↑ Up</button>
          <span style={{
            flex: 1, fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
            color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', direction: 'rtl', textAlign: 'left',
          }}>{curPath || '…'}</span>
        </div>

        {/* Entries */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {loading && <div style={{ padding: 16, fontSize: 12, color: 'var(--ink-dim)', textAlign: 'center' }}>Loading…</div>}
          {err    && <div style={{ padding: 12, fontSize: 11, color: 'var(--red, #f87171)' }}>⚠ {officeCause(err)}</div>}
          {!loading && entries.length === 0 && !err && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--ink-dim)', textAlign: 'center' }}>Empty folder</div>
          )}
          {entries.map(e => (
            <div
              key={e.path}
              onClick={() => e.type === 'dir' && browse(e.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 14px', cursor: e.type === 'dir' ? 'pointer' : 'default',
                fontSize: 12, color: e.type === 'dir' ? 'var(--ink)' : 'var(--ink-dim)',
                borderBottom: '1px solid var(--rule)',
              }}
              className={e.type === 'dir' ? 'tree-row' : ''}
            >
              <span style={{ fontSize: 14, width: 20 }}>{e.type === 'dir' ? '📁' : '📄'}</span>
              <span style={{ flex: 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{e.name}</span>
              {e.type === 'dir' && <span style={{ fontSize: 10, color: 'var(--ink-dim)' }}>›</span>}
            </div>
          ))}
        </div>

        {/* Footer — select current folder */}
        <div style={{
          padding: '10px 14px', borderTop: '1px solid var(--rule)',
          display: 'flex', gap: 8, justifyContent: 'flex-end',
          background: 'var(--paper-2)',
        }}>
          <button className="px-btn secondary" onClick={onClose}>Cancel</button>
          <button
            className="px-btn primary"
            disabled={!curPath}
            onClick={() => { if (curPath) onSelect(curPath); }}
          >✓ Select This Folder</button>
        </div>
      </div>
    </div>
  );
}

/* ── Add Project modal ────────────────────────────────────────────────────── */
function AddProjectModal({ prefillName, onClose, onCommit }) {
  const [tab, setTab] = useSV('local');           // 'local' | 'github'
  const [name, setName] = useSV(prefillName || '');
  const [path, setPath] = useSV('');
  const [repoUrl, setRepoUrl] = useSV('');
  const [shallow, setShallow] = useSV(true);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [showBrowser, setShowBrowser] = useSV(false);

  const submitLocal = (e) => {
    e && e.preventDefault();
    setErr(null);
    if (!name.trim()) return setErr('name required');
    if (!path.trim()) return setErr('path required');
    onCommit({ name: name.trim(), path: path.trim(), source: 'local' });
  };

  const submitGithub = async (e) => {
    e && e.preventDefault();
    setErr(null);
    const url = repoUrl.trim();
    if (!url) return setErr('repo URL or owner/repo required');
    setBusy(true);
    try {
      const r = await CafresoHQClient.cloneRepo({
        url,
        name: name.trim() || undefined,
        depth: shallow ? 1 : 0,
      });
      onCommit({ name: r.name, path: r.path, source: 'github:' + url });
    } catch (e2) {
      /* This box used to print `message + '\n' + detail`, and `detail` is
         git's stderr verbatim. Typing a repo name with a typo, on the
         surface the getting-started checklist sends you to at step 5, got:

           git clone failed (exit 128)
           Cloning into '/private/tmp/…/pj-space/repo'...
           remote: Repository not found.
           fatal: repository 'https://github.com/owner/repo/' not found

         An exit code, an absolute path, "remote:", "fatal:" — and the one
         line that says what to DO about it is third of four. Same class as
         the vault's raw dumps, and the same fix: one honest sentence.

         The raw text is not thrown away, it goes to the console, because
         the person debugging a self-hosted install is a different reader
         from the one adding their first project. */
      const raw = (e2.message || String(e2)) + (e2.detail ? '\n' + e2.detail : '');
      try { console.warn('[projects] clone failed:', raw); } catch (_) {}
      setErr(repoCause(raw));
      setBusy(false);
    }
  };

  /* Portaled to <body>: this modal is opened from INSIDE the floating
     Workspace .hq-window (position:fixed, z-index:300), which forms a
     stacking context — so however high the backdrop's own z-index, it was
     capped at the window's 300 and rendered BENEATH any body-level modal
     (z 400). Concretely: the onboarding's Job Postings book covered the
     Add-Project dialog completely, so "+ ADD" looked like it did nothing. */
  return ReactDOM.createPortal(
    <div className="backdrop" onClick={onClose}>
      <div className="modal addproj-modal" onClick={e => e.stopPropagation()} style={{width:'min(560px, 100%)', gridTemplateRows: 'auto auto 1fr'}}>
        <div className="modal-head">
          <span className="title">ADD PROJECT</span>
          <button className="px-btn secondary" onClick={onClose} style={{fontSize:11,padding:'4px 10px'}}>✕</button>
        </div>
        <div className="addproj-tabs">
          <button className={'addproj-tab' + (tab === 'local' ? ' active' : '')} onClick={() => setTab('local')}>📁 Local folder</button>
          <button className={'addproj-tab' + (tab === 'github' ? ' active' : '')} onClick={() => setTab('github')}>🐙 GitHub repo</button>
        </div>
        <div className="modal-body">
          {tab === 'local' ? (
            <form onSubmit={submitLocal} className="addproj-form">
              <label>Name<input value={name} onChange={e => setName(e.target.value)} placeholder="My project" autoFocus /></label>
              <label>
                Absolute path
                {/* POSIX, not "C:\Users\You\...": the Browse picker two lines
                   down lists this same server's real paths and has always
                   returned them slash-style ("Users/you/…") — the manual
                   field's own hint disagreed with its sibling button in the
                   same form. _cafresohq_allowed_dirs defaults to
                   expanduser('~'), which is what every self-hosted install
                   actually resolves to. */}
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    value={path}
                    onChange={e => setPath(e.target.value)}
                    placeholder="/Users/you/projects/myrepo"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="px-btn secondary"
                    onClick={() => setShowBrowser(true)}
                    style={{ whiteSpace: 'nowrap', fontSize: 11, padding: '4px 10px' }}
                  >📁 Browse</button>
                </div>
              </label>
              {/* Was: "Path must be inside CAFRESOHQ_ALLOWED_DIRS for your
                  coworkers to reach it." An environment-variable name, as
                  the ONLY guidance about which paths work, in the dialog
                  the getting-started checklist opens at step 5 — and a
                  boss who has never seen that name has no way to look up
                  its value from here.

                  It was also false for the common install. `_safe_path`
                  skips the whitelist entirely when the runtime is local
                  and nothing was set explicitly (serve.py), so on a
                  default self-hosted run there is no such restriction —
                  the sentence invented a rule and then named it in a
                  vocabulary the reader could not act on.

                  This says the same thing in the one place it is true in
                  BOTH modes: Browse lists exactly what the coworkers can
                  reach, because it resolves through the same guard. */}
              <small>Any folder on this machine — 📁 Browse shows the ones your coworkers can open.</small>
              {err ? <div className="addproj-err">{err}</div> : null}
              <div className="addproj-actions">
                <button type="button" className="px-btn secondary" onClick={onClose}>Cancel</button>
                <button type="submit" className="px-btn primary">Add</button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitGithub} className="addproj-form">
              <label>Repo<input value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="owner/repo  or  https://github.com/owner/repo" autoFocus /></label>
              <label>Local folder name (optional)<input value={name} onChange={e => setName(e.target.value)} placeholder="auto from URL if blank" /></label>
              <label className="checkbox-row">
                <input type="checkbox" checked={shallow} onChange={e => setShallow(e.target.checked)} />
                <span>Shallow clone (fast — no history)</span>
              </label>
              <small>Cloned into the first allowed directory. Requires <code>git</code> on the server's PATH.</small>
              {err ? <div className="addproj-err" style={{whiteSpace:'pre-wrap'}}>{err}</div> : null}
              <div className="addproj-actions">
                <button type="button" className="px-btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
                <button type="submit" className="px-btn primary" disabled={busy}>{busy ? 'Cloning…' : 'Clone & add'}</button>
              </div>
            </form>
          )}
        </div>
      </div>
      {showBrowser && (
        <FileBrowserModal
          initialPath={path || ''}
          onSelect={(selected) => { setPath(selected); if (!name.trim()) setName(selected.split(/[\\/]/).filter(Boolean).pop() || ''); setShowBrowser(false); }}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </div>,
    document.body
  );
}

/* ---------------- Coming Soon placeholder ---------------- */

export { ProjectsView, WorkspaceView };

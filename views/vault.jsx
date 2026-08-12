import { CafresoHQClient, VaultBridge } from '../claude-client.jsx';
import { snagCause } from '../app/floor.jsx';
import { FolderTree } from './core.jsx';
import { GraphView, simulate } from './graph.jsx';
import { renderMarkdown } from './ide.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;

const _isHtmlPath = (path) => /\.html?$/i.test(path || '');

/* "Simple page" is one of exactly THREE starter tasks on the whole app's
   front door (§3.6) — a boss's first delivery is very often an .html file.
   renderMarkdown() escapes every `<`/`>` before it ever looks for markdown
   syntax (views/ide.jsx), so a real page's own source came back as inert
   text — `<!DOCTYPE html>`, `<style>`, `<script>`, one escaped line per tag
   — under a "Preview" checkbox that is ON. §4 rules this out in as many
   words: "Not a dev console." An iframe is the only preview that keeps the
   promise the DeliverySheet button already makes: "Open the page →". No
   `allow-same-origin` — page markup can come from any hired coworker, and a
   sandboxed opaque origin means a live script in there still cannot reach
   this app's own storage, cookies, or DOM. */
function HtmlFramePreview({ html }) {
  return (
    <iframe
      className="vault-preview vault-preview-html"
      srcDoc={html || ''}
      sandbox="allow-scripts allow-forms allow-modals allow-popups"
      style={{ width: '100%', height: '100%', border: 0, background: '#fff' }}
      title="Page preview"
    />
  );
}

function VaultView({ agents = null, onOpenSettings } = {}) {
  const [status, setStatus] = useSV(null);
  const [files, setFiles] = useSV([]);
  const [q, setQ] = useSV('');
  const [hits, setHits] = useSV(null);
  const [openNote, setOpenNote] = useSV(null);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [expanded, setExpanded] = useSV(new Set());
  const [preview, setPreview] = useSV(true);
  const [graphMinimized, setGraphMinimized] = useSV(false);
  const _isMobileV = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;
  /* Opens on FILES, not the graph. It used to default to 'graph' on any
     viewport under 768px, which is the phone AND a narrow window.

     Measured on a fresh office right after the first delivery landed: the
     boss taps the filing cabinet to look at the thing their coworker just
     filed, and gets a network diagram plus an analysis panel telling them
     the cabinet is "Dispersed — many scattered topics, consider bridging
     them", with "Separate clusters: 2" and a "Structural gap" between the
     one note and the coworker who wrote it. On a cabinet containing one
     file.

     A filing cabinet's job is to show you your files. The graph is a
     genuinely good power feature and it is one tap away — but it cannot be
     the answer to "where is my document". */
  const [vaultTab, setVaultTab] = useSV(_isMobileV ? 'tree' : null); // 'tree' | 'graph' | 'editor'

  // ── Bridge mode: when running inside the SvelteKit shell iframe, all vault
  // reads/writes go through VaultBridge (postMessage → parent decrypts).
  // Falls back to the local serve.py API when opened standalone.
  const _bridge = typeof window !== 'undefined' && VaultBridge?.isAvailable()
    ? VaultBridge : null;
  // Map display path → blob id (only populated in bridge mode)
  const _pathToId = useRV({});

  // Helper: adapt bridge file list [{id,name,...}] → [{path,title,id,...}]
  const _adaptBridgeFiles = (bridgeFiles) => {
    const m = {};
    const adapted = (bridgeFiles || []).map(f => {
      m[f.name] = f.id;
      return { ...f, path: f.name, title: f.name.split(/[\\/]/).pop().replace(/\.md$/i, '') };
    });
    _pathToId.current = m;
    return adapted;
  };

  /* GraphView (embedded below) loads its data once on mount and again only
     when its own `source`/`scope` controls change — never when a note gets
     created, deleted, renamed, or saved here. It already exposes a
     `window.CafresoHQGraph.refresh()` escape hatch for exactly this, but
     nothing called it: the file tree updated correctly on every mutation
     while the graph panel next to it kept showing deleted notes as present
     and never picked up new ones. Watched live — deleted a note, created
     a fresh one, clicked this same Refresh button, and "On the map: 8" /
     the deleted note's own node sat there unchanged the whole time; only
     the file list caught up. Best-effort and swallowed: a graph panel one
     tick behind is a cosmetic problem, not one worth a broken vault over. */
  const refreshGraph = () => {
    try { window.CafresoHQGraph && window.CafresoHQGraph.refresh(); } catch (_e) {}
  };

  /* §7, "every failure is one honest sentence": these used to be native
     `alert()`s, three of them interpolating a raw `e.message` straight at
     the boss — the exact thing the note further down criticises the removed
     Obsidian button for, sitting five lines from where it was written. The
     vault had already moved to hqConfirm/hqPrompt for confirm and prompt;
     the alerts were simply left behind, and the comment claiming they were
     gone was never checked against the file it lives in.

     `say` for things that merely happened, `snag` for things that failed —
     the latter runs the cause through the same classifier the floor and the
     chat paths use, so a vault failure reads like every other failure in the
     office instead of like a browser dialog.

     snagCAUSE, not snagSentence: these messages bring their own subject and
     verb ("Couldn't delete that note"), and snagSentence prepends a "hit a
     snag — " spine meant for surfaces that have none. Written the wrong way
     first and caught by reading the toast it actually produced: "Couldn't
     delete that note — hit a snag — NetworkError…", two spines in one line.
     floor.jsx says this in as many words above snagCause — "One classifier,
     two shapes, no regex surgery at the call site" — and names the twin
     mistake (stripping the prefix instead) that once printed a verbless
     "Kenji that brain isn't signed in yet". Both shapes exist precisely so
     neither call site has to improvise. */
  const say = (text, kind = 'info') => {
    const t = window.cafresohqToast;
    if (t && t[kind]) t[kind](text);
  };
  const snag = (what, err) => {
    say(`${what} — ${snagCause((err && err.message) || String(err))}`, 'error');
  };

  const refresh = async () => {
    setErr(null);
    if (_bridge) {
      try {
        const bridgeFiles = await _bridge.list();
        setFiles(_adaptBridgeFiles(bridgeFiles));
        setStatus({ configured: true, exists: true, name: '🔐 Encrypted Vault', backend: 'bridge' });
        refreshGraph();
      } catch (e) {
        setErr(e.message || 'Could not load vault from shell.');
        setStatus({ configured: false, unavailable: true, error: e.message });
      }
      return;
    }
    try {
      const s = await CafresoHQClient.vaultStatus();
      setStatus(s);
      if (!s.configured) { setFiles([]); return; }
      try {
        setFiles(await CafresoHQClient.vaultList());
        refreshGraph();
      } catch (e) {
        setFiles([]);
        setErr(e.message || 'Could not list vault notes.');
      }
    } catch (e) {
      const message = e.message || 'CafresoHQ bridge is not reachable.';
      setFiles([]);
      setStatus({ configured: false, unavailable: true, error: message });
      setErr(message);
    }
  };
  React.useEffect(() => { refresh(); }, []);

  // Listen for live vault file updates pushed from the parent shell
  React.useEffect(() => {
    if (!_bridge) return;
    const handler = (e) => {
      if (e.source !== window.parent) return;
      // Same origin pin as the bridges in claude-client.jsx — otherwise any
      // framing page could inject a fake vault file list into this view.
      if (e.origin !== window.__hqShellOrigin) return;
      if (e.data?.type === 'vault:files:update') {
        setFiles(_adaptBridgeFiles(e.data.files || []));
        if (!status) setStatus({ configured: true, exists: true, name: '🔐 Encrypted Vault', backend: 'bridge' });
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  React.useEffect(() => {
    const handler = (e) => { if (e.detail && e.detail.path) openByPath(e.detail.path); };
    window.addEventListener('cafresohq:openNote', handler);
    return () => window.removeEventListener('cafresohq:openNote', handler);
  }, []);

  // Esc closes the open note (so the graph can re-expand to fullspan).
  // Don't fire while typing into inputs/textareas.
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      const t = e.target;
      const tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) return;
      closeNote();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /* Bridge-mode search: VaultBridge has no vault:search message — the shell
     only exposes list/read/write/create/remove — so vaultSearch() was being
     called unconditionally and hitting the LOCAL serve.py /vault/search
     endpoint even inside the encrypted shell, where that endpoint has no
     relationship to the boss's actual (encrypted, parent-held) notes. A
     search for a word that IS in the vault came back empty, or errored, with
     nothing telling the boss their real notes were never even looked at —
     exactly the silent-wrong-answer failure the vetKeys trust story can't
     afford. Mirrors serve.py's own /vault/search scoring (title match worth
     3, then raw occurrence count) so results rank the same either way. */
  const bridgeSearch = async (query) => {
    const ql = query.toLowerCase();
    const candidates = files.filter(f => !f.isBinary);
    const results = await Promise.all(candidates.map(async (f) => {
      let text;
      try { text = await _bridge.read(f.id); } catch (_e) { return null; }
      const tl = String(text || '').toLowerCase();
      const titleScore = f.title && f.title.toLowerCase().includes(ql) ? 3 : 0;
      const count = ql ? tl.split(ql).length - 1 : 0;
      if (!titleScore && !count) return null;
      const idx = tl.indexOf(ql);
      let snippet = '';
      if (idx >= 0) {
        const s = Math.max(0, idx - 60), e = Math.min(text.length, idx + query.length + 60);
        snippet = (s > 0 ? '…' : '') + text.slice(s, e).replace(/\n/g, ' ').trim() + (e < text.length ? '…' : '');
      }
      return { path: f.path, title: f.title, score: titleScore + count, snippet };
    }));
    return results.filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 10);
  };

  const search = async () => {
    if (!q.trim()) { setHits(null); return; }
    try { setHits(_bridge ? await bridgeSearch(q.trim()) : await CafresoHQClient.vaultSearch(q.trim())); }
    catch (e) { setErr(e.message); setHits([]); }
  };

  const openByPath = async (path) => {
    if (!path) return;
    // Binary files (images, video, audio) can't open in the text editor
    const fileMeta = files.find(f => f.path === path);
    if (fileMeta?.isBinary) {
      say(`"${fileMeta.title}" is an image or media file — open it from the vault at ai.cafreso.com to view it.`, 'info');
      return;
    }
    // Flush any dirty buffer before swapping files — no silent edit loss.
    if (openNoteRef.current && openNoteRef.current.dirty) {
      await saveNoteRef.current({ quiet: true });
    }
    setBusy(true); setErr(null); setSaveState('');
    try {
      let text;
      if (_bridge) {
        const id = _pathToId.current[path];
        if (!id) throw new Error('File not found in vault index: ' + path);
        text = await _bridge.read(id);
      } else {
        text = await CafresoHQClient.vaultRead(path);
      }
      setOpenNote({ path, id: _pathToId.current[path] || null, content: text, dirty: false });
      if (_isMobileV) setVaultTab('editor');
      const parts = path.split('/').filter(Boolean);
      const newExp = new Set(expanded);
      for (let i = 1; i < parts.length; i++) newExp.add(parts.slice(0, i).join('/'));
      setExpanded(newExp);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  /* Saving is tracked per-editor (inline chip) and NEVER via the view-level
     `err` — a failed save used to replace the whole vault view with an error
     screen, hiding the user's unsaved text. Autosave (2.5s idle) plus
     flush-on-leave below mean typed text can no longer be silently lost. */
  const [saveState, setSaveState] = React.useState('');   // '' | 'saving' | 'saved' | 'error: …'
  const openNoteRef = React.useRef(null);
  openNoteRef.current = openNote;

  const saveNote = async (opts) => {
    const note = openNoteRef.current;
    if (!note || !note.dirty) return;
    setBusy(true); setSaveState('saving');
    try {
      if (_bridge) {
        if (note.id) {
          await _bridge.write(note.id, note.content);
        } else {
          const meta = await _bridge.create(note.path, note.content);
          setOpenNote(n => (n && n.path === note.path ? { ...n, id: meta.id } : n));
        }
      } else {
        await CafresoHQClient.vaultWrite(note.path, note.content, 'write');
      }
      // Clear dirty only if nothing was typed while the save was in flight.
      setOpenNote(n => (n && n.path === note.path && n.content === note.content)
        ? { ...n, dirty: false } : n);
      setSaveState('saved');
      if (!(opts && opts.quiet)) await refresh();
    } catch (e) {
      setSaveState('error: ' + (e.message || 'save failed'));
    }
    setBusy(false);
  };
  const saveNoteRef = React.useRef(saveNote);
  saveNoteRef.current = saveNote;

  // Autosave: 2.5s after the last keystroke.
  React.useEffect(() => {
    if (!openNote || !openNote.dirty) return;
    const t = setTimeout(() => { saveNoteRef.current({ quiet: true }); }, 2500);
    return () => clearTimeout(t);
  }, [openNote && openNote.content, openNote && openNote.dirty]);

  // Flush-on-leave: unmounting the vault view (switching to another app view)
  // fires a final save of any dirty buffer.
  React.useEffect(() => () => {
    const n = openNoteRef.current;
    if (n && n.dirty) saveNoteRef.current({ quiet: true });
  }, []);

  // Closing or switching notes flushes the dirty buffer first.
  const closeNote = () => {
    const n = openNoteRef.current;
    if (n && n.dirty) saveNoteRef.current({ quiet: true });
    setSaveState('');
    setOpenNote(null);
  };

  /* File management — upload / rename / delete. Server-vault backends only
     (the encrypted bridge vault manages its own files in the parent shell). */
  const fileInputRef = React.useRef(null);
  const onUpload = async (e) => {
    const list = Array.from(e.target.files || []);
    e.target.value = '';
    if (!list.length) return;
    setBusy(true);
    try {
      const r = await CafresoHQClient.vaultUpload(list);
      await refresh();
      /* A partial upload is a real, mixed outcome, so it says both halves and
         names the files that didn't make it — but only the first few, since
         a toast is not a log and forty filenames in one is its own kind of
         dishonesty. The count carries the rest. */
      if (r && r.failed && r.failed.length) {
        const named = r.failed.slice(0, 3).map(f => f.path).join(', ');
        const more = r.failed.length > 3 ? ` and ${r.failed.length - 3} more` : '';
        say(`Filed ${r.count}. Couldn't file ${r.failed.length}: ${named}${more}.`, 'warn');
      } else if (r && r.count) {
        say(`Filed ${r.count} file${r.count === 1 ? '' : 's'} in the vault.`, 'success');
      }
    } catch (er) { snag("Couldn't add those to the vault", er); }
    setBusy(false);
  };
  const renameNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    // Native window.prompt breaks the pixel aesthetic, blocks the JS thread,
    // and — per ui/feedback.jsx's own docstring — is silently disabled on
    // some hosts (iframe sandboxes). views/projects.jsx already made this
    // switch for its identical rename flow; the vault, the single most
    // important data surface in the app, had not.
    const to = await window.hqPrompt('Rename / move to (path inside the vault):', { value: n.path });
    if (!to || to.trim() === n.path) return;
    if (n.dirty) await saveNoteRef.current({ quiet: true });
    try {
      await CafresoHQClient.vaultRename(n.path, to.trim());
      setOpenNote(o => o ? { ...o, path: to.trim() } : o);
      await refresh();
    } catch (e) { snag("Couldn't move that note", e); }
  };
  const deleteNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    if (!(await window.hqConfirm(`Delete "${n.path}"? This cannot be undone.`, { danger: true }))) return;
    try {
      await CafresoHQClient.vaultDelete(n.path);
      setSaveState('');
      setOpenNote(null);
      await refresh();
    } catch (e) { snag("Couldn't delete that note", e); }
  };

  const newNote = async () => {
    const path = await window.hqPrompt('New note path (e.g. "Inbox/idea.md"):');
    if (!path) return;
    const norm = path.endsWith('.md') ? path : path + '.md';
    // id is null for new notes — saveNote() will call bridge.create()
    setOpenNote({ path: norm, id: null, content: '', dirty: true });
  };

  /* `openInObsidian` used to live here. Removed, not just unwired: the ONLY
     backend it can ever reach is /vault/open, which 400s unconditionally
     unless _vault_backend === 'rest' — and the one UI that could ever set
     that (modals/providers.jsx's VaultTab, with its DETECT OBSIDIAN button
     and REST key field) is deliberately excluded from the bundle (see
     modals.jsx's own comment: "kept for a future self-host build flag").

     So this button had a 0% success rate in every shipped build, by
     construction, sitting on the single most-visited pane in the vault —
     which OFFICE_AS_INTERFACE §3.6 calls "the cabinet", the story of this
     product. Its failure path was also a native `alert()` — which this note
     originally called "this app's only one — everything else is
     cafresohqToast or an inline sentence". That was wrong when it was
     written: THIS FILE still held five more, at the binary-file notice, the
     partial-upload report, and the upload/rename/delete catch blocks, three
     of them interpolating a raw `e.message`. They are toasts now (see `say`
     and `snag` above). A claim about the whole app, written from one line of
     it, and contradicted a hundred lines up in the same file — worth leaving
     visible rather than quietly deleting. The alert read
     "Could not open in Obsidian: open-in-Obsidian requires REST backend" —
     raw backend cause text, "REST backend", straight at a boss with no
     context for what that means. North-star §5: "Obsidian bridge — serves
     a power-user 1%; vault is the story." The wiring was already correctly
     parked; this was the one piece of it left standing on the core path.
     Comes back trivially alongside VaultTab whenever that flag ships. */

  if (!status) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 VAULT</div><div className="empty-state"><div className="empty-title">Loading…</div></div></div>;
  }
  /* The whole-cabinet failure screen. It used to read, in full:

          Error
          NetworkError when attempting to fetch resource.

      — the raw browser exception under the literal word "Error", with no
      button on it anywhere. Three §7 breaches at once (raw dump, dev word,
      no way forward) on the surface §3.6 calls "the cabinet", and it
      REPLACES the file tree, so the boss loses sight of their documents and
      is handed a stack-trace fragment instead. Driven live by failing
      /vault/status; the app's own offline banner answers the very same
      outage with "Your office is offline… then hit Retry", which is the bar
      this never met.

      Classifying here rather than at the five setErr() call sites on
      purpose: this is the single choke point they all render through, so
      one honest sentence covers every one of them, and `err` stays the raw
      cause for anyone debugging. */
  if (err) {
    const cause = snagCause(err);
    return (
      <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}>
        <div className="section-title">📓 VAULT</div>
        <div className="empty-state">
          <div className="empty-title">The cabinet won't open</div>
          <div className="empty-sub">{cause}. Your files are safe where they are — this is the office not answering, not the vault losing anything.</div>
          <button className="px-btn primary" style={{marginTop:16,fontSize:12,padding:'10px 20px'}}
                  onClick={() => { setErr(null); setStatus(null); refresh(); }}>↻ Try again</button>
        </div>
      </div>
    );
  }
  if (!status.configured) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 VAULT</div><div className="empty-state"><div className="empty-title">Vault not configured.</div><div className="empty-sub">Choose a Markdown vault directory in Connections settings.</div>{onOpenSettings && <button className="px-btn primary" style={{marginTop:16,fontSize:12,padding:'10px 20px'}} onClick={onOpenSettings}>⚙️ Open Settings</button>}</div></div>;
  }

  const hasNote = !!openNote;
  const showGraph = !graphMinimized;

  // Grid columns: tree pane is fixed-ish, edit + graph share remaining space.
  let gridCols;
  if (hasNote && showGraph)        gridCols = '240px 1fr 1fr';
  else if (hasNote && !showGraph)  gridCols = '240px 1fr';
  else if (!hasNote && showGraph)  gridCols = '240px 1fr';
  else                              gridCols = '240px 1fr';

  /* ---- Mobile: single-pane tab switcher ---- */
  if (_isMobileV) {
    const mobileOpenByPath = async (p) => {
      await openByPath(p);
      setVaultTab('editor');
    };
    return (
      <div className="vault-mobile" style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'}}>
        {/* Tab switcher bar */}
        <div style={{
          display:'flex',gap:0,
          borderBottom:'2px solid var(--ink)',
          background:'var(--paper-2)',
          flexShrink:0,
        }}>
          {[
            ['tree', '\u{1F4C1}', 'Files'],
            ['graph', '\u{1F9E0}', 'Graph'],
            ...(openNote ? [['editor', '✏️', openNote.path.split(/[\\/]/).pop().replace(/\.md$/,'')]] : []),
          ].map(([key, ico, label]) => (
            <button
              key={key}
              onClick={() => setVaultTab(key)}
              style={{
                flex:1,
                padding:'10px 6px',
                background: vaultTab === key ? 'var(--paper)' : 'transparent',
                border:'none',
                borderBottom: vaultTab === key ? '3px solid var(--accent-sun)' : '3px solid transparent',
                color: vaultTab === key ? 'var(--ink)' : 'var(--ink-2)',
                cursor:'pointer',
                fontFamily:"'Press Start 2P',monospace",
                fontSize:9,
                display:'flex',alignItems:'center',justifyContent:'center',gap:4,
                minHeight:44,
              }}
            >
              <span>{ico}</span> {label}
            </button>
          ))}
        </div>

        {/* Active pane */}
        <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0,overflow:'hidden'}}>
          {vaultTab === 'tree' && (
            <div className="vault-tree-pane" style={{flex:1,display:'flex',flexDirection:'column',overflow:'auto',borderRight:'none',maxHeight:'none'}}>
              <div className="vault-toolbar">
                <span style={{fontWeight:600,fontSize:11,flex:1}}>{status ? status.name : 'Vault'}</span>
                <button className="px-btn ghost" onClick={newNote} title="New note">{'➕'}</button>
                {!_bridge && (
                  <button className="px-btn ghost" onClick={() => fileInputRef.current && fileInputRef.current.click()}
                    title="Upload files into the vault">📤</button>
                )}
                <button className="px-btn ghost" onClick={refresh} title="Refresh">{'↻'}</button>
                <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
              </div>
              <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
                <input style={{width:'100%',boxSizing:'border-box'}} value={q} onChange={e=>setQ(e.target.value)} placeholder="Search vault…" onKeyDown={e=>e.key==='Enter'&&search()} />
                <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>{'🔎'} SEARCH</button>
              </div>
              {hits ? (
                <div style={{overflowY:'auto',flex:1}}>
                  <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    {hits.length} result(s)
                    <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>{'✕'}</button>
                  </div>
                  {hits.map(h => (
                    <div key={h.path} className="tree-row tree-file" onClick={()=>{ mobileOpenByPath(h.path); }}>
                      <span className="tree-name">{h.title || h.path}</span>
                      <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <FolderTree files={files} openPath={openNote?.path} onOpen={(p) => mobileOpenByPath(p)} expanded={expanded} setExpanded={setExpanded} />
              )}
            </div>
          )}

          {vaultTab === 'graph' && (
            <div className="vault-graph-pane fullspan" style={{flex:1,display:'flex',flexDirection:'column',borderLeft:'none'}}>
              <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={(p) => mobileOpenByPath(p)} onMinimize={() => setVaultTab('tree')} />
            </div>
          )}

          {vaultTab === 'editor' && openNote && (
            <div className="vault-edit-pane" style={{flex:1,display:'flex',flexDirection:'column',borderRight:'none'}}>
              <div className="vault-edit-head">
                <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
                <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
                  <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
                </label>
                {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
                {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
                <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
                  onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
                  {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
                </button>
                <button className="px-btn ghost" onClick={() => { closeNote(); setVaultTab('tree'); }} title="Close" style={{fontSize:11}}>{'✕'}</button>
              </div>
              {preview ? (
                _isHtmlPath(openNote.path)
                  ? <HtmlFramePreview html={openNote.content} />
                  : <div className="vault-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content) }} />
              ) : (
                <textarea className="vault-edit" value={openNote.content} onChange={e=>setOpenNote({ ...openNote, content: e.target.value, dirty: true })} />
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ---- Desktop: 3-column grid ---- */
  return (
    <div className="vault-layout-3col" style={{ gridTemplateColumns: gridCols }}>
      <div className="vault-tree-pane">
        <div className="vault-toolbar">
          <span style={{fontWeight:600,fontSize:11,flex:1}}>{status.name}</span>
          <button className="px-btn ghost" onClick={newNote} title="New note">➕</button>
          {!_bridge && (
            <button className="px-btn ghost" onClick={() => fileInputRef.current && fileInputRef.current.click()}
              title="Upload files into the vault">📤</button>
          )}
          <button className="px-btn ghost" onClick={refresh} title="Refresh">↻</button>
          <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
        </div>
        <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
          <input style={{width:'100%',boxSizing:'border-box'}} value={q} onChange={e=>setQ(e.target.value)} placeholder="Search vault…" onKeyDown={e=>e.key==='Enter'&&search()} />
          <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>🔎 SEARCH</button>
        </div>
        {hits ? (
          <div style={{overflowY:'auto',flex:1}}>
            <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              {hits.length} result(s)
              <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>✕</button>
            </div>
            {hits.map(h => (
              <div key={h.path} className="tree-row tree-file" onClick={()=>openByPath(h.path)}>
                <span className="tree-name">{h.title || h.path}</span>
                <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
              </div>
            ))}
          </div>
        ) : (
          <FolderTree files={files} openPath={openNote?.path} onOpen={openByPath} expanded={expanded} setExpanded={setExpanded} />
        )}
      </div>

      {hasNote && (
        <div className={`vault-edit-pane${!showGraph ? ' fullspan' : ''}`}>
          <div className="vault-edit-head">
            <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
            <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
              <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
            </label>
            {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
            {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
            <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
              onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
              {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
            </button>
            {!showGraph && (
              <button className="px-btn ghost" onClick={() => setGraphMinimized(false)} title="Show graph">🧠</button>
            )}
            <button
              className="px-btn ghost"
              onClick={closeNote}
              title="Close note (Esc)"
              style={{fontSize:11}}
            >✕</button>
          </div>
          {preview ? (
            _isHtmlPath(openNote.path)
              ? <HtmlFramePreview html={openNote.content} />
              : <div className="vault-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content) }} />
          ) : (
            <textarea className="vault-edit" value={openNote.content} onChange={e=>setOpenNote({ ...openNote, content: e.target.value, dirty: true })} />
          )}
        </div>
      )}

      {showGraph && (
        <div className={`vault-graph-pane${!hasNote ? ' fullspan' : ''}`}>
          <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={p => openByPath(p)} onMinimize={() => setGraphMinimized(true)} />
        </div>
      )}

      {graphMinimized && !hasNote && (
        <div className="vault-graph-pane fullspan" style={{display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer'}} onClick={() => setGraphMinimized(false)}>
          <span style={{fontSize:11,opacity:0.5}}>🧠 VAULT GRAPH (click to show)</span>
        </div>
      )}
    </div>
  );
}


/* ---------------- Vault Graph (force-directed canvas) ---------------- */

const useForceGraph = (initialState) => {
  const stateRef = React.useRef(initialState);
  const [_, setTick] = useSV(0);

  const wakeSim = () => {
    if (stateRef.current.energy < 1) stateRef.current.energy = 1;
  };

  React.useEffect(() => {
    let frame;
    const loop = () => {
      if (stateRef.current.energy > 0.001) {
        simulate(stateRef.current);
        setTick(t => t + 1);
        stateRef.current.energy *= 0.99; // Cooling
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, []);

  return [stateRef.current, wakeSim, _];
};



export { VaultView };

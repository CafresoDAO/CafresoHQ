import { CafresoHQClient, VaultBridge } from '../claude-client.jsx';
import { obsidianCause, officeCause, uploadReceipt } from '../app/floor.jsx';
import { FolderTree } from './core.jsx';
import { GraphView, simulate } from './graph.jsx';
import { renderMarkdown } from './ide.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;

const _isHtmlPath = (path) => /\.html?$/i.test(path || '');

/* The first path segment that would make a note invisible, or null.

   Every listing this room has skips dotted parts — serve.py's fs and oci
   branches filter `part.startswith('.')` outright, and the REST walk skips
   dot-entries at every level — so filing a note at `.drafts/plan.md` files
   it where no list in the product will ever show it. The server refuses
   such writes now (#140, `_vault_hidden_part`), but the client must refuse
   FIRST: newNote opens a dirty buffer and the 2.5s autosave files it
   without the boss pressing anything, so by the time the server's 400
   lands, the boss has typed into a buffer that was never going to be kept.
   Refuse at the prompt, before there is a buffer to lose.

   '..' is deliberately not treated as hidden — it is a traversal attempt,
   the server refuses it as one, and calling it "hidden" would send the
   boss to rename a file that was never the problem. And only DESTINATIONS
   are checked: a dotted SOURCE stays movable, because rescuing
   `.lost/plan.md` back to `plan.md` is the one move that fixes an
   already-invisible file instead of trapping it. */
const _hiddenPart = (path) => {
  for (let part of String(path || '').replace(/\\/g, '/').split('/')) {
    part = part.trim();
    if (part === '' || part === '.' || part === '..') continue;
    if (part.startsWith('.')) return part;
  }
  return null;
};
const _hiddenMsg = (part) =>
  `Hidden files can't be filed here — the Library never lists anything under "${part}". Drop the leading dot so the note stays visible.`;

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

/* A deck is not a note, and the Library holds both. Everything below exists
   because the 📤 button files anything the boss picks and says so — "Filed 3
   files in the Library" — while the pane beside it could only ever render
   markdown, so the honest half of the product ended at the toast.

   What a boss is owed here is small and specific: see it in the tree, click
   it, be told what it is, and be able to get it back out. Not an editor
   pretending a PowerPoint is text. */
const _BIN_KINDS = [
  [/\.(pptx?|key|odp)$/i,                'Presentation',  '📊'],
  [/\.(docx?|odt|rtf|pages)$/i,          'Document',      '📄'],
  [/\.(xlsx?|ods|numbers)$/i,            'Spreadsheet',   '📈'],
  [/\.pdf$/i,                            'PDF',           '📕'],
  [/\.(png|jpe?g|gif|webp|bmp|avif|ico|tiff?)$/i, 'Image', '🖼'],
  [/\.svg$/i,                            'Vector image',  '🖼'],
  [/\.(mp3|wav|m4a|aac|flac|ogg)$/i,     'Audio',         '🎧'],
  [/\.(mp4|mov|webm|mkv|avi)$/i,         'Video',         '🎬'],
  [/\.(zip|tar|gz|tgz|7z|rar)$/i,        'Archive',       '🗜'],
];
const _binKind = (name) => {
  for (const [re, word, glyph] of _BIN_KINDS) if (re.test(name)) return [word, glyph];
  const ext = (name.match(/\.([A-Za-z0-9]+)$/) || [])[1];
  return [ext ? ext.toUpperCase() + ' file' : 'File', '📎'];
};
const _fileSize = (n) => {
  if (!(n > 0)) return '';
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + ' KB';
  return (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + ' MB';
};

function FiledFilePanel({ path, size }) {
  const name = (path || '').split('/').pop();
  const url = '/vault/file?path=' + encodeURIComponent(path);
  const [kind, glyph] = _binKind(name);
  /* Images render here rather than only downloading — a chart a coworker
     filed is a thing to look at, and /vault/file serves image types inline.
     Everything else gets its glyph, its kind and its size: enough for the
     boss to know what they're holding before they spend a click on it. */
  const isImage = kind === 'Image';
  /* A PDF is a document to READ, not a glyph to acknowledge — the same gap
     an image would have if it only ever showed a 🖼 and a download link.
     serve.py already answers with content-disposition: inline for
     application/pdf (_vault_inline_ok) — the browser's own PDF viewer does
     the rest inside a plain iframe, same as views/ide.jsx's FilePreview
     already does for the Projects/IDE surface. This surface never had it:
     the Library's binary-file panel only ever special-cased images. */
  const isPdf = kind === 'PDF';
  if (isPdf) {
    return (
      <div className="vault-preview vault-preview-file vault-preview-pdf" style={{
        display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', padding: 0,
      }}>
        <iframe title={name} src={url} style={{flex:1, width:'100%', border:0, background:'#fff'}} />
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
          fontSize: 11, borderTop: '1px solid rgba(124,107,255,0.15)',
        }}>
          <span style={{fontWeight:600, wordBreak:'break-all'}}>{name}</span>
          <span style={{opacity:0.65}}>{_fileSize(size)}</span>
          <a className="px-btn primary" href={url} download={name}
             style={{marginLeft:'auto', fontSize:10, textDecoration:'none', flexShrink:0}}>⬇ DOWNLOAD</a>
        </div>
      </div>
    );
  }
  return (
    <div className="vault-preview vault-preview-file" style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 10, textAlign: 'center', padding: 20,
      overflow: 'auto',
    }}>
      {isImage
        ? <img src={url} alt={name} style={{maxWidth:'100%',maxHeight:'60%',objectFit:'contain'}} />
        : <div style={{fontSize:44,lineHeight:1}}>{glyph}</div>}
      <div style={{fontSize:12,fontWeight:600,wordBreak:'break-all'}}>{name}</div>
      <div style={{fontSize:10,opacity:0.65}}>
        {kind}{_fileSize(size) ? ' · ' + _fileSize(size) : ''}
      </div>
      <div style={{fontSize:10,opacity:0.65,maxWidth:340}}>
        {isImage
          ? 'Filed in the Library. The editor only opens text, so this is the file itself.'
          : "Filed in the Library. The editor can't open this format — download it to work on it."}
      </div>
      <a className="px-btn primary" href={url} download={name}
         style={{fontSize:10,textDecoration:'none',marginTop:4}}>⬇ DOWNLOAD</a>
    </div>
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
  /* Kind filter for the tree — the Library holds notes, decks, documents
     and research side by side now, and a boss looking for "the deck" should
     not have to scan past every note to find it. Chips, not a dropdown:
     one glance shows which kinds exist here at all (a chip only renders
     when the Library holds at least one file of its kind). The tree is
     rebuilt from the filtered list, so a folder with nothing matching
     drops out with its contents — an empty shelf under a filter is
     noise, not orientation. */
  const [kindFilter, setKindFilter] = useSV('all');
  const VAULT_KINDS = [
    ['all',   'ALL',   () => true],
    ['notes', 'NOTES', (f) => !f.isBinary],
    ['decks', 'DECKS', (f) => /\.(pptx?|key|odp)$/i.test(f.path)],
    ['docs',  'DOCS',  (f) => /\.(docx?|odt|rtf|pages|pdf)$/i.test(f.path)],
    ['data',  'DATA',  (f) => /\.(xlsx?|ods|numbers|csv|json|base)$/i.test(f.path)],
    ['media', 'MEDIA', (f) => /\.(png|jpe?g|gif|webp|bmp|avif|svg|mp3|wav|m4a|mp4|mov|webm)$/i.test(f.path)],
  ];
  const kindPred = (VAULT_KINDS.find(([id]) => id === kindFilter) || VAULT_KINDS[0])[2];
  const kindFiles = kindFilter === 'all' ? files : files.filter(kindPred);
  const kindChips = (
    <div style={{display:'flex',gap:4,flexWrap:'wrap',padding:'4px 0'}} role="group" aria-label="Filter the Library by kind">
      {VAULT_KINDS.filter(([id, _l, pred]) => id === 'all' || files.some(pred)).map(([id, label]) => (
        <button key={id} className={'px-btn ' + (kindFilter === id ? 'primary' : 'ghost')}
          style={{fontSize:8,padding:'3px 7px'}} aria-pressed={kindFilter === id}
          onClick={() => setKindFilter(id)}>{label}</button>
      ))}
    </div>
  );

  // ── Bridge mode: when running inside the SvelteKit shell iframe, all vault
  // reads/writes go through VaultBridge (postMessage → parent decrypts).
  // Falls back to the local serve.py API when opened standalone.
  const _bridge = typeof window !== 'undefined' && VaultBridge?.isAvailable()
    ? VaultBridge : null;
  /* The one condition POST /vault/open answers to: serve.py returns 400
     'open-in-Obsidian requires REST backend' for every other value, so a
     control shown anywhere else is a button whose only possible outcome is
     a snag. `status` is null while the pane loads and 'bridge' inside the
     encrypted shell; both read false here, which is right. See the note
     above `openInObsidian` for why this gate is the whole ticket. */
  const _obsidianOn = !!status && status.backend === 'rest';
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

     A CLAUSE, not a sentence: these messages bring their own subject and
     verb ("Couldn't delete that note"), so they need the half without the
     "hit a snag — " spine that snagSentence prepends for surfaces that have
     none. Written the wrong way first and caught by reading the toast it
     actually produced: "Couldn't delete that note — hit a snag —
     NetworkError…", two spines in one line. floor.jsx says this in as many
     words — "no regex surgery at the call site" — and names the twin mistake
     (stripping the prefix instead) that once printed a verbless "Kenji that
     brain isn't signed in yet". The shapes exist precisely so no call site
     has to improvise.

     And officeCAUSE, not snagCause. This paragraph named snagCause while the
     line below called officeCause, which is how the bug it documents gets
     re-introduced: the vault is a filing cabinet, and snagCause's every
     sentence names a brain, so an offline delete announced "couldn't reach
     that brain — it looks offline from here" about the boss's own files. */
  const say = (text, kind = 'info') => {
    const t = window.cafresohqToast;
    if (t && t[kind]) t[kind](text);
  };
  const snag = (what, err) => {
    say(`${what} — ${officeCause((err && err.message) || String(err))}`, 'error');
  };

  const refresh = async () => {
    setErr(null);
    if (_bridge) {
      try {
        const bridgeFiles = await _bridge.list();
        setFiles(_adaptBridgeFiles(bridgeFiles));
        setStatus({ configured: true, exists: true, name: '🔐 Encrypted Library', backend: 'bridge' });
        refreshGraph();
      } catch (e) {
        setErr(e.message || 'Could not load the Library from shell.');
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
        setErr(e.message || 'Could not list the Library.');
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
        if (!status) setStatus({ configured: true, exists: true, name: '🔐 Encrypted Library', backend: 'bridge' });
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
    /* NOT setErr — that gate replaces the whole tree/editor with the
       "cabinet won't open" screen (below), which is true for a failed
       vault LOAD but not for one failed query against an already-open
       Library. Same distinction saveNote already draws (see its own
       comment) for the same reason: a scoped failure must not evict
       everything the boss can still see and use. */
    try { setHits(_bridge ? await bridgeSearch(q.trim()) : await CafresoHQClient.vaultSearch(q.trim())); }
    catch (e) { snag('Search failed', e); setHits(null); }
  };

  const openByPath = async (path) => {
    if (!path) return;
    // Files the text editor can't open — decks, PDFs, images, archives.
    const fileMeta = files.find(f => f.path === path);
    if (fileMeta?.isBinary) {
      /* Bridge mode has no local file to hand back: the bytes live encrypted
         in the parent shell and VaultBridge exposes read/write for text only,
         so the notice below is still the whole truth there.

         On a server backend it was never true. Until now `isBinary` was set
         by exactly one producer — the encrypted bridge index — so this notice
         was the ONLY thing that could happen to a non-text file, and every
         server-backed office got it: a boss with a deck in a folder on their
         own disk, sent to another website to look at it. §5. */
      if (_bridge) {
        say(`"${fileMeta.title}" is an image or media file — open it from the Library at ai.cafreso.com to view it.`, 'info');
        return;
      }
      if (openNoteRef.current && openNoteRef.current.dirty) {
        await saveNoteRef.current({ quiet: true });
      }
      setErr(null); setSaveState('');
      setOpenNote({ path, id: null, content: '', dirty: false,
                    binary: true, size: fileMeta.size || 0 });
      if (_isMobileV) setVaultTab('editor');
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
        if (!id) throw new Error('File not found in the Library index: ' + path);
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
    } catch (e) {
      /* Never setErr here: the view-level error replaces the ENTIRE
         Library — tree, editor, graph — with "The cabinet won't open",
         and this catch fires for ONE note that wouldn't open (a stale
         graph id, a note deleted elsewhere). Driven live: one click on
         an office node in the links graph blanked the whole room. The
         room is fine; only this door stuck. */
      snag("Couldn't open that note", e);
    }
    setBusy(false);
  };

  /* Saving is tracked per-editor (inline chip) and NEVER via the view-level
     `err` — a failed save used to replace the whole vault view with an error
     screen, hiding the user's unsaved text. Autosave (2.5s idle) plus
     flush-on-leave below mean typed text can no longer be silently lost. */
  const [saveState, setSaveState] = React.useState('');   // '' | 'saving' | 'saved' | 'error: …'
  const openNoteRef = React.useRef(null);
  // Per-path signature of the last-saved [[wikilink]] set — see saveNote.
  const lastLinkSigRef = React.useRef({});
  openNoteRef.current = openNote;

  const saveNote = async (opts) => {
    const note = openNoteRef.current;
    if (!note || !note.dirty) return;
    /* A brand-new note is only ever filed by the QUIET autosave (newNote
       opens a dirty buffer; nothing else saves it), and quiet used to skip
       refresh() entirely — so the note existed on the server, sat open in
       the editor, and appeared in neither the file tree nor the graph
       until a manual ↻. Driven live: create, type a [[wikilink]], switch
       to the graph — two nodes, no edge, no tree row. Quiet still skips
       the refresh for ordinary edits; a save that CREATES the file
       refreshes everything, and a save whose wikilink set changed
       refreshes the graph (never mid-prose — the signature only moves
       when the link structure does). */
    const creating = _bridge ? !note.id : !files.some(f => f.path === note.path);
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
      const linkSig = ((note.content || '').match(/\[\[[^\]]+\]\]/g) || []).sort().join('|');
      const linksChanged = lastLinkSigRef.current[note.path] !== linkSig;
      lastLinkSigRef.current[note.path] = linkSig;
      if (creating || !(opts && opts.quiet)) await refresh();
      else if (linksChanged) refreshGraph();
    } catch (e) {
      /* The 'error' prefix is load-bearing — saveState is a little state
         machine and the button reads startsWith('error') to switch to
         Retry. Only the CAUSE goes through the classifier; it surfaces
         as this button's tooltip, so a raw exception was visible on
         hover. Caught by the core-path sweep, not by the pass that
         fixed this file's alerts — I had grepped for alert() and
         setErr(), and this is neither. */
      setSaveState('error: ' + officeCause(e && e.message));
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
      /* A partial upload is a real, mixed outcome, and this sentence is
         composed in app/floor.jsx from the server's own answer — shared with
         the two Projects doors, which were reporting the boss's pick count
         back at them when the server had filed none of it. */
      const receipt = uploadReceipt(r, { verb: 'Filed', tried: 'file', where: 'in the Library' });
      if (receipt) say(receipt.text, receipt.tone);
    } catch (er) { snag("Couldn't add those to the Library", er); }
    setBusy(false);
  };
  /* The links graph draws OFFICE nodes too — agents, tasks, receipts —
     and clicking one used to feed its id ('agent:…') straight into
     openByPath, whose 404 hit the view-level error state: one click on a
     legitimately-drawn node replaced the entire Library (tree, editor,
     graph) with "The cabinet won't open." Reproduced live. Only an id
     the file list actually holds is a note this room can open; anything
     else keeps its engine-side selection highlight and nothing more. */
  const openGraphNode = (p, open) => {
    if (files.some(f => f.path === p)) open(p);
  };

  /* A [[wikilink]] in the preview used to render as an inert chip —
     cursor:auto, click swallowed. In a Library whose graph is BUILT from
     these links, the link itself has to be a door. Delegated here (the
     preview is dangerouslySetInnerHTML, so the spans carry data-wikilink
     instead of their own handlers). */
  const openWikilink = async (e) => {
    const el = e.target && e.target.closest && e.target.closest('.md-wikilink');
    if (!el) return;
    const target = String(el.getAttribute('data-wikilink') || '').trim();
    if (!target) return;
    const lower = target.toLowerCase();
    const hit = files.find(f => {
      const p = String(f.path).toLowerCase();
      const base = p.split('/').pop();
      return p === lower || p === lower + '.md'
          || base === lower || base === lower + '.md';
    });
    if (hit) { await openByPath(hit.path); return; }
    /* A dead link is where the NEXT note gets born in a linked library —
       a toast alone was a dead end. Offer the create; on yes, open the
       same empty dirty buffer newNote opens (the quiet autosave files
       it). A bare name lands beside the note that links to it; a path
       goes where it says. Hidden parts are refused exactly as newNote
       refuses them (#140). */
    const hidden = _hiddenPart(target);
    if (hidden) { say(_hiddenMsg(hidden), 'error'); return; }
    if (!(await window.hqConfirm(`"${target}" isn't in the Library yet — create it?`))) return;
    const here = (openNoteRef.current && openNoteRef.current.path.includes('/'))
      ? openNoteRef.current.path.replace(/\/[^/]*$/, '/') : '';
    const rel = target.includes('/') ? target : here + target;
    const norm = rel.endsWith('.md') ? rel : rel + '.md';
    setOpenNote({ path: norm, id: null, content: '', dirty: true });
    if (_isMobileV) setVaultTab('editor');
  };

  /* A checkbox in the preview is the task itself, not a picture of it:
     clicking box N rewrites task line N in the source and marks the
     buffer dirty (the quiet autosave files it). The walk mirrors
     renderMarkdown's numbering exactly — skip a leading frontmatter
     block, skip fenced code, count only `- `/`* ` lines whose remainder
     opens with [ ]/[x]. Change the detection here and there together. */
  const togglePreviewTask = (e) => {
    const box = e.target;
    if (!box || box.tagName !== 'INPUT' || box.getAttribute('data-task') == null) return false;
    const n = Number(box.getAttribute('data-task'));
    const note = openNoteRef.current;
    if (!note || note.binary) return true;
    const lines = note.content.split('\n');
    let k = 0;
    if (lines[0] === '---') {
      k = 1;
      while (k < lines.length && lines[k] !== '---') k++;
      if (k < lines.length) k++;
    }
    let inCode = false, seen = -1;
    for (; k < lines.length; k++) {
      if (lines[k].startsWith('```')) { inCode = !inCode; continue; }
      if (inCode) continue;
      if (!(lines[k].startsWith('- ') || lines[k].startsWith('* '))) continue;
      const m = lines[k].slice(2).match(/^\[( |x|X)\]/);
      if (!m) continue;
      seen++;
      if (seen !== n) continue;
      // The mark sits at index 3: "- [x] …". Flip only that byte.
      lines[k] = lines[k].slice(0, 3) + (m[1] === ' ' ? 'x' : ' ') + lines[k].slice(4);
      setOpenNote({ ...note, content: lines.join('\n'), dirty: true });
      break;
    }
    return true;
  };

  const onPreviewClick = async (e) => {
    if (togglePreviewTask(e)) return;
    await openWikilink(e);
  };

  const renameNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    // Native window.prompt breaks the pixel aesthetic, blocks the JS thread,
    // and — per ui/feedback.jsx's own docstring — is silently disabled on
    // some hosts (iframe sandboxes). views/projects.jsx already made this
    // switch for its identical rename flow; the vault, the single most
    // important data surface in the app, had not.
    const to = await window.hqPrompt('Rename / move to (path inside the Library):', { value: n.path });
    if (!to || to.trim() === n.path) return;
    /* Destination only — a dotted SOURCE stays movable (that's the rescue
       path out of an already-invisible folder). A dotted destination is a
       visible note about to leave every list this room keeps (#140). */
    const hidden = _hiddenPart(to);
    if (hidden) { say(_hiddenMsg(hidden), 'error'); return; }
    if (n.dirty) await saveNoteRef.current({ quiet: true });
    try {
      const res = await CafresoHQClient.vaultRename(n.path, to.trim());
      setOpenNote(o => o ? { ...o, path: to.trim() } : o);
      /* The server rewrites inbound [[wikilinks]] so links follow the
         file (fs backend). Say so — a silent rename leaves the boss
         wondering whether their links just died, because everywhere
         else they would have. */
      if (res && res.linksRewritten > 0) {
        say(`Moved — ${res.linksRewritten} link${res.linksRewritten === 1 ? '' : 's'} in ${res.filesTouched} note${res.filesTouched === 1 ? '' : 's'} followed the rename.`);
      }
      await refresh();
    } catch (e) { snag("Couldn't move that note", e); }
  };
  const deleteNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    /* Renames follow inbound [[wikilinks]] now; deletes can't — so the
       confirm names the damage before it happens. The count comes from
       the graph engine's last snapshot (note→note edges only: office
       nodes like tasks and receipts aren't wikilinks and can't go
       dead). Best-effort — with no snapshot the plain confirm stands. */
    let confirmMsg = `Delete "${n.path}"? This cannot be undone.`;
    try {
      const g = window.CafresoHQGraph && window.CafresoHQGraph._lastGraph;
      const inbound = g ? [...new Set((g.edges || [])
        .filter(e => String(e.target) === n.path && /\.md$/i.test(String(e.source)))
        .map(e => String(e.source)))] : [];
      if (inbound.length) {
        confirmMsg = `Delete "${n.path}"? ${inbound.length} note${inbound.length === 1 ? '' : 's'} still link${inbound.length === 1 ? 's' : ''} to it — ${inbound.length === 1 ? 'that link goes' : 'those links go'} dead. This cannot be undone.`;
      }
    } catch (_e) {}
    if (!(await window.hqConfirm(confirmMsg, { danger: true }))) return;
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
    /* Before the buffer exists. A dotted path would be autosaved 2.5s after
       the first keystroke and then absent from every list this room keeps —
       "Saved" over a note that just vanished (#140). */
    const hidden = _hiddenPart(path);
    if (hidden) { say(_hiddenMsg(hidden), 'error'); return; }
    const norm = path.endsWith('.md') ? path : path + '.md';
    /* An existing path here used to open an EMPTY dirty buffer over the
       real note, and the 2.5s quiet autosave filed it — the note's whole
       content gone, zero keystrokes, no message. Reproduced live before
       this guard. Case-insensitive because the shipping fs backend sits
       on a case-insensitive disk, where the write clobbers either way. */
    const existing = files.find(f => String(f.path).toLowerCase() === norm.toLowerCase());
    if (existing) {
      say(`"${existing.path}" already exists — opening it instead.`, 'info');
      await openByPath(existing.path);
      return;
    }
    // id is null for new notes — saveNote() will call bridge.create()
    setOpenNote({ path: norm, id: null, content: '', dirty: true });
  };

  /* `openInObsidian` lived here, was REMOVED, and is now back behind the
     gate it always needed. The removal note used to read, in part:

         the ONLY backend it can ever reach is /vault/open, which 400s
         unconditionally unless _vault_backend === 'rest' — and the one UI
         that could ever set that (modals/providers.jsx's VaultTab, with
         its DETECT OBSIDIAN button and REST key field) is deliberately
         excluded from the bundle (see modals.jsx's own comment: "kept for
         a future self-host build flag").

     Every clause of that was true when written and none of it is true now.
     `modals/settings.jsx` imports VaultTab, MediaTab, BraveTab and
     BrowserKeysTab from providers.jsx and renders VaultTab under
     Connections, so providers.jsx ships; modals.jsx's barrel comment,
     which was the whole evidence for "excluded", has been wrong for as
     long as that import has existed and is corrected there too.

     What the stale premise hid is worse than the dead button it justified.
     VaultTab tells the boss, in as many words, that Obsidian REST "unlocks
     plugin-mediated file access and open-in-Obsidian". The switch really
     works — the backend flips, and POST /vault/open is fully implemented.
     So a boss installed a community plugin, pasted an API key, threw the
     switch, and the one capability the switch named by name did not exist
     anywhere in the product. §5: a wrong door is worse than a locked one,
     and this door had been bricked up while the sign stayed on the wall.

     The original complaint was still right, though, and the gate is how
     both things can be true at once: the button had a 0% success rate in
     every shipped build, by construction, sitting on the single most-visited
     pane in the vault — */
  const openInObsidian = async () => {
    const n = openNoteRef.current;
    if (!n || !n.path) return;
    try {
      await CafresoHQClient.vaultOpenInObsidian(n.path);
      say('Opened in Obsidian');
    } catch (e) {
      /* Never the old alert(), and never its cause text. That read "Could
         not open in Obsidian: open-in-Obsidian requires REST backend" —
         raw backend vocabulary at a boss who asked to open a note.

         `obsidianCause`, not the `snag` every other handler here uses.
         Driven live with the plugin shut, snag said "Couldn't open that in
         Obsidian — the office isn't answering — check it's still running":
         the office answered fine, it was Obsidian that refused, and the
         one sentence the boss got named the wrong program. Obsidian is a
         fifth subject; see the table in app/floor.jsx. */
      say(`Couldn't open that in Obsidian — ${obsidianCause((e && e.message) || String(e))}`,
          'error');
    }
  };

  /* (continuing) — which OFFICE_AS_INTERFACE §3.6 calls "the cabinet", the
     story of this product. That is the part the gate answers: the control
     is rendered only when the live backend is already 'rest', so the 99%
     who never touched Obsidian see exactly what they saw yesterday, and
     the boss who did the setup gets the thing the setup promised. §5's
     "power-user 1%" is a reason to keep something off the core path, not a
     reason to sell it and then withhold it.

     One more piece of the original note is worth keeping, because it is
     about how these notes go wrong. It called the alert() "this app's only
     one — everything else is cafresohqToast or an inline sentence". That
     was false as written: THIS FILE still held five more, at the
     binary-file notice, the partial-upload report, and the
     upload/rename/delete catch blocks, three of them interpolating a raw
     `e.message`. They are toasts now (see `say` and `snag` above). A claim
     about the whole app, written from one line of it, and contradicted a
     hundred lines up in the same file. The premise this ticket just
     replaced failed the same way — a true observation about one file,
     generalised into a claim about the build, left to rot until it was
     load-bearing for a deletion. Both are left visible on purpose. */

  if (!status) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 LIBRARY</div><div className="empty-state"><div className="empty-title">Loading…</div></div></div>;
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
    const cause = officeCause(err);
    return (
      <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}>
        <div className="section-title">📓 LIBRARY</div>
        <div className="empty-state">
          <div className="empty-title">The cabinet won't open</div>
          {/* The reassurance used to end "...this is the office not answering,
              not the vault losing anything", which was written when {cause}
              said "couldn't reach that brain" and so had to name the office
              itself. Now that officeCause names it correctly, that clause
              repeated the sentence directly before it — measured live:
              "the office isn't answering — check it's still running. Your
              files are safe where they are — this is the office not
              answering, not the vault losing anything." The reassurance is
              still needed; the re-diagnosis is not. */}
          <div className="empty-sub">{cause}. Your files are safe where they are — nothing has been lost.</div>
          <button className="px-btn primary" style={{marginTop:16,fontSize:12,padding:'10px 20px'}}
                  onClick={() => { setErr(null); setStatus(null); refresh(); }}>↻ Try again</button>
        </div>
      </div>
    );
  }
  if (!status.configured) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 LIBRARY</div><div className="empty-state"><div className="empty-title">No Library yet.</div><div className="empty-sub">Pick the folder your team should file into — decks, documents, research and notes all land there.</div>{onOpenSettings && <button className="px-btn primary" style={{marginTop:16,fontSize:12,padding:'10px 20px'}} onClick={onOpenSettings}>⚙️ Open Settings</button>}</div></div>;
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
                <span style={{fontWeight:600,fontSize:11,flex:1}}>{status ? status.name : 'Library'}</span>
                <button className="px-btn ghost" onClick={newNote} title="New note">{'➕'}</button>
                {!_bridge && (
                  <button className="px-btn ghost" onClick={() => fileInputRef.current && fileInputRef.current.click()}
                    title="Upload files into the Library">📤</button>
                )}
                <button className="px-btn ghost" onClick={refresh} title="Refresh">{'↻'}</button>
                <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
              </div>
              <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
                <input style={{width:'100%',boxSizing:'border-box'}} value={q} aria-label="Search the Library" onChange={e=>setQ(e.target.value)} placeholder="Search the Library…" onKeyDown={e=>e.key==='Enter'&&search()} />
                <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>{'🔎'} SEARCH</button>
              </div>
              {hits ? (
                <div style={{overflowY:'auto',flex:1}}>
                  <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    {hits.length} result(s)
                    <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>{'✕'}</button>
                  </div>
                  {hits.map(h => (
                    <div key={h.path} className="tree-row tree-file" role="button" tabIndex={0}
                      onClick={()=>{ mobileOpenByPath(h.path); }}
                      onKeyDown={e=>{ if (e.key==='Enter'||e.key===' ') { e.preventDefault(); mobileOpenByPath(h.path); } }}>
                      <span className="tree-name">{h.title || h.path}</span>
                      <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  {kindChips}
                  <FolderTree files={kindFiles} openPath={openNote?.path} onOpen={(p) => mobileOpenByPath(p)} expanded={expanded} setExpanded={setExpanded} />
                </>
              )}
            </div>
          )}

          {vaultTab === 'graph' && (
            <div className="vault-graph-pane fullspan" style={{flex:1,display:'flex',flexDirection:'column',borderLeft:'none'}}>
              <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={(p) => openGraphNode(p, mobileOpenByPath)} onMinimize={() => setVaultTab('tree')} />
            </div>
          )}

          {vaultTab === 'editor' && openNote && (
            <div className="vault-edit-pane" style={{flex:1,display:'flex',flexDirection:'column',borderRight:'none'}}>
              <div className="vault-edit-head">
                <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
                {/* Preview and Save belong to the editor, and the editor is
                    not open. A "Saved" chip over a deck the textarea never
                    held is a claim about a file nothing here can make. */}
                {!openNote.binary && (
                  <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
                    <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
                  </label>
                )}
                {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
                {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
                {_obsidianOn && <button className="px-btn ghost" onClick={openInObsidian}
                  title="Open in Obsidian">⧉</button>}
                {!openNote.binary && (
                  <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
                    onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
                    {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
                  </button>
                )}
                <button className="px-btn ghost" onClick={() => { closeNote(); setVaultTab('tree'); }} title="Close" style={{fontSize:11}}>{'✕'}</button>
              </div>
              {openNote.binary ? (
                <FiledFilePanel path={openNote.path} size={openNote.size} />
              ) : preview ? (
                _isHtmlPath(openNote.path)
                  ? <HtmlFramePreview html={openNote.content} />
                  : <div className="vault-preview" onClick={onPreviewClick} dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content, { wikilinks: true }) }} />
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
              title="Upload files into the Library">📤</button>
          )}
          <button className="px-btn ghost" onClick={refresh} title="Refresh">↻</button>
          <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
        </div>
        <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
          <input style={{width:'100%',boxSizing:'border-box'}} value={q} aria-label="Search the Library" onChange={e=>setQ(e.target.value)} placeholder="Search the Library…" onKeyDown={e=>e.key==='Enter'&&search()} />
          <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>🔎 SEARCH</button>
        </div>
        {hits ? (
          <div style={{overflowY:'auto',flex:1}}>
            <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              {hits.length} result(s)
              <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>✕</button>
            </div>
            {hits.map(h => (
              <div key={h.path} className="tree-row tree-file" role="button" tabIndex={0}
                onClick={()=>openByPath(h.path)}
                onKeyDown={e=>{ if (e.key==='Enter'||e.key===' ') { e.preventDefault(); openByPath(h.path); } }}>
                <span className="tree-name">{h.title || h.path}</span>
                <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
              </div>
            ))}
          </div>
        ) : (
          <>
            {kindChips}
            <FolderTree files={kindFiles} openPath={openNote?.path} onOpen={openByPath} expanded={expanded} setExpanded={setExpanded} />
          </>
        )}
      </div>

      {hasNote && (
        <div className={`vault-edit-pane${!showGraph ? ' fullspan' : ''}`}>
          <div className="vault-edit-head">
            <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
            {!openNote.binary && (
              <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
                <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
              </label>
            )}
            {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
            {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
            {_obsidianOn && <button className="px-btn ghost" onClick={openInObsidian}
              title="Open in Obsidian">⧉</button>}
            {!openNote.binary && (
              <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
                onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
                {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
              </button>
            )}
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
          {openNote.binary ? (
            <FiledFilePanel path={openNote.path} size={openNote.size} />
          ) : preview ? (
            _isHtmlPath(openNote.path)
              ? <HtmlFramePreview html={openNote.content} />
              : <div className="vault-preview" onClick={onPreviewClick} dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content, { wikilinks: true }) }} />
          ) : (
            <textarea className="vault-edit" value={openNote.content} onChange={e=>setOpenNote({ ...openNote, content: e.target.value, dirty: true })} />
          )}
        </div>
      )}

      {showGraph && (
        <div className={`vault-graph-pane${!hasNote ? ' fullspan' : ''}`}>
          <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={p => openGraphNode(p, openByPath)} onMinimize={() => setGraphMinimized(true)} />
        </div>
      )}

      {graphMinimized && !hasNote && (
        <div className="vault-graph-pane fullspan" role="button" tabIndex={0}
          style={{display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer'}}
          onClick={() => setGraphMinimized(false)}
          onKeyDown={e=>{ if (e.key==='Enter'||e.key===' ') { e.preventDefault(); setGraphMinimized(false); } }}>
          <span style={{fontSize:11,opacity:0.5}}>🧠 LIBRARY GRAPH (click to show)</span>
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

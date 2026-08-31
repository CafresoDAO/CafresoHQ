import { CafresoHQClient } from '../claude-client.jsx';
/* officeCause, not snagCause: a directory listing that fails is the office's
   own file tools not answering, not a brain. snagCause's whole table names
   brains, so it would confidently blame the wrong component here.

   It was cleanCause first, and that was only half the fix. cleanCause was
   the right call the morning the classifier still had two shapes — better a
   sanitised line than a confident lie about a brain — but it names no cause
   at all, and this is the one surface where the office table has rows
   written for exactly what goes wrong: a folder that moved (ENOENT) and one
   we aren't allowed to open (EACCES). Both are things the boss can act on,
   and both were being thrown away to print "ENOENT: no such file or
   directory" instead. The subject was never in doubt here — this file's own
   comment said "the office's own file tools" while importing the shape that
   declines to say so. */
import { officeCause } from '../app/floor.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;
function renderMarkdown(text, opts) {
  if (!text) return '';
  opts = opts || {};
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => {
    s = esc(s);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    s = s.replace(/`(.+?)`/g, '<code>$1</code>');
    /* opts.wikilinks (the Library preview): a [[link]] is a door, not a
       decoration — carry the target so the caller's click handler can
       open it. Elsewhere (IDE file preview) there is nothing to open
       into, so the plain chip stands and nothing looks clickable. */
    /* Obsidian-flavored embeds — ![[file]] / ![[file|alt]] — are how the
       vault's own Obsidian backend writes every image. The bare [[ arm
       below would eat the brackets and strand the '!'. Resolution needs
       the file list, which only the caller has: opts.resolveEmbed maps a
       target to a vault path (the same matching the click-time opener
       uses). A resolved image renders through /vault/file like any
       embed; everything else stays a door chip — never a stray '!'. */
    s = s.replace(/!\[\[(.+?)\]\]/g, (_m, innerTxt) => {
      const parts = innerTxt.split('|');
      const target = parts[0].split('#')[0].trim();
      const shown = (parts[1] || parts[0]).trim();
      const p = opts.resolveEmbed ? opts.resolveEmbed(target) : null;
      if (p && /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i.test(p))
        return '<img class="md-img" src="/vault/file?path='
             + encodeURIComponent(p).replace(/"/g, '&quot;')
             + '" alt="' + shown.replace(/"/g, '&quot;') + '" style="max-width:100%">';
      if (!opts.wikilinks) return '<span class="md-tag">' + innerTxt + '</span>';
      return '<span class="md-tag md-wikilink" style="cursor:pointer" '
           + 'title="Open in the Library" data-wikilink="'
           + target.replace(/"/g, '&quot;') + '">' + shown + '</span>';
    });
    s = s.replace(/\[\[(.+?)\]\]/g, (_m, innerTxt) => {
      if (!opts.wikilinks) return '<span class="md-tag">' + innerTxt + '</span>';
      const parts = innerTxt.split('|');
      const target = parts[0].split('#')[0].trim();
      const shown = (parts[1] || parts[0]).trim();
      return '<span class="md-tag md-wikilink" style="cursor:pointer" '
           + 'title="Open in the Library" data-wikilink="'
           + target.replace(/"/g, '&quot;') + '">' + shown + '</span>';
    });
    s = s.replace(/#([\w-]+)/g, '<span class="md-tag">#$1</span>');
    /* Images BEFORE links, or ![alt](src) renders as a stray '!' plus a
       text link. In the Library preview (opts.wikilinks) a bare relative
       src is a vault file — an uploaded screenshot, a chart beside the
       note — served through the same /vault/file door the binary preview
       uses (it answers images inline, sandboxed). Elsewhere, and for
       absolute/data URLs, the src stands as written. */
    /* Three src spellings, because uploads keep their names and every
       screenshot's default name has spaces: <angle-bracketed>, %20-encoded
       (decoded before re-encoding, or the path double-encodes into a dead
       %2520), and plain. The graph builder and the rename rewriter parse
       embeds with these same rules — change them together. */
    /* (The text is entity-escaped before inline() runs, so the angle
       form arrives as &lt;…&gt; here — the Python parsers see raw <…>.) */
    s = s.replace(/!\[([^\]]*)\]\((?:&lt;(.+?)&gt;|([^)\s]+))\)/g, (_m, alt, a, b) => {
      const src = a || b;
      let dec = src;
      try { dec = decodeURIComponent(src); } catch (_e) {}
      const url = (opts.wikilinks && !/^(https?:|data:|\/)/i.test(dec))
        ? '/vault/file?path=' + encodeURIComponent(dec) : src;
      return '<img class="md-img" src="' + url.replace(/"/g, '&quot;')
           /* No loading="lazy": with no intrinsic size the img lays out
              0×0, never intersects the viewport, and never loads at all
              — caught live, complete:false forever. */
           + '" alt="' + alt.replace(/"/g, '&quot;')
           + '" style="max-width:100%">';
    });
    s = s.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>');
    return s;
  };

  let html = '';
  const lines = text.split('\n');
  let i = 0;

  /* Frontmatter block */
  if (lines[0] === '---') {
    i = 1;
    const fmLines = [];
    while (i < lines.length && lines[i] !== '---') { fmLines.push(lines[i]); i++; }
    if (i < lines.length) i++;
    if (fmLines.length > 0) {
      const fmHtml = fmLines.map(l => {
        const m = l.match(/^([\w ]+):\s*(.*)/);
        return m
          ? '<div><span class="md-fm-label">' + esc(m[1]) + ':</span> ' + esc(m[2]) + '</div>'
          : '<div>' + esc(l) + '</div>';
      }).join('');
      html += '<div class="md-frontmatter">' + fmHtml + '</div>';
    }
  }

  let inCode = false;
  let codeLines = [];
  /* Task-list checkboxes are numbered in order of appearance; the Library
     preview's click handler walks the SOURCE with the same rules (skip
     frontmatter, skip fenced code, `- `/`* ` then `[ ]`/`[x]`) to flip
     the matching line. Change the detection here and there together. */
  let taskN = 0;

  while (i < lines.length) {
    const line = lines[i];

    /* Fenced code blocks */
    if (line.startsWith('```')) {
      if (inCode) {
        html += '<pre class="md-pre"><code>' + esc(codeLines.join('\n')) + '</code></pre>';
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      i++; continue;
    }
    if (inCode) { codeLines.push(line); i++; continue; }

    /* Headings */
    const hm = line.match(/^(#{1,6})\s+(.*)/);
    if (hm) { html += '<div class="md-h md-h' + hm[1].length + '">' + inline(hm[2]) + '</div>'; i++; continue; }

    /* Horizontal rule — before lists, or "- - -" reads as a bullet.
       (A line-0 '---' was already eaten by the frontmatter block.) */
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      html += '<hr class="md-hr" style="border:none;border-top:1px solid rgba(128,128,128,0.4);margin:14px 0">';
      i++; continue;
    }

    /* Tables — a research brief's native shape. These used to fall
       through to the paragraph arm, one <p> of pipes per row. Inline
       styles, not styles.css: the preview must carry its own table the
       same way it carries its own wikilink cursor. */
    if (line.trim().startsWith('|') && i + 1 < lines.length
        && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const cellB = 'border:1px solid rgba(128,128,128,0.35);padding:4px 10px;text-align:left';
      const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => inline(c.trim()));
      const head = cells(line).map(c => '<th style="' + cellB + ';font-weight:600">' + c + '</th>').join('');
      i += 2;
      let rows = '';
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows += '<tr>' + cells(lines[i]).map(c => '<td style="' + cellB + '">' + c + '</td>').join('') + '</tr>';
        i++;
      }
      html += '<div style="overflow-x:auto"><table class="md-table" style="border-collapse:collapse;margin:0 0 14px">'
            + '<thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
      continue;
    }

    /* Blockquotes */
    if (line.startsWith('> ') || line.trim() === '>') {
      const q = [];
      while (i < lines.length && (lines[i].startsWith('> ') || lines[i].trim() === '>')) {
        q.push(lines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      html += '<blockquote class="md-quote" style="margin:0 0 14px;padding:2px 14px;border-left:3px solid rgba(128,128,128,0.5);opacity:0.9">'
            + q.map(l => l.trim() === '' ? '' : '<p class="md-p" style="margin:4px 0">' + inline(l) + '</p>').join('')
            + '</blockquote>';
      continue;
    }

    /* Unordered lists */
    if (line.startsWith('- ') || line.startsWith('* ')) {
      let items = '';
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('* '))) {
        /* A checklist is a research note's native shape; "[ ] todo" as a
           literal bullet reads like a rendering bug. In the Library
           (opts.wikilinks) the box is live — clicks are delegated to the
           preview handler, which rewrites the source line — elsewhere
           it's shown but disabled. */
        const tm = lines[i].slice(2).match(/^\[( |x|X)\]\s?(.*)$/);
        if (tm) {
          const done = tm[1] !== ' ';
          items += '<li class="md-task" style="list-style:none">'
            + '<input type="checkbox" data-task="' + (taskN++) + '"'
            + (done ? ' checked' : '') + (opts.wikilinks ? '' : ' disabled')
            + ' style="margin-right:7px;vertical-align:-2px'
            + (opts.wikilinks ? ';cursor:pointer' : '') + '">'
            + (done
                ? '<span style="opacity:0.6;text-decoration:line-through">' + inline(tm[2]) + '</span>'
                : inline(tm[2]))
            + '</li>';
        } else {
          items += '<li>' + inline(lines[i].slice(2)) + '</li>';
        }
        i++;
      }
      html += '<ul class="md-ul">' + items + '</ul>';
      continue;
    }

    /* Ordered lists */
    if (/^\d+\.\s/.test(line)) {
      let items = '';
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items += '<li>' + inline(lines[i].replace(/^\d+\.\s+/, '')) + '</li>';
        i++;
      }
      html += '<ol class="md-ol">' + items + '</ol>';
      continue;
    }

    /* Blank line */
    if (line.trim() === '') { i++; continue; }

    /* Paragraph */
    html += '<p class="md-p">' + inline(line) + '</p>';
    i++;
  }

  /* Unclosed code block */
  if (inCode && codeLines.length > 0) {
    html += '<pre class="md-pre"><code>' + esc(codeLines.join('\n')) + '</code></pre>';
  }

  return html;
}

/* ---------------- Parse DIR_LIST output into entry objects ----------------
   serve.py /tools/exec DIR_LIST returns one entry per line:
     "Subfolder/"
     "filename.md  (1234 B)"
     "(empty directory)"  // sentinel
     "…(truncated at 300 entries)"  // sentinel
*/
function parseDirEntries(text, basePath) {
  if (typeof text !== 'string') text = String(text || '');
  // Pick directory separator based on what the basePath uses (Windows uses \).
  const useBackslash = /\\/.test(basePath) && !/\//.test(basePath);
  const sep = useBackslash ? '\\' : '/';
  const trimEndSep = (s) => s.replace(/[/\\]+$/, '');

  const out = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('(') || line.startsWith('…')) continue; // sentinels
    const isDir = line.endsWith('/');
    let name, size = 0;
    if (isDir) {
      name = line.slice(0, -1);
    } else {
      // "filename  (1234 B)" — capture name and size separately if present.
      const m = line.match(/^(.+?)\s+\((\d+)\s*B\)\s*$/);
      if (m) { name = m[1]; size = parseInt(m[2], 10) || 0; }
      else   { name = line; }
    }
    out.push({
      name,
      isDir,
      size,
      path: trimEndSep(basePath) + sep + name,
    });
  }
  return out;
}

/* ---------------- Local file-tree with lazy sub-directory loading ---------------- */
function LocalTree({ path, onSelectFile, refreshNonce, onRename, onDelete, onUploadTo, pulsePaths }) {
  const [entries, setEntries] = useSV(null);
  const [expanded, setExpanded] = useSV(new Set());
  const [subEntries, setSubEntries] = useSV({});
  const [loading, setLoading] = useSV(false);
  const [err, setErr] = useSV(null);
  const [dropDir, setDropDir] = useSV(null);   // folder row being dragged over
  /* A retry the tree owns. `refreshNonce` comes from the parent and is only
     bumped after an upload, so on a failed listing there was no way to ask
     again — and the failure REPLACES the whole tree, so the boss lost the
     files and the route back in one go. */
  const [retryNonce, setRetryNonce] = useSV(0);

  /* Collapse + clear cached sub-listings only when the project PATH changes.
     A refresh (refreshNonce bump after an upload) deliberately keeps expanded
     state: dropped files always land in the root, so only the root listing
     needs to change — losing the user's open subfolders would be a regression. */
  React.useEffect(() => {
    setExpanded(new Set());
    setSubEntries({});
  }, [path]);

  /* Re-fetch the root listing when the path changes OR refreshNonce bumps. */
  React.useEffect(() => {
    if (!path) return;
    setLoading(true);
    setErr(null);
    CafresoHQClient.toolExec('DIR_LIST', path)
      .then(text => { setEntries(parseDirEntries(text, path)); setLoading(false); })
      .catch(e => { setErr(officeCause(e && e.message ? e.message : e)); setLoading(false); });
  }, [path, refreshNonce, retryNonce]);

  const loadSub = (subPath) => {
    if (subEntries[subPath]) return;
    CafresoHQClient.toolExec('DIR_LIST', subPath)
      .then(text => { setSubEntries(prev => ({ ...prev, [subPath]: parseDirEntries(text, subPath) })); })
      .catch(() => { setSubEntries(prev => ({ ...prev, [subPath]: [] })); });
  };

  const toggle = (p) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else { next.add(p); loadSub(p); }
      return next;
    });
  };

  /* Hover/tap actions on a row: upload-here (folders only), rename, delete.
     stopPropagation so they don't trigger the row's open/toggle. */
  const rowActions = (e) => (
    <span className="tree-actions" onClick={ev => ev.stopPropagation()}>
      {onUploadTo && e.isDir && <button className="tree-act" title="Upload files here" onClick={ev => { ev.stopPropagation(); onUploadTo(e); }}>📤</button>}
      {onRename && <button className="tree-act" title="Rename" onClick={ev => { ev.stopPropagation(); onRename(e); }}>✎</button>}
      {onDelete && <button className="tree-act" title="Delete" onClick={ev => { ev.stopPropagation(); onDelete(e); }}>🗑</button>}
    </span>
  );

  const renderEntries = (list, depth) => list.map(e => {
    if (e.isDir) {
      const isOpen = expanded.has(e.path);
      const kids = subEntries[e.path];
      const dropProps = onUploadTo ? {
        onDragOver: (ev) => { ev.preventDefault(); ev.stopPropagation(); setDropDir(e.path); },
        onDragLeave: (ev) => { if (!ev.currentTarget.contains(ev.relatedTarget)) setDropDir(null); },
        onDrop: (ev) => { ev.preventDefault(); ev.stopPropagation(); setDropDir(null); if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files.length) onUploadTo(e, ev.dataTransfer.files); },
      } : {};
      return (
        <div key={e.path}>
          <div className={'tree-row tree-folder' + (isOpen ? ' open' : '') + (dropDir === e.path ? ' drop-target' : '') + (pulsePaths && pulsePaths.has(e.path) ? ' agent-wrote' : '')} style={{paddingLeft: 10 + depth * 14}} onClick={() => toggle(e.path)} {...dropProps}>
            <span className="tree-chev">{isOpen ? '▾' : '▸'}</span>
            <span className="tree-icon">{isOpen ? '📂' : '📁'}</span>
            <span className="tree-name">{e.name}</span>
            {pulsePaths && pulsePaths.has(e.path) && <span className="tree-agent-dot" title="just written by a coworker">A</span>}
            {rowActions(e)}
          </div>
          {isOpen && kids && renderEntries(kids, depth + 1)}
          {isOpen && !kids && <div style={{paddingLeft: 6 + (depth + 1) * 14, fontSize: 9, opacity: 0.5}}>Loading…</div>}
        </div>
      );
    }
    return (
      <div key={e.path} className={'tree-row tree-file' + (pulsePaths && pulsePaths.has(e.path) ? ' agent-wrote' : '')} style={{paddingLeft: 10 + depth * 14 + 14}} onClick={() => onSelectFile && onSelectFile(e.path)}>
        <span className="tree-name">{e.name}</span>
        {pulsePaths && pulsePaths.has(e.path) && <span className="tree-agent-dot" title="just written by a coworker">A</span>}
        {e.size > 0 && <span className="tree-size">{e.size < 1024 ? `${e.size} B` : `${(e.size / 1024).toFixed(1)} KB`}</span>}
        {rowActions(e)}
      </div>
    );
  });

  if (!path) return <div className="proj-empty-msg">No project path set.</div>;
  if (loading) return <div className="proj-empty-msg">Loading…</div>;
  if (err) return (
    <div className="proj-empty-msg">
      <div style={{ color: 'var(--danger)', marginBottom: 8 }}>
        Couldn’t read this folder — {err}
      </div>
      <button className="px-btn" style={{ fontSize: 9 }}
        onClick={() => { setErr(null); setRetryNonce(n => n + 1); }}>
        ↻ TRY AGAIN
      </button>
    </div>
  );
  if (!entries) return null;
  return <div className="tree-root">{renderEntries(entries, 0)}</div>;
}

/* ---------------- Projects view (with file editing) ---------------- */
/* Simple language detection from filename — used to pick a label and to
   tweak the syntax highlighter when something obvious like a comment
   prefix differs (//, #, --). Default falls back to JS-ish tinting which
   covers most code we'd see. */
function ideLangFromPath(p) {
  if (!p) return 'text';
  const lower = String(p).toLowerCase();
  if (/\.(jsx?|tsx?|mjs)$/.test(lower)) return 'javascript';
  if (/\.py$/.test(lower)) return 'python';
  if (/\.rs$/.test(lower)) return 'rust';
  if (/\.go$/.test(lower)) return 'go';
  if (/\.(c|h|cc|cpp|hpp)$/.test(lower)) return 'c';
  if (/\.css$/.test(lower)) return 'css';
  if (/\.html?$/.test(lower)) return 'html';
  if (/\.json$/.test(lower)) return 'json';
  if (/\.md$/.test(lower)) return 'markdown';
  if (/\.toml$/.test(lower)) return 'toml';
  if (/\.ya?ml$/.test(lower)) return 'yaml';
  if (/\.sh$/.test(lower)) return 'shell';
  return 'text';
}
function ideFileIcon(p) {
  const l = ideLangFromPath(p);
  return ({
    javascript: '𝙅𝙎', python: '🐍', rust: '🦀', go: 'GO',
    c: 'C', css: '🎨', html: '🌐', json: '{}', markdown: 'M↓',
    toml: '⚙', yaml: '⚙', shell: '$', text: '📄',
  })[l] || '📄';
}

/* Light-touch IDE-feel editor — keeps the textarea (so all keyboard
   behavior works) but layers a syntax-tinted <pre> behind it for visual
   highlighting, plus a gutter of line numbers that scrolls with content.
   Not Monaco — but feels like an editor instead of a notepad, and ships
   in 50 LOC instead of 200KB. */
function IDEEditor({ value, onChange, path }) {
  const taRef = useRV(null);
  const gutterRef = useRV(null);
  const overlayRef = useRV(null);
  const minimapRef = useRV(null);
  const minimapThumbRef = useRV(null);
  const lineCount = value.split('\n').length;
  const lang = ideLangFromPath(path);
  const _isMobileIDE = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  /* Sync scroll between textarea, the syntax overlay <pre>, the line-
     number gutter, and the minimap viewport indicator. The textarea is
     the "source of truth" — scrolling it scrolls the others. */
  const onScroll = () => {
    const ta = taRef.current; if (!ta) return;
    if (gutterRef.current) gutterRef.current.scrollTop = ta.scrollTop;
    if (overlayRef.current) {
      overlayRef.current.scrollTop = ta.scrollTop;
      overlayRef.current.scrollLeft = ta.scrollLeft;
    }
    // Minimap viewport thumb
    if (minimapRef.current && minimapThumbRef.current) {
      const mm = minimapRef.current;
      const ratio = ta.scrollTop / (ta.scrollHeight - ta.clientHeight || 1);
      const thumbH = Math.max(20, (ta.clientHeight / ta.scrollHeight) * mm.scrollHeight);
      const thumbTop = ratio * (mm.clientHeight - thumbH);
      minimapThumbRef.current.style.height = thumbH + 'px';
      minimapThumbRef.current.style.top = thumbTop + 'px';
    }
  };

  /* Tab inserts 2 spaces (no tab character — keeps diffs consistent and
     avoids screen jumps). Shift-Tab dedents the current line. */
  const onKey = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.target;
      const start = ta.selectionStart, end = ta.selectionEnd;
      if (e.shiftKey) {
        const before = value.slice(0, start);
        const lineStart = before.lastIndexOf('\n') + 1;
        const head = value.slice(0, lineStart);
        const middle = value.slice(lineStart, end);
        const dedented = middle.replace(/^( {1,2})/gm, '');
        const tail = value.slice(end);
        onChange(head + dedented + tail);
      } else {
        const next = value.slice(0, start) + '  ' + value.slice(end);
        onChange(next);
        requestAnimationFrame(() => {
          if (taRef.current) {
            taRef.current.selectionStart = taRef.current.selectionEnd = start + 2;
          }
        });
      }
    }
  };

  /* Click on minimap scrolls to that position */
  const onMinimapClick = (e) => {
    const ta = taRef.current;
    const mm = minimapRef.current;
    if (!ta || !mm) return;
    const rect = mm.getBoundingClientRect();
    const ratio = (e.clientY - rect.top) / rect.height;
    ta.scrollTop = ratio * (ta.scrollHeight - ta.clientHeight);
  };

  const tinted = ideTintCode(value, lang);
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => i + 1).join('\n');

  return (
    <div className="ide-editor-wrap">
      <div className="ide-gutter" ref={gutterRef}>
        <pre>{lineNumbers}</pre>
      </div>
      <div className="ide-edit-area">
        <pre className="ide-overlay" ref={overlayRef} aria-hidden="true">{tinted}</pre>
        <textarea
          ref={taRef}
          className="ide-textarea"
          value={value}
          onChange={e => onChange(e.target.value)}
          onScroll={onScroll}
          onKeyDown={onKey}
          spellCheck={false}
          wrap="off"
        />
      </div>
      {/* Sublime-style minimap — scaled-down code overview with viewport thumb */}
      {lineCount > 20 && (
        <div
          className="ide-minimap"
          ref={minimapRef}
          onClick={onMinimapClick}
        >
          <pre className="ide-minimap-code">{tinted}</pre>
          <div className="ide-minimap-thumb" ref={minimapThumbRef} />
        </div>
      )}
    </div>
  );
}

/* Local copy of the chat tintCode — small enough to inline; keeps
   views.jsx independent of ui.jsx loading order. Returns a string with
   color spans interleaved (rendered as React children). */
function ideTintCode(src, lang) {
  if (!src) return '';
  const parts = [];
  let i = 0;
  // Comment syntax varies; support //, #, --, /* */.
  // String quotes: ", ', `.
  // Numbers: integer + float + hex.
  // Keyword set is broad-stroke (covers JS, Python, Rust, Go).
  const re = /(\/\/[^\n]*|#[^\n]*|--[^\n]*|\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b|\b(function|const|let|var|if|else|for|while|return|class|extends|new|this|import|export|from|async|await|try|catch|throw|true|false|null|undefined|def|lambda|pass|None|True|False|elif|fn|pub|use|impl|struct|enum|match|trait|mut|self|in|not|and|or|is|with|as|raise|yield|break|continue|switch|case|default|do|finally|interface|type|namespace|public|private|protected|static|void|int|float|bool|string|char|long|short|double)\b/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    if (m.index > i) parts.push(src.slice(i, m.index));
    if (m[1]) parts.push(<span key={'c'+m.index} className="cb-comment">{m[1]}</span>);
    else if (m[2]) parts.push(<span key={'s'+m.index} className="cb-string">{m[2]}</span>);
    else if (m[3]) parts.push(<span key={'n'+m.index} className="cb-num">{m[3]}</span>);
    else if (m[4]) parts.push(<span key={'k'+m.index} className="cb-kw">{m[4]}</span>);
    i = m.index + m[0].length;
  }
  if (i < src.length) parts.push(src.slice(i));
  return parts;
}

function previewKind(path) {
  const ext = (String(path || '').split('.').pop() || '').toLowerCase();
  if (ext === 'html' || ext === 'htm') return 'html';
  if (ext === 'md' || ext === 'markdown') return 'markdown';
  if (ext === 'svg') return 'svg';
  if (ext === 'pdf') return 'pdf';
  if (['png','jpg','jpeg','gif','webp','bmp','ico','avif'].indexOf(ext) >= 0) return 'image';
  if (ext === 'csv' || ext === 'tsv') return 'csv';
  return 'code';
}

/* Does this HTML reference sibling files (relative <link>/<script>/<img>)?
   If so it's a multi-file site and must be served from its directory so those
   refs resolve — a `srcDoc` blob has no base URL and would 404 every asset. */
function htmlNeedsSiteServe(content) {
  if (!content) return false;
  const re = /(?:src|srcset|href)\s*=\s*["']([^"']*)["']/gi;
  let m;
  while ((m = re.exec(content))) {
    const u = (m[1] || '').trim();
    if (!u) continue;
    if (/^(?:https?:|\/\/|data:|blob:|#|mailto:|tel:|javascript:)/i.test(u)) continue;
    return true; // a relative / root-relative ref → needs real serving
  }
  return false;
}

/* Split an OS path (either separator) into { dir, base }. */
function splitOsPath(p) {
  p = String(p || '');
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  return i >= 0 ? { dir: p.slice(0, i), base: p.slice(i + 1) } : { dir: '', base: p };
}

/* UTF-8-safe, URL-safe, unpadded base64 — matches serve.py's
   base64.urlsafe_b64decode(b64 + padding) in /fs/site. */
function b64urlUtf8(s) {
  const bytes = new TextEncoder().encode(String(s || ''));
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function CsvPreview({ text, sep }) {
  const rows = String(text || '').replace(/\s+$/, '').split(/\r?\n/).slice(0, 500).map(l => l.split(sep));
  if (!rows.length || (rows.length === 1 && !rows[0][0])) return <div style={{padding:16,opacity:0.6}}>Empty file.</div>;
  const head = rows[0], body = rows.slice(1);
  const cell = { border:'1px solid var(--rule,#d8cfb8)', padding:'3px 8px', fontSize:12, maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' };
  return (
    <div style={{overflow:'auto', flex:1, padding:8, background:'var(--paper,#fff)'}}>
      <table style={{borderCollapse:'collapse', fontFamily:'var(--mono,ui-monospace,monospace)'}}>
        <thead><tr>{head.map((h,i) => <th key={i} style={{...cell, fontWeight:700, background:'var(--paper-2,#f0e9d8)', position:'sticky', top:0}}>{h}</th>)}</tr></thead>
        <tbody>{body.map((r,i) => <tr key={i}>{r.map((c,j) => <td key={j} style={cell}>{c}</td>)}</tr>)}</tbody>
      </table>
      {rows.length >= 500 && <div style={{padding:8,opacity:0.6,fontSize:11}}>Showing first 500 rows.</div>}
    </div>
  );
}

function FilePreview({ file, nonce }) {
  const [imgErr, setImgErr] = useSV(false);
  const kind = previewKind(file.path);
  const apiBase = (typeof window !== 'undefined' && window._API_BASE) || '';
  // nonce (bumped when an agent rewrites the open file) cache-busts the streamed
  // URLs so image/pdf/site previews actually reload — the "preview chases the agent" effect.
  const bust = nonce ? ('&_n=' + nonce) : '';
  const fileUrl = apiBase + '/fs/file?path=' + encodeURIComponent(file.path) + bust;
  const frame = { flex:1, width:'100%', height:'100%', minHeight:0, border:0, background:'#fff' };
  const pad = { flex:1, overflow:'auto', display:'flex', alignItems:'center', justifyContent:'center', padding:16, background:'#fff' };
  if (kind === 'html') {
    // Multi-file site → serve from its directory so relative assets resolve;
    // self-contained page → render inline (works without the /fs/site endpoint).
    // A truncated FILE_READ also routes to site-serve: detection can't see refs
    // past the 8000-char cap, and the iframe loads the FULL file from disk, so a
    // long page renders complete instead of cut off.
    const truncated = /\(truncated to \d+ chars\)\s*$/.test(file.content || '');
    if (file.path && (htmlNeedsSiteServe(file.content) || truncated)) {
      const { dir, base } = splitOsPath(file.path);
      const siteUrl = apiBase + '/fs/site/' + b64urlUtf8(dir) + '/' + encodeURIComponent(base) + (nonce ? ('?_n=' + nonce) : '');
      return <iframe title="Site preview" style={frame} sandbox="allow-scripts allow-popups allow-forms allow-modals" src={siteUrl} />;
    }
    return <iframe title="HTML preview" style={frame} sandbox="allow-scripts allow-popups allow-forms allow-modals" srcDoc={file.content} />;
  }
  if (kind === 'markdown')
    return <div className="vault-preview" style={{flex:1, overflow:'auto', padding:'16px 22px', background:'var(--paper,#fff)'}} dangerouslySetInnerHTML={{ __html: renderMarkdown(file.content || '') }} />;
  if (kind === 'svg')
    return <div style={pad} dangerouslySetInnerHTML={{ __html: file.content }} />;
  if (kind === 'csv')
    return <CsvPreview text={file.content} sep={String(file.path).toLowerCase().endsWith('.tsv') ? '\t' : ','} />;
  if (kind === 'image')
    return (
      <div style={pad}>
        {imgErr
          ? <div style={{textAlign:'center',opacity:0.6,fontSize:12}}>Couldn't load image.<br/>Needs a newer HQ (one that serves <code>/fs/file</code>) — update and restart.</div>
          : <img src={fileUrl} alt={file.path} onError={() => setImgErr(true)} style={{maxWidth:'100%', maxHeight:'100%', objectFit:'contain'}} />}
      </div>
    );
  if (kind === 'pdf')
    return <iframe title="PDF preview" style={frame} src={fileUrl} />;
  return <pre style={{flex:1, overflow:'auto', margin:0, padding:16, fontFamily:'var(--mono,ui-monospace,monospace)', fontSize:12, whiteSpace:'pre-wrap', wordBreak:'break-word', background:'var(--paper,#fff)'}}>{file.content}</pre>;
}

/* ═══════════════════ Cohabit Workspace — the unified Agentic-OS surface ═══════
   One screen where you and your agents are two operators on the SAME container
   filesystem: a file tree, a center editor⇄live-preview deck, an integrated
   terminal drawer, and an agent rail co-inhabit a single layout. The agent's
   writes (via the cafresohq:agentTool event bus) light up the tree, refresh the
   preview, and stream into a re-runnable activity ledger — conflict-safely, so a
   live agent write never clobbers your unsaved edits. A top-bar toggle flips to
   the classic Projects view (kept intact). */

export { FilePreview, IDEEditor, LocalTree, ideFileIcon, ideLangFromPath, previewKind, renderMarkdown };

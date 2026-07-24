// ─────────────────────────────────────────────────────────────────────────────
// Deep Research → an Obsidian-style vault.
//
// A deep entry is stored on-chain as {entry, research.json}. This module turns
// that pair into something a note-taker already knows how to hold: a little
// vault of .md files — Overview.md, one note per research angle, Sources.md —
// cross-linked with [[wikilinks]]. The /library/vault page renders it with a
// file tree + reading pane; downloadVault() zips the same files so the vault
// opens, unchanged, in actual Obsidian.
//
// Everything here is derived client-side from public JSON. No new canister
// state, no new routes on the worker — the vault is a *view*.
// ─────────────────────────────────────────────────────────────────────────────

import { fmtNsDate } from '$lib/utils/time.js';

/** Strip tags/control chars from model-written text before it becomes content. */
function plain(t) {
  return String(t || '').replace(/<[^>]+>/g, '').replace(/[\u0000-\u0008\u000b-\u001f]/g, '').trim();
}

/** A string Obsidian accepts as a file name (no  \ / : * ? " < > | # [ ] ^ ). */
function fileSafe(t, fallback) {
  const s = plain(t).replace(/[\\/:*?"<>|#[\]^]/g, '').replace(/\s+/g, ' ').trim().slice(0, 70);
  return s || fallback;
}

function domain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; }
}

const fmtDate = (ns) => fmtNsDate(ns, 'long');

// ── Vault construction ───────────────────────────────────────────────────────

/**
 * Build the vault from a library entry + its research.json.
 * Returns { name, files, byPath, backlinks } where each file is
 * { path, name, folder, title, md, words } and `name` (basename, no .md)
 * doubles as its [[wikilink]] target.
 */
export function buildVault(entry, research) {
  const q = plain(entry?.query || research?.q || 'Deep research');
  const pages = (research?.pages || []).map((p, i) => ({
    id: p.id || `t${i}`,
    title: plain(p.title) || `Angle ${i + 1}`,
    question: plain(p.question),
    body: plain(p.body),
    sources: (p.sources || []).map((s) => ({
      title: plain(s.title) || domain(s.url) || 'Source',
      url: String(s.url || ''),
      note: plain(s.note)
    }))
  }));

  const noteName = (p, i) => `${String(i + 1).padStart(2, '0')} ${fileSafe(p.title, `Angle ${i + 1}`)}`;

  const files = [];

  // Overview.md — the synthesis, plus the map of the vault.
  {
    const lines = [`# ${q}`, ''];
    const answer = plain(entry?.answer || research?.answer);
    if (answer) lines.push(answer, '');
    if (pages.length) {
      lines.push('## The angles', '');
      pages.forEach((p, i) => {
        lines.push(`- [[${noteName(p, i)}]]${p.question ? ` — ${p.question}` : ''}`);
      });
      lines.push('');
    }
    lines.push('## About this vault', '');
    lines.push(`> [!info] Researched by the Cafreso search network${entry?.model ? ` · ${plain(entry.model)}` : ''}`);
    lines.push(`> Answered ${fmtDate(entry?.answeredAt || entry?.ts) || 'recently'} and stored on-chain forever. See [[Sources]] for the full bibliography.`);
    files.push({ path: 'Overview.md', name: 'Overview', folder: '', title: q, md: lines.join('\n') });
  }

  // notes/NN Title.md — one page per research angle.
  pages.forEach((p, i) => {
    const name = noteName(p, i);
    const lines = [`# ${p.title}`, ''];
    if (p.question) lines.push(`> [!question] The angle`, `> ${p.question}`, '');
    if (p.body) lines.push(p.body, '');
    if (p.sources.length) {
      lines.push('## Sources', '');
      p.sources.forEach((s, si) => {
        lines.push(`${si + 1}. [${s.title}](${s.url})${s.note ? ` — ${s.note}` : ''}`);
      });
      lines.push('');
    }
    lines.push('---', '');
    const next = i + 1 < pages.length ? ` · Next: [[${noteName(pages[i + 1], i + 1)}]]` : '';
    lines.push(`Part of [[Overview|${q}]]${next}`);
    files.push({ path: `notes/${name}.md`, name, folder: 'notes', title: p.title, md: lines.join('\n') });
  });

  // Sources.md — the combined bibliography, grouped by the note that found it.
  {
    const lines = ['# Sources', '', `Everything read while researching [[Overview|${q}]].`, ''];
    const top = (entry?.sources || []).filter((s) => s?.url);
    if (top.length && !pages.length) {
      top.forEach((s, i) => lines.push(`${i + 1}. [${plain(s.title) || domain(s.url)}](${s.url})`));
      lines.push('');
    }
    pages.forEach((p, i) => {
      if (!p.sources.length) return;
      lines.push(`## Via [[${noteName(p, i)}]]`, '');
      p.sources.forEach((s) => lines.push(`- [${s.title}](${s.url}) · ${domain(s.url)}`));
      lines.push('');
    });
    files.push({ path: 'Sources.md', name: 'Sources', folder: '', title: 'Sources', md: lines.join('\n') });
  }

  for (const f of files) f.words = f.md.split(/\s+/).filter(Boolean).length;

  const byPath = new Map(files.map((f) => [f.path, f]));
  // Wikilink graph → backlinks ("Linked mentions" under each note).
  const byName = new Map(files.map((f) => [f.name.toLowerCase(), f]));
  const backlinks = new Map(files.map((f) => [f.path, []]));
  for (const f of files) {
    for (const m of f.md.matchAll(/\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g)) {
      const to = byName.get(m[1].trim().toLowerCase());
      if (to && to.path !== f.path && !backlinks.get(to.path).includes(f.path)) {
        backlinks.get(to.path).push(f.path);
      }
    }
  }

  return { name: fileSafe(q, 'Deep research'), files, byPath, byName, backlinks };
}

// ── Markdown-lite → HTML (escape-first; only the syntax the vault writes) ────

function esc(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Inline spans on already-escaped text: [[wiki]] · [md](url) · **b** · *i* · `c` */
function inline(t, vault) {
  return t
    .replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, target, label) => {
      const f = vault?.byName?.get(target.trim().toLowerCase());
      const text = label || target;
      return f
        ? `<a href="#" class="v-wiki" data-path="${esc(f.path)}">${text}</a>`
        : `<span class="v-wiki v-wiki-missing">${text}</span>`;
    })
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, text, url) =>
      `<a href="${url}" class="v-ext" target="_blank" rel="noopener noreferrer">${text}</a>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/** Render one vault file's markdown to HTML. Escapes everything first, then
    layers the few constructs buildVault emits — never a general MD engine. */
export function renderMd(md, vault) {
  const out = [];
  let list = null;   // 'ul' | 'ol' while inside a list
  let callout = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const closeCallout = () => { if (callout) { out.push('</div></div>'); callout = null; } };

  for (const raw of String(md || '').split('\n')) {
    const line = raw.trimEnd();

    const co = line.match(/^> \[!(\w+)\]\s*(.*)$/);
    if (co) {
      closeList(); closeCallout();
      callout = co[1].toLowerCase();
      out.push(`<div class="v-callout v-callout-${esc(callout)}"><div class="v-callout-t">${inline(esc(co[2] || co[1]), vault)}</div><div class="v-callout-b">`);
      continue;
    }
    if (callout && line.startsWith('>')) {
      out.push(`<p>${inline(esc(line.replace(/^>\s?/, '')), vault)}</p>`);
      continue;
    }
    closeCallout();

    if (line === '') { closeList(); continue; }
    const h = line.match(/^(#{1,3}) (.+)$/);
    if (h) { closeList(); out.push(`<h${h[1].length + 1}>${inline(esc(h[2]), vault)}</h${h[1].length + 1}>`); continue; }
    if (line === '---') { closeList(); out.push('<hr>'); continue; }
    if (/^[-*] /.test(line)) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul'; }
      out.push(`<li>${inline(esc(line.slice(2)), vault)}</li>`);
      continue;
    }
    const oli = line.match(/^\d+\. (.+)$/);
    if (oli) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol'; }
      out.push(`<li>${inline(esc(oli[1]), vault)}</li>`);
      continue;
    }
    if (line.startsWith('> ')) { closeList(); out.push(`<blockquote>${inline(esc(line.slice(2)), vault)}</blockquote>`); continue; }
    closeList();
    out.push(`<p>${inline(esc(line), vault)}</p>`);
  }
  closeList(); closeCallout();
  return out.join('\n');
}

// ── Export: the vault as a real .zip of .md files (store-only, no deps) ─────

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** Minimal ZIP writer: STORE method only — .md files are tiny, and "no
    compression" keeps this ~60 lines instead of a dependency. */
export function buildVaultZip(vault) {
  const enc = new TextEncoder();
  const chunks = [];
  const central = [];
  let offset = 0;

  for (const f of vault.files) {
    const name = enc.encode(`${vault.name}/${f.path}`);
    const data = enc.encode(f.md + '\n');
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);          // local file header
    local.setUint16(4, 20, true);                  // version needed
    local.setUint16(6, 0x0800, true);              // UTF-8 names
    local.setUint16(8, 0, true);                   // method: store
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);        // compressed size
    local.setUint32(22, data.length, true);        // uncompressed size
    local.setUint16(26, name.length, true);
    chunks.push(new Uint8Array(local.buffer), name, data);

    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true);             // central directory header
    cd.setUint16(4, 20, true);
    cd.setUint16(6, 20, true);
    cd.setUint16(8, 0x0800, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, data.length, true);
    cd.setUint32(24, data.length, true);
    cd.setUint16(28, name.length, true);
    cd.setUint32(42, offset, true);                // local header offset
    central.push(new Uint8Array(cd.buffer), name);
    offset += 30 + name.length + data.length;
  }

  const cdSize = central.reduce((n, c) => n + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);              // end of central directory
  end.setUint16(8, vault.files.length, true);
  end.setUint16(10, vault.files.length, true);
  end.setUint32(12, cdSize, true);
  end.setUint32(16, offset, true);
  chunks.push(...central, new Uint8Array(end.buffer));

  return new Blob(chunks, { type: 'application/zip' });
}

/** Trigger a browser download of the vault zip. */
export function downloadVault(vault) {
  const url = URL.createObjectURL(buildVaultZip(vault));
  const a = document.createElement('a');
  a.href = url;
  a.download = `${vault.name.replace(/\s+/g, '-').toLowerCase()}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

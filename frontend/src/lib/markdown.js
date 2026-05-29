// Markdown-lite → devlog block parser.
//
// Stores body as a JSON array of typed blocks. Supports original types plus
// interactive widget blocks prefixed with `::`.
//
// Original types:
//   ## Heading                           → { kind: 'h2', text }
//   - item                               → { kind: 'ul', items }
//   > icon | Title | Body                → { kind: 'callout', icon, title, text }
//   (blank line)                         → paragraph break
//   any other line                       → { kind: 'p', text }
//
// Widget types (:: prefix):
//   ::stats | Label:Value | …            → { kind: 'stats', items: [{label,value}] }
//   ::chart | area | Title | Jan:2.1 | … → { kind: 'chart', type, title, points:[{label,value}] }
//   ::roadmap | done:Q1:Title | now:…   → { kind: 'roadmap', phases:[{status,date,title}] }
//   ::progress | 614/1000 | Label | Sub → { kind: 'progress', value, max, label, sub }
//   ::calculator | apy=7.25 | max=50000 | currency=CF | min=250 | step=250
//                                        → { kind: 'calculator', apy, max, currency, min, step }

export function parseBlocks(source) {
  if (!source || typeof source !== 'string') return [];
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let para = [];
  let bullets = [];

  const flushPara = () => {
    if (para.length) {
      out.push({ kind: 'p', text: para.join(' ').trim() });
      para = [];
    }
  };
  const flushBullets = () => {
    if (bullets.length) {
      out.push({ kind: 'ul', items: bullets.slice() });
      bullets = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();

    // Blank line — flush pending paragraph/bullets
    if (line === '') {
      flushPara();
      flushBullets();
      continue;
    }

    // Widget blocks — :: prefix
    if (line.startsWith('::')) {
      flushPara();
      flushBullets();
      const widget = parseWidget(line);
      if (widget) { out.push(widget); continue; }
    }

    // ## Heading
    if (line.startsWith('## ')) {
      flushPara();
      flushBullets();
      out.push({ kind: 'h2', text: line.slice(3).trim() });
      continue;
    }

    // Bullet
    if (line.startsWith('- ') || line.startsWith('* ')) {
      flushPara();
      bullets.push(line.slice(2).trim());
      continue;
    }

    // Callout  > icon | Title | Body
    if (line.startsWith('> ')) {
      flushPara();
      flushBullets();
      const parts = line.slice(2).split('|').map((s) => s.trim());
      out.push({ kind: 'callout', icon: parts[0] || 'info', title: parts[1] || '', text: parts.slice(2).join(' | ') });
      continue;
    }

    flushBullets();
    para.push(line.trim());
  }
  flushPara();
  flushBullets();
  return out;
}

function parseWidget(line) {
  // Extract widget type and the rest of the pipe-separated params
  const rest = line.slice(2); // strip ::
  const parts = rest.split('|').map((s) => s.trim());
  const type = parts[0].toLowerCase();

  // ::stats | Label:Value | Label2:Value2 | …
  if (type === 'stats') {
    const items = parts.slice(1).map((p) => {
      const idx = p.indexOf(':');
      if (idx === -1) return { label: p, value: '' };
      return { label: p.slice(0, idx).trim(), value: p.slice(idx + 1).trim() };
    }).filter((i) => i.label);
    return { kind: 'stats', items };
  }

  // ::chart | area | Title | Jan:2.1 | Feb:2.2 | …
  if (type === 'chart') {
    const chartType = parts[1] || 'area';
    const title = parts[2] || '';
    const points = parts.slice(3).map((p) => {
      const idx = p.indexOf(':');
      if (idx === -1) return null;
      const val = parseFloat(p.slice(idx + 1).replace(/[^0-9.-]/g, ''));
      return isNaN(val) ? null : { label: p.slice(0, idx).trim(), value: val };
    }).filter(Boolean);
    return { kind: 'chart', chartType, title, points };
  }

  // ::roadmap | done:Q1 2026:Foundation | now:Apr 18:Testnet | next:Q2 2026:Mainnet
  if (type === 'roadmap') {
    const phases = parts.slice(1).map((p, i) => {
      const segs = p.split(':');
      return {
        num: String(i).padStart(2, '0'),
        status: segs[0]?.trim() || 'next',
        date: segs[1]?.trim() || '',
        title: segs.slice(2).join(':').trim() || '',
      };
    }).filter((ph) => ph.title || ph.date);
    return { kind: 'roadmap', phases };
  }

  // ::progress | 614/1000 | Testnet seats reserved | Opens May 12, 2026
  if (type === 'progress') {
    const fraction = (parts[1] || '0/100').split('/');
    return {
      kind: 'progress',
      value: parseInt(fraction[0]) || 0,
      max: parseInt(fraction[1]) || 100,
      label: parts[2] || '',
      sub: parts[3] || '',
    };
  }

  // ::calculator | apy=7.25 | max=50000 | currency=CF | min=250 | step=250
  if (type === 'calculator') {
    const kv = {};
    for (const p of parts.slice(1)) {
      const idx = p.indexOf('=');
      if (idx !== -1) kv[p.slice(0, idx).trim()] = p.slice(idx + 1).trim();
    }
    return {
      kind: 'calculator',
      apy: parseFloat(kv.apy ?? '7.25'),
      max: parseInt(kv.max ?? '50000'),
      currency: kv.currency ?? 'CF',
      min: parseInt(kv.min ?? '250'),
      step: parseInt(kv.step ?? '250'),
    };
  }

  return null;
}

// Serialize blocks back to markdown-lite for the editor.
export function blocksToMarkdown(blocks) {
  if (!Array.isArray(blocks)) return '';
  const out = [];
  for (const b of blocks) {
    if (b.kind === 'h2') out.push(`## ${b.text}`);
    else if (b.kind === 'p') out.push(b.text);
    else if (b.kind === 'ul') out.push(b.items.map((i) => `- ${i}`).join('\n'));
    else if (b.kind === 'callout') out.push(`> ${b.icon} | ${b.title || ''} | ${b.text || ''}`);
    else if (b.kind === 'stats') out.push(`::stats | ${b.items.map((i) => `${i.label}:${i.value}`).join(' | ')}`);
    else if (b.kind === 'chart') out.push(`::chart | ${b.chartType} | ${b.title} | ${b.points.map((p) => `${p.label}:${p.value}`).join(' | ')}`);
    else if (b.kind === 'roadmap') out.push(`::roadmap | ${b.phases.map((p) => `${p.status}:${p.date}:${p.title}`).join(' | ')}`);
    else if (b.kind === 'progress') out.push(`::progress | ${b.value}/${b.max} | ${b.label} | ${b.sub}`);
    else if (b.kind === 'calculator') out.push(`::calculator | apy=${b.apy} | max=${b.max} | currency=${b.currency} | min=${b.min} | step=${b.step}`);
    out.push('');
  }
  return out.join('\n').trim();
}

// Quick read-time estimate: ~220 words/minute.
export function readMinutes(source) {
  if (!source) return 1;
  const words = source.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 220));
}

// URL-safe slug from title.
export function slugify(text) {
  return (text || '')
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 80);
}

// Widget snippet templates — inserted by the composer toolbar.
export const WIDGET_SNIPPETS = {
  stats: '::stats | APY:7.25% | Treasury:$2.4M | Non-custodial:✓ | Audited:Trail of Bits',
  chart: '::chart | area | Treasury Balance | Jan:2.1 | Feb:2.2 | Mar:2.4 | Apr:2.4',
  roadmap: '::roadmap | done:Q1 2026:Foundation | now:Today:Testnet Waitlist | next:Q2 2026:Mainnet Deposits',
  progress: '::progress | 614/1000 | Testnet seats reserved | Opens May 12, 2026',
  calculator: '::calculator | apy=7.25 | max=50000 | currency=CF | min=250 | step=250',
};

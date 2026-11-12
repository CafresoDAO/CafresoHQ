#!/usr/bin/env python3
"""A coworker can publish one file — a PDF, a Word document, a deck — not just a site.

PUBLISH_SITE only understood a folder or an index.html, so the things coworkers
actually make (a report as a PDF, a deck) had no way onto the public host even
though that host stores any content type. publishSite now asks the office what
the path is and hands a single file to publishFile, which ships the file and a
share page in front of it. This runs the real source from claude-client.jsx
under node with the office and the shell stubbed.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
start = src.index('const _PUBLISH_TYPES = {')
end = src.index('/* Publish a built site. Prefers the public HQ host')
block = src[start:end]
ps_start = src.index('async function publishSite(path, opts = {}) {')
guard = src[ps_start:src.index("  const isHtml = /\\.html?$/i.test(path || '');", ps_start)]

harness = r'''
const published = []; const uploaded = [];
let chainUp = true, statAnswer = { ok: true, size: 1200 }, skip = [];
const _API_BASE = '';
const _splitOsPath = (p) => { const i = p.lastIndexOf('/'); return i >= 0 ? { dir: p.slice(0, i), base: p.slice(i + 1) } : { dir: '', base: p }; };
const _bytesToStdB64 = (b) => Buffer.from(b).toString('base64');
globalThis.File = class { constructor(parts, name) { this.name = name; this.body = parts.join(''); } };
const fsUpload = async (dir, files) => { uploaded.push([dir, files[0].name, files[0].body]); };
const fsStat = async (p) => { if (!statAnswer) throw new Error('that is a folder, not a file'); return statAnswer; };
globalThis.fetch = async () => ({ ok: true, arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer });
const CafresoHQChain = { isAvailable: () => chainUp,
  publish: async (slug, files) => { published.push({ slug, files }); return { mode: 'canister', url: 'https://host.example/me/' + slug + '/', skipped: skip }; } };
''' + block + guard + r'''
  return 'SITE';
}
const out = {};
(async () => {
  out.pdf = await publishSite('/work/Q3 Report (final).pdf', { tipJar: { agentName: 'Mika' } });
  out.sent = published[0].files.map(f => [f.path, f.contentType]);
  out.slug = published[0].slug;
  out.page = Buffer.from(published[0].files[0].b64, 'base64').toString('utf8');
  out.shortcut = uploaded[0];
  statAnswer = null; out.folder = await publishSite('/work/site');
  statAnswer = { ok: true, size: 5 }; out.html = await publishSite('/work/site/index.html');
  statAnswer = { ok: true, size: 3500000 };
  try { await publishSite('/work/big.pptx'); out.big = 'published'; } catch (e) { out.big = e.message; }
  statAnswer = { ok: true, size: 900 }; skip = ['deck.pptx (file exceeds 2 MiB limit)'];
  try { await publishSite('/work/deck.pptx'); out.refused = 'published'; } catch (e) { out.refused = e.message; }
  skip = []; chainUp = false; out.local = await publishSite('/work/notes.docx');
  out.xss = fileSharePage({ title: '<script>x</script>', fileName: 'a.pdf', size: 10 });
  console.log(JSON.stringify(out));
})();
'''
r = subprocess.run(['node', '--input-type=module', '-e', harness], capture_output=True, text=True, timeout=60)
if r.returncode != 0:
    print('    FAIL  the real publish source ran under node\n' + r.stderr[-1500:])
    sys.exit(1)
o = json.loads(r.stdout.strip().splitlines()[-1])
failures = []


def check(name, ok, detail=''):
    print(('    ok    ' if ok else '    FAIL  ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(name)


check('a PDF goes to the public host', o['pdf']['mode'] == 'canister' and o['pdf']['url'].startswith('https://'), str(o['pdf']))
check('it ships a share page and the file itself, with the right type',
      o['sent'] == [['index.html', 'text/html'], ['Q3-Report-final.pdf', 'application/pdf']], str(o['sent']))
check('the address is made from the file name', o['slug'] == 'Q3-Report-final', o['slug'])
page = o['page']
check('the share page names the file, its kind and who made it',
      'Q3 Report (final)' in page and '>PDF<' in page and 'made by Mika' in page)
check('the share page downloads and previews the file it sits beside',
      'href="Q3-Report-final.pdf" download' in page and '<iframe class="pv" src="Q3-Report-final.pdf"' in page)
check('the share page loads nothing from anywhere else', 'http://' not in page and 'https://' not in page and '<script' not in page)
check('a clickable link is filed beside the original', o['shortcut'][0] == '/work' and o['shortcut'][1] == 'Q3-Report-final.url'
      and 'URL=https://host.example/me/Q3-Report-final/' in o['shortcut'][2], str(o['shortcut']))
check('a folder is still published as a site', o['folder'] == 'SITE')
check('an index.html is still published as a site', o['html'] == 'SITE')
check('a file over 2 MB is refused with its size, not half-published',
      '3.5 MB' in o['big'] and '2 MB at most' in o['big'], o['big'])
check('a file the host turned away is a failure, not a link to an empty page',
      'turned the file away' in o['refused'], o['refused'])
check('with no sign-in the result is called a preview, never public', o['local']['mode'] == 'preview', str(o['local']))
check('a file name cannot inject markup into the share page', '<script>x' not in o['xss'] and '&lt;script&gt;' in o['xss'])
rt = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
check('coworkers are told they can publish a PDF, a Word document or a deck',
      'a PDF, a Word document (.docx)' in rt and 'PowerPoint deck (.pptx)' in rt)

if failures:
    print(f'\n{len(failures)} check(s) failed')
    sys.exit(1)
print('\nall checks passed')

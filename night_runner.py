"""CafresoHQ night runner — Sprint 4 MVP-1 ("close the laptop, work continues").

Executes scheduled missions server-side, inside the serve.py process, while no
browser is attached. It is a Python port of ONLY the mission iteration loop
from missions.jsx (runMissionIteration): build prompt → call the LLM with the
container-side provider key (~/.hermes/.env, the same store /hermes/provider
writes) → parse bracket-marker tool calls → execute → loop (max 4 hops).

TOOL GRAMMAR v1 — the regexes below are TEXTUALLY IDENTICAL to TOOL_REGISTRY
in hq-runtime.jsx. scripts/test_night_grammar.py extracts both sides and fails
CI on drift. If you change a marker there, bump NIGHT_GRAMMAR_VERSION in BOTH
files and update the test fixtures.

NIGHT TOOL SUBSET (the seam holds by construction): read/search/fetch + vault
writes only. No WALLET_*, no PUBLISH_SITE, no BASH, no FILE_WRITE, no
EXPORT_*/GENERATE_* — anything that signs, spends, publishes, or mutates the
host filesystem stays in the authenticated browser shell.

Tool execution self-calls serve.py over localhost HTTP so every existing
server-side validation (vault path rules, CAFRESOHQ_ALLOWED_DIRS, API key)
applies unchanged.
"""

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

NIGHT_GRAMMAR_VERSION = 1

# ── Grammar (verbatim from hq-runtime.jsx TOOL_REGISTRY; /i → re.IGNORECASE) ──
_TOOL_RE_SRC = {
    'SEARCH':        r'\[\s*SEARCH\s*:\s*([^\]\n]+)\]',
    'VAULT_SEARCH':  r'\[\s*VAULT_SEARCH\s*:\s*([^\]\n]+)\]',
    'VAULT_READ':    r'\[\s*VAULT_READ\s*:\s*([^\]\n]+)\]',
    'VAULT_APPEND':  r'\[\s*VAULT_APPEND\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_APPEND\s*\]',
    'VAULT_NEW':     r'\[\s*VAULT_NEW\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_NEW\s*\]',
    'FILE_READ':     r'\[\s*FILE_READ\s*:\s*([^\]\n]+)\]',
    'DIR_LIST':      r'\[\s*DIR_LIST\s*:\s*([^\]\n]+)\]',
    'BROWSER_FETCH': r'\[\s*BROWSER_FETCH\s*:\s*([^\]\n]+)\]',
}
TOOL_RES = {k: re.compile(v, re.IGNORECASE) for k, v in _TOOL_RE_SRC.items()}
BLOCK_TOOLS = {'VAULT_APPEND', 'VAULT_NEW'}
MAX_TOOL_HOPS = 4          # parity with missions.jsx maxToolHops
MAX_ITER_TOKENS = 2048     # parity with missions.jsx maxTokens


class NightContext(object):
    """Everything a run needs to reach the host serve.py + providers."""

    def __init__(self, base_url, api_key='', hermes_home='', brave_key=''):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or ''
        self.hermes_home = hermes_home or os.environ.get('HERMES_HOME', '').strip() \
            or os.path.expanduser('~/.hermes')
        self.brave_key = brave_key or os.environ.get('BRAVE_API_KEY', '').strip()
        # Self-signed TLS on localhost is fine — we are calling ourselves.
        self.ssl_ctx = ssl._create_unverified_context() if self.base_url.startswith('https') else None


def _self_call(ctx, method, path, body=None, headers=None, timeout=90):
    """HTTP to our own serve.py. Returns (status, bytes)."""
    url = ctx.base_url + path
    data = None
    hdrs = {'X-Night-Runner': '1'}
    if ctx.api_key:
        hdrs['X-API-Key'] = ctx.api_key
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    kw = {'timeout': timeout}
    if ctx.ssl_ctx is not None:
        kw['context'] = ctx.ssl_ctx
    try:
        with urllib.request.urlopen(req, **kw) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        # urlopen RAISES on status >= 400 and never returns it. Return the
        # (status, body) tuple instead so callers' status checks (vault-write
        # s != 200, VAULT_READ s == 404) actually run — otherwise a failed
        # vault PUT is miscounted as a successful note in the run log/Gazette.
        return e.code, e.read()


# ── LLM call via the container-side provider key store ──────────────────────
_PROVIDER_ENDPOINTS = {
    'openrouter':    ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'gemini':        ('GOOGLE_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'google-openai': ('GOOGLE_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'groq':          ('GROQ_API_KEY', 'https://api.groq.com/openai/v1/chat/completions'),
}


def read_provider_config(hermes_home):
    """Read (provider, model, key) from ~/.hermes/{config.yaml,.env} — the same
    store /hermes/provider writes. Returns (None, None, None) if unconfigured."""
    provider, model = 'openrouter', ''
    try:
        with open(os.path.join(hermes_home, 'config.yaml'), 'r', encoding='utf-8') as f:
            cfg = f.read()
        pm = re.search(r'^\s*provider:\s*(\S+)', cfg, re.MULTILINE)
        mm = re.search(r'^\s*default:\s*(\S+)', cfg, re.MULTILINE)
        if pm:
            provider = pm.group(1).strip()
        if mm:
            model = mm.group(1).strip()
    except Exception:
        pass
    spec = _PROVIDER_ENDPOINTS.get({'google-openai': 'gemini'}.get(provider, provider))
    if not spec:
        return None, None, None
    env_var, _url = spec
    key = os.environ.get(env_var, '').strip()
    if not key:
        try:
            with open(os.path.join(hermes_home, '.env'), 'r', encoding='utf-8') as f:
                m = re.search(r'(?m)^%s\s*=\s*(\S+)' % re.escape(env_var), f.read())
            if m:
                key = m.group(1).strip().strip('"\'')
        except Exception:
            pass
    if not key:
        return None, None, None
    return provider, model, key


def llm_call(ctx, messages, max_tokens=MAX_ITER_TOKENS):
    """Non-streaming OpenAI-compatible chat completion. Returns (text, tokens)."""
    provider, model, key = read_provider_config(ctx.hermes_home)
    if not key:
        raise RuntimeError('no provider key configured (~/.hermes/.env) — '
                           'set one via Settings → BYO key before scheduling night shifts')
    env_var, url = _PROVIDER_ENDPOINTS[{'google-openai': 'gemini'}.get(provider, provider)]
    payload = json.dumps({
        'model': model or 'openai/gpt-oss-120b:free',
        'messages': messages,
        'max_tokens': max_tokens,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + key,
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode('utf-8', 'replace'))
    text = ''
    try:
        text = data['choices'][0]['message']['content'] or ''
    except Exception:
        raise RuntimeError('provider returned no choices: %s' % json.dumps(data)[:300])
    used = 0
    try:
        used = int(data.get('usage', {}).get('total_tokens', 0) or 0)
    except Exception:
        pass
    return text, used


# ── Tool execution (localhost self-calls; server-side validation applies) ────
def run_tool(ctx, name, arg, body):
    arg = (arg or '').strip()
    try:
        if name == 'SEARCH':
            if not ctx.brave_key:
                return 'SEARCH is unavailable on the night shift (no server-side BRAVE_API_KEY). Use BROWSER_FETCH on a known URL, or work from vault + project files.'
            s, raw = _self_call(ctx, 'GET', '/brave/search?q=' + urllib.parse.quote(arg),
                                headers={'X-Brave-Key': ctx.brave_key})
            data = json.loads(raw.decode('utf-8', 'replace'))
            results = (data.get('web', {}) or {}).get('results', [])[:6]
            if not results:
                return 'No results.'
            return '\n'.join('%d. %s\n   %s\n   %s' % (
                i + 1, r.get('title', ''), r.get('url', ''), r.get('description', ''))
                for i, r in enumerate(results))
        if name == 'VAULT_SEARCH':
            s, raw = _self_call(ctx, 'GET', '/vault/search?q=%s&limit=8' % urllib.parse.quote(arg))
            hits = json.loads(raw.decode('utf-8', 'replace')).get('hits', [])
            if not hits:
                return 'No matches in vault.'
            return '\n\n'.join('• %s\n  %s' % (h.get('path', ''), h.get('snippet', '')) for h in hits)
        if name == 'VAULT_READ':
            s, raw = _self_call(ctx, 'GET', '/vault/note?path=' + urllib.parse.quote(arg))
            if s == 404:
                return 'Not found: ' + arg
            text = raw.decode('utf-8', 'replace')
            return text[:4000] + '\n\n…(truncated)' if len(text) > 4000 else text
        if name in ('VAULT_APPEND', 'VAULT_NEW'):
            mode = 'append' if name == 'VAULT_APPEND' else 'write'
            s, raw = _self_call(ctx, 'PUT', '/vault/note?path=%s&mode=%s' % (
                urllib.parse.quote(arg), mode), body=(body or ''),
                headers={'Content-Type': 'text/markdown'})
            if s != 200:
                return 'Vault write failed (%d): %s' % (s, raw[:200].decode('utf-8', 'replace'))
            verb = 'Appended' if mode == 'append' else 'Wrote'
            return '%s %d chars → %s' % (verb, len(body or ''), arg)
        if name in ('FILE_READ', 'DIR_LIST'):
            s, raw = _self_call(ctx, 'POST', '/tools/exec',
                                body=json.dumps({'tool': name, 'arg': arg}))
            data = json.loads(raw.decode('utf-8', 'replace'))
            if not data.get('ok'):
                return 'Tool error: ' + str(data.get('error', 'unknown'))
            out = str(data.get('result', ''))
            return out[:6000] + '\n…(truncated)' if len(out) > 6000 else out
        if name == 'BROWSER_FETCH':
            s, raw = _self_call(ctx, 'GET', '/browser/fetch?url=%s&max_chars=8000' %
                                urllib.parse.quote(arg))
            data = json.loads(raw.decode('utf-8', 'replace'))
            if data.get('error'):
                return 'Browser fetch error: ' + str(data['error'])
            head = 'URL: %s\nStatus: %s\nTitle: %s\n%s\n' % (
                data.get('url', arg), data.get('status', '?'), data.get('title', '(none)'), '─' * 40)
            return head + str(data.get('text', ''))[:8000]
        return 'Unknown tool: ' + name
    except Exception as e:  # tools never kill an iteration
        return 'Tool %s failed: %s' % (name, e)


def find_first_tool(text):
    """Earliest bracket-marker match → (name, arg, body, span) or None.
    Mirrors the browser runtime: one tool per hop, first match wins."""
    best = None
    for name, rx in TOOL_RES.items():
        m = rx.search(text or '')
        if m and (best is None or m.start() < best[3][0]):
            body = m.group(2) if name in BLOCK_TOOLS and m.lastindex and m.lastindex >= 2 else None
            best = (name, m.group(1), body, m.span())
    return best


# ── Prompt (night edition of missions.jsx buildResearchPrompt/ProjectStudy) ──
def build_prompt(sched, iteration, total_iters, notes_list, allow_search):
    folder = sched.get('vaultFolder', 'Research/night')
    is_study = sched.get('type') == 'project-study'
    actions = []
    if is_study:
        actions.append('  • [DIR_LIST: <path>] — explore the project structure')
        actions.append('  • [FILE_READ: <file path>] — read a project file to understand it')
    if allow_search:
        actions.append('  • [SEARCH: <specific query>] — query the web for a NEW angle. Be specific.')
    actions.append('  • [BROWSER_FETCH: <url>] — fetch a page you already know the URL of')
    actions.append('  • [VAULT_SEARCH: <query>] / [VAULT_READ: <path>] — review existing notes')
    actions.append('  • [VAULT_NEW: %s/<descriptive-slug>.md]\\n# <title>\\n\\n<focused note>\\n[/VAULT_NEW]' % folder)
    actions.append('  • [VAULT_APPEND: <path>]\\n<content>\\n[/VAULT_APPEND] — extend an existing note')
    lines = [
        'You are on the NIGHT SHIFT: an unattended, scheduled work session. Nobody is watching; your notes ARE the deliverable and will headline the morning report.',
        '',
        ('PROJECT: %s\nPATH: %s' % (sched.get('projectName', ''), sched.get('projectPath', '')))
        if is_study else ('TOPIC: %s' % sched.get('topic', '')),
        'ITERATION: %d of ~%d planned tonight' % (iteration + 1, total_iters),
        'VAULT FOLDER: %s/' % folder,
        '',
        'Notes already written under %s/:' % folder,
        notes_list or '  (none yet)',
        '',
        '=== YOUR JOB THIS ITERATION ===',
        'Do EXACTLY ONE focused read-and-write cycle: pick a single angle not covered yet, gather what you need, write ONE focused note. Leave the rest for later iterations.',
        '',
        'Available actions (use ONE, max two):',
    ] + actions + [
        '',
        'Rules:',
        '  - ONE gather step → ONE note. Never chain multiple searches or reads beyond two actions.',
        "  - Don't re-write notes that already exist — extend them with VAULT_APPEND instead.",
        '  - Use frontmatter (---\\ntags: [night-shift]\\n---) and wikilinks ([[other-note]]) on new notes.',
        '  - Night shift is read-only outside the vault: no shell, no publishing, no money — those need the boss awake.',
        '  - End your reply with a plain status line: "Wrote X. Next iteration could explore Y."',
    ]
    return '\n'.join(lines)


def _notes_index(ctx, folder):
    try:
        s, raw = _self_call(ctx, 'GET', '/vault/list')
        files = json.loads(raw.decode('utf-8', 'replace')).get('files', [])
        prefix = folder.rstrip('/') + '/'
        rows = [f for f in files if str(f.get('path', '')).startswith(prefix)]
        rows.sort(key=lambda f: f.get('mtime', 0) or 0, reverse=True)
        return '\n'.join('  - %s' % f.get('path', '') for f in rows[:20])
    except Exception:
        return ''


def run_iteration(ctx, sched, iteration, total_iters):
    """One prompt → hop-loop → note. Returns {writes, tokens, summary, error}."""
    notes = _notes_index(ctx, sched.get('vaultFolder', ''))
    prompt = build_prompt(sched, iteration, total_iters, notes, bool(ctx.brave_key))
    persona = ('You are %s, an autonomous research agent in CafresoHQ. '
               'You work in disciplined, small steps and produce well-structured '
               'markdown notes.') % (sched.get('agentName') or 'a night-shift agent')
    messages = [{'role': 'system', 'content': persona},
                {'role': 'user', 'content': prompt}]
    writes, tokens_used, reply = [], 0, ''
    try:
        for _hop in range(MAX_TOOL_HOPS):
            reply, used = llm_call(ctx, messages)
            tokens_used += used
            hit = find_first_tool(reply)
            if not hit:
                break
            name, arg, body, _span = hit
            result = run_tool(ctx, name, arg, body)
            if name in ('VAULT_NEW', 'VAULT_APPEND') and not str(result).startswith('Vault write failed'):
                writes.append({'name': name, 'path': arg.strip(), 'at': int(time.time() * 1000)})
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'user', 'content':
                             'TOOL RESULT [%s]:\n%s\n\nContinue. Use at most one more tool, '
                             'or finish with your plain status line.' % (name, result)})
    except Exception as e:
        return {'writes': writes, 'tokens': tokens_used, 'summary': '', 'error': str(e)}
    summary = ' '.join((reply or '').split())[-300:]
    return {'writes': writes, 'tokens': tokens_used, 'summary': summary, 'error': None}


def run_mission(ctx, sched, on_progress=None, should_abort=None):
    """Full night mission: iterate every intervalMs until durationMs elapses.
    Blocking — the caller owns the thread. Returns the final run record."""
    started = int(time.time() * 1000)
    duration_ms = min(int(sched.get('durationMs', 3600000)), 4 * 3600 * 1000)
    interval_ms = max(int(sched.get('intervalMs', 300000)), 60000)
    total_iters = max(1, round(duration_ms / float(interval_ms)))
    run = {
        'id': 'run_%d' % started,
        'scheduleId': sched.get('id', ''),
        'agentId': sched.get('agentId', ''),
        'agentName': sched.get('agentName', ''),
        'topic': sched.get('topic', ''),
        'vaultFolder': sched.get('vaultFolder', ''),
        'startedAt': started,
        'finishedAt': 0,
        'iterations': 0,
        'writes': [],
        'tokensUsed': 0,
        'errors': 0,
        'lastError': '',
        'summary': '',
        'grammarVersion': NIGHT_GRAMMAR_VERSION,
    }
    deadline = started + duration_ms
    error_streak = 0
    while int(time.time() * 1000) < deadline:
        if should_abort and should_abort():
            run['lastError'] = 'aborted'
            break
        res = run_iteration(ctx, sched, run['iterations'], total_iters)
        run['iterations'] += 1
        run['writes'].extend(res['writes'])
        run['tokensUsed'] += res['tokens']
        if res['error']:
            run['errors'] += 1
            run['lastError'] = res['error'][:300]
            error_streak += 1
            if error_streak >= 3:   # parity with the browser runner's auto-pause
                break
        else:
            error_streak = 0
            if res['summary']:
                run['summary'] = res['summary']
        if on_progress:
            try:
                on_progress(dict(run))
            except Exception:
                pass
        # Sleep in 5s slices so aborts are responsive.
        wake_at = time.time() + interval_ms / 1000.0
        while time.time() < wake_at and int(time.time() * 1000) < deadline:
            if should_abort and should_abort():
                break
            time.sleep(5)
    run['finishedAt'] = int(time.time() * 1000)
    return run

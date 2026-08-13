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

import collections
import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

# LLM calls ride the driver contract (docs/DRIVER_CONTRACT.md §5 step 4) —
# night missions inherit every OpenAI-compat backend the drivers support,
# including keyless LOCAL daemons the old private client refused outright.
from drivers.base import DriverError as _DriverError, run_task_text as _run_task_text
from drivers.local_http import (GeminiDriver as _GeminiDriver,
                                GroqDriver as _GroqDriver,
                                LMStudioDriver as _LMStudioDriver,
                                OpenRouterDriver as _OpenRouterDriver)

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
# parity with missions.jsx's "(m.errors || 0) >= 3" auto-pause. Named, not
# left inline where run_mission uses it, so scripts/test_night_grammar.py
# can check it against the browser source the same way it already checks
# _TOOL_RE_SRC -- a comment claiming parity is not parity, it is a promise
# nothing verifies. See that file's section on why this matters: the
# harmony-parsing gap and the dotted-tool-naming gap were both found by
# actually running the code, not by reading a "mirrors X" comment and
# trusting it.
ERROR_STREAK_AUTO_PAUSE = 3


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


_PROVIDER_ALIASES = {'google-openai': 'gemini'}

# Local OpenAI-compatible servers: reached via the config's own base_url and
# usually keyless. hermes-bootstrap's model block calls all of these 'lmstudio'
# (see its comment "LM Studio / Ollama / vLLM") — there is no 'ollama' provider
# in hermes-agent, so 'ollama' is a UI label that writes provider: lmstudio.
_LOCAL_PROVIDERS = frozenset(('lmstudio', 'ollama', 'vllm', 'llamacpp', 'openai-compatible'))

# Everything needed to call a model backend directly, without the agent gateway.
Backend = collections.namedtuple('Backend', 'provider raw_provider model url headers key local')


def read_model_config(hermes_home):
    """Parse ONLY the `model:` block of hermes config.yaml.

    Returns {'raw_provider', 'model', 'base_url', 'ok'}; never raises — it runs
    per search job, and an unreadable config must degrade, not crash.

    Scoping to the block matters: a bare `^\\s*default:` search (what the old
    readers did) also matches `default:` under `approvals:`/`tools:`, so an
    unrelated key could silently become the model.
    """
    out = {'raw_provider': '', 'model': '', 'base_url': '', 'ok': False}
    try:
        with open(os.path.join(hermes_home, 'config.yaml'), 'r', encoding='utf-8') as f:
            cfg = f.read()
    except Exception:
        return out
    m = re.search(r'(?m)^model:[ \t]*$', cfg)
    if not m:
        return out
    # The block is the indented run after `model:` — stop at the next line that
    # starts in column 0 (the next top-level key).
    rest = cfg[m.end():]
    end = re.search(r'(?m)^(?=\S)', rest)
    block = rest[:end.start()] if end else rest
    for field, key in (('default', 'model'), ('provider', 'raw_provider'), ('base_url', 'base_url')):
        # No trailing `$`: `(\S+)` already stops at whitespace, and anchoring to
        # end-of-line dropped the value whenever an inline YAML comment followed
        # (`provider: lmstudio  # local box`) — which then defaulted the whole
        # backend to the openrouter cloud. Indentation + block-scoping still keep
        # a decoy `default:` under another top-level key from matching.
        f_m = re.search(r'(?m)^[ \t]+%s:[ \t]*(\S+)' % field, block)
        if f_m:
            out[key] = f_m.group(1).strip().strip('"\'')
    out['ok'] = bool(out['raw_provider'] or out['model'])
    return out


def _read_env_key(hermes_home, env_var, env=None):
    env = os.environ if env is None else env
    key = (env.get(env_var) or '').strip()
    if key:
        return key
    try:
        with open(os.path.join(hermes_home, '.env'), 'r', encoding='utf-8') as f:
            m = re.search(r'(?m)^%s\s*=\s*(\S+)' % re.escape(env_var), f.read())
        if m:
            return m.group(1).strip().strip('"\'')
    except Exception:
        pass
    return ''


def resolve_backend(hermes_home, model_override='', env=None):
    """The one place that answers "how do I call the operator's chosen brain
    DIRECTLY?" — i.e. without the hermes agent gateway.

    Returns a Backend, or None when no direct path exists and the caller must
    fall back to the gateway. Never raises.

    Why direct at all: the gateway is an AGENT runtime. It layers a ~13k-token
    system prompt onto every call and — verified against hermes-agent 0.15.1 —
    silently DROPS max_tokens/response_format and IGNORES `model` (it echoes the
    requested name back while running whatever config.yaml says). For a plain
    summarisation call that is pure cost, and the echo makes provenance lie.
    Agent work still belongs on the gateway; this is for everything that isn't.
    """
    cfg = read_model_config(hermes_home)
    base_url = cfg['base_url']
    # openrouter is the zero-config default, but ONLY when nothing else is known.
    # A base_url with no provider is a local/custom backend — defaulting it to
    # openrouter would POST the operator's prompt to a third-party cloud on any
    # stale OPENROUTER_API_KEY and silently ignore the box they actually chose.
    raw = cfg['raw_provider'] or ('' if base_url else 'openrouter')
    provider = _PROVIDER_ALIASES.get(raw, raw)
    model = (model_override or '').strip() or cfg['model']

    spec = _PROVIDER_ENDPOINTS.get(provider)
    if spec:
        # Known cloud provider: the URL comes from _PROVIDER_ENDPOINTS, NEVER
        # from base_url. The two writers disagree — hermes-bootstrap writes
        # gemini's base_url as .../v1beta while serve.py writes
        # .../v1beta/openai — so trusting base_url here would POST to
        # /v1beta/chat/completions and 404 on half the fleet.
        env_var, url = spec
        key = _read_env_key(hermes_home, env_var, env)
        if not key:
            return None                       # unconfigured cloud → gateway
        return Backend(provider, raw, model, url,
                       {'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + key}, key, False)

    if provider in _LOCAL_PROVIDERS or base_url:
        # Local (or any unknown provider that told us where it lives). Keyless
        # is a legitimate config here — the old reader treated "no key" as
        # "unconfigured" and threw local backends away entirely.
        if not base_url:
            return None
        headers = {'Content-Type': 'application/json'}
        key = _read_env_key(hermes_home, 'LMSTUDIO_API_KEY', env)
        if key:
            headers['Authorization'] = 'Bearer ' + key
        return Backend(provider, raw, model,
                       base_url.rstrip('/') + '/chat/completions', headers, key, True)

    return None                               # e.g. anthropic → gateway only


def read_provider_config(hermes_home):
    """DEPRECATED — use resolve_backend(). Kept verbatim in contract for
    llm_call and any caller written against (provider, model, key), where the
    (None, None, None) return is load-bearing (llm_call raises on a missing
    key). Returns raw_provider so callers' own _PROVIDER_ENDPOINTS alias lookup
    still works."""
    b = resolve_backend(hermes_home)
    if b is None or not b.key or b.local:
        return None, None, None
    return b.raw_provider, b.model, b.key


_LLM_RETRY_MAX = 3            # total attempts
_LLM_RETRY_BASE_S = 1.5
_LLM_RETRY_CAP_S = 20.0


def _driver_for_backend(b):
    """Private driver instance for a resolved Backend. Private (not the
    registry singleton) so the hermes-config-resolved key/base_url never
    leaks into the drivers /agent/stream uses."""
    if b.local:
        # Backend.url is the full …/chat/completions endpoint; the driver
        # wants the API root.
        root = b.url[:-len('/chat/completions')] if b.url.endswith('/chat/completions') else b.url
        return _LMStudioDriver(base_url=root, api_key=b.key)
    return {
        'openrouter': _OpenRouterDriver,
        'gemini':     _GeminiDriver,
        'groq':       _GroqDriver,
    }[b.provider](api_key=b.key)


def llm_call(ctx, messages, max_tokens=MAX_ITER_TOKENS):
    """Non-streaming OpenAI-compatible chat completion via the driver family
    (drivers/local_http.py). Returns (text, tokens).

    Retry policy unchanged from the old private client: the night shift runs
    unattended for hours against free provider tiers, so a single 429 used to
    end an iteration and three in a row ended the run. Only 429/5xx/network
    failures retry — a 401 (bad key) or 400 (bad request) fails identically on
    a second attempt. Mirrors fetchStreamHead's policy in claude-client.jsx —
    keep the two in step.
    """
    b = resolve_backend(ctx.hermes_home)
    if b is None:
        raise RuntimeError('no provider key configured (~/.hermes/.env) — '
                           'set one via Settings → BYO key before scheduling night shifts')
    drv = _driver_for_backend(b)
    task = {'messages': list(messages), 'model': b.model or '',
            'limits': {'maxTokens': max_tokens}}
    last_err = None
    for attempt in range(_LLM_RETRY_MAX):
        try:
            text, usage = _run_task_text(drv, task)
            if not text:
                raise RuntimeError('provider returned no content')
            return text, int(usage.get('inTokens', 0)) + int(usage.get('outTokens', 0))
        except _DriverError as e:
            last_err = e
            up = e.upstream
            transient = (up == 429 or (up is not None and 500 <= up <= 599)
                         or (up is None and e.status == 502))
            if not transient:
                raise
            wait = e.retry_after
        if attempt == _LLM_RETRY_MAX - 1:
            break
        if wait is None:
            exp = min(_LLM_RETRY_BASE_S * (2 ** attempt), _LLM_RETRY_CAP_S)
            wait = exp / 2 + random.random() * (exp / 2)
        print('[night] %s — retrying in %.1fs (%d/%d)'
              % (str(last_err)[:120], wait, attempt + 2, _LLM_RETRY_MAX), flush=True)
        time.sleep(wait)
    raise last_err if last_err else RuntimeError('llm_call failed after retries')


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


_HARMONY_RE = re.compile(
    r'<\|channel\|>\s*commentary\s+to=([A-Za-z0-9_.]+)\s*'
    r'(?:<\|constrain\|>\w+\s*)?<\|message\|>(.*?)'
    r'(?=<\|channel\||<\|end\|>|<\|call\|>|<\|return\|>|$)',
    re.IGNORECASE | re.DOTALL)

# The prompt's own closing rule (build_prompt) demands a status line shaped
# like "Wrote X. Next iteration could explore Y." — X is a bare count, not
# necessarily the word "note" ("Wrote 1. Next iteration..." was the exact
# live-observed fabrication, and it never says "note" at all). Two shapes,
# either one trips the honesty check in run_iteration:
#   - the prompt's own literal format: "Wrote" + a number
#   - a paraphrase naming what got written: wrote/saved/added/created a
#     note/vault entry/file
_CLAIMS_A_WRITE_RE = re.compile(
    r'\bwrote\b\s*\d+'
    r'|\b(?:wrote|saved|added|created)\b[^.\n]{0,40}\b(?:note|vault|file)\b',
    re.IGNORECASE)


def _harmony_args_for(name, payload):
    """Map a harmony JSON payload to the (arg, body) night_runner's own
    tool runners expect. Ported from hq-runtime.jsx's harmonyArgsFor,
    trimmed to the 8 tools this runner actually supports (TOOL_RES) --
    the browser's version also covers DM_TO/HIRE_AGENT/etc, which have no
    meaning here (night shift is vault-only, see build_prompt's own
    "no shell, no publishing, no money" line)."""
    try:
        parsed = json.loads(payload)
    except Exception:
        parsed = None

    def get(*keys):
        if not isinstance(parsed, dict):
            return None
        for k in keys:
            if parsed.get(k) is not None:
                return str(parsed[k])
        return None

    if name in ('SEARCH', 'VAULT_SEARCH'):
        return get('query', 'q', 'search') or payload, None
    if name in ('VAULT_READ', 'FILE_READ', 'DIR_LIST', 'BROWSER_FETCH'):
        return get('path', 'file', 'url', 'query') or payload, None
    if name in ('VAULT_APPEND', 'VAULT_NEW'):
        return get('path', 'file') or '', get('content', 'body', 'text') or ''
    return payload, None


def find_first_tool(text):
    """Earliest bracket-marker match → (name, arg, body, span) or None.
    Mirrors the browser runtime: one tool per hop, first match wins.

    Bracket format only, until a live run proved that half a promise: an
    Ollama llama3.1 mission ran clean -- iterations: 1, errors: 0 -- and
    wrote NOTHING, because its reply was harmony syntax
    ("<|channel|>commentary to=browser_fetch...") that this function had
    no regex for. `hit` came back None, the hop loop's `if not hit: break`
    fired on the very first turn, and the run reported SUCCESS having done
    nothing at all -- worse than an honest error, because a quiet night and
    a broken tool-call format are indistinguishable to the boss reading
    the morning report. The browser side already carries this exact fix
    (extractHarmonyToolCalls / harmonyArgsFor) for "gpt-oss-20b, qwen-3,
    and other OSS models" -- both of which this machine's own LM Studio
    catalog actually offers, so this is not a hypothetical, it is the
    other half of a fix that only shipped to chat."""
    best = None
    for name, rx in TOOL_RES.items():
        m = rx.search(text or '')
        if m and (best is None or m.start() < best[3][0]):
            body = m.group(2) if name in BLOCK_TOOLS and m.lastindex and m.lastindex >= 2 else None
            best = (name, m.group(1), body, m.span())
    if best is not None:
        return best
    hm = _HARMONY_RE.search(text or '')
    if not hm:
        return None
    # Two live-observed namings for the same tool, in two different runs of
    # the SAME model: "browser_fetch" (underscore) and "browser.fetch"
    # (dotted, plus an extra unrelated "id" field neither JS nor this
    # function cares about). Strip an optional "functions." namespace
    # prefix, then fold any remaining dots to underscores before matching
    # TOOL_RES -- one normalization step, not a second special case bolted
    # onto the first.
    name = re.sub(r'^functions\.', '', hm.group(1)).replace('.', '_').upper()
    if name not in TOOL_RES:
        return None   # a tool night shift doesn't support (e.g. DM_TO) — not ours to run
    arg, body = _harmony_args_for(name, hm.group(2).strip())
    if not arg:
        return None
    return (name, arg, body, hm.span())


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
        'Do EXACTLY ONE focused read-and-write cycle: ONE gather action, THEN one write action, THEN your status line. That is three things, not two — the write is a real tool call, not a sentence describing one.',
        '',
        'Available actions (one gather, then one write):',
    ] + actions + [
        '',
        'Rules:',
        '  - ONE gather step, THEN one write. Never chain multiple searches or reads.',
        "  - Don't re-write notes that already exist — extend them with VAULT_APPEND instead.",
        '  - Use frontmatter (---\\ntags: [night-shift]\\n---) and wikilinks ([[other-note]]) on new notes.',
        '  - Night shift is read-only outside the vault: no shell, no publishing, no money — those need the boss awake.',
        '  - The write is MANDATORY and is a TOOL CALL: [VAULT_NEW: ...] or [VAULT_APPEND: ...], not a sentence claiming you wrote something. "I wrote a note about X" with no VAULT_NEW/VAULT_APPEND call is a LIE the boss will catch, because nothing lands in the vault.',
        '  - Only AFTER that tool call has run: end your reply with a plain status line reporting what you actually just wrote: "Wrote X. Next iteration could explore Y."',
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
    error = None
    if not writes and _CLAIMS_A_WRITE_RE.search(reply or ''):
        # The prompt's own closing rule demands a status line like "Wrote
        # X." -- and a model that skips the actual VAULT_NEW/VAULT_APPEND
        # call but still produces that sentence has written a LIE, not a
        # note. Watched live: iterations: 1, errors: 0, writes: [], and a
        # reply ending "Wrote 1. Next iteration could explore..." with no
        # tool call anywhere in the transcript -- a run that reported
        # success while the vault gained nothing. A quiet, honest night
        # (no claim, no write) is not an error; THIS -- a claim with
        # nothing behind it -- is exactly what fabricatedRelay() catches
        # on the chat side, and the morning report deserves the same
        # honesty: better to say the claim didn't match reality than to
        # let "Wrote 1" stand unexamined next to an empty writes list.
        # Office words, and SHORT. This lands verbatim in the morning
        # Gazette, which slices lastError for display — at 60 chars the
        # old wording ('…never called VAULT_NEW/VAULT_APPEND — nothing
        # landed in the vault', 90 chars) was cut precisely at the end of
        # the protocol tokens, so the boss read two wire-format names and
        # LOST the clause that says what it means. §6 bans those names on
        # a human surface; the truncation made it jargon-only.
        error = 'said it saved a note, but nothing reached the vault'
    return {'writes': writes, 'tokens': tokens_used, 'summary': summary, 'error': error}


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
            # This word reaches the boss. `should_abort` is only ever true
            # because the boss deleted the schedule (serve.py's
            # _missions_delete is the sole writer of _night_abort), so the
            # honest sentence names them as the cause and says what it cost
            # -- and 'aborted' is a wire word, which §6 bans on a human
            # surface. Nothing reads this field as a sentinel; all three
            # surfaces that show it print it as prose. It was easy to miss
            # because the Gazette used to bury it behind `summary`.
            run['lastError'] = 'you stopped this one — the rest of the night did not run'
            break
        res = run_iteration(ctx, sched, run['iterations'], total_iters)
        run['iterations'] += 1
        run['writes'].extend(res['writes'])
        run['tokensUsed'] += res['tokens']
        if res['error']:
            run['errors'] += 1
            run['lastError'] = res['error'][:300]
            error_streak += 1
            if error_streak >= ERROR_STREAK_AUTO_PAUSE:
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

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

# Every surface that shows a night error SLICES it, and they disagree:
# features.jsx's Gazette at 90, missions.jsx's list at 60, its detail pane at
# 200, and views/terminal.jsx's CLI night report at 50. The tightest wins,
# because a sentence is only as complete as the narrowest place it is read.
#
# Measured 2026-08-15: the message below this block was deliberately shortened
# once already, after an earlier 90-character version was cut exactly at the
# end of its protocol tokens. It came out at 51 — one over — so the CLI report
# has been printing "…nothing reached the vaul" for as long as it has existed.
# Counting by hand is what produced 51; this constant plus the check in
# scripts/test_night_says_what_it_cannot_do.py is what stops the next one.
NIGHT_ERROR_MAX = 50

# The 23 TOOL_REGISTRY tools the night shift does NOT carry, each with the
# office word for what was being reached for. The seam itself is deliberate
# and stays: anything that signs, spends, publishes or mutates the host
# filesystem needs the boss's identity, and at 3am nobody is holding it.
#
# What was NOT deliberate is what happened when a coworker reached anyway.
# find_first_tool returned None, the hop loop's `if not hit: break` fired,
# and the run recorded errors: 0 — a clean night, with the reach nowhere in
# the record. That is the same shape this file's own find_first_tool
# docstring condemns for harmony syntax: a quiet night and a coworker who
# could not do the job are indistinguishable to whoever reads the morning
# report. Reproduced 2026-08-15 against a canned brain emitting
# [PUBLISH_SITE: …] — writes: [], error: None, and the raw marker printed
# verbatim in the summary, absolute filesystem path and all.
#
# Phrases are short on purpose; see NIGHT_ERROR_MAX. The test asserts that
# this table plus NIGHT_IGNORES covers every name in hq-runtime.jsx's
# TOOL_REGISTRY, so a tool added to the browser cannot quietly become a
# 24th silent no-op.
NIGHT_CANNOT = {
    'BASH':               'shell commands',
    'BROWSER_SCREENSHOT': 'screenshots',
    'DM_TO':              'messaging',
    'EXPORT_DOCX':        'exports',
    'EXPORT_PDF':         'exports',
    'EXPORT_PPTX':        'exports',
    'FILE_WRITE':         'file changes',
    'GENERATE_IMAGE':     'image making',
    'GENERATE_VIDEO':     'video making',
    'HANDOFF_TO':         'handoffs',
    'HIRE_AGENT':         'hiring',
    'HIRE_ASSISTANT':     'hiring',
    'MEMORY_APPEND':      'memory',
    'MEMORY_LIST':        'memory',
    'MEMORY_READ':        'memory',
    'MEMORY_WRITE':       'memory',
    'PEER_JOURNAL':       'peer notes',
    'PUBLISH_SITE':       'publishing',
    'REQUEST_ELEVATION':  'access requests',
    'SPAWN_SUBAGENT':     'sub-agents',
    'WALLET_BALANCE':     'wallet reads',
    'WALLET_SEND':        'spending',
}

# ACK is a protocol acknowledgement, not a request to do work — a night reply
# containing one has not tried and failed at anything, so reporting it would
# be noise in the morning report. Listed rather than omitted so the coverage
# check can tell "decided to ignore" from "forgot about".
NIGHT_IGNORES = {'ACK'}

# Marker scan for the tools above. Deliberately NOT built from TOOL_RES: the
# night regexes capture arguments, and here only the NAME matters — matching
# on membership in NIGHT_CANNOT is what keeps prose like "[NOTE: ...]" from
# tripping it.
_UNSUPPORTED_RE = re.compile(r'\[\s*([A-Za-z_]{3,})\s*[:\]]')

# ── Reasoning blocks (parity with REASONING_TAGS in hq-runtime.jsx) ──────────
# The night shift runs local brains by design — the free, tireless ones — and
# those are exactly the models that inline their chain of thought as
# `<think>…</think>` in `content`. Three things go wrong at 3am without this,
# all of them the browser-side defect measured on 2026-08-16 (office 9280):
# the monologue lands in the morning report; a marker the model was only
# WEIGHING gets executed; and find_unsupported_tool reports "reached for
# publishing" about a tool the coworker explicitly talked itself out of —
# an accusation, in the morning report, for something that never happened.
#
# The tag list is pinned on both sides by
# scripts/test_reasoning_is_not_the_bosss.py, the same way _TOOL_RE_SRC is
# pinned by scripts/test_night_grammar.py: a comment claiming parity is not
# parity, it is a promise nothing verifies.
REASONING_TAGS = 'think|thinking|reasoning|reflection'
_REASONING_RES = (
    re.compile(r'<(%s)\b[^>]*>[\s\S]*?</\1\s*>' % REASONING_TAGS, re.I),
    re.compile(r'^[\s\S]*?</(?:%s)\s*>' % REASONING_TAGS, re.I),
    re.compile(r'<(?:%s)\b[^>]*>[\s\S]*$' % REASONING_TAGS, re.I),
)


def mask_reasoning(text):
    """Blank reasoning blocks in place — what a coworker only THOUGHT.

    Equal-length blanking, like the browser's maskReasoning: find_first_tool
    returns the match SPAN and the hop loop slices the reply by it, so
    removing bytes here would cut the reply in the wrong place.
    """
    s = text or ''
    if '<' not in s:
        return s
    for rx in _REASONING_RES:
        s = rx.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), s)
    return s


def strip_reasoning(text):
    """Remove reasoning blocks outright — for text headed at the boss."""
    s = text or ''
    if '<' not in s:
        return s
    for rx in _REASONING_RES:
        s = rx.sub('', s)
    return s.strip()


def night_cannot_sentence(tool):
    """§7 shape, inside NIGHT_ERROR_MAX: what happened, plus the way forward."""
    what = NIGHT_CANNOT.get(tool)
    return ('reached for %s — do it in the office' % what) if what else ''


# The one string run_tool writes when the vault turns a write away, and the
# one reader that takes it apart again. Two callers need the status back out
# of a message written for the model to read: the write ledger, which must
# not count a refused write as a note, and the morning report, which has to
# say which door is shut.
#
# Anchored in ONE place — `.match` below, no `^` in the pattern. Both at
# once reads as caution and is the opposite: with the anchor written twice,
# neither copy can be removed without the other still holding, so a test
# that deletes one sees no change and reports the reader as covered when
# half of it is not.
_VAULT_FAIL_PREFIX = 'Vault write failed'
_VAULT_FAIL_RE = re.compile(r'%s \((\d+)\)' % re.escape(_VAULT_FAIL_PREFIX))


def vault_write_status(result):
    """HTTP status behind a refused vault write, or None if it went through.

    Anchored: run_tool writes this as the WHOLE message, so the phrase
    turning up inside a longer string is prose, not a second failure.
    """
    m = _VAULT_FAIL_RE.match(str(result or ''))
    return int(m.group(1)) if m else None


def vault_refused_sentence(status):
    """§7 shape, inside NIGHT_ERROR_MAX: what happened, plus the way forward.

    Two sentences because there are two doors. 502/503 is the vault itself —
    Obsidian shut, the OCI bucket unreachable, no backend configured at all —
    and the boss fixes that in Connections. Anything else came back from a
    vault that answered, so the path is the suspect, not the wiring; sending
    the boss to Connections for a rejected filename would be the wrong door
    twice over.
    """
    if status in (502, 503):
        return 'vault is not reachable — check Connections'
    return 'vault refused the write — check the note path'


def vault_can_take_a_note(ctx):
    """Can anything land tonight? (ready, sentence).

    Every mission type this file writes a prompt for ends with a mandatory
    vault write; the notes ARE the deliverable. The office already knows the
    answer — /vault/status probes an Obsidian REST backend for real and
    stats an fs one — and nothing asked it, so a night with nowhere to file
    spent three iterations and three brain calls learning what one GET
    would have said before the first one.

    Unknown counts as ready, deliberately. This is an optimisation over a
    path that is already honest: since the refused-write branch in
    run_iteration, a dead vault is caught on the first iteration and the
    error streak stops the run. A probe that cannot answer must not be the
    thing that cancels a night the office could have run.
    """
    try:
        s, raw = _self_call(ctx, 'GET', '/vault/status', timeout=20)
        if s != 200:
            return True, ''
        # The read is inside the try with the request. An office that
        # answered in a shape this function did not expect is not a vault
        # that is down, and letting the AttributeError out would surface in
        # the morning report as lastError: "'list' object has no attribute
        # 'get'" — a stack message where the door should be, via
        # _night_run_one's str(e). Found by the suite for this fix.
        if json.loads(raw.decode('utf-8', 'replace')).get('configured'):
            return True, ''
    except Exception:
        return True, ''
    # 503 is not a guess: it is what this office's own PUT /vault/note
    # answers when no backend is configured, so the boss reads the same
    # sentence whether the vault was missing at the door or went down at
    # 1am. One fact, one wording, one door.
    return False, vault_refused_sentence(503)


def find_unsupported_tool(text):
    """First out-of-subset tool NAME reached for in `text`, or None.

    Checks the harmony form too, because a model that speaks harmony reaches
    for unavailable tools in harmony as well — find_first_tool already
    returns None for both, so both were silent.
    """
    text = mask_reasoning(text)   # weighing a tool is not reaching for one
    for m in _UNSUPPORTED_RE.finditer(text or ''):
        name = m.group(1).upper()
        if name in NIGHT_CANNOT:
            return name
    hm = _HARMONY_RE.search(text or '')
    if hm:
        name = re.sub(r'^functions\.', '', hm.group(1)).replace('.', '_').upper()
        if name in NIGHT_CANNOT:
            return name
    return None


def strip_unsupported_markers(text):
    """Drop out-of-subset markers from text headed for the morning report.

    The reach is reported as an error, in office words. The raw marker is
    wire format — §6 — and in the reproduced case it also carried the
    absolute path of a folder on the boss's machine into a summary line.
    """
    def _drop(m):
        return '' if m.group(1).upper() in NIGHT_CANNOT else m.group(0)
    out = re.sub(r'\[\s*([A-Za-z_]{3,})\s*:[^\]\n]*\]', _drop, strip_reasoning(text))
    return ' '.join(out.split())


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


# Same patterns as app/floor.jsx's SNAG_CAUSES (same classifier, same
# order), the wording tightened to fit NIGHT_ERROR_MAX rather than copied
# byte-for-byte — the browser's snag bubble is not sliced at 50 chars and
# this surface is. Ported because run_iteration below caught every
# llm_call failure and returned str(e) verbatim as `lastError`, which
# missions.jsx/features.jsx/terminal.jsx then render raw on the RECENT
# NIGHT RUNS / Gazette / CLI surfaces with no cleaning — reproduced live
# 2026-08-18 as "cannot reach http://10.0.0.100:1234/v1: <urlopen error
# [Errno 60] Operation timed out>" on the boss's own screen.
#
# Safe to treat every exception here as a BRAIN failure, not a
# misattributed one (the mistake app/floor.jsx's own comments warn
# against): run_tool catches its own exceptions ("tools never kill an
# iteration") and always returns a string, and find_first_tool /
# vault_write_status only ever pattern-match strings llm_call already
# guarantees are non-empty. The only raises reaching run_iteration's outer
# except come from llm_call itself.
_BRAIN_CAUSES = [
    (re.compile(r"no api key|api[- ]?key (?:not|isn'?t) |missing api key|unauthor|invalid bearer|\b401\b", re.I),
     "that brain isn't signed in — check Settings"),
    (re.compile(r"\b429\b|rate.?limit|too many requests", re.I),
     'that brain is rate-limited — try again soon'),
    (re.compile(r"insufficient|quota|billing|payment required|\b402\b", re.I),
     'that brain is out of credit — try another'),
    (re.compile(r"econnrefused|connection refused|enotfound|failed to fetch|network ?error|load failed|dns", re.I),
     "couldn't reach that brain — try again"),
    (re.compile(r"did ?n[o']?t start responding|did ?n[o']?t respond|not responding", re.I),
     'that brain is still warming up — try again'),
    (re.compile(r"timed? ?out|etimedout|\b504\b", re.I),
     'that took too long — try again'),
    (re.compile(r"\b5\d\d\b|internal server error|service unavailable", re.I),
     "that brain's having trouble — not you"),
    (re.compile(r"(?:\b404\b[^\n]{0,40})?(?:model[^\n]{0,60}(?:not found|does ?n[o']?t exist)|no such model|unknown model|pull the model)", re.I),
     "that brain isn't installed — pick another"),
]


def _clean_cause(raw):
    """cleanCause, ported: strip URLs/JSON shrapnel, cap to NIGHT_ERROR_MAX
    (not the JS side's 90 — that bubble isn't sliced at 50, this surface
    is). The fallback for a failure this table can't identify with
    confidence — a vague honest line beats a wrong-but-confident
    diagnosis."""
    first = str(raw or '').split('\n', 1)[0]
    first = re.sub(r'https?://\S+', '', first)
    first = re.sub(r'[{}\[\]"\\]', ' ', first)
    first = re.sub(r'\s+', ' ', first).strip()
    line = first or 'something went wrong on the last run'
    return (line[:NIGHT_ERROR_MAX - 1].rstrip() + '…'
            if len(line) > NIGHT_ERROR_MAX else line)


def brain_cause(raw):
    """One honest §7-shaped sentence for a night-shift brain-call failure.
    See _BRAIN_CAUSES above — this is snagCause's Python mirror."""
    text = str(raw or '')
    for rx, sentence in _BRAIN_CAUSES:
        if rx.search(text):
            return sentence
    return _clean_cause(text)


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
            if s != 200:
                # The status was read into `s` and never looked at. Every
                # refusal /brave/search can answer — 429 (the free tier the
                # night shift runs on, all night, one query per second), 401
                # for a key that expired since bedtime, 402 for a quota spent
                # by midnight, 502 for Brave unreachable — comes back as a
                # JSON error body with no `web.results` in it, so the slice
                # below produced [] and this branch told the coworker
                # "No results." A lookup that FAILED was reported as a lookup
                # that SUCCEEDED and found the web empty. The coworker then
                # filed exactly the note it was told to file — "no current
                # sources on <topic>" — and the run recorded errors: 0. Same
                # defect as the VAULT_READ error body returned as a note's
                # text, one door over, and worse unattended: nothing
                # downstream contradicts an empty search the way a shut vault
                # eventually refuses the write.
                return 'Search failed (%d): %s' % (
                    s, raw[:200].decode('utf-8', 'replace'))
            data = json.loads(raw.decode('utf-8', 'replace'))
            results = (data.get('web', {}) or {}).get('results', [])[:6]
            if not results:
                return 'No results.'
            return '\n'.join('%d. %s\n   %s\n   %s' % (
                i + 1, r.get('title', ''), r.get('url', ''), r.get('description', ''))
                for i, r in enumerate(results))
        if name == 'VAULT_SEARCH':
            s, raw = _self_call(ctx, 'GET', '/vault/search?q=%s&limit=8' % urllib.parse.quote(arg))
            if s != 200:
                # Same swallowed status, same lie in the other direction: a
                # 502 from a shut Obsidian or an unreachable OCI bucket has no
                # `hits` key, so this said "No matches in vault." — the vault
                # is EMPTY on that subject — to a coworker whose standing
                # instruction is "Don't re-write notes that already exist".
                # It duly wrote the note again. Not "Vault write failed", so
                # vault_write_status can't read a status out of it and this
                # must never be spelled like one.
                return 'Vault search failed (%d): %s' % (
                    s, raw[:200].decode('utf-8', 'replace'))
            hits = json.loads(raw.decode('utf-8', 'replace')).get('hits', [])
            if not hits:
                return 'No matches in vault.'
            return '\n\n'.join('• %s\n  %s' % (h.get('path', ''), h.get('snippet', '')) for h in hits)
        if name == 'VAULT_READ':
            s, raw = _self_call(ctx, 'GET', '/vault/note?path=' + urllib.parse.quote(arg))
            if s == 404:
                return 'Not found: ' + arg
            if s != 200:
                # 404 was the ONLY status this branch ever read. Every other
                # refusal GET /vault/note can answer — 502 from a shut
                # Obsidian or an unreachable OCI bucket, 415 for a filed deck
                # the editor door can't open, 400 for a path the vault won't
                # resolve, 500 for a read that blew up — comes back as a JSON
                # error body, and this returned that body AS THE NOTE'S TEXT.
                # The coworker then quoted, summarised and VAULT_APPENDed to
                # `{"error": "obsidian: <urlopen error [Errno 61] Connection
                # refused>"}` believing it was the note, and the run recorded
                # errors: 0 — the same quiet-night shape find_first_tool's
                # docstring condemns, with a fabricated note on top of it. A
                # door that is shut has to say so.
                return 'Vault read failed (%d): %s' % (
                    s, raw[:200].decode('utf-8', 'replace'))
            text = raw.decode('utf-8', 'replace')
            return text[:4000] + '\n\n…(truncated)' if len(text) > 4000 else text
        if name in ('VAULT_APPEND', 'VAULT_NEW'):
            mode = 'append' if name == 'VAULT_APPEND' else 'write'
            try:
                s, raw = _self_call(ctx, 'PUT', '/vault/note?path=%s&mode=%s' % (
                    urllib.parse.quote(arg), mode), body=(body or ''),
                    headers={'Content-Type': 'text/markdown'})
            except Exception as e:
                # A PUT that never got an answer (serve.py gone, socket
                # timeout — _self_call only converts HTTPError; a URLError
                # propagates) used to fall to the generic handler below and come
                # back as 'Tool VAULT_NEW failed: …'. vault_write_status has
                # no status to read out of that shape, returns None, and
                # run_iteration counted the write as a LANDED NOTE — writes:
                # [path], error: None, a morning report asserting a note the
                # vault never saw (and the phantom even cleared an earlier
                # genuine `refused`). Same wire, same words: 503 is already
                # the "vault is not reachable" door (see vault_can_take_a_note),
                # so the boss reads one sentence whether the vault refused or
                # never picked up.
                return '%s (503): %s' % (_VAULT_FAIL_PREFIX, e)
            if s != 200:
                return '%s (%d): %s' % (_VAULT_FAIL_PREFIX, s,
                                        raw[:200].decode('utf-8', 'replace'))
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

# A write claim at least describes something the night shift CAN do, so the
# check above compares it against the writes ledger. A PUBLISH claim has no
# ledger to check because there is no tool behind it at night at all — and
# measured 2026-08-15 against a canned brain, a reply with no marker and no
# write ("Reviewed the vendor copy… I published the updated site —
# cafreso.com is live with the new vendor page.") sailed through both
# checks: writes [], error None, errors 0 — and run_iteration's
# `summary = strip_unsupported_markers(reply)[-300:]` made the fabricated
# claim ITSELF the morning summary of a clean night. The boss wakes up to
# a Gazette asserting their site changed overnight.
#
# Two shapes, both anchored, because §4's cost analysis cuts the other way
# here — the night shift is a RESEARCH agent and its notes legitimately
# discuss other people publishing things ("the vendor published a report in
# 2024" must never trip this):
#   - a sentence that OPENS with the bare verb — the same status-line shape
#     as "Wrote 1" above; third-party mentions carry a subject before the
#     verb, so they cannot sit at sentence start. This branch also demands
#     a site/page/live/update object so a heading like "Published figures
#     show…" (verb as adjective) stays quiet.
#   - first person + verb, with at most one auxiliary from a fixed list
#     between them ("I published", "we've deployed", "I just launched") —
#     an open [^.\n]{0,N} gap here would match "we noticed they published
#     a fix", which is reporting, not claiming.
# Three verbs, deliberately: published/deployed/launched are the publish
# surface's own vocabulary. Claims of other undoable deeds (sent money,
# emailed someone, ran a shell command) are NOT covered — that is a
# judgment-call taxonomy with no registry to sweep, and each shape added
# is another chance to call an honest coworker a liar. Also uncovered, as
# a known recall hole: the coordinated form ("Saved the note and
# published the site update") — a regex cannot tell a subjectless
# coordination from a subject three words back ("the vendor rebranded
# and launched a new page"), and the false alarm is the expensive error.
# Both prices pinned in scripts/test_a_publish_claimed_at_night.py.
_CLAIMS_A_PUBLISH_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))(?:published|deployed|launched)\b'
    r'[^.\n]{0,60}\b(?:site|page|live|update)'
    r'|\b(?:I|we)(?:[\'’]ve| have| just| also| then)?\s+'
    r'(?:published|deployed|launched)\b',
    re.IGNORECASE | re.MULTILINE)


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
    text = mask_reasoning(text)   # see mask_reasoning: thinking is not calling
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


# ── Long-term memory (night edition of hq-runtime memorySummary) ───────────
# Parity with hq-runtime.jsx MEMORY_PROMPT_CAP: the Memory panel's header
# quotes that constant ("the newest N go out with every job"), so the night
# edition must cap at the same N — a different number here makes the panel
# true about the browser and false about the night.
# scripts/test_the_night_shift_carries_the_bosss_memory.py pins both sides.
MEMORY_PROMPT_CAP = 24


def memory_summary(ctx):
    """The boss's long-term memory, byte-identical to what hq-runtime's
    memorySummary folds into every browser job's system prompt — same
    header, same `  [TAG] text` rows, same newest-MEMORY_PROMPT_CAP slice,
    read from the same file the browser persists (/hq/memory/context,
    newest-first).

    The Memory panel promises entries are "carried into every job CafresoHQ
    and the team pick up". The browser keeps that promise in agentStream for
    every job it dispatches; this is the night half — until it existed,
    every night-shift job went out cold and the panel's "every" was false
    from dusk to dawn (#142).

    Best-effort by design: the read is a localhost call to our own serve.py
    (a missing file comes back 200 + null), and memory is context for the
    work, not the work — a run that cannot load it should still research
    and file notes, not die at the door."""
    try:
        s, raw = _self_call(ctx, 'GET', '/hq/memory/context', timeout=20)
        if s != 200:
            return ''
        entries = json.loads(raw.decode('utf-8', 'replace'))
    except Exception:
        return ''
    if not isinstance(entries, list):
        return ''
    lines = []
    for m in entries[:MEMORY_PROMPT_CAP]:
        # Well-formed entries render exactly as the browser renders them;
        # a corrupt row (non-dict, or no text) is skipped rather than
        # rendered as "[None] None" noise the browser would never show.
        if isinstance(m, dict) and str(m.get('text') or '').strip():
            lines.append('  [%s] %s' % (m.get('tag'), m.get('text')))
    if not lines:
        return ''
    return ('Long-term memory (notes CafresoHQ has saved about the boss & '
            'ongoing work):\n' + '\n'.join(lines))


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
    # Same placement as the browser: agentStream folds this block into the
    # system prompt of every job it dispatches, and the Memory panel's
    # "every job" includes the ones dispatched while the boss sleeps (#142).
    mem = memory_summary(ctx)
    if mem:
        persona += '\n\n' + mem
    messages = [{'role': 'system', 'content': persona},
                {'role': 'user', 'content': prompt}]
    writes, tokens_used, reply = [], 0, ''
    # The status of a write the vault turned away. Kept because throwing it
    # away is what let a dead vault look like a quiet night: the note never
    # landed, nothing counted it, and the only surface that noticed was a
    # claim check that blamed the coworker for the office's own shut door.
    refused = None
    # Every reply, not just the last. A hop can pick up a supported tool and
    # leave an out-of-subset marker behind it in the same message —
    # find_first_tool takes the earliest match — and that reach would
    # otherwise vanish when the next hop overwrote `reply`.
    replies = []
    try:
        for _hop in range(MAX_TOOL_HOPS):
            reply, used = llm_call(ctx, messages)
            tokens_used += used
            replies.append(reply or '')
            hit = find_first_tool(reply)
            if not hit:
                break
            name, arg, body, _span = hit
            result = run_tool(ctx, name, arg, body)
            if name in ('VAULT_NEW', 'VAULT_APPEND'):
                status = vault_write_status(result)
                if status is None:
                    writes.append({'name': name, 'path': arg.strip(),
                                   'at': int(time.time() * 1000)})
                    # A later write landing clears an earlier refusal in the
                    # same iteration — `refused` gates the whole error chain
                    # below on "the vault's answer to the LAST attempt", not
                    # "did it ever say no this iteration". A flaky vault that
                    # 502s once and then accepts the retry actually saved a
                    # note; without this, that note sits in `writes` while
                    # the iteration is still reported as a vault outage, and
                    # three such iterations trip ERROR_STREAK_AUTO_PAUSE and
                    # kill the rest of the night over a fault that already
                    # cleared.
                    refused = None
                else:
                    refused = status
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'user', 'content':
                             'TOOL RESULT [%s]:\n%s\n\nContinue. Use at most one more tool, '
                             'or finish with your plain status line.' % (name, result)})
    except Exception as e:
        # Every raise reaching here is a brain-call failure (see
        # brain_cause's docstring above) — never the raw str(e), which
        # used to put a bare URL and a Python exception repr in front of
        # the boss on RECENT NIGHT RUNS / the Gazette / the CLI report.
        return {'writes': writes, 'tokens': tokens_used, 'summary': '', 'error': brain_cause(e)}
    summary = strip_unsupported_markers(reply)[-300:]
    error = None
    # Masked BEFORE the claim checks, for the same reason find_first_tool
    # and find_unsupported_tool mask before theirs: thinking is not saying.
    # A think-model drafting its status line inside <think> ("I must not
    # say 'Wrote 1' without the tool call") had the drafted sentence read
    # as a CLAIM by the unmasked regexes below — 'said it saved a note' /
    # 'said it published' about text nobody said, and three such honest
    # iterations tripped ERROR_STREAK_AUTO_PAUSE and ended the night. The
    # exact accusation shape the REASONING_TAGS block above condemns, on
    # the two readers that never got the mask.
    all_replies = mask_reasoning('\n'.join(replies))
    reached = find_unsupported_tool(all_replies)
    if refused is not None:
        # First, and ahead of the reach check that used to hold this spot,
        # because this is the only branch here resting on an observed HTTP
        # status rather than on reading the reply's prose — and because the
        # two claim checks below describe its consequences rather than its
        # cause. A coworker ordered to file, who filed, and was refused has
        # said nothing untrue; 'said it saved a note' would be the office
        # blaming them for its own shut door. Reproduced 2026-08-16 with the
        # vault pointed at a closed Obsidian REST: writes [], error 'said it
        # saved a note, nothing reached the vault', and a real [VAULT_NEW]
        # in the transcript that the vault answered 502 to.
        error = vault_refused_sentence(refused)
    elif reached:
        # Ahead of the claim checks below on purpose. All three can describe
        # one bad night, but this one names the actual cause and a door the
        # boss can walk through; "said it published" would be true and
        # useless next to it.
        error = night_cannot_sentence(reached)
    elif _CLAIMS_A_PUBLISH_RE.search(all_replies):
        # NOT gated on `writes`: a real vault note does not back a claim
        # that the SITE changed — "saved the note and published the site"
        # is still half a lie with a write in the ledger. And every hop's
        # reply, not just the last, for the same reason the marker scan
        # above reads them all: a hop that lied and a hop that reached are
        # equally absent from a final status line.
        error = 'said it published, but nothing went live'
    elif not writes and _CLAIMS_A_WRITE_RE.search(all_replies):
        # Every hop's reply, not just the last — the same scope the reach
        # scan and the publish check above already use, and for the same
        # reason they give: a hop that lied is as absent from a final
        # status line as a hop that reached. This check alone read only
        # `reply`, so a coworker that said "I saved the note to
        # Research/Night/pricing.md" in the hop that carried a
        # [VAULT_SEARCH] marker, and then closed the next hop with a
        # blameless "Next iteration could explore…", was recorded as a
        # clean night: writes [], errors 0, lastError ''. Reproduced
        # against the real run_iteration; the identical transcript with
        # "I published the pricing page update" in place of the write
        # sentence WAS caught, one branch up, because that branch reads
        # all_replies. The ledger gate is what makes the wider scope safe:
        # `not writes` means a hop that claimed early and genuinely wrote
        # later still passes silently.
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
        # 51 characters, and the CLI night report slices at 50 — so this
        # carefully-shortened sentence has been arriving as "…reached the
        # vaul". One word out; see NIGHT_ERROR_MAX, which is now checked.
        error = 'said it saved a note, nothing reached the vault'
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
        'stoppedByBoss': False,
        'summary': '',
        'grammarVersion': NIGHT_GRAMMAR_VERSION,
    }
    # Before the first brain call, not after the third. A night whose
    # deliverable has nowhere to land is not a night that went badly — it is
    # one that should not have started, and saying so at the door costs one
    # GET instead of ERROR_STREAK_AUTO_PAUSE iterations of paid tokens
    # against a vault that will refuse every one of them.
    ready, why = vault_can_take_a_note(ctx)
    if not ready:
        run['errors'] = 1
        run['lastError'] = why
        run['finishedAt'] = int(time.time() * 1000)
        return run
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
            # A flag for the XP ledger, set BEFORE the prose so nothing comes
            # between that assignment and the break (a sibling test reads the
            # sentence out of exactly that shape). The browser used to have to
            # infer this ending from `errors` -- 0 on a stop, so a cancelled
            # night was filed as a finished one and paid for -- or from
            # `lastError`, which is set here and would have docked it as a
            # snag instead. Neither is true; the boss stopped it, and §5 says
            # that is on neither side of the ledger. Nothing compares against
            # the sentence itself; that stays free to be reworded.
            run['stoppedByBoss'] = True
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

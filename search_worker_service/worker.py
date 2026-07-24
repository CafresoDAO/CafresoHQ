#!/usr/bin/env python3
"""CafresoHQ search-network worker — standalone service.

Extracted from serve.py (the CafresoHQ "HQ" monolith) so a search worker can
run on its own, minimal, stdlib-only image: no terminal/PTY, no Hermes agent
gateway, no vault, no UI. Joins the on-chain search network, claiming queued
queries from cafresohq_state over HMAC-signed plain HTTPS (Python has no IC
agent — the canister verifies HMAC-SHA256 over the raw body against the
secret registered from the browser). Pipeline per job: Brave (this instance's
own key) -> a directly-configured LLM backend -> graph snapshot -> fulfill.
Fulfilled answers become public on-chain library entries attributed (and
paid) to WORKER_PRINCIPAL.

Every function/section below is ported verbatim from serve.py's _sw_*/
_brave_*/_gap_*/_news_*/_topics_* code unless a comment says otherwise. Only
FOUR things are genuinely redesigned for standalone operation (search for
"standalone-service design" below for the full rationale):

  1. Model/backend selection no longer follows a co-located Hermes gateway's
     config.yaml (there isn't one here). It follows the SAME public canister
     config channel the gpuNode.enabled pause switch already uses
     (_operator_config()), extended with a non-secret searchWorker.{model,
     backendUrl} field an operator can publish live from the admin panel.
     WORKER_BACKEND_KEY (the real secret) is local-only, NEVER read from that
     public channel.
  2. The Hermes-agent-gateway fallback tier is gone (nothing to fall back
     to) — unresolved backend just means sources-only, same end state the
     original "no model reachable" path always had.
  3. The shared-trial-key log notice is dropped (non-critical, FYI-only).
  4. A tiny status HTTP listener replaces the two status routes that used to
     live on serve.py's main Handler (/gap/status, /news/status) — see
     _StatusHandler / main() at the bottom of this file.

Env vars:
  SEARCH_WORKER=1                    required to join the network at all
  WORKER_PRINCIPAL=<principal>       registered via ai.cafreso.com settings
  WORKER_SECRET=<64-hex secret>      shown once at registration
  BRAVE_API_KEY=<your Brave key>
  SEARCH_STATE_URL=<override>        defaults to mainnet
  WORKER_JOB_BUDGET / WORKER_IDLE_TIMEOUT / WORKER_MAX_TOKENS / WORKER_DEEP_BUDGET / WORKER_DEEP_TOPICS
  WORKER_MODEL / WORKER_BACKEND_URL / WORKER_BACKEND_KEY   local model config (see above)
  GAP_CRON / GAP_INTERVAL_MIN / GAP_PER_RUN_MAX
  NEWS_CRON / NEWS_INTERVAL_MIN / NEWS_PER_RUN_MAX
  TOPICS_CRON / TOPICS_INTERVAL_H
  CAFRESOHQ_HQ_STATE_DIR              ledger/state JSON files (default ./hq-state)
  STATUS_PORT                         status HTTP listener (default 8788)

Operational rule spanning every deployment of this image: only ONE instance
total should ever have GAP_CRON/NEWS_CRON/TOPICS_CRON enabled at a time. Each
instance keeps its own local "already asked" ledger, uncoordinated via the
canister — two instances with crons on would submit duplicate questions.
Additional/redundant instances run with SEARCH_WORKER=1 but crons off,
contributing job-claiming capacity only.
"""
import hashlib
import http.server
import json
import os
import pathlib
import re
import secrets
import socket
import socketserver
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = int(os.environ.get('STATUS_PORT', '8788') or '8788')

# ── Shared utilities — ported verbatim from serve.py (_night_load/_night_save/
# _night_path, _hq_state_dir, _operator_config + its globals). Duplicated
# rather than imported from serve.py on purpose: the whole point of this
# extraction is that the two images stop needing synchronized deploys. Keep
# behavior identical to the originals if ever touched. ───────────────────────
_hq_state_dir = pathlib.Path(os.environ.get('CAFRESOHQ_HQ_STATE_DIR',
                    os.path.join(os.path.dirname(__file__), 'hq-state')))


def _night_path(name):
    return _hq_state_dir / name


def _night_load(name, default):
    try:
        with open(_night_path(name), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _night_save(name, data):
    _hq_state_dir.mkdir(parents=True, exist_ok=True)
    tmp = _night_path(name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(tmp, _night_path(name))


_OPERATOR_BASE = os.environ.get(
    'SEARCH_STATE_URL', 'https://ydacz-riaaa-aaaal-qxeja-cai.icp0.io').rstrip('/')
_operator_cfg = {'ts': 0.0, 'data': {}}
_operator_cfg_lock = threading.Lock()


def _operator_config():
    with _operator_cfg_lock:
        if time.time() - _operator_cfg['ts'] < 60:
            return _operator_cfg['data']
    data = None
    try:
        with urllib.request.urlopen(_OPERATOR_BASE + '/operator/config.json', timeout=6) as r:
            parsed = json.loads(r.read().decode('utf-8'))
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        pass
    with _operator_cfg_lock:
        if data is not None:
            _operator_cfg['data'] = data
        _operator_cfg['ts'] = time.time()
        return _operator_cfg['data']


# ---- Ai Cafreso Search — network worker ------------------------------------
# Opt-in: this container joins the on-chain search network, claiming queued
# queries from cafresohq_state over HMAC-signed plain HTTPS (Python has no IC
# agent — the canister verifies HMAC-SHA256 over the raw body against the
# secret registered from the browser). Pipeline per job: Brave (this
# container's own key) → local LLM (hermes gateway first, night-runner
# provider fallback) → graph snapshot → fulfill. Fulfilled answers become
# public on-chain library entries attributed (and paid) to WORKER_PRINCIPAL.
#
#   SEARCH_WORKER=1
#   WORKER_PRINCIPAL=<principal registered via ai.cafreso.com settings>
#   WORKER_SECRET=<64-hex secret shown once at registration>
#   BRAVE_API_KEY=<your free Brave key>
#   SEARCH_STATE_URL=<override for local-replica testing; defaults to mainnet>
#   WORKER_JOB_BUDGET=<seconds for the whole claim→fulfill window; default 200>
#   WORKER_IDLE_TIMEOUT=<seconds of LLM silence before giving up; default 25>
#   WORKER_MAX_TOKENS=<completion cap for the answer; default 700>
#   WORKER_MODEL=<OPTIONAL override; by default search follows the operator's
#                 HQ brain picker — see _sw_model()>
#
# The model comes from the brain picker by default, deliberately: an operator
# who switches their brain in HQ expects search to follow, and a stale
# WORKER_MODEL pin pointing at a model the backend no longer has loaded fails
# EVERY job (silently, sources-only) with no hint as to why.
#
# The loop is SINGLE-THREADED by design: the canister's replay guard requires
# each worker's signed timestamps to strictly increase, which serialized calls
# guarantee for free. Workers run standalone — this loop makes only outbound
# calls and never touches the idle tracker, so it will not keep a fleet
# container awake by itself; a worker box must have idle-stop disabled.
#
# EVERY job runs against one wall-clock deadline. The canister's claim lease is
# 240s (CLAIM_LEASE_NS) and is NOT renewable — heartbeat does not touch
# claimedAt and there is no renew op. Overrunning it is silent and lossy: the
# fulfill comes back not-your-claim, the work is discarded, attempts increments,
# and three strikes fail the job for good. So Brave + LLM + graph + upload all
# have to fit inside _SW_JOB_BUDGET, which sits 40s inside the lease.
_SW_ENABLED = os.environ.get('SEARCH_WORKER', '').strip() == '1'
_SW_PRINCIPAL = os.environ.get('WORKER_PRINCIPAL', '').strip()
_SW_SECRET_HEX = os.environ.get('WORKER_SECRET', '').strip()
_SW_BASE = os.environ.get(
    'SEARCH_STATE_URL', 'https://ydacz-riaaa-aaaal-qxeja-cai.icp0.io').rstrip('/')
_SW_JOB_BUDGET = float(os.environ.get('WORKER_JOB_BUDGET', '') or 200)
_SW_TTFT_TIMEOUT = 60.0    # first token: prefill on a saturated box is slow
_SW_IDLE_TIMEOUT = float(os.environ.get('WORKER_IDLE_TIMEOUT', '') or 25)
_SW_MAX_TOKENS = int(os.environ.get('WORKER_MAX_TOKENS', '') or 700)
_SW_ANSWER_CAP = 4000      # LIB_MAX_ANSWER — the canister rejects anything longer
# Deep research (job['mode']=='deep') is now RESUMABLE: one angle gets done
# per claim, checkpointed via the 'progress' worker op, then the job rests
# (pending, not claimable) until the submitter's requested interval elapses —
# real wall-clock spacing enforced by the canister's jobNextRunAt, not by
# anything in this process. Only the LAST angle synthesises + fulfills, same
# as before. Each claim still needs a bigger wall-clock budget than a fast job
# (planning on the first claim, one Brave+note step every claim). The canister
# hands deep jobs a ~6.3-min lease (DEEP_LEASE_NS); this sits ~30s inside it,
# same margin discipline as the fast budget vs the 240s lease.
_SW_DEEP_BUDGET = float(os.environ.get('WORKER_DEEP_BUDGET', '') or 350)
_SW_DEEP_MAX_TOPICS = int(os.environ.get('WORKER_DEEP_TOPICS', '') or 5)
_SW_DEEP_PAGE_CAP = 1400   # per note-page body; the whole tree caps at LIB_MAX_GRAPH
_sw_last_ts = 0
# Serializes signed worker calls end-to-end. The canister's replay guard rejects
# any ts <= the last one it accepted, on the assumption that a worker serializes
# its calls — true when only the search loop called _sw_call, but the topics
# cron now calls it from another thread. Without this lock two threads can build
# monotonic ts values yet have their HTTP requests arrive out of order, 403-ing
# whichever loses the race. Holding the lock across build+send keeps arrival
# order == ts order.
_sw_call_lock = threading.Lock()


def _sw_left(deadline, floor=1.0):
    """Seconds until `deadline`, floored. The floor is load-bearing: urlopen
    reads timeout=0 as 'block forever', so passing a non-positive remaining
    straight through would turn a blown deadline into a hang."""
    if deadline is None:
        return None
    return max(floor, deadline - time.monotonic())




def _sw_call(op, extra_lines):
    """Signed worker call. Returns (status, dict). Envelope + HMAC per docs/SEARCH_NETWORK.md.
    Serialized across threads so ts order == arrival order (see _sw_call_lock)."""
    global _sw_last_ts
    import hmac as _hmac
    with _sw_call_lock:
        ts = max(int(time.time() * 1000), _sw_last_ts + 1)
        _sw_last_ts = ts
        body = '\n'.join(['v1', _SW_PRINCIPAL, str(ts), secrets.token_hex(8), op]
                         + list(extra_lines)).encode('utf-8')
        sig = _hmac.new(bytes.fromhex(_SW_SECRET_HEX), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(_SW_BASE + '/worker/' + op, data=body, headers={
            'x-worker-signature': sig, 'Content-Type': 'text/plain'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode('utf-8'))
            except Exception:
                return e.code, {}
        except Exception as e:
            return 0, {'error': str(e)[:200]}


# ── Brave quota ledger ──────────────────────────────────────────────────────
# Brave Search API moved to pay-as-you-go metered pricing in Feb 2026 (no more
# fixed free/base tiers): $0.003-$0.005/query, $5/mo credit auto-applied. So
# this is no longer "Brave's plan allows N queries" — it's a self-imposed
# SPEND ceiling. 3000/month is ~$15/month at the conservative (high) end of
# that per-query range, i.e. an intentional "grow the library" budget, not the
# old default-safe 1000. Its 50/s rate limit is irrelevant next to that —
# volume (now: dollars) is what binds, and nothing else in this process was
# counting it. Note the canister's searchDailyBudget is 500/day
# (main.mo:1823) = ~15,000/month, i.e. 15x this quota: that cap has never bound
# because volume is low, and it does NOT protect the key. This ledger does.
#
# Four spenders, and they are NOT equal. Priority is encoded as a reserve each
# one may not dip below, so scarcity degrades in a fixed order:
#   human  — a person is waiting. Served until the quota is gone.
#   deep   — user-requested deep research. Yields once the month is 15% left.
#   gap    — the hourly cron's machine-invented library questions. Yields at
#            35%, so it starves ahead of both human demand.
#   news   — the hourly breaking-news cron. Newest and least proven of the
#            three machine spenders, so it has the lowest priority of all:
#            yields at 40%, ahead of gap, so a slow news day never crowds out
#            gap questions and neither ever touches human/deep headroom.
# This is what "weigh human questions more" means in the only place it can be
# enforced: the budget.
_BRAVE_CAP = int(os.environ.get('BRAVE_MONTHLY_CAP', '') or 3000)
_BRAVE_RESERVE = {'human': 0.0, 'deep': 0.15, 'gap': 0.35, 'news': 0.40}
_brave_lock = threading.Lock()


def _brave_month():
    """Calendar month in UTC. If your Brave plan renews on a billing date rather
    than the 1st, this under-counts near the boundary — set BRAVE_MONTHLY_CAP
    lower to buy margin rather than trying to model the billing cycle here."""
    return time.strftime('%Y-%m', time.gmtime())


def _brave_usage():
    u = _night_load('brave-usage.json', {})
    if not isinstance(u, dict) or u.get('month') != _brave_month():
        return {'month': _brave_month(), 'used': 0, 'byKind': {}}
    return u


def _brave_remaining():
    return max(0, _BRAVE_CAP - int(_brave_usage().get('used', 0) or 0))


def _brave_spend(kind='human', n=1):
    """Reserve n queries for `kind`. True = go ahead (and it's already counted).

    Counts on RESERVE, not on success: a Brave call that 500s or times out has
    still consumed quota on their side, so counting after the fact would drift
    optimistic exactly when the key is in trouble."""
    with _brave_lock:
        u = _brave_usage()
        used = int(u.get('used', 0) or 0)
        floor = _BRAVE_CAP * _BRAVE_RESERVE.get(kind, 0.35)
        if used + n > _BRAVE_CAP - floor:
            return False
        u['used'] = used + n
        u['byKind'][kind] = int(u['byKind'].get(kind, 0) or 0) + n
        try:
            _night_save('brave-usage.json', u)
        except Exception:
            pass   # a ledger we can't persist is still better than no ceiling
        return True


def _brave_refund(kind, n):
    """Hand back reserved-but-unspent queries.

    The gap cron reserves its whole batch up front (it must — it can't submit
    questions it might not be able to pay for), but dedup and validation
    routinely drop most of them. Without this, a day that reserves 10 and
    submits 2 leaks 8 queries, and at ~240/month leaked the cron would starve
    itself against its own reserve for no work done."""
    if n <= 0:
        return
    with _brave_lock:
        u = _brave_usage()
        u['used'] = max(0, int(u.get('used', 0) or 0) - n)
        u['byKind'][kind] = max(0, int(u['byKind'].get(kind, 0) or 0) - n)
        try:
            _night_save('brave-usage.json', u)
        except Exception:
            pass


def _sw_brave(q, deadline=None, kind='human', vertical='web', extras=None):
    """This worker's own Brave key. Every row now carries the FULL harvest the
    quota paid for — description, publish date, thumbnail, favicon, extra
    snippets — and it all flows into the on-chain entry graph (deliberate
    posture change 2026-07: we pay per query, we keep what it returns; the
    old title+url-only conservatism kept discarding bought data).

    Pass extras={} to also receive the response's free-riding blocks:
    extras['faq'] (people-also-ask pairs) and extras['infobox'] (entity card),
    which cost nothing beyond the web query they ride on.

    vertical='news' hits Brave's news endpoint instead — fresh, dated,
    publisher-attributed results for time-sensitive questions. Same key, same
    monthly cap, so it spends the same lane as a web query."""
    key = os.environ.get('BRAVE_API_KEY', '').strip()
    if not key:
        return None
    if not _brave_spend(kind):
        print('[brave] %s query refused — month at %d/%d (reserve for higher '
              'priority callers)' % (kind, _brave_usage().get('used', 0), _BRAVE_CAP))
        return None
    endpoint = 'news/search' if vertical == 'news' else 'web/search'
    base = ('https://api.search.brave.com/res/v1/' + endpoint + '?q='
            + urllib.parse.quote(q) + '&count=8')
    timeout = 30 if deadline is None else min(30, _sw_left(deadline))

    def _fetch(url, t):
        req = urllib.request.Request(url, headers={
            'Accept': 'application/json', 'Accept-Encoding': 'identity',
            'X-Subscription-Token': key, 'User-Agent': 'CafresoHQ/1.0'})
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read().decode('utf-8'))

    # extra_snippets is plan-gated; a plan that lacks it may 4xx the param, so
    # fall back to the bare query rather than losing the search (and the spent
    # quota) to an optional nicety. The fallback recomputes its own timeout
    # from what's actually left on the deadline — reusing the original budget
    # for both calls could let one job's two round-trips together blow well
    # past the lease it was given.
    t0 = time.monotonic()
    try:
        data = _fetch(base + '&extra_snippets=true', timeout)
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            t_left = timeout if deadline is None else max(1, _sw_left(deadline))
            data = _fetch(base, t_left)
        else:
            raise
    untag = lambda s: re.sub(r'<[^>]+>', '', s) if isinstance(s, str) else ''
    # Web nests results under .web.results; news returns them at top level.
    rows = (data.get('results') if vertical == 'news'
            else (data.get('web') or {}).get('results')) or []
    out = []
    for x in rows[:8]:
        if not isinstance(x, dict):
            continue
        try:
            if not x.get('url'):
                continue
            desc = untag(x.get('description'))
            # News results carry an age ("2 hours ago") — prepend it so the
            # LLM can weigh recency and cite dates in the answer.
            if vertical == 'news' and x.get('age'):
                desc = '[%s] %s' % (x['age'], desc)
            # page_age is ISO ("2025-03-08T…") — keep the date; age is the
            # human string ("2 hours ago"). Either helps; ISO sorts.
            age = (x.get('page_age') or '')[:10] or (x.get('age') or '')[:40]
            out.append({'title': (x.get('title') or x['url'])[:600],
                        'url': x['url'][:600],
                        'description': desc,
                        'age': age,
                        'thumbnail': ((x.get('thumbnail') or {}).get('src') or '')[:600],
                        'favicon': ((x.get('meta_url') or {}).get('favicon') or '')[:600],
                        'snippets': [untag(s)[:300]
                                     for s in (x.get('extra_snippets') or [])[:3]]})
        except Exception as e:
            # A malformed row (unexpected type from a non-string field) used to
            # propagate all the way out of a fulfilled Brave spend, leaving the
            # job claimed with no fail/ok call sent until its lease expired —
            # skip just this row instead of losing the whole paid query.
            print('[brave] skipped a malformed result row:', str(e)[:120])
            continue
    if extras is not None:
        try:
            extras['faq'] = [
                {'q': untag(f.get('question'))[:200], 'a': untag(f.get('answer'))[:300],
                 'url': (f.get('url') or '')[:600]}
                for f in ((data.get('faq') or {}).get('results') or [])[:5]
                if f.get('question')]
            ib = ((data.get('infobox') or {}).get('results') or [{}])[0]
            if ib.get('long_desc') or ib.get('label') or ib.get('title'):
                extras['infobox'] = {
                    'label': untag(ib.get('label') or ib.get('title'))[:120],
                    'desc': untag(ib.get('long_desc'))[:400],
                    'img': (((ib.get('thumbnail') or {}).get('src')) or '')[:600],
                    'url': (ib.get('website_url') or ib.get('url') or '')[:600]}
        except Exception as e:
            print('[brave] extras parse failed (rows unaffected):', str(e)[:120])
    return out


# ── Model/backend resolution — standalone-service design ────────────────────
# No co-located Hermes agent gateway exists here (this is the standalone
# search-worker service, extracted out of the HQ monolith), so there is no
# local config.yaml to follow and no gateway to fall back to. Model/backend
# choice instead follows the SAME public canister config channel the
# gpuNode.enabled pause switch already uses (_operator_config(), above) —
# extended with a non-secret `searchWorker: {model, backendUrl}` field the
# operator can publish live from the admin panel (operator_set_config on
# cafresohq_state; see docs/AGENT_BRIEF.md for the extraction plan this came
# from). Precedence in both resolvers below matches the ORIGINAL code's own
# stated philosophy (WORKER_MODEL as "an explicit override for operators who
# deliberately want search on a different model"): an explicit local env var
# always wins over whatever's published remotely.
#
# WORKER_BACKEND_KEY is deliberately NEVER read from the remote config: that
# channel (/operator/config.json) is public and unauthenticated by design —
# any anonymous worker reads it to check gpuNode.enabled — so publishing a
# real API key through it would leak it to anyone who requests the URL. The
# key is local-only, set once per instance at deploy time.
WORKER_MODEL = os.environ.get('WORKER_MODEL', '').strip()
WORKER_BACKEND_URL = os.environ.get('WORKER_BACKEND_URL', '').strip()
WORKER_BACKEND_KEY = os.environ.get('WORKER_BACKEND_KEY', '').strip()


class _Backend:
    """Drop-in replacement for night_runner.Backend — every caller
    (_sw_llm/_sw_complete/_gap_propose/_news_propose/_topics_propose) only
    ever reads .url/.headers/.model/.provider, so this is the whole contract."""
    __slots__ = ('url', 'headers', 'model', 'provider')

    def __init__(self, url, headers, model, provider):
        self.url, self.headers, self.model, self.provider = url, headers, model, provider


def _sw_remote_search_config():
    """The non-secret {model, backendUrl} fields an operator may have
    published to the canister's public operator config — see module note
    above. {} when absent; never raises."""
    cfg = _operator_config().get('searchWorker')
    return cfg if isinstance(cfg, dict) else {}


def _sw_model():
    """Which model answers searches. Local WORKER_MODEL wins if set; else the
    operator's published searchWorker.model; else a sane default."""
    if WORKER_MODEL:
        return WORKER_MODEL
    remote = _sw_remote_search_config().get('model')
    if isinstance(remote, str) and remote.strip():
        return remote.strip()
    return 'default'


def _sw_backend():
    """The endpoint this worker calls directly. Local WORKER_BACKEND_URL wins
    if set; else the operator's published searchWorker.backendUrl; else None
    (nothing configured — callers already degrade gracefully to sources-only,
    same as the original code's "no model reachable" path)."""
    url = WORKER_BACKEND_URL or (_sw_remote_search_config().get('backendUrl') or '').strip()
    if not url:
        return None
    headers = {'Content-Type': 'application/json'}
    if WORKER_BACKEND_KEY:
        headers['Authorization'] = 'Bearer ' + WORKER_BACKEND_KEY
    return _Backend(url=url, headers=headers, model=_sw_model(), provider='direct')


def _sw_hermes_key():
    """Always empty: no co-located Hermes gateway in this standalone service.
    Kept (rather than deleted) purely so downstream dispatch code that checks
    `if key:` degrades the same way it always has — see _sw_llm/_sw_complete."""
    return 


_SW_ESCAPES = {'"': '"', '\\': '\\', '/': '/', 'b': '\b',
               'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
_SW_MIN_SALVAGE_WORDS = 3  # a salvaged sentence shorter than this isn't worth publishing


def _sw_json_str_at(t, i):
    """Scan the JSON string literal starting at t[i] == '"'.
    Returns (value, end_index, complete). complete=False means the text ran out
    mid-literal (a truncated stream) — value is then everything decoded so far,
    which is exactly what we want to keep."""
    if i >= len(t) or t[i] != '"':
        return '', i, False
    out = []
    i += 1
    while i < len(t):
        c = t[i]
        if c == '"':
            return ''.join(out), i + 1, True
        if c != '\\':
            out.append(c)
            i += 1
            continue
        # Escape: needs at least one more char, \u needs four more.
        if i + 1 >= len(t):
            break
        e = t[i + 1]
        if e == 'u':
            if i + 5 >= len(t):
                break                       # cut inside \uXXXX — keep what we have
            try:
                out.append(chr(int(t[i + 2:i + 6], 16)))
            except ValueError:
                out.append(t[i + 2:i + 6])  # malformed \u — pass through, never raise
            i += 6
        else:
            out.append(_SW_ESCAPES.get(e, e))
            i += 2
    return ''.join(out), len(t), False


def _sw_salvage_json(t):
    """Best-effort (summary, notes) from possibly-truncated JSON.

    Targeted scanning, NOT general repair — brace-balancing mis-repairs
    silently. This works because the prompt pins "summary" FIRST: a stream cut
    anywhere inside "notes" still yields a complete summary, which is the
    artifact that actually matters. Returns (None, None) when there's no
    "summary" key at all, so the caller can fall through to plain text."""
    ks = t.find('"summary"')
    if ks < 0:
        return None, None
    vs = t.find('"', ks + len('"summary"'))
    if vs < 0:
        return None, None
    summary, end, complete = _sw_json_str_at(t, vs)
    summary = summary.strip()
    if not complete:
        # Library entries are permanent and public, so only publish a truncated
        # summary if a WHOLE sentence survived: trim back to the last boundary,
        # and if there wasn't one, a half-thought like "ICP i" is worse than no
        # answer — degrade to source-only and let the entry be honestly
        # summary-less. Applies to truncated text ONLY; a model that
        # deliberately returns one terse complete sentence keeps it.
        cut = max(summary.rfind('.'), summary.rfind('!'), summary.rfind('?'))
        if cut <= 0:
            return None, None
        summary = summary[:cut + 1]
        if len(summary.split()) < _SW_MIN_SALVAGE_WORDS:
            return None, None
        return summary, {}
    notes = {}
    kn = t.find('"notes"', end)
    if kn < 0:
        return (summary or None), notes
    i = t.find('{', kn)
    if i < 0:
        return (summary or None), notes
    i += 1
    while i < len(t):
        ks = t.find('"', i)
        if ks < 0:
            break
        # A '}' before the next key means the notes object closed — stop here
        # rather than reading keys from whatever follows it.
        close = t.find('}', i)
        if close >= 0 and close < ks:
            break
        key, i, ok = _sw_json_str_at(t, ks)
        if not ok:
            break                            # truncated key — nothing usable past here
        vs = t.find('"', i)
        if vs < 0:
            break
        val, i, ok = _sw_json_str_at(t, vs)
        if not ok:
            break                            # truncated value — drop this partial note
        try:
            notes[int(key) - 1] = val.strip()[:200]
        except (ValueError, TypeError):
            pass
    return (summary or None), notes


def _sw_parse_analysis(text):
    """Parse the model's {"summary", "notes"} JSON; degrade to plain text.
    Returns (summary, notes) where notes maps 0-based source index → blurb.

    Three tiers: strict parse (well-formed output) → salvage (stream truncated
    by the deadline) → raw text."""
    t = (text or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    m = re.search(r'\{.*\}', t, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            summary = str(d.get('summary') or '').strip()
            notes = {}
            for k, v in (d.get('notes') or {}).items():
                try:
                    notes[int(k) - 1] = str(v).strip()[:200]
                except (ValueError, TypeError):
                    pass
            if summary:
                return summary, notes
        except Exception:
            pass
    summary, notes = _sw_salvage_json(t)
    if summary:
        return summary, notes or {}
    if t.startswith('{') or '"summary"' in t:
        # It was trying to be our JSON and nothing usable survived. Returning the
        # raw text here would publish a broken `{"summary": "ICP i` fragment as
        # the permanent public answer — an empty answer degrades to source-only,
        # which is honest.
        return '', {}
    return t, {}


def _sw_fmt_tokens(n):
    return '%.1fk' % (n / 1000.0) if n >= 1000 else str(n)


def _sw_settimeout(resp, secs):
    """Re-bound an open response's socket. Reaches through private API
    (fp.raw._sock), so it's best-effort by design: on failure the socket keeps
    the coarser timeout from urlopen, which still bounds us — just less tightly.
    Never raises."""
    try:
        fp = getattr(resp, 'fp', None)
        s = getattr(getattr(fp, 'raw', None), '_sock', None) or getattr(fp, '_sock', None)
        if s is not None:
            s.settimeout(secs)
            return True
    except Exception:
        pass
    return False


def _sw_chat(url, headers, payload, deadline, stream=True, usage_opt=True):
    """One OpenAI-compatible chat call → (text, model, tokens, truncated).

    Streams by default so a slow backend yields a PARTIAL answer at the deadline
    instead of nothing. Raises on hard failure (connection refused, HTTP error,
    zero content) so the caller can try the next backend; returns whatever
    arrived when the wall clock or the idle timer fires."""
    body = dict(payload)
    if stream:
        body['stream'] = True
        if usage_opt:
            # usage is omitted from streamed responses unless asked for explicitly.
            body['stream_options'] = {'include_usage': True}
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers)
    # Open with the WHOLE remaining budget, not the TTFT bound. A blocking
    # gateway withholds headers until generation finishes, so a TTFT-bounded open
    # would kill a healthy 100s blocking generation with 140s still on the clock.
    # Streaming costs nothing here — SSE headers land immediately — and its
    # tighter TTFT/idle bounds go on the socket below, where they belong. If the
    # socket isn't reachable those bounds degrade to this one: coarser, but the
    # deadline still holds and we still salvage.
    r = urllib.request.urlopen(req, timeout=_sw_left(deadline) or (_SW_TTFT_TIMEOUT * 3))
    try:
        # Backward-compat gate: a gateway that ignored `stream` just sends JSON.
        # Read it as a blocking response — no exception, no retry, no wasted decode.
        if 'text/event-stream' not in (r.headers.get('Content-Type') or ''):
            data = json.loads(r.read().decode('utf-8'))
            text = data['choices'][0]['message']['content']
            tokens = int((data.get('usage') or {}).get('total_tokens') or 0)
            return text, data.get('model') or '', tokens, False

        # Streaming: bound the FIRST token by TTFT (prefill on a saturated box is
        # slow but not unbounded), then tighten to the idle timeout once tokens
        # are flowing. Best-effort — see _sw_sock.
        _sw_settimeout(r, _SW_TTFT_TIMEOUT)
        chunks, model, tokens, deltas, truncated = [], '', 0, 0, False
        while True:
            if deadline is not None and time.monotonic() > deadline:
                truncated = True
                break
            try:
                line = r.readline()
            except (socket.timeout, TimeoutError):
                truncated = True          # backend went quiet — keep what we have
                break
            if not line:
                break
            line = line.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            model = obj.get('model') or model
            usage = obj.get('usage')
            if usage:
                tokens = int(usage.get('total_tokens') or 0)
            for ch in (obj.get('choices') or []):
                piece = (ch.get('delta') or {}).get('content')
                if piece:
                    chunks.append(piece)
                    deltas += 1
                    if deltas == 1:
                        # First token is in: tighten from the prefill bound to
                        # the idle bound so a mid-stream stall aborts fast.
                        _sw_settimeout(r, _SW_IDLE_TIMEOUT)
        text = ''.join(chunks)
        if not text:
            raise RuntimeError('empty stream')
        # A truncated stream never carries the final usage chunk, so fall back to
        # the delta count. That's completion-only (excludes prefill) and so
        # UNDER-reports — deliberate: the chip says "~", and guessing a prompt
        # estimate to close the gap would be inventing numbers.
        return text, model, (tokens or deltas), truncated
    finally:
        try:
            r.close()          # drop a slow socket rather than leak it into the next job
        except Exception:
            pass


# (stream, usage_opt, schema) — richest first. response_format is dropped LAST
# because it's the rung that carries real value: it's what makes a note per
# source structurally required rather than a polite request.
_SW_ATTEMPTS = ((True, True, True), (True, False, True),
                (True, False, False), (False, False, False))
_SW_CAPS = {}          # url → index of the last rung that worked


def _sw_stream_or_block(url, headers, payload, deadline):
    """_sw_chat with a graceful climb-down for backends that reject a param.

    A 4xx means the backend dislikes something we sent, so retry smaller. A 5xx
    means the backend itself is unhappy and re-sending the same work won't help
    — raise so the caller moves on.

    The per-url memo is what makes a 4-rung ladder affordable: a backend that
    hates response_format costs ONE wasted round-trip per process, not one per
    job. A 4xx carries no decode, so even uncached the cost is milliseconds."""
    start = _SW_CAPS.get(url, 0)
    for i in range(start, len(_SW_ATTEMPTS)):
        stream, usage_opt, schema = _SW_ATTEMPTS[i]
        body = dict(payload)
        if not schema:
            body.pop('response_format', None)
        try:
            out = _sw_chat(url, headers, body, deadline, stream=stream, usage_opt=usage_opt)
            _SW_CAPS[url] = i
            return out
        except urllib.error.HTTPError as e:
            if not (400 <= e.code < 500) or i == len(_SW_ATTEMPTS) - 1:
                raise      # 5xx, or the last rung 4xx'd — genuinely broken
            dropped = ('stream_options' if usage_opt else
                       'response_format' if schema else 'stream')
            print('[search-worker] backend rejected %s (%s) — climbing down' % (dropped, e.code))
    raise RuntimeError('unreachable')


def _sw_schema(n):
    """Strict json_schema for the {summary, notes} answer.

    Two deliberate choices:
    - `summary` is FIRST in properties. Constrained decoders emit in schema
      order, and _sw_salvage_json depends on summary-before-notes to rescue a
      deadline-truncated answer.
    - notes enumerates keys "1".."N" with `required` rather than a typed
      additionalProperties. OpenAI-flavoured strict mode REJECTS a typed
      additionalProperties, and `required` makes a note per source structurally
      mandatory instead of a polite request the model may ignore (observed:
      gpt-oss-20b dropping notes and blowing the word budget on some prompts).
    """
    keys = [str(i + 1) for i in range(n)]
    return {'type': 'json_schema', 'json_schema': {
        'name': 'search_analysis', 'strict': True,
        'schema': {'type': 'object', 'properties': {
            'summary': {'type': 'string'},
            'notes': {'type': 'object',
                      'properties': {k: {'type': 'string'} for k in keys},
                      'required': keys, 'additionalProperties': False}},
            'required': ['summary', 'notes'], 'additionalProperties': False}}}


_SW_STOP = frozenset(('the', 'and', 'for', 'are', 'was', 'were', 'what', 'which',
                      'who', 'how', 'why', 'when', 'where', 'this', 'that', 'with',
                      'from', 'into', 'does', 'did', 'has', 'have', 'can', 'you'))


def _sw_focus(desc, q, max_chars=220):
    """Keep only the query-relevant sentence(s) of a Brave description.

    Decode dominates the job budget, but prefill isn't free either, and a
    saturated box feels every token. This only ever NARROWS text that was
    already prompt-only, so the Brave-ToS posture is unchanged: descriptions
    still never leave this function's caller, and graph notes stay the LLM's
    own words."""
    d = (desc or '').strip()
    if len(d) <= max_chars:
        return d
    terms = set(w for w in re.findall(r'[a-z0-9]+', q.lower())
                if len(w) > 2 and w not in _SW_STOP)
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', d) if s.strip()]
    if not terms or not sents:
        return d[:max_chars]
    scored = sorted(((sum(1 for w in terms if w in s.lower()), -i, s)
                     for i, s in enumerate(sents)), reverse=True)
    if scored[0][0] == 0:
        return d[:max_chars]          # nothing matched (synonyms only) — take the head
    keep, out = [], 0
    for score, negi, s in scored[:2]:  # 2 not 1: cheap hedge against a mis-scored pick
        if score == 0 or out + len(s) > max_chars:
            break
        keep.append((-negi, s))
        out += len(s)
    if not keep:
        return d[:max_chars]
    return ' '.join(s for _, s in sorted(keep))


def _sw_llm(q, results, deadline=None):
    """(answer, model, notes, tokens) via the local hermes gateway, falling
    back to the night-runner provider config. Empty values when no model is
    reachable — sources + graph are still worth fulfilling."""
    def _src_block(i, r):
        # Date + extra snippets when the harvest carried them: dated sources
        # let the model cite "as of March 2025" instead of hedging, and the
        # snippets are more page text for the same Brave query.
        head = '[%d] %s%s' % (i + 1, r['title'],
                              (' (%s)' % r['age']) if r.get('age') else '')
        parts = [head, r['url'], _sw_focus(r['description'], q)]
        parts += (r.get('snippets') or [])[:2]
        return '\n'.join(p for p in parts if p)
    src = '\n\n'.join(_src_block(i, r) for i, r in enumerate(results))
    # "summary" MUST come first and the prompt must say so: the salvage parser
    # in _sw_parse_analysis relies on it, so a stream the deadline cuts short
    # still yields a complete summary and merely loses some notes. Field order
    # here is load-bearing, not cosmetic.
    prompt = (
        'You are a research summarizer. Use ONLY the numbered sources below.\n'
        '"summary": 2-3 sentences, 60 words MAX total, on what the sources '
        'collectively say about the query, citing like [1][3]. If they do not '
        'answer it, say what they DO cover.\n'
        '"notes": for each source number, at most 12 words in your own words on '
        'what that page contributes. Do not copy phrases from the source text.\n'
        'Output STRICT JSON only — no prose, no code fence, "summary" first:\n'
        '{"summary": "...", "notes": {"1": "...", "2": "..."}}\n\n'
        'Query: %s\n\nSources:\n%s' % (q, src))
    want = _sw_model()
    payload = {'model': want,
               'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': _SW_MAX_TOKENS,
               'response_format': _sw_schema(len(results))}

    def _finish(text, rmodel, tokens, truncated, via):
        """No gateway path in this service (see _sw_hermes_key) — the direct
        backend's reported model name is always trustworthy, unlike the old
        gateway path which echoed the requested name while running whatever
        config.yaml said."""
        summary, notes = _sw_parse_analysis(text)
        if truncated:
            print('[search-worker] %s truncated at deadline — salvaged %d chars, %d notes'
                  % (via, len(summary or ''), len(notes)))
        actual = rmodel or want
        if actual and want and actual.split('/')[-1] != want.split('/')[-1]:
            print('[search-worker] asked for %s but %s answered as %s — the chip reports what '
                  'actually ran' % (want, via, actual))
        # A salvaged partial IS success: falling through would trade a usable
        # summary for a second full decode we can't afford inside the lease.
        return summary, (actual or via)[:80], notes, tokens

    # Direct to the operator's configured brain — see _sw_backend(). No agent
    # gateway in this service, so no fallback tier: unresolved means
    # sources-only, same end state the original gateway-absent path had.
    b = _sw_backend()
    if b is not None:
        try:
            text, rmodel, tokens, truncated = _sw_stream_or_block(
                b.url, b.headers, dict(payload, model=b.model or want), deadline)
            return _finish(text, rmodel, tokens, truncated, b.provider or 'direct')
        except Exception as e:
            print('[search-worker] direct backend failed (provider=%s url=%s model=%s): %s'
                  % (b.provider, b.url, b.model or want, str(e)[:120]))
    else:
        print('[search-worker] no backend configured (WORKER_BACKEND_URL or the '
              'operator-published searchWorker.backendUrl) — answers will be sources-only')

    # Sources + graph are still worth fulfilling.
    return '', '', {}, 0


_SW_PALETTE = ['#7DC9B0', '#C9B8E0', '#E8A9A9', '#F0C987',
               '#9BC0E8', '#B8E09A', '#E0A47C', '#D89BE0']


def _sw_domain(u):
    try:
        return (urllib.parse.urlparse(u).hostname or u).replace('www.', '', 1)
    except Exception:
        return u


def _sw_color(name):
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _SW_PALETTE[h % len(_SW_PALETTE)]


def _sw_graph(q, results, notes=None, extras=None):
    """Query hub → result ring → domain ring, wrapped exactly as
    graph-viewer.html expects. Result nodes carry url/domain/note attributes
    so the viewer can render hover cards and click-through — plus the full
    Brave harvest (age/img/snippet, favicons on domains) since the 2026-07
    keep-what-we-paid-for posture change. The graphJson blob is the schema-free
    seam: everything here lands on-chain through the existing library_put.

    extras (from _sw_brave): 'faq' becomes faint kind:'suggest' ghost nodes —
    questions the web says people also ask, which the viewer renders as an
    exploration frontier around the answer; 'infobox' becomes one kind:'entity'
    card node. Both are visual-only: reducers ignore unknown kinds gracefully,
    so old viewers just show them as plain nodes."""
    import math
    notes = notes or {}
    extras = extras or {}
    nodes = [{'key': 'q', 'attributes': {'label': q, 'size': 18, 'x': 0, 'y': 0,
                                         'color': '#F5D25D', 'kind': 'query'}}]
    edges = []
    domains = {}
    domicon = {}
    for i, r in enumerate(results):
        a = (i / max(1, len(results))) * math.pi * 2
        d = _sw_domain(r['url'])
        at = {'label': r['title'][:60], 'size': 8,
              'x': math.cos(a) * 10, 'y': math.sin(a) * 10,
              'color': _sw_color(d), 'kind': 'source',
              'url': r['url'][:600], 'domain': d,
              'note': (notes.get(i) or '')[:200]}
        if r.get('age'):
            at['age'] = r['age']
        if r.get('thumbnail'):
            at['img'] = r['thumbnail']
        if r.get('description'):
            at['snippet'] = r['description'][:240]
        nodes.append({'key': 'r%d' % i, 'attributes': at})
        edges.append({'key': 'eq%d' % i, 'source': 'q', 'target': 'r%d' % i, 'attributes': {}})
        domains.setdefault(d, []).append(i)
        if r.get('favicon') and d not in domicon:
            domicon[d] = r['favicon']
    for di, (d, ixs) in enumerate(domains.items()):
        a = (di / max(1, len(domains))) * math.pi * 2 + 0.35
        at = {'label': d, 'size': 5 + len(ixs),
              'x': math.cos(a) * 17, 'y': math.sin(a) * 17, 'color': _sw_color(d),
              'kind': 'domain', 'domain': d}
        if domicon.get(d):
            at['favicon'] = domicon[d]
        nodes.append({'key': 'd:' + d, 'attributes': at})
        for i in ixs:
            edges.append({'key': 'ed%d_%d' % (di, i), 'source': 'r%d' % i,
                          'target': 'd:' + d, 'attributes': {}})
    faqs = (extras.get('faq') or [])[:5]
    for si, f in enumerate(faqs):
        a = (si / max(1, len(faqs))) * math.pi * 2 + 0.8
        at = {'label': f['q'][:90], 'size': 6,
              'x': math.cos(a) * 25, 'y': math.sin(a) * 25,
              'color': '#9C8F6E', 'kind': 'suggest', 'suggest': 1}
        if f.get('a'):
            at['snippet'] = f['a'][:200]
        nodes.append({'key': 's%d' % si, 'attributes': at})
        edges.append({'key': 'es%d' % si, 'source': 'q', 'target': 's%d' % si, 'attributes': {}})
    ib = extras.get('infobox')
    if ib and (ib.get('label') or ib.get('desc')):
        at = {'label': (ib.get('label') or 'About')[:90], 'size': 11,
              'x': 0, 'y': -14, 'color': '#C9B8E0', 'kind': 'entity'}
        if ib.get('desc'):
            at['snippet'] = ib['desc'][:280]
        if ib.get('img'):
            at['img'] = ib['img']
        if ib.get('url'):
            at['url'] = ib['url']
        nodes.append({'key': 'ib', 'attributes': at})
        edges.append({'key': 'eib', 'source': 'q', 'target': 'ib', 'attributes': {}})
    return json.dumps({'graph': {'options': {'type': 'mixed', 'multi': False,
                                             'allowSelfLoops': True},
                                 'attributes': {}, 'nodes': nodes, 'edges': edges},
                       'title': 'Search: ' + q, 'ts': int(time.time() * 1000)})


# ── Deep research (job['mode']=='deep') ─────────────────────────────────────
# The fast path is one Brave search + one summarising LLM call. Deep research is
# the HQ "Kip" pattern ported into the worker: decompose the question into
# angles, then for each angle run its own Brave search and write a synthesised
# NOTE PAGE, then write a top-level synthesis over the pages. The output is a
# research TREE (query → topics → sources) plus the note pages, which the viewer
# lets a reader click through. It spends the reserved `deep` Brave lane.
#
# RESUMABLE: one angle per claim (see _sw_deep_step), checkpointed via the
# 'progress' worker op and resumed on a later claim after the submitter's
# requested interval — see _sw_process_deep for the checkpoint/fulfill split.

def _sw_json_obj(text):
    """First JSON object/array in possibly code-fenced model text, or None.
    Deep steps ask for small JSON; this is the lenient extractor (the fast path
    keeps its own truncation-salvage parser, which deep steps don't need)."""
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
    m = re.search(r'(\{.*\}|\[.*\])', t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _sw_complete(prompt, deadline, max_tokens=600, schema=None):
    """One free-form completion via the operator's configured brain (see
    _sw_backend() -- no agent gateway in this service), without the fixed
    summary/notes schema _sw_llm uses. Returns (text, model, tokens, via);
    ('','',0,'') when nothing is reachable so the caller can degrade."""
    want = _sw_model()
    payload = {'model': want,
               'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': max_tokens}
    if schema is not None:
        payload['response_format'] = schema
    b = _sw_backend()
    if b is not None:
        try:
            text, rmodel, tokens, _tr = _sw_stream_or_block(
                b.url, b.headers, dict(payload, model=b.model or want), deadline)
            return text, (rmodel or want), tokens, (b.provider or 'direct')
        except Exception as e:
            print('[deep] direct backend failed: %s' % str(e)[:120])
    return '', '', 0, ''


def _sw_deep_plan(q, deadline, max_topics=None):
    """Decompose the question into distinct, independently-searchable angles.
    max_topics overrides the operator default (_SW_DEEP_MAX_TOPICS) — this is
    the submitter's requested depth, already capped server-side by the
    canister (DEEP_MAX_TOPICS_USER) before it ever reaches here."""
    topics = max_topics if max_topics else _SW_DEEP_MAX_TOPICS
    prompt = (
        'You are planning a research report that will thoroughly answer a '
        'question. Break it into %d DISTINCT, focused sub-questions ("angles") '
        'that together cover the topic — e.g. background, mechanism, evidence, '
        'trade-offs, current state. Each must be independently searchable on the '
        'open web.\nOutput STRICT JSON only: {"angles": ["...", "..."]}\n\n'
        'Question: %s' % (topics, q))
    text, model, tokens, _via = _sw_complete(prompt, deadline, max_tokens=400)
    obj = _sw_json_obj(text) or {}
    angles = obj.get('angles') if isinstance(obj, dict) else obj
    out = []
    for a in (angles or []):
        a = str(a).strip()
        if a and a not in out and len(out) < topics:
            out.append(a[:200])
    return out, model, tokens


def _sw_deep_note(q, angle, results, deadline):
    """Write one research note page from an angle's sources.
    Returns (title, body, model, tokens)."""
    src = '\n\n'.join('[%d] %s\n%s\n%s' % (i + 1, r['title'], r['url'],
                                           _sw_focus(r['description'], angle))
                      for i, r in enumerate(results))
    prompt = (
        'You are writing ONE section of a research report.\n'
        'The report answers: %s\n'
        'This section covers: %s\n'
        'Using ONLY the numbered sources, write a focused note of 100-160 words '
        'in your OWN words, opening with a one-line takeaway and citing sources '
        'inline like [1][3]. Do not copy phrases from the sources.\n'
        'Output STRICT JSON only: {"title": "3-6 word section title", '
        '"body": "the note with [n] citations"}\n\nSources:\n%s'
        % (q, angle, src))
    text, model, tokens, _via = _sw_complete(prompt, deadline, max_tokens=500)
    obj = _sw_json_obj(text)
    if isinstance(obj, dict) and str(obj.get('body') or '').strip():
        title = str(obj.get('title') or angle)[:80]
        body = str(obj['body']).strip()[:_SW_DEEP_PAGE_CAP]
    else:
        # Degrade: keep the raw prose as the body rather than losing the work.
        title = angle[:80]
        body = (text or '').strip()[:_SW_DEEP_PAGE_CAP]
    return title, body, model, tokens


def _sw_deep_synth(q, pages, deadline):
    """Top-level synthesis over the note pages. Returns (answer, model, tokens)."""
    joined = '\n\n'.join('## %s\n%s' % (p['title'], p['body']) for p in pages)
    prompt = (
        'You are writing the executive summary of a research report.\n'
        'Question: %s\n'
        'Below are the report sections. Write a cohesive 80-130 word synthesis '
        'that directly answers the question, weaving the sections together. '
        'Plain prose — no JSON, no headings, no citations markup.\n\n'
        'Sections:\n%s' % (q, joined))
    text, model, tokens, _via = _sw_complete(prompt, deadline, max_tokens=500)
    return (text or '').strip()[:_SW_ANSWER_CAP], model, tokens


def _sw_deep_graph(q, pages):
    """Research tree wrapped for graph-viewer.html: query hub → topic nodes →
    source nodes. Topic nodes carry a `page` attribute (the note-page id) so the
    viewer opens the note on click instead of linking out; source nodes keep the
    url/domain/note attributes and click through to the source."""
    import math
    nodes = [{'key': 'q', 'attributes': {'label': q[:60], 'size': 20, 'x': 0, 'y': 0,
                                         'color': '#F5D25D', 'kind': 'query'}}]
    edges = []
    n = max(1, len(pages))
    for ti, p in enumerate(pages):
        ta = (ti / n) * math.pi * 2
        tk = p['id']
        nodes.append({'key': tk, 'attributes': {
            'label': p['title'][:60], 'size': 12,
            'x': math.cos(ta) * 12, 'y': math.sin(ta) * 12,
            'color': '#C9B8E0', 'kind': 'topic',
            'page': p['id'], 'note': (p.get('question') or '')[:200]}})
        edges.append({'key': 'eq_%s' % tk, 'source': 'q', 'target': tk, 'attributes': {}})
        srcs = p.get('sources') or []
        for si, r in enumerate(srcs):
            sa = ta + (si - (len(srcs) - 1) / 2.0) * 0.16
            sk = '%s_r%d' % (tk, si)
            d = _sw_domain(r['url'])
            nodes.append({'key': sk, 'attributes': {
                'label': r['title'][:60], 'size': 6,
                'x': math.cos(sa) * 22, 'y': math.sin(sa) * 22,
                'color': _sw_color(d), 'kind': 'source',
                'url': r['url'][:600], 'domain': d, 'note': (r.get('note') or '')[:200]}})
            edges.append({'key': 'e_%s' % sk, 'source': tk, 'target': sk, 'attributes': {}})
    return json.dumps({'graph': {'options': {'type': 'mixed', 'multi': False,
                                             'allowSelfLoops': True},
                                 'attributes': {}, 'nodes': nodes, 'edges': edges},
                       'title': 'Deep research: ' + q, 'ts': int(time.time() * 1000)})


def _sw_deep_step(q, deadline, progress_in, max_topics):
    """Advance a resumable deep-research job by exactly ONE angle — one
    checkpoint per claim, so 'iterations' in the UI map 1:1 to real angles
    attempted, each spaced by the submitter's requested interval (enforced by
    the canister's jobNextRunAt, not by anything in this process).

    progress_in: the dict from a prior 'progress' checkpoint (angles, pages,
    nextAngle, tokens, model), or None on a job's first claim, which plans the
    angle list fresh. Returns {'angles','pages','tokens','model','nextAngle',
    'done'} or None to signal the caller should degrade to a single-shot
    answer (planning failed, or nothing usable was ever produced)."""
    if progress_in:
        angles = progress_in.get('angles') or []
        pages = progress_in.get('pages') or []
        tokens = progress_in.get('tokens') or 0
        model_seen = progress_in.get('model') or ''
        next_i = progress_in.get('nextAngle', len(pages))
    else:
        angles, model_seen, pt = _sw_deep_plan(q, deadline, max_topics)
        if not angles:
            return None                       # planning failed → degrade
        print('[deep] %s → %d angles (requested topics=%s)'
              % (q[:60], len(angles), max_topics or _SW_DEEP_MAX_TOPICS))
        pages, tokens, next_i = [], pt, 0

    if next_i < len(angles) and _sw_left(deadline) >= 45:
        angle = angles[next_i]
        results = _sw_brave(angle, deadline, kind='deep')
        if results:
            title, body, nmodel, nt = _sw_deep_note(q, angle, results, deadline)
            tokens += nt
            model_seen = nmodel or model_seen
            pages.append({'id': 't%d' % len(pages), 'title': title, 'question': angle,
                          'body': body, 'ranAt': int(time.time() * 1000),
                          'sources': [{'title': r['title'], 'url': r['url'], 'note': ''}
                                      for r in results]})
        else:
            # No results for this angle — still a real, receipt-worthy
            # iteration. Recorded (empty body/sources) rather than silently
            # skipped, so the reader can see what was tried and came up dry.
            pages.append({'id': 't%d' % len(pages), 'title': angle, 'question': angle,
                          'body': '', 'ranAt': int(time.time() * 1000), 'sources': []})
        next_i += 1
    if not pages:
        return None                           # nothing usable yet → degrade
    return {'angles': angles, 'pages': pages, 'tokens': tokens, 'model': model_seen,
            'nextAngle': next_i, 'done': next_i >= len(angles)}


def _sw_process_deep(job, jid, q, deadline, started, P):
    """Deep-research checkpoint/fulfill. Returns True if this claim handled the
    job (either checkpointed a mid-run angle via 'progress', or terminally
    fulfilled it), False to let the caller fall back to a single-shot answer.

    Reads job['progress'] (JSON from an earlier checkpoint, '' on a job's
    first claim) and job['topics'] (the submitter's requested angle count,
    '' = use the operator default) — both come straight off the canister's
    claim response, already validated/capped server-side."""
    progress_raw = job.get('progress') or ''
    progress_in = None
    if progress_raw:
        try:
            progress_in = json.loads(progress_raw)
        except Exception:
            progress_in = None       # corrupt/unexpected → replan rather than crash
    topics_raw = str(job.get('topics') or '')
    max_topics = int(topics_raw) if topics_raw.isdigit() and int(topics_raw) > 0 else None

    print('[deep] claimed %s: %s%s' % (jid, q[:80], ' (resuming)' if progress_in else ''))
    state = _sw_deep_step(q, deadline, progress_in, max_topics)
    if state is None:
        return False

    if not state['done']:
        progress_json = json.dumps({
            'angles': state['angles'], 'pages': state['pages'],
            'nextAngle': state['nextAngle'], 'tokens': state['tokens'],
            'model': state['model']})
        status, resp = _sw_call('progress', [jid, P(progress_json)])
        if status == 200 and resp.get('ok'):
            print('[deep] %s checkpoint: %d/%d angles (%.0fs)'
                  % (jid, state['nextAngle'], len(state['angles']), time.monotonic() - started))
        else:
            print('[deep] progress rejected %s: %s %s' % (jid, status, resp))
        return True

    # Last angle just landed — synthesize + graph + terminal fulfill, exactly
    # like a single-shot deep run always has (this code is unchanged from
    # before resumability; only how `pages` got built above it is new).
    pages = state['pages']
    model, tokens = state['model'], state['tokens']
    if not any(p['body'] for p in pages):
        # Every single angle came up dry across the whole run — a real,
        # receipt-worthy outcome per angle, but nothing to synthesize or
        # publish. Fail the job rather than fulfilling an empty answer.
        _sw_call('fail', [jid, P('every angle returned no results')])
        print('[deep] %s: all %d angles empty — failed, not fulfilled' % (jid, len(pages)))
        return True
    answer, smodel, st = _sw_deep_synth(q, pages, deadline)
    tokens += st
    model = smodel or model
    if not answer:
        # Synthesis failed: stitch each page's opening sentence as the answer.
        answer = ' '.join(p['body'].split('.')[0].strip() + '.'
                          for p in pages if p['body'])[:_SW_ANSWER_CAP]
    graph = _sw_deep_graph(q, pages)
    if tokens:
        model = ('%s · ~%s tok' % (model or 'local', _sw_fmt_tokens(tokens)))[:80]
    if len(answer) > _SW_ANSWER_CAP:
        answer = answer[:_SW_ANSWER_CAP]
    # Dedupe sources across pages for the entry's flat source list, capped at
    # LIB_MAX_SOURCES (10) — the canister rejects more. The FULL per-angle source
    # set is preserved in the research tree (graph) and note pages, which are
    # bounded only by LIB_MAX_GRAPH.
    seen, sources = set(), []
    for p in pages:
        for r in (p.get('sources') or []):
            if r['url'] not in seen:
                seen.add(r['url'])
                sources.append(r)
    sources = sources[:10]
    pages_json = json.dumps({
        'q': q, 'answer': answer,
        'pages': [{'id': p['id'], 'title': p['title'], 'question': p['question'],
                   'body': p['body'], 'sources': p['sources'], 'ranAt': p.get('ranAt')}
                  for p in pages],
        'ts': int(time.time() * 1000)})
    # Deep fulfill == fast fulfill + one trailing pages field. `brave · deep`
    # marks provenance (renders wherever the engine chip does); the canister
    # tags the job mode itself, this is the human-readable echo.
    lines = [jid, P(model), P('brave · deep'), P(answer), str(len(sources))]
    for r in sources:
        lines.append('%s %s' % (P(r['title']), P(r['url'])))
    lines.append(P(graph))
    lines.append(P(pages_json))
    status, resp = _sw_call('fulfill', lines)
    if status == 200 and resp.get('ok'):
        print('[deep] fulfilled %s -> %s (%d pages, %.0fs)'
              % (jid, resp.get('libraryId'), len(pages), time.monotonic() - started))
    else:
        print('[deep] fulfill rejected %s: %s %s' % (jid, status, resp))
    return True


def _sw_process(job, deadline=None):
    jid, q = job['id'], job['q']
    mode = job.get('mode') or 'fast'
    started = time.monotonic()
    P = lambda s: urllib.parse.quote(s, safe='')
    try:
        if mode == 'deep':
            # Deep can degrade to the single-shot path below (planning/notes/
            # Brave all failed) so the user still gets an answer within the lease.
            if _sw_process_deep(job, jid, q, deadline, started, P):
                return
            print('[deep] %s: degrading to single-shot' % jid)
        print('[search-worker] claimed %s: %s%s' % (jid, q[:80], ' [news]' if mode == 'news' else ''))
        extras = {}
        results = _sw_brave(q, deadline, vertical='news' if mode == 'news' else 'web',
                            extras=extras)
        if mode == 'news' and not results:
            # News vertical came up dry (niche query, no coverage) — a web
            # answer beats a fail; the engine chip below still says how we got it.
            results = _sw_brave(q, deadline, extras=extras)
        if not results:
            # Three different failures used to share one message. They need
            # different operator responses — top up the plan, set the key, or
            # nothing at all — so say which one it is.
            has_key = bool(os.environ.get('BRAVE_API_KEY', '').strip())
            why = ('brave month exhausted (%d/%d)' % (_brave_usage().get('used', 0), _BRAVE_CAP)
                   if has_key and not _brave_remaining()
                   else 'no brave key' if not has_key else 'no results')
            print('[search-worker] %s: %s' % (jid, why))
            _sw_call('fail', [jid, P(why)])
            return
        answer, model, notes, tokens = _sw_llm(q, results, deadline)
        if tokens:
            # Token burn rides in the model field ("llama-3.1-8b · ~1.2k tok")
            # — the canister entry has no dedicated field and this shows
            # everywhere the model chip renders, with zero schema changes.
            model = ('%s · ~%s tok' % (model or 'local', _sw_fmt_tokens(tokens)))[:80]
        # libValidate hard-rejects an over-cap answer, and a rejected fulfill
        # leaves the job claimed until the lease expires — burning an attempt
        # each time. The degrade path can hand us raw model prose, so clamp.
        if len(answer) > _SW_ANSWER_CAP:
            print('[search-worker] answer %d chars — clamping to %d' % (len(answer), _SW_ANSWER_CAP))
            answer = answer[:_SW_ANSWER_CAP]
        graph = _sw_graph(q, results, notes, extras)
        # Provenance: say so when the AI asked this, not a person. It rides two
        # channels — the engine field ('brave · ai-gap', for the chip the UI
        # already renders) AND the on-chain askedBy field (the 12th fulfill line,
        # which the canister honours only as "ai-gap"). The engine string alone
        # was invisible to index.json's askedBy, which read "human" for every
        # entry; the trailing line fixes that so the gap cron is verifiable.
        #
        # Known limit: only the node that SUBMITTED the question knows it was a
        # gap question, so if another operator's worker claims it the entry
        # reads plain 'brave' / "human".
        is_gap = q in set(_gap_asked())
        is_news_cron = (not is_gap) and q in set(_news_asked())
        engine = ('brave · ai-gap' if is_gap
                  else 'brave · ai-news' if is_news_cron
                  else 'brave · news' if mode == 'news' else 'brave')
        lines = [jid, P(model), P(engine), P(answer), str(len(results))]
        for r in results:
            lines.append('%s %s' % (P(r['title']), P(r['url'])))
        lines.append(P(graph))
        # 12th line — askedBy for fast jobs (deep jobs use this slot for pages).
        # The canister accepts the 11-line envelope too, so appending is safe
        # across the deploy window. 'ai-news' is its own value, never folded
        # into 'ai-gap' or 'human' — see the news-cron block below for why.
        #
        # CRITICAL: only send this for a job that was ALWAYS fast. The canister
        # disambiguates the trailing line by the job's ORIGINALLY-SUBMITTED
        # mode (jobMode(id), fixed at submit time), not by what actually
        # happened here — so for a job submitted as 'deep' that degraded to
        # this single-shot path (planning/Brave failed above), the canister
        # still treats this slot as pagesJson and would store the literal
        # string "human"/"ai-gap" as this entry's "research pages", corrupting
        # research.json for a "Deep Research"-labeled entry that has none.
        # Confirmed live: two entries' research.json bodies were exactly the
        # 5-byte string "human" from this exact path. Omitting the line here
        # keeps lines.size() <= 11+nSrc, so the canister's own
        # `lines.size() > 11 + nSrc` guard naturally skips pagesJson (stays
        # "") AND askedBy (deep jobs hardcode askedBy="human" regardless, so
        # nothing is lost by not sending it).
        if mode != 'deep':
            lines.append(P('ai-gap' if is_gap else 'ai-news' if is_news_cron else 'human'))
        # Always attempt fulfill, even past our budget: the budget is soft and
        # sits 40s inside the lease, so the common case still lands. When we're
        # genuinely late the reap fires on the next worker's claim regardless,
        # so `attempts` increments whether we call or stay quiet — bailing would
        # save nothing and guarantee the loss.
        status, resp = _sw_call('fulfill', lines)
        if status == 200 and resp.get('ok'):
            print('[search-worker] fulfilled %s -> %s (%.0fs)'
                  % (jid, resp.get('libraryId'), time.monotonic() - started))
        else:
            print('[search-worker] fulfill rejected %s: %s %s' % (jid, status, resp))
    except Exception as e:
        print('[search-worker] job %s error: %s' % (jid, str(e)[:200]))
        _sw_call('fail', [jid, P(str(e)[:180])])


def _sw_loop():
    print('[search-worker] joining the search network as %s -> %s'
          % (_SW_PRINCIPAL[:12] + '…', _SW_BASE))
    paused = False
    dry = False
    while True:
        try:
            # Operator can take this node down from the admin panel
            # (gpuNode.enabled=false): stop claiming AND stop heartbeating so it
            # ages out of the network and clients see it offline — no SSH needed.
            gpu = _operator_config().get('gpuNode') or {}
            if gpu.get('enabled') is False:
                if not paused:
                    print('[search-worker] paused by operator (gpuNode.enabled=false)')
                    paused = True
                time.sleep(20)
                continue
            if paused:
                print('[search-worker] resumed by operator')
                paused = False
            # Don't claim work we can't do. Claiming with the month spent would
            # fail the job, burn one of its three attempts, and — since claim
            # hands out the OLDEST pending — do it again to the next one, so a
            # dry key would chew through the whole queue in minutes and fail
            # jobs a second operator with quota could have answered. Leaving
            # them pending costs nothing; heartbeat keeps us visible.
            if not _brave_remaining():
                if not dry:
                    print('[search-worker] brave month exhausted (%d/%d) — not claiming; '
                          'heartbeat continues' % (_brave_usage().get('used', 0), _BRAVE_CAP))
                    dry = True
                _sw_call('heartbeat', [])
                time.sleep(60)
                continue
            if dry:
                print('[search-worker] brave quota available again — claiming')
                dry = False
            # Clock starts BEFORE the claim: the canister stamps claimedAt during
            # that request, so a pre-call reading is guaranteed conservative.
            # monotonic, never time.time() — an NTP step mid-job would silently
            # blow (or extend) the budget.
            t0 = time.monotonic()
            status, resp = _sw_call('claim', [])
            if status == 403:
                # Not approved yet (or suspended): heartbeat keeps the
                # registration's lastSeen fresh so the operator sees "connected".
                _sw_call('heartbeat', [])
            elif status == 200 and resp.get('job'):
                _job = resp['job']
                # Deep jobs get the longer lease (DEEP_LEASE_NS), so give the
                # worker the matching wall-clock budget for its multi-hop loop.
                _budget = _SW_DEEP_BUDGET if _job.get('mode') == 'deep' else _SW_JOB_BUDGET
                _sw_process(_job, t0 + _budget)
                continue          # drain the queue without sleeping between jobs
        except Exception as e:
            print('[search-worker] loop error:', str(e)[:200])
        time.sleep(20)


if _SW_ENABLED and _SW_PRINCIPAL and re.fullmatch(r'[0-9a-fA-F]{64}', _SW_SECRET_HEX or ''):
    threading.Thread(target=_sw_loop, daemon=True, name='search-worker').start()
GAP_ENABLED = os.environ.get('GAP_CRON', '').strip() != '0'
# 5/run x 24 runs/day tops out near 3600/month, but the 35% reserve floor
# against the (now $15/mo-sized) Brave cap is what actually keeps this in
# check — see _BRAVE_RESERVE. Raised from 2 alongside BRAVE_MONTHLY_CAP
# specifically to grow the library faster while spend is intentional.
GAP_PER_RUN_MAX = int(os.environ.get('GAP_PER_RUN_MAX', '') or os.environ.get('GAP_DAILY_MAX', '') or 5)
GAP_INTERVAL_MIN = int(os.environ.get('GAP_INTERVAL_MIN', '') or 60)
GAP_TZ = os.environ.get('GAP_TZ', '') or 'America/New_York'   # display/log only now
MAX_GAP_RUNS_KEPT = 120
_gap_lock = threading.Lock()


def _hourly_next_run_ms(after_ms=None, offset_min=0, interval_min=60):
    """Epoch-ms of the next `interval_min`-aligned tick + offset_min, strictly
    after `after_ms` (or now). Timezone-invariant on purpose — "on the hour"
    doesn't need a calendar, only a clock, so this sidesteps the DST-drift trap
    the old once/day-at-a-fixed-ET-hour scheduler had to work around
    explicitly. Shared by the gap/news/weather crons, each at its own interval
    and a small offset, so they don't all hit Brave/NWS in the same second."""
    interval_ms = max(1, interval_min) * 60_000
    off = (offset_min * 60_000) % interval_ms
    now_ms = after_ms if after_ms else int(time.time() * 1000)
    run = (now_ms // interval_ms) * interval_ms + off
    if run <= now_ms:
        run += interval_ms
    return run


def _gap_next_run_ms(after_ms=None):
    """Epoch-ms of the next gap-cron run: every GAP_INTERVAL_MIN, offset 0."""
    return _hourly_next_run_ms(after_ms, offset_min=0, interval_min=GAP_INTERVAL_MIN)


def _gap_asked():
    """Queries this node submitted as gap questions. Exact strings: the canister
    stores `q` verbatim and hands it back on claim, so matching needs no copy of
    libNorm/libKey here (and a drifting copy of that would be worse than none)."""
    return _night_load('gap-asked.json', [])


def _gap_library():
    """(all_questions, human_questions) from the public library index."""
    try:
        with urllib.request.urlopen(_SW_BASE + '/library/index.json', timeout=20) as r:
            idx = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print('[gap] could not read the library index:', str(e)[:120])
        return None, None
    entries = idx if isinstance(idx, list) else (idx.get('entries') or [])
    asked = set(_gap_asked())
    all_qs, human_qs = [], []
    for e in entries:
        # index.json emits the question as "query" (the canister's field name);
        # "q" is only the raw submit shape. Reading only "q" made this return an
        # empty list, which silently degraded the gap cron to proposing blind
        # and starved the topics cron entirely.
        q = (e.get('query') or e.get('q') or '').strip()
        if not q:
            continue
        all_qs.append(q)
        if q not in asked:
            human_qs.append(q)
    return all_qs, human_qs


def _gap_structure():
    """Structural picture of the merged library graph, as prompt text ('' on any
    failure — the cron then proposes from the flat question list as before).

    The graph is questions linked to the source DOMAINS they cited, so two
    questions sharing a domain sit in the same evidence neighbourhood. Project
    questions onto shared domains and report what the flat list can't show:
    which questions are evidential islands, which little clusters float apart
    from the main web, and which domains anchor it. Questions that bridge
    those islands are the highest-value gaps to close."""
    try:
        with urllib.request.urlopen(_SW_BASE + '/library/graph.json', timeout=20) as r:
            j = json.loads(r.read().decode('utf-8'))
        g = j.get('graph') or j
        if isinstance(g, str):
            g = json.loads(g)
        nodes = g.get('nodes') or []
        edges = g.get('edges') or g.get('links') or []
        label = {}          # question node key -> question text
        for nd in nodes:
            k = nd.get('key') or nd.get('id')
            at = nd.get('attributes') or {}
            if k and at.get('entryId'):
                label[k] = str(at.get('label') or '').strip()
        if len(label) < 8:
            return ''       # too small for structure to mean anything
        qdoms = {q: set() for q in label}
        domqs = {}          # domain -> set of question keys citing it
        for e in edges:
            s, t = e.get('source'), e.get('target')
            q, d = (s, t) if s in qdoms else (t, s) if t in qdoms else (None, None)
            if q is None or d is None or d in qdoms:
                continue
            qdoms[q].add(d)
            domqs.setdefault(d, set()).add(q)

        # Union-find over questions joined by any shared domain.
        parent = {q: q for q in qdoms}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for qs in domqs.values():
            it = iter(qs)
            first = next(it, None)
            for q in it:
                ra, rb = find(first), find(q)
                if ra != rb:
                    parent[rb] = ra
        comps = {}
        for q in qdoms:
            comps.setdefault(find(q), []).append(q)
        comps = sorted(comps.values(), key=len, reverse=True)

        main_share = len(comps[0]) * 100 // len(qdoms)
        # Islands: everything outside the main component, singletons last so the
        # model sees clusters (bridgeable areas) before one-off orphans.
        islands = [c for c in comps[1:] if len(c) > 1]
        orphans = [c[0] for c in comps[1:] if len(c) == 1]
        hubs = sorted(domqs.items(), key=lambda kv: len(kv[1]), reverse=True)[:6]

        lines = ['%d questions; %d%% form one connected web (via shared sources).'
                 % (len(qdoms), main_share)]
        if islands:
            lines.append('Islands disconnected from the main web (each list is one island):')
            for c in islands[:5]:
                qs = [label[q] for q in c[:3] if label.get(q)]
                lines.append('- [%d questions] %s' % (len(c), ' | '.join(qs)))
        if orphans:
            lines.append('Isolated questions sharing no sources with anything else:')
            for q in orphans[:8]:
                if label.get(q):
                    lines.append('- ' + label[q])
        if hubs:
            lines.append('Best-anchored source domains: '
                         + ', '.join('%s (%d)' % (d.replace('d:', '', 1), len(qs))
                                     for d, qs in hubs))
        return '\n'.join(lines)
    except Exception as e:
        print('[gap] structure read failed (proposing from the flat list):', str(e)[:120])
        return ''


def _gap_schema(n):
    return {'type': 'json_schema', 'json_schema': {'name': 'gap_questions', 'strict': True,
            'schema': {'type': 'object', 'additionalProperties': False,
                       'properties': {'questions': {
                           'type': 'array', 'minItems': 1, 'maxItems': n,
                           'items': {'type': 'string'}}},
                       'required': ['questions']}}}


def _gap_propose(all_qs, human_qs, n, deadline, structure=''):
    """Ask the model for n gap-closing questions. Returns [] on any failure —
    a quiet no-op day is the correct outcome; there is nothing to salvage and
    a bad question becomes a permanent public entry."""
    recent_human = human_qs[:25]
    struct_block = ''
    if structure:
        struct_block = (
            '\n\nStructure of the library\'s knowledge graph (questions are '
            'linked when their answers cite the same sources):\n%s\n'
            'Prefer questions that would CONNECT an island or isolated question '
            'back to the main web — a question whose answer plausibly cites '
            'sources from both sides closes a structural hole, not just a '
            'topical one.' % structure)
    prompt = (
        'You curate a public Q&A library that grows over time. Below is what it '
        'already covers, and separately the questions REAL PEOPLE recently asked.\n\n'
        'Propose %d NEW questions that close the biggest gaps in coverage.\n'
        'Rules:\n'
        '- Aim at the topics real people are asking about: extend and deepen '
        'those areas rather than wandering into unrelated subjects.\n'
        '- Do NOT restate, rephrase, or narrowly re-ask anything already covered.\n'
        '- Each question must be self-contained and answerable from public web '
        'sources — no opinions, no predictions, nothing time-sensitive.\n'
        '- One sentence each, under 100 characters, phrased as a real question.\n'
        'Output STRICT JSON only: {"questions": ["...", "..."]}\n\n'
        'Recently asked by people (this is the demand signal — follow it):\n%s\n\n'
        'Already covered (do not repeat):\n%s%s'
        % (n,
           '\n'.join('- ' + q for q in recent_human) or '- (nothing yet)',
           '\n'.join('- ' + q for q in all_qs[:120]) or '- (empty library)',
           struct_block))
    want = _sw_model()
    payload = {'model': want, 'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': 600, 'response_format': _gap_schema(n)}
    b = _sw_backend()
    if b is None:
        print('[gap] no model reachable — skipping')
        return []
    try:
        text, _m, _t, _tr = _sw_stream_or_block(
            b.url, b.headers, dict(payload, model=b.model or want), deadline)
        # Same shape as _sw_parse_analysis: strip a code fence, take the outer
        # object. No salvage tier here on purpose — a half-decoded question is
        # not worth publishing permanently, and skipping a day costs nothing.
        t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
        m = re.search(r'\{.*\}', t, re.S)
        data = json.loads(m.group(0)) if m else {}
        out = [str(q).strip() for q in (data.get('questions') or []) if str(q).strip()]
        # 400 chars is the canister's hard query cap (LIB_MAX_QUERY); the prompt
        # asks for <100 but the cap is what actually protects the submit.
        return [q for q in out if len(q) <= 400][:n]
    except Exception as e:
        print('[gap] proposal failed:', str(e)[:160])
        return []


def _gap_submit(q):
    """POST /search/submit — the same anonymous route the website uses. Returns
    the canister's outcome word ('queued' | 'hit' | 'rejected:...' | 'error')."""
    try:
        req = urllib.request.Request(_SW_BASE + '/search/submit',
                                     data=q.encode('utf-8'),
                                     headers={'Content-Type': 'text/plain'})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode('utf-8'))
        if d.get('id'):
            return 'queued'
        return str(d.get('status') or d.get('error') or 'unknown')[:60]
    except Exception as e:
        return 'error: ' + str(e)[:60]


def _gap_run():
    t0 = time.monotonic()
    run = {'at': int(time.time() * 1000), 'submitted': [], 'skipped': [], 'note': ''}

    # Ask for the Brave budget FIRST. Each question becomes a job some worker
    # answers with one Brave query, so N proposals cost N queries even though
    # this process may not spend them itself. Reserving up front is what stops
    # the cron from quietly handing the network a bill it can't pay.
    n = GAP_PER_RUN_MAX
    while n > 0 and not _brave_spend('gap', n):
        n -= 1
    if n <= 0:
        run['note'] = ('brave month too tight for gap questions (%d/%d used) — '
                       'human searches keep the rest'
                       % (_brave_usage().get('used', 0), _BRAVE_CAP))
        print('[gap]', run['note'])
        _gap_log(run)
        return
    if n < GAP_PER_RUN_MAX:
        print('[gap] trimmed %d → %d questions to stay inside the brave month'
              % (GAP_PER_RUN_MAX, n))

    # From here on the batch is reserved, so every exit has to give it back or
    # a bad-library-index day permanently costs 10 queries for zero questions.
    all_qs, human_qs = _gap_library()
    if all_qs is None:
        _brave_refund('gap', n)
        run['note'] = 'library index unreachable'
        _gap_log(run)
        return

    structure = _gap_structure()
    if structure:
        run['structure'] = structure.splitlines()[0]   # headline into the ledger
    proposed = _gap_propose(all_qs, human_qs, n, time.monotonic() + 90, structure)
    if not proposed:
        _brave_refund('gap', n)
        run['note'] = 'no questions proposed'
        _gap_log(run)
        return

    # Dedup locally before spending a submit. The canister dedups too (libKey),
    # but a #hit there still costs a round trip and tells us nothing new.
    seen = {q.strip().lower() for q in all_qs}
    asked = _gap_asked()
    fresh = []
    for q in proposed:
        if q.strip().lower() in seen:
            run['skipped'].append({'q': q, 'why': 'already covered'})
            continue
        seen.add(q.strip().lower())
        fresh.append(q)

    for q in fresh:
        outcome = _gap_submit(q)
        if outcome == 'queued':
            run['submitted'].append(q)
            asked.append(q)
        else:
            run['skipped'].append({'q': q, 'why': outcome})

    # Give back what we reserved but didn't use. Dedup and validation drop most
    # proposals on a mature library, so this is the common path, not the edge.
    _brave_refund('gap', n - len(run['submitted']))

    _night_save('gap-asked.json', asked[-500:])
    run['spent'] = len(run['submitted'])
    run['note'] = ('submitted %d of %d proposed in %.1fs (reserved %d, refunded %d)'
                   % (len(run['submitted']), len(proposed), time.monotonic() - t0,
                      n, n - len(run['submitted'])))
    print('[gap] %s' % run['note'])
    for q in run['submitted']:
        print('[gap]   + %s' % q[:90])
    _gap_log(run)


def _gap_log(run):
    try:
        runs = _night_load('gap-runs.json', [])
        runs.append(run)
        _night_save('gap-runs.json', runs[-MAX_GAP_RUNS_KEPT:])
    except Exception:
        pass


def _gap_loop():
    sched = _night_load('gap-schedule.json', {})
    nxt = int(sched.get('nextRunAt', 0) or 0)
    now_ms = int(time.time() * 1000)
    bound = max(2 * GAP_INTERVAL_MIN, 180) * 60_000
    if not nxt or abs(nxt - now_ms) > bound:
        # No schedule, one stale enough it would otherwise fire immediately on
        # boot, OR (the migration case) a next-run left over from the OLD
        # once/day-at-10am scheduler — that value is a future timestamp, so a
        # past-only staleness check would never catch it and gap would
        # silently stay on the daily cadence until that old run time arrived.
        # Bounding BOTH directions around "now" catches that too.
        nxt = _gap_next_run_ms()
        _night_save('gap-schedule.json', {'nextRunAt': nxt})
    print('[gap] next run %s (hourly, every %d min)'
          % (time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(nxt / 1000)), GAP_INTERVAL_MIN))
    while True:
        time.sleep(30)
        try:
            now_ms = int(time.time() * 1000)
            if now_ms < nxt:
                continue
            with _gap_lock:
                nxt = _gap_next_run_ms(now_ms)
                _night_save('gap-schedule.json', {'nextRunAt': nxt})
            _gap_run()
            print('[gap] next run %s'
                  % time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(nxt / 1000)))
        except Exception as e:
            print('[gap] loop error:', str(e)[:200])


if GAP_ENABLED and _SW_ENABLED and _SW_PRINCIPAL:
    threading.Thread(target=_gap_loop, daemon=True, name='gap-cron').start()
NEWS_ENABLED = os.environ.get('NEWS_CRON', '').strip() == '1'   # opt-in: off by default until proven out
NEWS_PER_RUN_MAX = int(os.environ.get('NEWS_PER_RUN_MAX', '') or 6)   # raised alongside BRAVE_MONTHLY_CAP — see GAP_PER_RUN_MAX
NEWS_INTERVAL_MIN = int(os.environ.get('NEWS_INTERVAL_MIN', '') or 60)
MAX_NEWS_RUNS_KEPT = 120
_news_lock = threading.Lock()


def _news_asked():
    """Questions THIS node submitted via the news cron. Same exact-string
    matching contract as _gap_asked() — see its docstring."""
    return _night_load('news-asked.json', [])


def _news_headlines(deadline):
    """Current breaking headlines via Brave's news vertical, spent against the
    'news' budget lane (not 'human') so a slow news day never looks like a
    person searched. Returns a list of title strings, [] on any failure."""
    try:
        results = _sw_brave('breaking news today', deadline, kind='news', vertical='news')
    except Exception as e:
        print('[news] brave fetch failed:', str(e)[:120])
        return []
    if not results:
        return []
    seen, out = set(), []
    for r in results:
        t = (r.get('title') or '').strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _news_schema(n):
    return {'type': 'json_schema', 'json_schema': {'name': 'news_questions', 'strict': True,
            'schema': {'type': 'object', 'additionalProperties': False,
                       'properties': {'questions': {
                           'type': 'array', 'minItems': 1, 'maxItems': n,
                           'items': {'type': 'string'}}},
                       'required': ['questions']}}}


def _news_propose(headlines, n, deadline):
    """Ask the model to turn today's headlines into self-contained, answerable
    questions — unlike _gap_propose, time-sensitive framing ('this week',
    'currently') is fine here; that's the entire point of this cron."""
    prompt = (
        'Below are current breaking-news headlines from a live news search.\n'
        'Write %d clear, self-contained questions a reader could ask to get a '
        'summary of each distinct story. One question per distinct story — do '
        'not invent multiple angles on the same headline.\n'
        'Rules:\n'
        '- One sentence each, under 140 characters, phrased as a real question.\n'
        '- Self-contained: someone with zero context should understand what is '
        'being asked.\n'
        'Output STRICT JSON only: {"questions": ["...", "..."]}\n\n'
        'Headlines:\n%s'
        % (n, '\n'.join('- ' + h for h in headlines[:15]) or '- (none)'))
    want = _sw_model()
    payload = {'model': want, 'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': 500, 'response_format': _news_schema(n)}
    b = _sw_backend()
    if b is None:
        print('[news] no model reachable — skipping')
        return []
    try:
        text, _m, _t, _tr = _sw_stream_or_block(
            b.url, b.headers, dict(payload, model=b.model or want), deadline)
        t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
        m = re.search(r'\{.*\}', t, re.S)
        data = json.loads(m.group(0)) if m else {}
        out = [str(q).strip() for q in (data.get('questions') or []) if str(q).strip()]
        return [q for q in out if len(q) <= 400][:n]
    except Exception as e:
        print('[news] proposal failed:', str(e)[:160])
        return []


def _news_submit(q):
    """POST /search/submit?mode=news — same anonymous route as _gap_submit,
    with mode=news so submitSearch (main.mo) tags the job and the worker hits
    Brave's news vertical instead of web for it."""
    try:
        url = _SW_BASE + '/search/submit?mode=news'
        req = urllib.request.Request(url, data=q.encode('utf-8'),
                                     headers={'Content-Type': 'text/plain'})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode('utf-8'))
        if d.get('id'):
            return 'queued'
        return str(d.get('status') or d.get('error') or 'unknown')[:60]
    except Exception as e:
        return 'error: ' + str(e)[:60]


def _news_run():
    t0 = time.monotonic()
    run = {'at': int(time.time() * 1000), 'submitted': [], 'skipped': [], 'note': ''}

    n = NEWS_PER_RUN_MAX
    while n > 0 and not _brave_spend('news', n):
        n -= 1
    if n <= 0:
        run['note'] = ('brave month too tight for news questions (%d/%d used)'
                       % (_brave_usage().get('used', 0), _BRAVE_CAP))
        print('[news]', run['note'])
        _news_log(run)
        return

    deadline = time.monotonic() + 90
    headlines = _news_headlines(deadline)
    if not headlines:
        _brave_refund('news', n)
        run['note'] = 'no headlines (brave news vertical came up dry or unreachable)'
        _news_log(run)
        return

    proposed = _news_propose(headlines, n, deadline)
    if not proposed:
        _brave_refund('news', n)
        run['note'] = 'no questions proposed'
        _news_log(run)
        return

    asked = _news_asked()
    seen = {q.strip().lower() for q in asked[-200:]}
    fresh = []
    for q in proposed:
        if q.strip().lower() in seen:
            run['skipped'].append({'q': q, 'why': 'already asked recently'})
            continue
        seen.add(q.strip().lower())
        fresh.append(q)

    for q in fresh:
        outcome = _news_submit(q)
        if outcome == 'queued':
            run['submitted'].append(q)
            asked.append(q)
        else:
            run['skipped'].append({'q': q, 'why': outcome})

    _brave_refund('news', n - len(run['submitted']))
    _night_save('news-asked.json', asked[-1000:])
    run['spent'] = len(run['submitted'])
    run['note'] = ('submitted %d of %d proposed in %.1fs (reserved %d, refunded %d)'
                   % (len(run['submitted']), len(proposed), time.monotonic() - t0,
                      n, n - len(run['submitted'])))
    print('[news] %s' % run['note'])
    for q in run['submitted']:
        print('[news]   + %s' % q[:90])
    _news_log(run)


def _news_log(run):
    try:
        runs = _night_load('news-runs.json', [])
        runs.append(run)
        _night_save('news-runs.json', runs[-MAX_NEWS_RUNS_KEPT:])
    except Exception:
        pass


def _news_next_run_ms(after_ms=None):
    return _hourly_next_run_ms(after_ms, offset_min=5, interval_min=NEWS_INTERVAL_MIN)


def _news_loop():
    sched = _night_load('news-schedule.json', {})
    nxt = int(sched.get('nextRunAt', 0) or 0)
    now_ms = int(time.time() * 1000)
    bound = max(2 * NEWS_INTERVAL_MIN, 180) * 60_000
    if not nxt or abs(nxt - now_ms) > bound:   # see _gap_loop for why both directions
        nxt = _news_next_run_ms()
        _night_save('news-schedule.json', {'nextRunAt': nxt})
    print('[news] next run %s (hourly, :05 past)'
          % time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(nxt / 1000)))
    while True:
        time.sleep(30)
        try:
            now_ms = int(time.time() * 1000)
            if now_ms < nxt:
                continue
            with _news_lock:
                nxt = _news_next_run_ms(now_ms)
                _night_save('news-schedule.json', {'nextRunAt': nxt})
            _news_run()
            print('[news] next run %s'
                  % time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(nxt / 1000)))
        except Exception as e:
            print('[news] loop error:', str(e)[:200])


if NEWS_ENABLED and _SW_ENABLED and _SW_PRINCIPAL:
    threading.Thread(target=_news_loop, daemon=True, name='news-cron').start()
# ---- Topics cron -----------------------------------------------------------
# Every TOPICS_INTERVAL_H hours, summarise the whole library's questions into a
# handful of named topic filters and push them on-chain (the `topics` worker op
# → /library/topics.json). The graph viewer's legend uses them as clickable
# filters, falling back to its own client-side clustering when they're absent.
#
# Unlike the gap cron this spends NO Brave budget — it only reads existing
# questions and calls the local model — so there is no reserve/refund dance. It
# is a pure overwrite: each run regenerates the whole topics blob.
TOPICS_ENABLED = os.environ.get('TOPICS_CRON', '').strip() != '0'
TOPICS_INTERVAL_S = int(os.environ.get('TOPICS_INTERVAL_H', '') or 6) * 3600
MAX_TOPICS_RUNS_KEPT = 40


def _topics_schema():
    return {'type': 'json_schema', 'json_schema': {'name': 'topics', 'strict': True,
            'schema': {'type': 'object', 'additionalProperties': False,
                       'properties': {'topics': {
                           'type': 'array', 'minItems': 1, 'maxItems': 10,
                           'items': {'type': 'object', 'additionalProperties': False,
                                     'properties': {
                                         'label': {'type': 'string'},
                                         'match': {'type': 'array', 'minItems': 1,
                                                   'items': {'type': 'string'}}},
                                     'required': ['label', 'match']}}},
                       'required': ['topics']}}}


def _topics_propose(all_qs, deadline):
    """Summarise the library's questions into named topic filters. Returns a
    list of {label, match:[...]} or [] on any failure (a skipped run just keeps
    the previous topics.json — or the viewer's own clustering — in place)."""
    prompt = (
        'Below are the questions in a public Q&A library. Group them into 6-10 '
        'broad TOPICS that a reader could use as filters.\n'
        'For each topic return:\n'
        '- "label": a short human-readable name, 2-4 words, Title Case '
        '(e.g. "Internet Computer", "DAOs & Governance", "Coffee & Farming").\n'
        '- "match": 2-5 lowercase keywords/phrases that actually appear in the '
        'questions of that topic, used to match questions to the topic.\n'
        'Cover the real spread of questions; do not invent topics with no '
        'questions. Output STRICT JSON only: '
        '{"topics":[{"label":"...","match":["...","..."]}]}\n\n'
        'Questions:\n%s'
        % ('\n'.join('- ' + q for q in all_qs[:200]) or '- (empty library)'))
    want = _sw_model()
    payload = {'model': want, 'messages': [{'role': 'user', 'content': prompt}],
               'max_tokens': 700, 'response_format': _topics_schema()}
    b = _sw_backend()
    if b is None:
        print('[topics] no model reachable — skipping')
        return []
    try:
        text, _m, _t, _tr = _sw_stream_or_block(
            b.url, b.headers, dict(payload, model=b.model or want), deadline)
        t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
        m = re.search(r'\{.*\}', t, re.S)
        data = json.loads(m.group(0)) if m else {}
        out = []
        for it in (data.get('topics') or []):
            label = str(it.get('label') or '').strip()[:40]
            match = [str(x).strip().lower() for x in (it.get('match') or []) if str(x).strip()][:5]
            if label and match:
                out.append({'label': label, 'match': match})
        return out[:10]
    except Exception as e:
        print('[topics] proposal failed:', str(e)[:160])
        return []


def _topics_run():
    t0 = time.monotonic()
    run = {'at': int(time.time() * 1000), 'count': 0, 'note': ''}
    all_qs, _human = _gap_library()
    if not all_qs:
        run['note'] = 'library index unreachable or empty'
        _topics_log(run)
        return
    topics = _topics_propose(all_qs, time.monotonic() + 90)
    if not topics:
        run['note'] = 'no topics proposed'
        _topics_log(run)
        return
    blob = json.dumps({'topics': topics, 'ts': int(time.time() * 1000)}, ensure_ascii=False)
    status, resp = _sw_call('topics', [urllib.parse.quote(blob, safe='')])
    if status == 200 and resp.get('ok'):
        run['count'] = len(topics)
        run['note'] = ('published %d topics in %.1fs' % (len(topics), time.monotonic() - t0))
        print('[topics] %s: %s' % (run['note'], ', '.join(t['label'] for t in topics)))
    else:
        run['note'] = 'publish rejected: %s %s' % (status, resp)
        print('[topics]', run['note'])
    _topics_log(run)


def _topics_log(run):
    try:
        runs = _night_load('topics-runs.json', [])
        runs.append(run)
        _night_save('topics-runs.json', runs[-MAX_TOPICS_RUNS_KEPT:])
    except Exception:
        pass


def _topics_loop():
    # First run shortly after boot so a fresh deploy populates topics.json, then
    # every TOPICS_INTERVAL_S. nextRunAt is persisted so a restart doesn't reset
    # the clock and republish on every bounce.
    sched = _night_load('topics-schedule.json', {})
    nxt = int(sched.get('nextRunAt', 0) or 0)
    now_ms = int(time.time() * 1000)
    if not nxt or nxt < now_ms:
        nxt = now_ms + 120_000   # 2 min after boot
        _night_save('topics-schedule.json', {'nextRunAt': nxt})
    print('[topics] next run %s (every %dh)'
          % (time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(nxt / 1000)),
             TOPICS_INTERVAL_S // 3600))
    while True:
        time.sleep(60)
        try:
            if int(time.time() * 1000) < nxt:
                continue
            nxt = int(time.time() * 1000) + TOPICS_INTERVAL_S * 1000
            _night_save('topics-schedule.json', {'nextRunAt': nxt})
            _topics_run()
        except Exception as e:
            print('[topics] loop error:', str(e)[:200])


if TOPICS_ENABLED and _SW_ENABLED and _SW_PRINCIPAL:
    threading.Thread(target=_topics_loop, daemon=True, name='topics-cron').start()

# ── Status HTTP listener ─────────────────────────────────────────────────────
# Standalone-service design: this replaces the /gap/status and /news/status
# routes that used to live on serve.py's main Handler (serve.py ~5334-5372,
# reproduced here byte-for-byte in JSON shape). serve.py's admin analytics
# dashboard (frontend/src/routes/(pages)/admin/analytics/+page.svelte) is the
# confirmed consumer of those two routes; repointing it at this service's own
# endpoint is tracked as a small, separate follow-up — see the extraction
# plan this file came from. /brave/* (a separate, general-purpose Brave
# search proxy, unrelated to this worker's own quota-metered _sw_brave())
# intentionally stays behind in serve.py and has no equivalent here.
class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # the loop threads already print their own progress lines

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/health':
            return self._send_json(200, {'ok': True, 'ts': int(time.time() * 1000)})
        if path == '/gap/status':
            u = _brave_usage()
            used = int(u.get('used', 0) or 0)
            return self._send_json(200, {
                'brave': {
                    'month': u.get('month'), 'used': used, 'cap': _BRAVE_CAP,
                    'remaining': max(0, _BRAVE_CAP - used),
                    'byKind': u.get('byKind', {}),
                    'headroom': {k: max(0, int(_BRAVE_CAP - _BRAVE_CAP * r - used))
                                 for k, r in _BRAVE_RESERVE.items()},
                },
                'gap': {
                    'enabled': bool(GAP_ENABLED and _SW_ENABLED and _SW_PRINCIPAL),
                    'perRunMax': GAP_PER_RUN_MAX,
                    'intervalMin': GAP_INTERVAL_MIN,
                    'nextRunAt': int((_night_load('gap-schedule.json', {}) or {}).get('nextRunAt', 0) or 0),
                    'askedTotal': len(_gap_asked()),
                    'runs': _night_load('gap-runs.json', [])[-10:],
                },
            })
        if path == '/news/status':
            return self._send_json(200, {
                'news': {
                    'enabled': bool(NEWS_ENABLED and _SW_ENABLED and _SW_PRINCIPAL),
                    'perRunMax': NEWS_PER_RUN_MAX,
                    'intervalMin': NEWS_INTERVAL_MIN,
                    'nextRunAt': int((_night_load('news-schedule.json', {}) or {}).get('nextRunAt', 0) or 0),
                    'askedTotal': len(_news_asked()),
                    'runs': _night_load('news-runs.json', [])[-10:],
                },
            })
        return self._send_json(404, {'error': 'not found'})


class _ThreadedStatusServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    # The four background loops (_sw_loop, and gap/news/topics crons) already
    # started above, at module-import time, gated by their own env checks —
    # ported unchanged from serve.py, where they worked the same way. This
    # function's only job is to serve the status endpoints in the foreground
    # so the container has a live process to run.
    if not _SW_ENABLED:
        print('[search-worker] SEARCH_WORKER != 1 — this service has nothing to do. '
              'Set SEARCH_WORKER=1, WORKER_PRINCIPAL, WORKER_SECRET to join the network.')
    server = _ThreadedStatusServer(('0.0.0.0', PORT), _StatusHandler)
    print('[search-worker] status endpoint on :%d (/health, /gap/status, /news/status)' % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

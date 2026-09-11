"""market_worker.py — the coworker's side of the hiring hall.

A coworker listed on the network (docs/AGENT_MARKETPLACE.md) has to take a
job, do it and file the result while its operator's browser is closed. This
is the loop that does that, from inside the coworker's own container:

  1. keep a key of its own (ic_agent.Ed25519Identity, hq-state/market/
     worker-key.json, 0600). Its principal is what the operator links to the
     listing with `linkWorker` from the shell. The seed never leaves the box.
  2. heartbeat the hall so the listing shows "at their desk";
  3. poll `workerPoll` — jobs addressed to this listing, or open jobs whose
     tags it covers at or above its asking price;
  4. `claimJob`, run the brief through a LOCAL driver (whichever brain the
     operator chose for network work — drivers/*, the same five-call
     contract everything else speaks), `deliverJob` with the text and its
     sha256, or `failJob` with one honest sentence when the brain could not.

Privacy boundary, enforced here and not just described: a network job runs
with NO tools (`tools: []`) and no working directory. The brief is the only
input; the brain's text is the only output. Nothing in this loop can open
the operator's vault, files or shell on a stranger's behalf. Operators who
want a coworker that can browse for network jobs opt in per listing
(`allowWeb`), and that is the only widening offered.

Configuration lives in hq-state/market/worker.json and is edited from the
Hiring Hall view through serve.py's /marketplace/worker/* routes:

  { "enabled": bool, "driver": "ollama", "model": "ollama:llama3.1",
    "pollSecs": 20, "canister": "<market canister id>", "host": "https://icp-api.io",
    "system": "<extra job description>", "allowWeb": false }

`run_task` is injectable so the loop can be driven end to end against a stub
hall with a stub brain (scripts/test_a_network_coworker_takes_a_job_…py)
without a replica, a model, or the network.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time

import ic_agent as ic

log = logging.getLogger('market_worker')

# ── Candid shapes, mirroring src/cafresohq_market/cafresohq_market.did ──────

JOB_STATUS = ('variant', [(s, None) for s in (
    'posted', 'funded', 'claimed', 'delivered', 'accepted', 'disputed', 'refunded', 'cancelled', 'failed')])
JOB_OFFER = ('record', [
    ('id', 'nat'), ('title', 'text'), ('brief', 'text'), ('kind', 'text'), ('tags', ('vec', 'text')),
    ('ledger', 'principal'), ('price', 'nat'), ('deadlineSecs', 'nat'), ('listing', ('opt', 'nat')),
    ('createdAt', 'int'),
])
RESULT = ('variant', [('ok', 'nat'), ('err', 'text')])
PUBLIC_STATUS = ('record', [
    ('id', 'nat'), ('status', JOB_STATUS), ('summary', 'text'), ('workerListing', ('opt', 'nat')),
    ('claimedAt', 'int'), ('deliveredAt', 'int'), ('updatedAt', 'int'),
])

BODY_MAX = 65_536
SUMMARY_MAX = 500
DEFAULTS = {
    'enabled': False, 'driver': '', 'model': '', 'pollSecs': 20,
    'canister': '', 'host': '', 'system': '', 'allowWeb': False,
}
ENV_CANISTER = 'CAFRESOHQ_MARKET_CANISTER'
ENV_HOST = 'CAFRESOHQ_IC_HOST'
DEFAULT_HOST = 'https://icp-api.io'


def _result(v):
    """Unwrap a Candid `Result` → (ok_value, err_text)."""
    if isinstance(v, dict):
        if 'ok' in v:
            return v['ok'], None
        if 'err' in v:
            return None, str(v['err'])
    return None, f'unexpected reply {v!r}'


def _status_name(v):
    return next(iter(v)) if isinstance(v, dict) and v else str(v)


def default_run_task(brief: str, cfg: dict, offer: dict) -> str:
    """Run the brief through the configured local driver. Tools OFF."""
    import drivers
    from drivers.base import run_task_text
    drv = drivers.get(cfg.get('driver'))
    if drv is None:
        raise RuntimeError(f"no driver named {cfg.get('driver')!r} on this machine")
    system = (
        'You are a coworker hired from the network through the Cafreso hiring hall. '
        'The message is a job brief from a boss you do not otherwise know. Do the job '
        'in full, in one reply; the reply is the deliverable and will be filed as-is. '
        'You have no files, no tools and no memory of this boss: work from the brief alone. '
        'Do not ask questions — state assumptions and deliver.'
    )
    extra = str(cfg.get('system') or '').strip()
    if extra:
        system += '\n\n' + extra
    task = {
        'prompt': f"Job: {offer.get('title', '')}\nKind: {offer.get('kind', '')}\n\n{brief}",
        'system': system,
        'model': str(cfg.get('model') or ''),
        'tools': ['web'] if cfg.get('allowWeb') else [],
        'agentName': 'network coworker',
        'limits': {'maxTokens': 8192},
    }
    text, _usage = run_task_text(drv, task)
    return text or ''


class MarketWorker:
    def __init__(self, state_dir: str, run_task=None, agent_factory=None):
        self.state_dir = os.path.join(state_dir, 'market')
        self.key_path = os.path.join(self.state_dir, 'worker-key.json')
        self.cfg_path = os.path.join(self.state_dir, 'worker.json')
        self._run_task = run_task or default_run_task
        self._agent_factory = agent_factory or (lambda host, ident: ic.Agent(host, ident))
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._identity = None
        self.cfg = dict(DEFAULTS)
        self.state = {
            'running': False, 'lastPoll': 0, 'lastHeartbeat': 0, 'lastError': '',
            'lastErrorAt': 0, 'jobsDone': 0, 'jobsFailed': 0, 'current': None,
            'linked': None, 'offersSeen': 0, 'log': [],
        }
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self):
        try:
            with open(self.cfg_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for k in DEFAULTS:
                    if k in data:
                        self.cfg[k] = data[k]
        except (OSError, ValueError):
            pass

    def _save(self):
        os.makedirs(self.state_dir, exist_ok=True)
        tmp = self.cfg_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(self.cfg, fh, indent=2)
        os.replace(tmp, self.cfg_path)

    def _note(self, line: str):
        self.state['log'] = (self.state['log'] + [{'at': time.time(), 'line': line}])[-40:]
        log.info('%s', line)

    # ── identity / config ───────────────────────────────────────────────────
    def identity(self) -> ic.Ed25519Identity:
        with self._lock:
            if self._identity is None:
                self._identity = ic.Ed25519Identity.load_or_create(self.key_path)
            return self._identity

    def principal(self) -> str:
        return self.identity().principal.to_text()

    def canister(self) -> str:
        return str(self.cfg.get('canister') or os.environ.get(ENV_CANISTER, '')).strip()

    def host(self) -> str:
        return str(self.cfg.get('host') or os.environ.get(ENV_HOST, '') or DEFAULT_HOST).rstrip('/')

    def configured(self) -> bool:
        return bool(self.canister())

    def configure(self, patch: dict) -> dict:
        with self._lock:
            for k, v in (patch or {}).items():
                if k not in DEFAULTS:
                    continue
                if k == 'pollSecs':
                    try:
                        v = max(5, min(600, int(v)))
                    except (TypeError, ValueError):
                        continue
                elif k in ('enabled', 'allowWeb'):
                    v = bool(v)
                else:
                    v = str(v or '').strip()
                self.cfg[k] = v
            self._save()
            if self.cfg['enabled'] and self.configured():
                self.start()
            else:
                self.stop()
            return self.status()

    def status(self) -> dict:
        with self._lock:
            cfg = dict(self.cfg)
            st = dict(self.state)
        return {
            'configured': self.configured(),
            'canister': self.canister(),
            'host': self.host(),
            'principal': self.principal(),
            'keyPath': self.key_path,
            'config': cfg,
            **st,
        }

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            if not self.configured():
                self.state['lastError'] = 'the hiring hall canister id is not set'
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name='market-worker')
            self.state['running'] = True
            self._thread.start()
            self._note('network coworker: on duty')

    def stop(self, wait: float = 0):
        with self._lock:
            t = self._thread
            self._stop.set()
            self.state['running'] = False
        if t and wait:
            t.join(wait)

    # ── the loop ────────────────────────────────────────────────────────────
    def _agent(self) -> ic.Agent:
        return self._agent_factory(self.host(), self.identity())

    def _loop(self):
        agent = self._agent()
        canister = self.canister()
        while not self._stop.is_set():
            try:
                self.tick(agent, canister)
            except Exception as e:                       # noqa: BLE001 — the loop must outlive one bad tick
                self._fail(f'{type(e).__name__}: {e}')
            self._stop.wait(max(5, int(self.cfg.get('pollSecs') or 20)))
        with self._lock:
            self.state['running'] = False

    def _fail(self, msg: str):
        with self._lock:
            self.state['lastError'] = msg[:300]
            self.state['lastErrorAt'] = time.time()
        self._note('snag: ' + msg[:300])

    def tick(self, agent: ic.Agent, canister: str) -> int:
        """One poll. Returns how many jobs were worked (0 or 1)."""
        now = time.time()
        if now - self.state['lastHeartbeat'] > 120:
            linked = agent.call(canister, 'workerHeartbeat', ret_types=['bool'])[0]
            with self._lock:
                self.state['lastHeartbeat'] = now
                self.state['linked'] = bool(linked)
            if not linked:
                self._fail('this coworker\'s key is not linked to a listing yet — link it from the Hiring Hall')
                return 0
        offers = agent.call(canister, 'workerPoll', ret_types=[('vec', JOB_OFFER)], query=True)[0]
        with self._lock:
            self.state['lastPoll'] = time.time()
            self.state['offersSeen'] += len(offers)
        if not offers:
            return 0
        # Oldest first; one job at a time.
        offers.sort(key=lambda o: (o.get('createdAt', 0), o.get('id', 0)))
        return 1 if self.work(agent, canister, offers[0]) else 0

    def work(self, agent: ic.Agent, canister: str, offer: dict) -> bool:
        jid = int(offer['id'])
        ok, err = _result(agent.call(canister, 'claimJob', ['nat'], [jid], ret_types=[RESULT])[0])
        if err:
            self._note(f'job {jid}: could not claim — {err}')
            return False
        with self._lock:
            self.state['current'] = {'id': jid, 'title': offer.get('title', ''), 'startedAt': time.time()}
        self._note(f'job {jid}: claimed "{offer.get("title", "")[:60]}"')
        try:
            agent.call(canister, 'progressJob', ['nat', 'text'], [jid, 'started'], ret_types=[RESULT])
            text = self._run_task(str(offer.get('brief', '')), dict(self.cfg), offer)
            text = str(text or '').strip()
            if not text:
                raise RuntimeError('the brain returned nothing')
            if len(text.encode('utf-8')) > BODY_MAX:
                cut = text.encode('utf-8')[:BODY_MAX - 200].decode('utf-8', 'ignore')
                text = cut + '\n\n[cut here: the full deliverable was longer than the hall accepts]'
            sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
            summary = (text.strip().splitlines() or ['delivered'])[0].strip()[:SUMMARY_MAX] or 'delivered'
            ok, err = _result(agent.call(canister, 'deliverJob', ['nat', 'text', 'text', 'text'],
                                         [jid, summary, text, sha], ret_types=[RESULT])[0])
            if err:
                raise RuntimeError('the hall refused the delivery: ' + err)
            with self._lock:
                self.state['jobsDone'] += 1
                self.state['current'] = None
            self._note(f'job {jid}: delivered ({len(text)} chars, sha256 {sha[:12]}…)')
            return True
        except Exception as e:                           # noqa: BLE001 — one honest sentence back to the hall
            reason = f'{type(e).__name__}: {e}'[:1900]
            try:
                agent.call(canister, 'failJob', ['nat', 'text'], [jid, reason], ret_types=[RESULT])
            except Exception as e2:                      # noqa: BLE001
                reason += f' (and failJob itself failed: {e2})'
            with self._lock:
                self.state['jobsFailed'] += 1
                self.state['current'] = None
            self._fail(f'job {jid}: {reason}')
            return False


# ── module singleton for serve.py ───────────────────────────────────────────

_WORKER = None
_WORKER_LOCK = threading.Lock()


def worker(state_dir: str) -> MarketWorker:
    """The one worker for this container, created on first use. If the
    operator enabled it before a restart, it goes back on duty here."""
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None:
            _WORKER = MarketWorker(state_dir)
            if _WORKER.cfg.get('enabled') and _WORKER.configured():
                _WORKER.start()
        return _WORKER

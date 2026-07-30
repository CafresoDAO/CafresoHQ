"""
SQLite-backed session store for the CafresoAI Fleet API.

Drop-in replacement for the fleet.json "sessions" key. Provides ACID
guarantees, crash recovery, and safe concurrent access from the threaded
HTTP server and background maintenance loops.

Usage:
    from session_store import get_store
    store = get_store()                       # module-level singleton
    sid = store.create_session({...})
    store.update_session(sid, {'status': 'running', 'ip': '10.0.0.5'})

No external dependencies -- stdlib only (sqlite3, threading, json, etc.).
"""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
import sqlite3
import threading
import uuid

log = logging.getLogger('session-store')

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT    PRIMARY KEY,
    principal        TEXT    NOT NULL,
    template_id      TEXT    NOT NULL,
    display_name     TEXT,
    status           TEXT    NOT NULL DEFAULT 'starting',
    provider         TEXT    NOT NULL,
    provider_id      TEXT,
    ip               TEXT,
    port             INTEGER,
    stream_protocol  TEXT,
    stream_url       TEXT,
    resources        TEXT,           -- JSON blob
    persistent       INTEGER DEFAULT 0,
    error            TEXT,
    created_at       TEXT    NOT NULL,
    last_accessed    TEXT,
    region           TEXT,
    moonlight_port   INTEGER,
    turn_servers     TEXT            -- JSON blob
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_principal ON sessions (principal);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status    ON sessions (status);",
]

# Columns that are stored as JSON blobs and need ser/deser.
_JSON_COLUMNS = frozenset({'resources', 'turn_servers'})

# Every column in the sessions table, in schema order.  Used for INSERT and
# for mapping between dicts and rows.
_ALL_COLUMNS = (
    'session_id', 'principal', 'template_id', 'display_name', 'status',
    'provider', 'provider_id', 'ip', 'port', 'stream_protocol', 'stream_url',
    'resources', 'persistent', 'error', 'created_at', 'last_accessed',
    'region', 'moonlight_port', 'turn_servers',
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _serialize_value(key: str, value):
    """Convert a Python value to its SQLite storage form."""
    if key in _JSON_COLUMNS and value is not None:
        return json.dumps(value, default=str)
    if key == 'persistent':
        return int(bool(value)) if value is not None else 0
    return value


def _deserialize_row(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row into a plain dict, deserializing JSON columns."""
    d = dict(row)
    for col in _JSON_COLUMNS:
        raw = d.get(col)
        if raw is not None:
            try:
                d[col] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass  # leave as-is
    # Convert persistent back to bool for callers that expect it
    if 'persistent' in d:
        d['persistent'] = bool(d['persistent'])
    return d


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------
class SessionStore:
    """Thread-safe, SQLite-backed session store.

    All public methods acquire ``_lock`` before touching the database so the
    store is safe to share across the HTTP handler threads and the background
    maintenance loops that fleet-api.py runs.
    """

    def __init__(self, db_path: str = 'sessions.db'):
        self._db_path = str(pathlib.Path(db_path).resolve())
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # -- internal -----------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return the persistent connection, creating it on first call."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level='DEFERRED',
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        return self._conn

    def _init_db(self):
        """Create the sessions table and indexes if they don't exist."""
        with self._lock:
            conn = self._get_conn()
            conn.execute(_CREATE_TABLE)
            for idx_sql in _CREATE_INDEXES:
                conn.execute(idx_sql)
            conn.commit()

    # -- public API ---------------------------------------------------------

    def create_session(self, session_dict: dict) -> str:
        """Insert a new session.  Returns the session_id.

        If ``session_dict`` does not contain a ``session_id``, one is
        generated automatically.  ``created_at`` defaults to UTC now.
        """
        d = dict(session_dict)
        if not d.get('session_id'):
            d['session_id'] = 'ses_' + uuid.uuid4().hex[:12]
        if not d.get('created_at'):
            d['created_at'] = (
                datetime.datetime.now(datetime.timezone.utc)
                .strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            )

        cols = [c for c in _ALL_COLUMNS if c in d]
        placeholders = ', '.join('?' for _ in cols)
        col_names = ', '.join(cols)
        values = tuple(_serialize_value(c, d[c]) for c in cols)

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                f"INSERT INTO sessions ({col_names}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        return d['session_id']

    def get_session(self, session_id: str) -> dict | None:
        """Return a single session dict, or ``None`` if not found."""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return _deserialize_row(row) if row else None

    def get_sessions_by_principal(self, principal: str) -> list[dict]:
        """Return all sessions belonging to *principal*, newest first."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM sessions WHERE principal = ? "
                "ORDER BY created_at DESC",
                (principal,),
            ).fetchall()
        return [_deserialize_row(r) for r in rows]

    def get_all_sessions(self) -> list[dict]:
        """Return every session, newest first."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            ).fetchall()
        return [_deserialize_row(r) for r in rows]

    def update_session(self, session_id: str, updates: dict) -> bool:
        """Apply a partial update to an existing session.

        Returns ``True`` if a row was modified, ``False`` if *session_id*
        was not found.  The ``session_id`` key inside *updates* is silently
        ignored (you cannot change a session's PK).
        """
        safe = {k: v for k, v in updates.items()
                if k in _ALL_COLUMNS and k != 'session_id'}
        if not safe:
            return False

        set_clause = ', '.join(f"{col} = ?" for col in safe)
        values = tuple(_serialize_value(c, v) for c, v in safe.items())

        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                f"UPDATE sessions SET {set_clause} WHERE session_id = ?",
                values + (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Remove a session by id.  Returns ``True`` if it existed."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    # -- aggregate queries --------------------------------------------------

    def count_by_status(self) -> dict:
        """Return ``{status_string: count, ...}`` across all sessions."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM sessions GROUP BY status"
            ).fetchall()
        return {r['status']: r['cnt'] for r in rows}

    def count_by_provider(self) -> dict:
        """Return ``{provider_string: count, ...}`` across all sessions."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT provider, COUNT(*) AS cnt FROM sessions GROUP BY provider"
            ).fetchall()
        return {r['provider']: r['cnt'] for r in rows}

    def count_active_for_principal(self, principal: str) -> int:
        """Count sessions with status in ('starting', 'running') for a user.

        Canister sessions are excluded (they don't count toward per-user
        limits, matching the existing fleet-api.py logic).
        """
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sessions "
                "WHERE principal = ? "
                "  AND status IN ('starting', 'running') "
                "  AND provider != 'canister'",
                (principal,),
            ).fetchone()
        return row['cnt'] if row else 0

    def get_active_sessions(self) -> list[dict]:
        """Return sessions whose status is 'starting' or 'running'."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM sessions "
                "WHERE status IN ('starting', 'running') "
                "ORDER BY created_at DESC"
            ).fetchall()
        return [_deserialize_row(r) for r in rows]

    def cleanup_stale(self, max_age_hours: int = 4) -> int:
        """Reap sessions that have been idle longer than *max_age_hours*.

        A session is considered idle if its ``last_accessed`` (or
        ``created_at`` if ``last_accessed`` is NULL) is older than the
        threshold.  Only sessions with status 'running' or 'starting' are
        reaped.  Canister sessions are excluded (externally managed).

        Reaped sessions are set to status='stopped' (not deleted), matching
        the existing reaper behavior in fleet-api.py.

        Returns the number of sessions reaped.
        """
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=max_age_hours)
        ).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "UPDATE sessions SET status = 'stopped' "
                "WHERE status IN ('starting', 'running') "
                "  AND provider != 'canister' "
                "  AND COALESCE(last_accessed, created_at) < ?",
                (cutoff,),
            )
            conn.commit()
        return cur.rowcount

    # -- migration ----------------------------------------------------------

    def migrate_from_json(self, fleet_json_path: str) -> int:
        """Import sessions from an existing fleet.json file.

        Reads the ``"sessions"`` key from *fleet_json_path* and inserts any
        sessions that do not already exist in the SQLite database (matched
        by ``session_id``).

        Returns the number of sessions imported.
        """
        path = pathlib.Path(fleet_json_path)
        if not path.exists():
            log.warning('migrate_from_json: %s not found', fleet_json_path)
            return 0

        try:
            fleet = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            log.error('migrate_from_json: failed to read %s: %s',
                      fleet_json_path, e)
            return 0

        sessions = fleet.get('sessions', {})
        if not sessions:
            log.info('migrate_from_json: no sessions in %s', fleet_json_path)
            return 0

        imported = 0
        for sid, sdata in sessions.items():
            sdata.setdefault('session_id', sid)
            # Skip if already in the DB
            if self.get_session(sid) is not None:
                continue
            try:
                self.create_session(sdata)
                imported += 1
            except Exception as e:
                log.warning('migrate_from_json: failed to import %s: %s',
                            sid, e)

        log.info('migrate_from_json: imported %d/%d sessions from %s',
                 imported, len(sessions), fleet_json_path)
        return imported

    # -- lifecycle ----------------------------------------------------------

    def close(self):
        """Close the underlying database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_store_instance: SessionStore | None = None
_store_lock = threading.Lock()


def get_store(db_path: str = 'sessions.db') -> SessionStore:
    """Return (and lazily create) the module-level SessionStore singleton.

    The *db_path* argument is only used on the first call; subsequent calls
    return the same instance regardless of what path is passed.
    """
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = SessionStore(db_path)
    return _store_instance


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _self_test():
    """Quick smoke test -- runs when the module is executed directly."""
    import tempfile
    import os

    print('--- SessionStore self-test ---')

    # Use a temp file so we don't pollute the real DB
    fd, tmp_db = tempfile.mkstemp(suffix='.db', prefix='session_store_test_')
    os.close(fd)

    try:
        store = SessionStore(db_path=tmp_db)

        # 1. create
        sid = store.create_session({
            'principal':    'test-principal-abc',
            'template_id':  'dev-ubuntu',
            'display_name': 'Dev Ubuntu',
            'status':       'starting',
            'provider':     'hyperv',
            'resources':    {'cpu': 2, 'memory_gb': 4},
            'persistent':   True,
            'turn_servers': [{'urls': 'turn:example.com', 'username': 'u'}],
        })
        print(f'  create_session -> {sid}')
        assert sid.startswith('ses_'), f'unexpected sid: {sid}'

        # 2. get
        s = store.get_session(sid)
        assert s is not None
        assert s['principal'] == 'test-principal-abc'
        assert s['provider'] == 'hyperv'
        assert s['persistent'] is True
        assert isinstance(s['resources'], dict)
        assert s['resources']['cpu'] == 2
        assert isinstance(s['turn_servers'], list)
        print(f'  get_session    -> OK (principal={s["principal"]})')

        # 3. update
        ok = store.update_session(sid, {
            'status': 'running',
            'ip':     '192.168.1.50',
            'port':   47989,
        })
        assert ok
        s2 = store.get_session(sid)
        assert s2['status'] == 'running'
        assert s2['ip'] == '192.168.1.50'
        assert s2['port'] == 47989
        print(f'  update_session -> OK (status={s2["status"]})')

        # 4. second session for same principal
        sid2 = store.create_session({
            'principal':    'test-principal-abc',
            'template_id':  'win11-pro',
            'display_name': 'Windows 11',
            'status':       'running',
            'provider':     'hyperv',
        })

        # 5. third session for a different principal
        sid3 = store.create_session({
            'principal':    'other-principal-xyz',
            'template_id':  'dev-ubuntu',
            'display_name': 'Dev Ubuntu',
            'status':       'stopped',
            'provider':     'oci',
        })

        # 6. get_sessions_by_principal
        by_p = store.get_sessions_by_principal('test-principal-abc')
        assert len(by_p) == 2
        print(f'  by_principal   -> {len(by_p)} sessions')

        # 7. get_all_sessions
        all_s = store.get_all_sessions()
        assert len(all_s) == 3
        print(f'  get_all        -> {len(all_s)} sessions')

        # 8. count_by_status
        cbs = store.count_by_status()
        assert cbs.get('running') == 2
        assert cbs.get('stopped') == 1
        assert cbs.get('starting') is None  # was updated to running
        print(f'  count_by_status   -> {cbs}')

        # 9. count_by_provider
        cbp = store.count_by_provider()
        assert cbp.get('hyperv') == 2
        assert cbp.get('oci') == 1
        print(f'  count_by_provider -> {cbp}')

        # 10. count_active_for_principal
        active = store.count_active_for_principal('test-principal-abc')
        assert active == 2
        print(f'  active_for_principal -> {active}')

        # 11. get_active_sessions
        actives = store.get_active_sessions()
        assert len(actives) == 2
        print(f'  get_active     -> {len(actives)} sessions')

        # 12. cleanup_stale -- make sid look old
        store.update_session(sid, {
            'last_accessed': '2020-01-01T00:00:00Z',
        })
        reaped = store.cleanup_stale(max_age_hours=1)
        assert reaped == 1
        stale = store.get_session(sid)
        assert stale['status'] == 'stopped'
        print(f'  cleanup_stale  -> reaped {reaped}')

        # 13. delete
        deleted = store.delete_session(sid3)
        assert deleted is True
        assert store.get_session(sid3) is None
        deleted2 = store.delete_session('nonexistent-id')
        assert deleted2 is False
        print(f'  delete_session -> OK')

        # 14. get_session for missing id
        assert store.get_session('no-such-session') is None
        print(f'  get missing    -> None (correct)')

        # 15. update non-existent
        ok = store.update_session('no-such-session', {'status': 'x'})
        assert ok is False
        print(f'  update missing -> False (correct)')

        # 16. migrate_from_json with a temp fleet.json
        fd2, tmp_fleet = tempfile.mkstemp(suffix='.json', prefix='fleet_test_')
        os.close(fd2)
        try:
            import pathlib as _pl
            _pl.Path(tmp_fleet).write_text(json.dumps({
                'sessions': {
                    'ses_migrated001': {
                        'session_id':   'ses_migrated001',
                        'principal':    'migrated-user',
                        'template_id':  'oci-desktop',
                        'display_name': 'OCI Desktop',
                        'status':       'running',
                        'provider':     'oci',
                        'ip':           '10.0.0.5',
                        'port':         8787,
                        'created_at':   '2026-05-10T12:00:00Z',
                    },
                }
            }), encoding='utf-8')

            count = store.migrate_from_json(tmp_fleet)
            assert count == 1
            migrated = store.get_session('ses_migrated001')
            assert migrated is not None
            assert migrated['principal'] == 'migrated-user'
            print(f'  migrate_json   -> imported {count}')

            # Idempotent -- running again should import 0
            count2 = store.migrate_from_json(tmp_fleet)
            assert count2 == 0
            print(f'  migrate again  -> imported {count2} (idempotent)')
        finally:
            os.unlink(tmp_fleet)

        store.close()
        print('--- All tests passed ---')

    finally:
        os.unlink(tmp_db)


if __name__ == '__main__':
    _self_test()


# ============================================================================
# Integration guide -- how fleet-api.py would adopt SessionStore
# ============================================================================
#
# Below are the key changes needed in fleet-api.py.  The pattern is:
#   1. Replace _load_sessions() / _save_session() / _delete_session_record()
#      calls with SessionStore methods.
#   2. Use aggregate helpers instead of manual dict iteration.
#
# These are documentation-only -- fleet-api.py is NOT modified by this file.
#
# ---- Import & init (top of fleet-api.py, after other imports) ----
#
#   from session_store import get_store
#
#   FLEET_DIR     = pathlib.Path(__file__).parent
#   SESSION_DB    = FLEET_DIR / 'sessions.db'
#   _session_store = get_store(str(SESSION_DB))
#
#   # One-time migration from fleet.json (safe to call repeatedly)
#   _session_store.migrate_from_json(str(FLEET_FILE))
#
#
# ---- Replace _load_sessions() calls ----
#
#   # Before:
#   sessions = _load_sessions()
#   session = sessions.get(sid)
#
#   # After:
#   session = _session_store.get_session(sid)
#
#
#   # Before (filter by principal):
#   sessions = _load_sessions()
#   user_sessions = [s for s in sessions.values()
#                    if s.get('principal') == principal]
#
#   # After:
#   user_sessions = _session_store.get_sessions_by_principal(principal)
#
#
#   # Before (all sessions for admin):
#   sessions = _load_sessions()
#   session_list = sorted(sessions.values(),
#                         key=lambda s: s.get('created_at', ''),
#                         reverse=True)
#
#   # After:
#   session_list = _session_store.get_all_sessions()   # already sorted
#
#
# ---- Replace _save_session() calls ----
#
#   # Before (new session):
#   _save_session(sid, session)
#
#   # After:
#   _session_store.create_session(session)
#
#
#   # Before (update existing):
#   session['status'] = 'running'
#   session['ip'] = vm_ip
#   _save_session(sid, session)
#
#   # After:
#   _session_store.update_session(sid, {'status': 'running', 'ip': vm_ip})
#
#
# ---- Replace _delete_session_record() calls ----
#
#   # Before:
#   _delete_session_record(sid)
#
#   # After:
#   _session_store.delete_session(sid)
#
#
# ---- Replace _check_user_session_limit() ----
#
#   # Before:
#   sessions = _load_sessions()
#   user_active = [s for s in sessions.values()
#                  if s.get('principal') == principal
#                  and s.get('status') in ('running', 'starting')
#                  and s.get('provider') != 'canister']
#   if len(user_active) >= SESSION_MAX_PER_USER: ...
#
#   # After:
#   if _session_store.count_active_for_principal(principal) >= SESSION_MAX_PER_USER:
#       ...
#
#
# ---- Replace admin dashboard aggregation ----
#
#   # Before:
#   sessions = _load_sessions()
#   by_status = {}
#   for s in sessions.values():
#       st = s.get('status', 'unknown')
#       by_status[st] = by_status.get(st, 0) + 1
#
#   # After:
#   by_status  = _session_store.count_by_status()
#   by_provider = _session_store.count_by_provider()
#
#
# ---- Replace idle reaper loop ----
#
#   # Before (manual iteration + timestamp parsing):
#   sessions = _load_sessions()
#   for sid, session in list(sessions.items()):
#       ...compare timestamps...
#       session['status'] = 'stopped'
#       _save_session(sid, session)
#
#   # After:
#   reaped = _session_store.cleanup_stale(
#       max_age_hours=SESSION_IDLE_TIMEOUT // 3600
#   )
#   if reaped:
#       log.info('[reaper] Stopped %d idle sessions', reaped)
#
#
# ---- Caddyfile rendering (reads sessions for stream routes) ----
#
#   # Before:
#   for sid, ses in fleet.get('sessions', {}).items():
#       if ses.get('status') != 'running': continue
#       ...
#
#   # After:
#   for ses in _session_store.get_active_sessions():
#       if ses.get('stream_protocol') != 'webrtc': continue
#       sid = ses['session_id']
#       ...
#
#
# ---- Prometheus metrics ----
#
#   # Before:  manual iteration over _load_sessions()
#   # After:
#   by_status   = _session_store.count_by_status()
#   by_provider = _session_store.count_by_provider()
#   active      = _session_store.get_active_sessions()
#   principals  = set(s['principal'] for s in active)

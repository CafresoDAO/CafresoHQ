#!/usr/bin/env python3
"""A search that failed came back as a search that found nothing.

night_runner's two GATHER lookups both read their status into `s` and then
never looked at it:

    s, raw = _self_call(ctx, 'GET', '/brave/search?q=' + ...)
    data = json.loads(raw...)
    results = (data.get('web', {}) or {}).get('results', [])[:6]
    if not results:
        return 'No results.'

    s, raw = _self_call(ctx, 'GET', '/vault/search?q=%s&limit=8' % ...)
    hits = json.loads(raw...).get('hits', [])
    if not hits:
        return 'No matches in vault.'

Every refusal those two doors answer with is a JSON error body — and an
error body has no `web.results` and no `hits`, so both slices came out
empty and both branches reported the cheerful negative. serve.py's own
`_brave_search` answers 401 (no key), 502 (`{"error": "brave: ..."}`) and
forwards Brave's own 429/402 verbatim; `/vault/search` answers 502
(`{"error": "obsidian: ..."}` / `{"error": "oci: ..."}`) and 400.

The night shift runs for hours, unattended, on a free Brave tier. A key
that expired since bedtime, a quota spent by midnight, one rate-limit
burst — and the coworker is told, with authority, that the web has
nothing on the topic. It then files exactly the note it was ordered to
file ("no current sources on <topic>"), the vault gains a confident piece
of fiction, and the run records **errors: 0**. Nothing downstream
contradicts an empty search; the boss reads a clean morning report.

The vault arm is the same lie pointed the other way. The prompt's standing
rule is "Don't re-write notes that already exist — extend them with
VAULT_APPEND instead." A 502 from a shut Obsidian said the vault held no
such note, so the coworker wrote it again, night after night.

This is the sibling of the VAULT_READ fix (a non-404 error body returned as
the note's TEXT), one door over and strictly worse unattended: a shut vault
eventually refuses the mandatory write and the run says so, whereas a failed
search is contradicted by nothing at all.

The fix: both lookups check the status they already fetched, and a non-200
is announced as a failed lookup — the same "<what> failed (NNN): <body>"
spelling the read and write doors already use — never as a finding.

Run: python3 scripts/test_a_search_that_failed_is_not_a_search_that_found_nothing.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as nr          # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


class FakeCtx(object):
    brave_key = 'a-key-that-was-good-at-bedtime'


# Bodies these two doors actually send, taken from serve.py's own handlers
# and from Brave's documented error envelope — not invented.
BRAVE_DOORS = {
    429: (b'{"type": "ErrorResponse", "error": {"id": "x", "status": 429, '
          b'"code": "RATE_LIMITED", "detail": "Too Many Requests"}}',
          'the free tier rate-limiting a night of queries'),
    401: (b'{"error": "no Brave key (set X-Brave-Key header or BRAVE_API_KEY env)"}',
          'a key that expired since bedtime'),
    402: (b'{"type": "ErrorResponse", "error": {"code": "SUBSCRIPTION_TOKEN_INVALID",'
          b' "detail": "quota exceeded"}}', 'a quota spent by midnight'),
    502: (b'{"error": "brave: <urlopen error [Errno 60] Operation timed out>"}',
          'Brave unreachable'),
}

VAULT_DOORS = {
    502: (b'{"error": "obsidian: <urlopen error [Errno 61] Connection refused>"}',
          'a shut Obsidian'),
    400: (b'{"error": "missing q"}', 'a query the vault refuses'),
}


def tool_with(name, arg, status, body):
    """run_tool for one gather tool against a door answering `status`."""
    def fake_self_call(ctx, method, path, b=None, headers=None, timeout=90):
        return status, body

    real = nr._self_call
    nr._self_call = fake_self_call
    try:
        return nr.run_tool(FakeCtx(), name, arg, None)
    finally:
        nr._self_call = real


def drive(replies, search_status, search_body):
    """One run_iteration whose SEARCH hits a door answering search_status
    and whose VAULT_NEW lands fine. Returns (result, tool results seen)."""
    seen = []
    calls = []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if path.startswith('/brave/search'):
            return search_status, search_body
        if method == 'PUT' and path.startswith('/vault/note'):
            return 200, b'{"path": "x", "mode": "write"}'
        return 200, b'{}'

    def fake_llm(ctx, messages, max_tokens=None):
        for m in messages:
            c = m.get('content') or ''
            if m.get('role') == 'user' and c.startswith('TOOL RESULT [') \
                    and c not in seen:
                seen.append(c)
        i = min(len(calls), len(replies) - 1)
        calls.append(1)
        return replies[i], 0

    real_llm, real_call = nr.llm_call, nr._self_call
    nr.llm_call, nr._self_call = fake_llm, fake_self_call
    try:
        res = nr.run_iteration(
            FakeCtx(), {'vaultFolder': 'Research/night', 'topic': 'carrier lead time'}, 0, 3)
    finally:
        nr.llm_call, nr._self_call = real_llm, real_call
    return res, seen


def main():
    print('a search that failed is not a search that found nothing')

    # ── 1. the web door: every refusal says so, none of them says "empty" ──
    for status, (body, what) in sorted(BRAVE_DOORS.items()):
        out = tool_with('SEARCH', 'carrier lead time 2026', status, body)
        check('brave %d (%s) is not reported as an empty web' % (status, what),
              out != 'No results.', repr(out))
        check('...and brave %d says the search failed, with its status' % status,
              out.startswith('Search failed (%d)' % status), repr(out))

    # ── 2. the vault door: the same lie, pointed the other way ────────────
    for status, (body, what) in sorted(VAULT_DOORS.items()):
        out = tool_with('VAULT_SEARCH', 'lead time', status, body)
        check('vault search %d (%s) is not reported as an empty vault'
              % (status, what), out != 'No matches in vault.', repr(out))
        check('...and vault search %d says the search failed, with its status'
              % status, out.startswith('Vault search failed (%d)' % status), repr(out))

    # ── 3. neither sentence can be mistaken for a refused WRITE ───────────
    # run_iteration's whole vault-refusal chain hangs off vault_write_status
    # matching "Vault write failed (NNN)" at the start of the string. A failed
    # LOOKUP must not trip it, or a rate-limited web search would be reported
    # to the boss as a vault outage.
    for nm, arg, body in (('SEARCH', 'q', BRAVE_DOORS[429][0]),
                          ('VAULT_SEARCH', 'q', VAULT_DOORS[502][0])):
        out = tool_with(nm, arg, 502 if nm == 'VAULT_SEARCH' else 429, body)
        check('a failed %s is not read as a refused write' % nm,
              nr.vault_write_status(out) is None, repr(out))

    # ── 4. the coworker is told, in the hop the runner threads back ────────
    # The reproduced night: gather from the web, get the 429 envelope, write
    # the note anyway. The write lands, so nothing else in run_iteration
    # objects — writes: [path], error: None, errors: 0.
    body429 = BRAVE_DOORS[429][0]
    replies = [
        '[SEARCH: carrier lead time 2026]',
        ('[VAULT_NEW: Research/night/carrier-lead-time.md]\n# Carrier lead time\n\n'
         'No current sources exist on this topic.\n[/VAULT_NEW]'),
        'Wrote 1. Next iteration could explore carrier overlap.',
    ]
    res, seen = drive(replies, 429, body429)
    search_results = [c for c in seen if c.startswith('TOOL RESULT [SEARCH]')]
    check('the search hop actually ran', len(search_results) == 1, seen)
    served = (search_results[0].split(':\n', 1)[-1].split('\n\nContinue', 1)[0]
              if search_results else '')
    check('a rate-limited search is not handed over as "No results."',
          served != 'No results.', repr(served))
    check('...it is announced as a failed search, status and all',
          served.startswith('Search failed (429)'), repr(served))
    check('the rest of the iteration is untouched — the write still lands',
          [w['path'] for w in res['writes']] == ['Research/night/carrier-lead-time.md']
          and res['error'] is None,
          [res['writes'], res['error']])

    # ── 5. the doors that already worked still work ───────────────────────
    empty_web = tool_with('SEARCH', 'q', 200, b'{"web": {"results": []}}')
    check('a web that genuinely has nothing still says so',
          empty_web == 'No results.', repr(empty_web))

    null_web = tool_with('SEARCH', 'q', 200, b'{"web": null}')
    check('...and a 200 with a null web block is still the empty answer',
          null_web == 'No results.', repr(null_web))

    hit_web = tool_with('SEARCH', 'q', 200,
                        b'{"web": {"results": [{"title": "T", "url": "https://e/",'
                        b' "description": "D"}]}}')
    check('a real web hit is still formatted as before',
          hit_web == '1. T\n   https://e/\n   D', repr(hit_web))

    empty_vault = tool_with('VAULT_SEARCH', 'q', 200, b'{"hits": []}')
    check('a vault that genuinely has no match still says so',
          empty_vault == 'No matches in vault.', repr(empty_vault))

    hit_vault = tool_with('VAULT_SEARCH', 'q', 200,
                          b'{"hits": [{"path": "a/b.md", "snippet": "s"}]}')
    check('a real vault hit is still formatted as before',
          hit_vault == '• a/b.md\n  s', repr(hit_vault))

    # ── 6. the no-key branch is untouched — it never reaches the door ──────
    class NoKey(object):
        brave_key = ''
    out = nr.run_tool(NoKey(), 'SEARCH', 'q', None)
    check('SEARCH with no server-side Brave key still says exactly that',
          out.startswith('SEARCH is unavailable on the night shift'), repr(out))

    print()
    if FAILS:
        print('FAILED: %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()

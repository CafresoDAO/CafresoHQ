#!/usr/bin/env python3
"""A vault that would not open handed its error page over as the note's text.

night_runner's VAULT_READ read exactly one status out of GET /vault/note —
404 — and returned the response body verbatim for everything else. serve.py's
own note door answers with a JSON error on at least four other statuses:

    502  obsidian shut / OCI bucket unreachable
    415  a filed deck or PDF ("not a text file — open it from the Library")
    400  a path the vault refuses to resolve
    500  a read that blew up

So on a night with the vault down, a coworker told to "extend an existing
note" ran [VAULT_READ: Research/night/lead-time.md] and was handed

    {"error": "obsidian: <urlopen error [Errno 61] Connection refused>"}

as the CONTENTS OF THAT NOTE. It is not an empty read the model can notice
and route around — it is a plausible-looking document, and the next hop
quotes it, summarises it, and VAULT_APPENDs to a note it now believes says
that. The write itself can land fine (a fs vault behind a broken REST probe,
a bucket that reads badly and writes well), so nothing downstream objects:
writes: [path], error: None, errors: 0. The boss wakes up to a clean night
and a note whose research is a stack message.

This is the shape this file's own find_first_tool docstring condemns —
"a quiet night and a broken tool-call format are indistinguishable to the
boss reading the morning report" — with a fabricated deliverable added.

The fix: any non-200 the note door answers is reported to the coworker as a
failed read, in the same "<what> failed (NNN): <body>" spelling the write
side already uses, and never as content.

Run: python3 scripts/test_a_vault_that_would_not_open_is_not_the_note.py
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
    brave_key = ''
    # Granted on purpose: this file exercises VAULT_READ's error-body
    # handling, not #375's grant gate — a fake that failed
    # may_write_to_vault would refuse before ever reaching the door
    # bodies below, for a reason none of these checks are about. Same
    # rationale as the sibling FakeCtx in
    # test_a_write_the_vault_never_heard_is_not_a_note.py.
    agent_tools = ['vault']

    def current_agent_tools(self):
        return self.agent_tools


NOTE_PATH = 'Research/night/lead-time.md'

# Bodies serve.py's own GET /vault/note actually sends for each status —
# copied from the shapes in its _vault() handler, not invented.
DOORS = {
    502: (b'{"error": "obsidian: <urlopen error [Errno 61] Connection refused>"}',
          'a shut Obsidian'),
    415: (b'{"error": "not a text file - open it from the Library, or download '
          b'it", "download": "/vault/file?path=x"}', 'a filed deck'),
    400: (b'{"error": "path escapes vault"}', 'a path the vault refuses'),
    500: (b'{"error": "[Errno 13] Permission denied"}', 'a read that blew up'),
}


def read_with(status, body, arg=NOTE_PATH):
    """run_tool VAULT_READ against a note door that answers `status`."""
    def fake_self_call(ctx, method, path, b=None, headers=None, timeout=90):
        return status, body

    real = nr._self_call
    nr._self_call = fake_self_call
    try:
        return nr.run_tool(FakeCtx(), 'VAULT_READ', arg, None)
    finally:
        nr._self_call = real


def drive(replies, read_status, read_body):
    """One run_iteration whose VAULT_READ hits a door answering read_status
    and whose VAULT_NEW lands fine. Returns (result, tool_results_seen)."""
    seen = []
    calls = []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if method == 'GET' and path.startswith('/vault/note'):
            return read_status, read_body
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
            FakeCtx(), {'vaultFolder': 'Research/night', 'topic': 't'}, 0, 3)
    finally:
        nr.llm_call, nr._self_call = real_llm, real_call
    return res, seen


def main():
    print('a vault that would not open is not the note')

    # ── 1. every shut door says so, and none of them reads as content ─────
    for status, (body, what) in sorted(DOORS.items()):
        out = read_with(status, body)
        decoded = body.decode('utf-8')
        check('%d (%s) is not returned as the note' % (status, what),
              out != decoded, repr(out))
        check('...and %d says the read failed, with its status' % status,
              out.startswith('Vault read failed (%d)' % status), repr(out))

    # ── 2. the coworker is told, in the hop the runner threads back ───────
    # The reproduced night: read a note to extend it, get the 502 page, write
    # anyway. The write lands, so nothing else in run_iteration objects.
    body502 = DOORS[502][0]
    replies = [
        '[VAULT_READ: %s]' % NOTE_PATH,
        ('[VAULT_NEW: Research/night/carriers.md]\n# Carriers\n\n'
         'The lead-time note says: %s\n[/VAULT_NEW]' % body502.decode('utf-8')),
        'Wrote 1. Next iteration could explore carrier overlap.',
    ]
    res, seen = drive(replies, 502, body502)
    read_results = [c for c in seen if c.startswith('TOOL RESULT [VAULT_READ]')]
    check('the read hop actually ran', len(read_results) == 1, seen)
    served = (read_results[0].split(':\n', 1)[-1].split('\n\nContinue', 1)[0]
              if read_results else '')
    check('the vault error page is not handed over as the note',
          served != body502.decode('utf-8'), repr(served))
    check('...it is announced as a failed read, status and all',
          served.startswith('Vault read failed (502)'), repr(served))
    check('the rest of the iteration is untouched — the write still lands',
          [w['path'] for w in res['writes']] == ['Research/night/carriers.md']
          and res['error'] is None,
          [res['writes'], res['error']])

    # ── 3. a shut READ door is not a refused WRITE ───────────────────────
    # run_iteration's whole refusal chain hangs off vault_write_status
    # matching "Vault write failed (NNN)". The new sentence must not be
    # mistaken for one, or a failed read would report the write door shut.
    out = read_with(502, body502)
    check('a failed read is not read as a refused write',
          nr.vault_write_status(out) is None, out)

    # ── 4. the doors that already worked still work ───────────────────────
    missing = read_with(404, b'{"error": "not found"}')
    check('404 still says Not found, in office words',
          missing == 'Not found: ' + NOTE_PATH, repr(missing))

    real_note = '# Lead time\n\nCarrier B is two days faster on the north lane.'
    ok = read_with(200, real_note.encode('utf-8'))
    check('a note that opens is returned verbatim', ok == real_note, repr(ok))

    long_note = 'x' * 5000
    trunc = read_with(200, long_note.encode('utf-8'))
    check('a long note is still truncated the same way',
          trunc == long_note[:4000] + '\n\n…(truncated)', len(trunc))

    print()
    if FAILS:
        print('FAILED: %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()

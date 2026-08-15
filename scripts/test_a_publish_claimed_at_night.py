#!/usr/bin/env python3
"""The morning report carried a publish that never happened.

Measured 2026-08-15 against a canned brain riding the real driver path: a
night iteration whose reply claimed, in prose, no marker anywhere —

    Reviewed the vendor copy and refreshed the landing text overnight. I
    published the updated site — cafreso.com is live with the new vendor
    page. Next iteration could tidy the changelog.

— came back {writes: [], error: None}. errors: 0, a clean night. And
run_iteration's `summary = strip_unsupported_markers(reply)[-300:]` made
the fabricated claim ITSELF the summary, so the Gazette's one line about
the night asserts the boss's site changed while they slept.

The two existing checks bracket this and both miss: find_unsupported_tool
needs a MARKER (a reach, not a claim), and _CLAIMS_A_WRITE_RE knows only
write verbs — a write claim describes something the night shift CAN do,
so it is checked against the writes ledger. A publish claim has no ledger
because there is no tool behind it at night at all: PUBLISH_SITE is in
NIGHT_CANNOT, so the claim is false by construction, before any evidence
is consulted.

The claim shape is anchored the same way #81 anchored markers, because
the night shift is a research agent and its notes legitimately report
other people publishing things: a sentence that OPENS with the bare verb
(the "Wrote 1" status-line shape — third-party mentions carry a subject),
or first person with at most one fixed auxiliary before the verb. What
this deliberately does NOT cover is pinned below with the negatives.

Run: python3 scripts/test_a_publish_claimed_at_night.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import night_runner as nr  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


MEASURED = ('Reviewed the vendor copy and refreshed the landing text '
            'overnight. I published the updated site — cafreso.com is live '
            'with the new vendor page. Next iteration could tidy the changelog.')

PUBLISH_SENTENCE = 'said it published, but nothing went live'


def run_canned(replies, tool_result='ok'):
    """run_iteration with the network unplugged: canned llm replies, a
    stubbed notes index, and a run_tool that always succeeds."""
    queue = list(replies)
    saved = (nr.llm_call, nr._notes_index, nr.run_tool)
    nr.llm_call = lambda ctx, messages, max_tokens=0: (
        (queue.pop(0), 10) if queue else ('', 0))
    nr._notes_index = lambda ctx, folder: []
    nr.run_tool = lambda ctx, name, arg, body: tool_result
    try:
        ctx = nr.NightContext(base_url='http://127.0.0.1:1')
        return nr.run_iteration(ctx, {'id': 's', 'agentId': 'a',
                                      'agentName': 'Vera', 'topic': 't',
                                      'vaultFolder': 'Research/Night'}, 0, 1)
    finally:
        nr.llm_call, nr._notes_index, nr.run_tool = saved


def main():
    print('a publish claimed at night')
    R = nr._CLAIMS_A_PUBLISH_RE

    # ---- the claim shapes ----
    for name, text in [
        ('the measured claim trips it', MEASURED),
        ('first person, plain', 'We deployed the changes to the site overnight.'),
        ("first person, contracted", "I've published it."),
        ('first person, one auxiliary', 'We just launched the refresh.'),
        ('the status-line shape', 'Published the new vendor page.'),
        ('status-line mid-reply', 'Done. Deployed the site update.'),
    ]:
        check(name, bool(R.search(text)), text)

    # ---- reporting is not claiming (§4: the false alarm is the expensive
    # error — every one of these is an honest research note) ----
    for name, text in [
        ('a third party publishing', 'The vendor published a report in 2024.'),
        ('a third party deploying', 'Acme deployed 40 new kiosks last year.'),
        ('reported speech', 'We noticed they published a fix overnight.'),
        ('the verb as adjective', 'Published figures show a 12% rise.'),
        ('a third party launching', 'Their team launched a beta in June.'),
        ("the write claim's own shape", 'Wrote 1. Next iteration could explore pricing.'),
        # Deliberate NON-coverage, pinned so a future reader can tell
        # "decided" from "forgot": a bare state assertion has no publish
        # verb to anchor on, and research prose says "X is now live" about
        # other people's sites constantly. Same call for claims of other
        # undoable deeds — no registry exists to sweep prose shapes from,
        # and each added shape is a fresh chance to call an honest
        # coworker a liar.
        ('a bare state assertion (deliberately uncovered)', 'The site is now live.'),
        ('another deed entirely (deliberately uncovered)', 'We emailed the vendor list to the boss.'),
        # The coordinated form is a recall hole, not an FP guard: "Saved
        # the note and published the site update." is a real fabrication
        # shape, but "the vendor rebranded and launched a new page in
        # June" is honest research prose, and a regex cannot tell a
        # subjectless coordination from a subject three words back. The
        # anchors stay strict; this is the price, pinned.
        ('a coordinated claim (deliberately uncovered)',
         'Saved the note and published the site update.'),
        ('third-party coordination stays quiet',
         'The vendor rebranded and launched a new page in June.'),
    ]:
        check(name, not R.search(text), text)

    # ---- run_iteration wiring ----
    res = run_canned([MEASURED])
    check('the measured night is no longer clean',
          res['error'] == PUBLISH_SENTENCE, res)
    check('the claim still reaches the summary beside the note',
          'published the updated site' in res['summary'], res['summary'])

    res = run_canned(['Compared three vendor quotes; drafting the summary next.'])
    check('an honest night stays clean', res['error'] is None, res)

    res = run_canned(['[VAULT_NEW: Research/Night/note.md]\nDraft summary.\n[/VAULT_NEW]',
                      'Saved the note. Published the site update.'])
    check('a real write does not back a publish claim',
          len(res['writes']) == 1 and res['error'] == PUBLISH_SENTENCE, res)

    res = run_canned(['I published the site refresh.\n[VAULT_READ: Research/notes.md]',
                      'Compared quotes; nothing else tonight.'])
    check('an early hop that lied is not erased by a clean final line',
          res['error'] == PUBLISH_SENTENCE, res)

    res = run_canned(['[PUBLISH_SITE: /site]\nI published the site.'])
    check('a reach outranks a claim — the door sentence wins',
          res['error'] == nr.night_cannot_sentence('PUBLISH_SITE'), res)

    check('the sentence survives the CLI slice',
          len(PUBLISH_SENTENCE) <= nr.NIGHT_ERROR_MAX,
          '%d > %d' % (len(PUBLISH_SENTENCE), nr.NIGHT_ERROR_MAX))

    # ---- structure: every hop is scanned, and no writes gate ----
    src = ROOT.joinpath('night_runner.py').read_text(encoding='utf-8')
    src = re.sub(r'(?m)^\s*#.*$', '', src)
    m = re.search(r'(?m)^\s*elif (.*_CLAIMS_A_PUBLISH_RE.*):', src)
    check('the publish check reads every reply, ungated',
          bool(m) and 'all_replies' in m.group(1) and 'writes' not in m.group(1),
          m.group(0) if m else 'no elif found')

    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

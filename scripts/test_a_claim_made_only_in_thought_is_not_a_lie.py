#!/usr/bin/env python3
"""A status line only THOUGHT about was prosecuted as a claim.

The night shift's default brains are exactly the local models that inline
their chain of thought as `<think>…</think>` in `content` — the file's own
REASONING_TAGS block names the failure class: "an accusation, in the
morning report, for something that never happened." Both tool detectors got
the mask (find_first_tool, find_unsupported_tool: "weighing a tool is not
reaching for one"). The two HONESTY checks never did.

So a think-model that drafted its mandatory status line inside its
reasoning —

    <think>The prompt wants me to end with "Wrote 1. Next iteration could
    explore X" — but I found nothing worth saving tonight, so I must NOT
    say I wrote a note.</think>
    No new findings this iteration; existing notes already cover this.

— and then finished honestly (no claim, no write) was flagged 'said it
saved a note, nothing reached the vault' by _CLAIMS_A_WRITE_RE reading the
RAW reply. Same for _CLAIMS_A_PUBLISH_RE over the raw joined replies ("I
can't say 'I published the site' — that needs the boss awake"). Three such
honest iterations tripped ERROR_STREAK_AUTO_PAUSE and ended the night —
over sentences nobody said.

WHAT THIS PINS

  · a write claim drafted only inside reasoning is not an error
  · a publish claim talked-out-of inside reasoning is not an error
  · a real fabrication OUTSIDE the reasoning block still trips both
    checks — the mask must not become an amnesty
  · run_iteration reads the claim checks through mask_reasoning (source
    pin, so the seam cannot quietly revert)

Run: python3 scripts/test_a_claim_made_only_in_thought_is_not_a_lie.py
"""
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


THOUGHT_WRITE = (
    '<think>The prompt wants me to end with "Wrote 1. Next iteration could '
    'explore X" — but I found nothing worth saving tonight, so I must NOT '
    'say I wrote a note.</think>\n'
    'No new findings this iteration; existing notes already cover this.')

THOUGHT_PUBLISH = (
    "<think>I can't say \"I published the site\" — publishing needs the "
    'boss awake.</think>\n'
    'Compared three vendor quotes; drafting the summary next.')


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
    print('a claim made only in thought is not a lie')

    # ---- the false accusations, ended ----
    res = run_canned([THOUGHT_WRITE])
    check('a write claim drafted only in <think> is not an error',
          res['error'] is None, res)

    res = run_canned([THOUGHT_PUBLISH])
    check('a publish claim talked-out-of in <think> is not an error',
          res['error'] is None, res)

    # An unclosed opener (streaming truncation) masks to end-of-reply the
    # same way — the third _REASONING_RES shape.
    res = run_canned(['Nothing new tonight.\n<think>or should I say "Wrote 1"'])
    check('an unclosed reasoning block cannot claim either',
          res['error'] is None, res)

    # ---- no amnesty: the same sentences SAID are still lies ----
    res = run_canned(['Wrote 1. Next iteration could explore pricing.'])
    check('a spoken write claim with no write is still an error',
          res['error'] == 'said it saved a note, nothing reached the vault', res)

    res = run_canned(['<think>Careful here.</think>\nI published the site refresh.'])
    check('a spoken publish claim beside real reasoning still trips',
          res['error'] == 'said it published, but nothing went live', res)

    # ---- source pin: the seam itself ----
    src = (ROOT / 'night_runner.py').read_text(encoding='utf-8')
    check('run_iteration joins the replies through mask_reasoning',
          "mask_reasoning('\\n'.join(replies))" in src)
    # This pin used to read `_CLAIMS_A_WRITE_RE.search(last_reply)` and
    # `last_reply = mask_reasoning(reply or '')`. That spelling pinned TWO
    # properties at once: the mask (which is what this file is about) and
    # the SCOPE — final reply only — which turned out to be the bug #302
    # fixed: a write claim made in a non-final hop was never checked at
    # all, while the publish check one branch up reads every hop. The mask
    # is still pinned, over the joined replies the check now reads.
    check('the write-claim check reads the masked replies',
          '_CLAIMS_A_WRITE_RE.search(all_replies)' in src
          and "all_replies = mask_reasoning('\\n'.join(replies))" in src)

    print()
    if FAILS:
        print('FAILED: %d check(s)' % len(FAILS))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()

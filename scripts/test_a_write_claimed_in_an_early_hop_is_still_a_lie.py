#!/usr/bin/env python3
"""A night-shift write claim made before the last hop was never checked.

`run_iteration` ends every iteration with one if/elif chain of honesty
checks. Three of them read the coworker's prose, and until #302 they did
not agree on how much of it to read:

    reached  = find_unsupported_tool(all_replies)   # every hop
    _CLAIMS_A_PUBLISH_RE.search(all_replies)        # every hop
    _CLAIMS_A_WRITE_RE.search(last_reply)           # the FINAL hop only

The publish check's own comment gives the reason for its scope — "every
hop's reply, not just the last, for the same reason the marker scan above
reads them all: a hop that lied and a hop that reached are equally absent
from a final status line." That reason is exactly as true of a write
claim, and the write check was the one site it never reached.

The hole is not hypothetical: the hop loop only stops when a reply carries
NO tool marker, so any reply that carries one is by construction not the
last. A coworker that says "I saved the note to Research/Night/pricing.md"
in the same breath as a `[VAULT_SEARCH: …]` marker — which writes nothing
— and then closes the next hop with a blameless "Next iteration could
explore competitor tiers." is recorded as a clean night: writes [], errors
0, lastError ''. The boss wakes to a morning report asserting a note the
vault never saw. Swap that one sentence for "I published the pricing page
update" and the SAME transcript is caught, one branch up, purely because
that branch reads `all_replies`.

WHAT THIS PINS

  · a write claim in a non-final hop, with an empty writes ledger, is an
    error — in the exact fabricated wording the final-hop case already used
  · the write check and the publish check agree on scope: the same
    transcript shape is caught for both verbs
  · the ledger gate still rules: a hop that claimed early and then really
    wrote is NOT accused
  · a refused write still outranks the claim (the office does not blame a
    coworker for its own shut door)
  · a claim drafted only inside <think> is still not a lie (#205's mask
    survives the wider scope)
  · a quiet, honest night is still not an error
  · source pin: the write check reads the joined replies

Run: python3 scripts/test_a_write_claimed_in_an_early_hop_is_still_a_lie.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import night_runner as nr  # noqa: E402

FAILS = []
WROTE_LIE = 'said it saved a note, nothing reached the vault'
PUBLISH_LIE = 'said it published, but nothing went live'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_canned(replies, tool_result='No matches in vault.'):
    """The real run_iteration with the network unplugged: canned llm
    replies, a stubbed notes index, and a run_tool with a fixed answer.
    Same harness as test_a_claim_made_only_in_thought_is_not_a_lie.py."""
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


# A hop that carries a marker is never the final hop — that is what makes
# this shape reachable at all. VAULT_SEARCH writes nothing, so the ledger
# stays empty behind the claim.
EARLY_WRITE_CLAIM = ('Checked what is already filed. [VAULT_SEARCH: pricing] '
                     'I saved the note to Research/Night/pricing.md.')
EARLY_PUBLISH_CLAIM = ('Checked what is already filed. [VAULT_SEARCH: pricing] '
                       'I published the pricing page update.')
CLOSING = 'Next iteration could explore competitor tiers.'

# A real note landing, in a block-form VAULT_NEW the runner's own grammar
# accepts, after an early hop that already claimed the write.
REAL_WRITE = ('I saved the note.\n[VAULT_NEW: Research/Night/pricing.md]\n'
              '# Pricing\n\nbody\n[/VAULT_NEW]')


def main():
    print('a write claimed in an early hop is still a lie')

    # ---- the hole ----
    res = run_canned([EARLY_WRITE_CLAIM, CLOSING])
    check('a write claim in a non-final hop, with nothing in the ledger, is an error',
          res['error'] == WROTE_LIE, res)
    check('...and the writes ledger really is empty behind it',
          res['writes'] == [], res)

    # ---- the twin that was already caught, same transcript shape ----
    res = run_canned([EARLY_PUBLISH_CLAIM, CLOSING])
    check('the publish twin of the same transcript is caught too',
          res['error'] == PUBLISH_LIE, res)

    # ---- the final-hop case #205 already covered must not regress ----
    res = run_canned(['Wrote 1. Next iteration could explore pricing.'])
    check('a spoken write claim in the only hop is still an error',
          res['error'] == WROTE_LIE, res)

    # ---- the ledger gate is what makes the wider scope safe ----
    res = run_canned([EARLY_WRITE_CLAIM, REAL_WRITE, CLOSING],
                     tool_result='Wrote 12 chars -> Research/Night/pricing.md')
    check('a hop that claimed early and then really wrote is not accused',
          res['error'] is None, res)
    check('...and that write is in the ledger',
          [w['path'] for w in res['writes']] == ['Research/Night/pricing.md'], res)

    # ---- a shut vault is the office's fault, not the coworker's ----
    res = run_canned([REAL_WRITE, CLOSING],
                     tool_result='Vault write failed (502): {"error": "obsidian"}')
    check('a refused write outranks the claim check',
          res['error'] and res['error'] != WROTE_LIE, res)

    # ---- #205's mask survives the wider scope ----
    res = run_canned(
        ['<think>The prompt wants "Wrote 1" but I found nothing worth saving, '
         'so I must NOT say I wrote a note.</think>\n'
         'Checking the vault. [VAULT_SEARCH: pricing]',
         'No new findings this iteration.'])
    check('a write claim drafted only in <think>, in an early hop, is not an error',
          res['error'] is None, res)

    # ---- a quiet night is not an error ----
    res = run_canned(['Checking. [VAULT_SEARCH: pricing]',
                      'Nothing new tonight; existing notes cover this.'])
    check('an honest hop chain with no claim and no write is not an error',
          res['error'] is None, res)

    # ---- third-party reporting is still not a claim (the expensive error) ----
    res = run_canned(['Reading around. [VAULT_SEARCH: pricing] '
                      'The vendor published a report in 2024.',
                      'Nothing worth filing yet.'])
    check('a vendor publishing something is not the coworker claiming it',
          res['error'] is None, res)

    # ---- source pin: scope, with comments stripped so this file's own
    #      prose about the old spelling cannot answer for the code ----
    src = (ROOT / 'night_runner.py').read_text(encoding='utf-8')
    code = '\n'.join(re.sub(r'(?<!["\'])#.*$', '', ln) for ln in src.splitlines())
    check('the write-claim check reads the joined replies',
          '_CLAIMS_A_WRITE_RE.search(all_replies)' in code, 'scope reverted')
    check('no last-reply-only scope is left behind',
          '_CLAIMS_A_WRITE_RE.search(last_reply)' not in code)
    check('the joined replies are still masked (the #205 seam)',
          "all_replies = mask_reasoning('\\n'.join(replies))" in code)

    print()
    if FAILS:
        print('FAILED: %d check(s)' % len(FAILS))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()

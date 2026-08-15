#!/usr/bin/env python3
"""The chief of staff was handed a coworker's failure notes.

Reproduced 2026-08-15 on a throwaway office (port 9261) pointed at a canned
brain (9236). Everything in ceoStream's no-call branch had been written for
a hire, and the chief of staff is not one.

Asked "what's the price of cycles today?" with a reply reaching for a tool
it does not hold, the office said about ITSELF:

    _(they reached for Web Search, which they don't have — turn it on from
      their card in Settings → Roster and ask again.)_

"They" casts the speaker as a third party, so the boss reads it as a
coworker having failed. And there is no card: the Roster renders
`agents.map(...)`, and opening it live on that office listed Vera and Kip
and nobody else.

The sibling branch was worse. On an empty reply:

    _(nothing came back from them this time. If they are on a free brain
      this usually means you asked for too much at once — try **Settings →
      Connections → Coworker capability → "Lite"**, or give them a smaller
      job.)_

Three wrong things. The control is labelled "Agent capability", not
"Coworker capability". It renders only when `s.provider === 'hermes'` — so
it is hidden in exactly the free-brain case the sentence invokes. Measured:
with the office on lmstudio, Settings → Connections was opened and the only
occurrence of the word "capability" anywhere on the screen was the note
itself, bleeding through from the chat behind the modal.

And the third hole, the same one #67 closed for coworkers, still open here.
Prose plus an ungranted marker produced:

    CafresoHQ  Sure — let me pull the current figure for you.

No figure, no note. `stripBlocks` removed the marker and the office
endorsed a promise it knew could not be kept (§4).

The doors that ARE real: `ceoTools` is gated on
`TOOL_REGISTRY.search.requires()` and `isVaultReady`, and both switches
live on one screen — Settings → Connections, as the BRAVE WEB SEARCH and
MARKDOWN VAULT panels, both confirmed present on the reproducing office.
Everything else the office might reach for is not a switch it can be given
at all, so §7's way forward there is a coworker, not a setting.

Verified live after the fix, same drive:

    _(I reached for Web Search, which isn't switched on yet — you can turn
      it on in Settings → Connections, then ask me again.)_

Run: python3 scripts/test_the_office_names_its_own_door.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
PROVIDERS = (ROOT / 'modals' / 'providers.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. The comments written with this fix quote both
    wrong sentences in full, Roster card and "Coworker capability" and all."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0.

    Bounded by structure, not by a character count or a `find` from some
    nearby string — both of those slide onto a neighbouring function and
    report a confident false statement about code they never read."""
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('the office names its own door')
    code = strip_comments(RUNTIME)
    ceo = brace_lift(code, 'async function ceoStream(')
    note = brace_lift(code, 'function ceoReachedForNote(')
    templates = re.findall(r'`_\(([^`]*)\)_`', note)
    # Every sentence the chief of staff can emit from its no-call branch,
    # wherever it is written. Checking the templates alone would miss a
    # sentence inlined into the branch, which is how the Roster copy got
    # there in the first place.
    ceo_says = re.findall(r"emit\(\s*(?:'([^']*)'|\"([^\"]*)\"|`([^`]*)`)", ceo)
    ceo_says = [a or b or c for a, b, c in ceo_says]

    # ── 1. the wrong doors are gone ─────────────────────────────────────
    # The Roster renders `agents.map(...)` — the office is not a hire, so
    # there is no card to send anyone to.
    check('the office has its own reach sentence',
          'function ceoReachedForNote(' in code,
          '— until this existed, ceoStream emitted the coworker copy verbatim')
    # The door map counts as a sentence: whatever is in it gets interpolated
    # into one. Fire-testing caught this — an arm that pointed CEO_DOORS at
    # the Roster left every template clean and this check green.
    doors_src = re.search(r'const CEO_DOORS = \{([\s\S]*?)\};', code)
    check('...and it never sends the boss to a Roster card',
          not any('Roster' in t for t in templates)
          and not any('their card' in t for t in templates)
          and doors_src and 'Roster' not in doors_src.group(1),
          [templates, doors_src and doors_src.group(1),
           '— the Roster lists hires; the chief of staff is not '
           'one of them, so that trip finds nothing'])
    check('...nor does anything else the chief of staff says',
          not any('Roster' in s for s in ceo_says),
          [ceo_says, '— including any sentence inlined into the branch '
           'rather than routed through the note'])
    check('the roster really is hires-only',
          re.search(r'agents\.map\(a =>', SETTINGS),
          '— if the office ever gets a card there, this ticket reopens and '
          'this check is the thing that should notice')

    # ── 2. the capability door, which never existed under that name ─────
    # `code`, not RUNTIME: the comment written with this fix quotes the old
    # sentence in full so the next reader knows why the wording moved.
    check('"Coworker capability" is gone',
          'Coworker capability' not in code,
          '— the control is labelled "Agent capability"; that exact string '
          'appeared nowhere in the product except the sentence naming it')
    check('...and the office no longer sends a free brain to a Hermes-only control',
          not any('capability' in s.lower() for s in ceo_says),
          [ceo_says, '— it renders under `s.provider === \'hermes\'`, so it '
           'is hidden in precisely the case the old sentence invoked'])
    check('that control is still Hermes-gated (the reason the sentence was wrong)',
          re.search(r"s\.provider === 'hermes'[\s\S]{0,600}?Agent capability",
                    PROVIDERS),
          '— if it ever becomes unconditional this finding changes shape')

    # ── 3. the office speaks as itself ──────────────────────────────────
    # `from: 'ceo'` renders these as CafresoHQ talking. Third person makes
    # the boss go looking for a coworker who was never involved.
    third = [t for t in templates + ceo_says
             if re.search(r'\b(they|them|their)\b', t, re.I)]
    check('the office describes itself in the first person',
          not third,
          [third, '— "they reached for Web Search" reads as a coworker '
           'having failed; it was the office describing its own reach'])
    check('...and says so plainly',
          all(re.search(r'\bI\b|\bme\b|\bmy\b', t) for t in templates),
          templates)

    # ── 4. the doors it does name are real ──────────────────────────────
    doors = re.search(r'const CEO_DOORS = \{([\s\S]*?)\};', code)
    check('the office keeps a door map of its own',
          doors, '— the coworker door is a card; the office door is a screen')
    named = sorted(set(re.findall(r"'(Settings → [^']+)'", doors.group(1)))) if doors else []
    check('...and every door it names is a real settings screen',
          named and all(
              re.search(r"id: '" + {'Settings → Connections': 'connections'}.get(d, '\x00') + "'",
                        SETTINGS)
              for d in named),
          [named, '— checked against SETTINGS_TABS, not against memory'])
    check('...and that screen is where its two tools actually switch on',
          re.search(r'<BraveTab />', SETTINGS) and re.search(r'<VaultTab />', SETTINGS),
          '— ceoTools is gated on search.requires() (braveEnabled+braveKey) '
          'and isVaultReady; both panels render in the Connections tab')

    # ── 5. §7 — every sentence leaves a way forward ─────────────────────
    # Per TEMPLATE, not per function: a sibling branch still carrying the
    # phrase is how three fire arms went uncaught on the last ticket.
    check('the note has one sentence per situation, and only three',
          len(templates) == 3,
          [len(templates), '— switchable, not switchable, and both at once'])
    # The door name is interpolated (`${doors.join(...)}`), so a literal
    # "Settings → " match here would only ever find the sentences that
    # hard-code one — which is the thing this ticket removed.
    check('every one of them leaves a way forward (§7)',
          templates and all(
              ('${doors' in t) or ('@-mention' in t) for t in templates),
          [templates, '— one honest sentence PLUS a way forward'])
    check('...and the ungrantable one offers a coworker, not a setting',
          templates and '@-mention' in templates[-1]
          and 'Settings → ' not in templates[-1],
          [templates[-1:], '— there is no switch that gives the office a '
           'shell, so naming any screen here would be a second wrong door'])

    # ── 6. one classifier, not a second copy of the regexes ─────────────
    check('the group id has one home',
          'function toolClaimGroup(' in code
          and re.search(r'function toolClaimLabel\([\s\S]{0,200}?toolClaimGroup\(', code),
          '— toolClaimLabel asks the same question one step later; two '
          'copies of those five regexes is the drift this file keeps paying for')
    # Both the split AND the door lookup must go through it — a `re.search`
    # for one occurrence passed while the split ran a private regex, because
    # the lookup below it still matched.
    check('...and the office door map reads it rather than re-testing names',
          len(re.findall(r'CEO_DOORS\[toolClaimGroup\(n\)\]', note)) == 2
          and not re.search(r'/\^?[A-Za-z_(\[|].*?/i?\.test', note),
          [note, '— a private regex here would answer "is this web work?" '
           'differently from the coworker path on the very same marker'])

    # ── 7. the three structural holes, ported from #67 ──────────────────
    check('a reach is remembered across tool hops',
          re.search(r'const reachedFor = new Set\(\);[\s\S]{0,400}?for \(let hop = 0;', ceo),
          '— only the last hop\'s buffer reaches the branch')
    add_at, call_at = ceo.find('reachedFor.add(n)'), ceo.find('if (!call) {')
    check('...and recorded before the tool-call check, not after',
          add_at >= 0 and call_at >= 0 and add_at < call_at,
          [add_at, call_at, '— a hop that DID fire a tool never reaches the '
           'branch below, and can still contain a second, ungranted reach'])
    check('bracket markers count, not just harmony orphans',
          'openedMarkers(buf, KNOWN_MARKERS)' in ceo,
          '— the bracket form is what most local brains emit')
    check('...and the empty path counts them too',
          re.search(r'\.\.\.orphans\.map\(o => o\.tool\), \.\.\.reachedFor', ceo),
          '— an empty reply carrying only a bracket marker fell through to '
          '"nothing came back"')
    check('a reach is reported even when the office also wrote prose',
          re.search(r'\}\s*else if \(reachedFor\.size\) \{', ceo),
          '— the reproduced case: "Sure — let me pull the current figure for '
          'you." arrived alone, with no figure and no note')
    check('both branches call the one sentence',
          len(re.findall(r'ceoReachedForNote\(', ceo)) == 2,
          [len(re.findall(r'ceoReachedForNote\(', ceo)),
           '— the empty-reply branch and the wrote-prose-anyway branch'])
    check('...and neither keeps its own copy of it',
          'I reached for' not in ceo,
          '— a hand-copied boss-facing sentence is how this one drifted out '
          'of step with the coworker copy in the first place')

    # ── 8. run it ───────────────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the sentence checks need it')
    else:
        js = ''
        # ceoReachedForNote reaches for four module-level things. Lifting
        # them by brace/paren match keeps the real logic under test; only
        # TOOLS_CATALOG is stubbed, and with the labels the product ships.
        js += "const TOOLS_CATALOG = [{id:'web',label:'Web Search'},"
        js += "{id:'vault',label:'Vault'},{id:'img',label:'Image Gen'}];\n"
        js += re.search(r'const ELEVATION_DOOR = .*?;', code).group(0) + '\n'
        js += re.search(r'const TOOL_CLAIM_GROUPS = \[[\s\S]*?\];', code).group(0) + '\n'
        js += re.search(r'const CEO_DOORS = \{[\s\S]*?\};', code).group(0) + '\n'
        for fn in ('function toolClaimGroup(', 'function toolClaimLabel(',
                   'function claimNeedsMediaDoor(', 'function claimLabels(',
                   'function ceoReachedForNote('):
            js += brace_lift(code, fn) + '\n'
        js += r'''
const R = {
  // The reproduced reach. Pre-fix: "they … their card in Settings → Roster".
  search:  ceoReachedForNote(['SEARCH']),
  vault:   ceoReachedForNote(['VAULT_NEW']),
  // Two switchable families behind ONE screen — named once, not twice.
  both:    ceoReachedForNote(['SEARCH', 'VAULT_READ']),
  // Not a switch the office can be handed. No settings screen may appear.
  shell:   ceoReachedForNote(['BASH']),
  file:    ceoReachedForNote(['FILE_WRITE']),
  img:     ceoReachedForNote(['GENERATE_IMAGE']),
  // One reply reaching for both kinds: the case a single door gets wrong.
  mixed:   ceoReachedForNote(['SEARCH', 'BASH']),
  // Routing markers have no door and are already spoken for elsewhere.
  dm:      ceoReachedForNote(['DM_TO']),
  handoff: ceoReachedForNote(['HANDOFF_TO', 'HIRE_AGENT']),
  empty:   ceoReachedForNote([]),
  // A marker the office has never heard of is not a capability question.
  unknown: ceoReachedForNote(['SPROCKETIFY']),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the sentence harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('a reach for web work names Connections',
                  'Settings → Connections' in R['search']
                  and 'Web Search' in R['search'],
                  [R['search'], '— this is the reproduced sentence'])
            check('...in the first person, with no card and no coworker',
                  R['search'].startswith('_(I reached for ')
                  and 'Roster' not in R['search']
                  and 'they' not in R['search'],
                  R['search'])
            check('a reach for the vault names the same screen',
                  'Settings → Connections' in R['vault'], R['vault'])
            check('two families behind one screen name it once',
                  R['both'].count('Settings → Connections') == 1,
                  [R['both'], '— both switches are panels on the same tab'])
            check('a reach for a shell names no settings screen at all',
                  'Settings' not in R['shell'] and '@-mention' in R['shell'],
                  [R['shell'], '— no switch grants the office a shell, so '
                   'any screen named here is a second wrong door'])
            check('...and so does file work',
                  'Settings' not in R['file'] and '@-mention' in R['file'],
                  R['file'])
            check('...and image work',
                  'Settings' not in R['img'] and '@-mention' in R['img'],
                  [R['img'], '— Settings → Media picks a provider for a '
                   'coworker who HAS the box; the office has no box'])
            check('a reply reaching for both kinds splits them',
                  'Settings → Connections' in R['mixed']
                  and '@-mention' in R['mixed']
                  and R['mixed'].index('Settings → Connections')
                      < R['mixed'].index('@-mention'),
                  [R['mixed'], '— the switchable half gets its switch, the '
                   'other half gets a coworker; one door for both is wrong '
                   'for whichever half it is not about'])
            check('...and names each family exactly once',
                  R['mixed'].count('Web Search') == 1
                  and R['mixed'].count('File & shell access') == 1,
                  R['mixed'])
            check('a routing marker says nothing',
                  R['dm'] == '' and R['handoff'] == '',
                  [R['dm'], R['handoff'], '— unsentHandoff and unsentBlocks '
                   'already speak for these on the same buffer'])
            check('nothing to report is silence, not a shrug',
                  R['empty'] == '' and R['unknown'] == '',
                  [R['empty'], R['unknown'], '— printing a raw marker name '
                   'to fill the gap is the habit claimLabels exists to break'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

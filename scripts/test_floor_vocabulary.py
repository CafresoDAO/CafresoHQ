#!/usr/bin/env python3
"""Tripwire: the office's internal vocabulary stays out of the office.

§6 is binding for UI copy, and it kept getting re-broken because the same
words live in three layers and I only ever fixed the one I was looking at:

  1. the PROMPT tells the model its colleagues are "sub-agents"
  2. the model says "sub-agent" back to the boss
  3. the UI copy says it too

Scrubbing layer 3 four separate times taught the lesson: the word has to be
banned everywhere it can reach a person, including the prompt that teaches
it. Each of these was live on the floor at some point:

  · "Sub-agent model swapped: ollama:llama3.1 → claudecode:sonnet"
  · "🛡 X is now elevated. Their next dispatch will have file/shell access."
  · "cap 220 tok/each · 90s timeout"
  · "iter 3 · 5 notes · 12,345 tok"

Only STRING LITERALS are checked, so `a.elevated` and `isElevated` are
untouched — the property is the mechanism, the prose is the claim. ALL-CAPS
protocol tokens are stripped before matching, because SPAWN_SUBAGENT is wire
format the parser and the models both depend on and must NOT be renamed.

Not a substitute for judgement — it catches these words, not the idea.
Run: python3 scripts/test_floor_vocabulary.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Everything a person can read: the views the boss looks at, and the prompt
# text the coworker reads and then repeats to them.
GLOBS = ['ui/*.jsx', 'views/*.jsx', 'app/*.jsx', 'modals/*.jsx',
         'app.jsx', 'features.jsx', 'missions.jsx', 'hq-runtime.jsx',
         'agent_runner.jsx']

BANNED = [
    (re.compile(r'sub-?agents?\b', re.I),
     'the office calls these helpers. A coworker is hired and stays; an '
     'assistant is a coworker\'s hire; a helper is one-shot. Rename the prose '
     '— never the SPAWN_SUBAGENT token.'),
    (re.compile(r'\belevat(ed|ion)\b', re.I),
     'names the mechanism, not the thing the boss decides. Say "file and '
     'shell access" — vagueness on a permission grant is worse than a '
     'slightly technical word.'),
    (re.compile(r'\btok\b|\btok/'),
     'a machine unit on a human surface. Say "effort", or put the exact '
     'figure in a tooltip (see EFFORT_TIP / OFFICE_EFFORT_TIP in cast.jsx).'),
    # `iter` is here because banning only the full word missed the shorter,
    # WORSE form: the Gazette shipped "3 iter · 5 notes" for months. An
    # abbreviation of a banned word is not a loophole — it is the same jargon
    # with the readable part removed.
    (re.compile(r'\biterations?\b|\biters?\b', re.I),
     'the Night Shift board calls these rounds.'),
]

# "agent" is the hardest one, so it is scoped rather than banned outright.
#
# CONFIG surfaces are exempt on purpose: Settings and the provider picker are
# where you choose a runtime, and naming the real thing is the point there —
# the same reasoning that leaves raw model IDs visible in Settings while
# banning them from the floor.
CONFIG_SURFACES = {'modals/settings.jsx', 'modals/providers.jsx',
                   'views/terminal.jsx'}

# …and a few places where "agent" is a genuine technical noun rather than a
# person: what is installed on the machine, a category of CLI tool, a folder
# path. Matched as substrings against the display string.
AGENT_OK = (
    'agent runtimes',      # which runtimes exist on this machine
    'CLI agent',           # a category of tool, not a colleague
    'Agents/<your name>',  # the private-notes folder path
    'Agents/',
)

AGENT_RE = re.compile(r'\bagents?\b', re.I)
AGENT_WHY = ('means the person here — the office calls them coworkers. If it '
             'genuinely means a runtime, a CLI tool or a folder path, add it '
             'to AGENT_OK with a note.')

# Files allowed to NAME the banned words while explaining why they were
# removed. Their comments are stripped anyway; this covers the rare case of
# a word inside a string that is documentation (e.g. a test fixture).
ALLOW = set()


def blank_comments(text):
    """A banned word quoted in a comment is documentation, not a claim on
    screen. Blanks comments IN PLACE (newlines kept) so reported line
    numbers still point at the real line — the first version stripped them
    and every line number it printed was wrong."""
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    return re.sub(r'^\s*//.*$', blank, text, flags=re.M)


_STR = r"""(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)"""

# Only strings in positions that actually REACH A PERSON. The first version
# scanned every string literal and drowned in CSS class names
# ("elevated-badge"), a syntax-highlighter's own regex, and className
# template literals — none of which anybody reads. A property is the
# mechanism; these positions are the claim.
# ONE list, both syntaxes. This was two arms with two different key lists —
# a colon form that knew about `hint`, `body` and `label`, and an equals form
# that knew only `title|placeholder|aria-label`. So the same word was banned
# in `hint: '…'` and allowed in `emptyHint="…"`, and the Team inbox sat there
# reading "Nothing pending. Approvals, agent activity, and receipts will land
# here." The rule had the exact defect it exists to catch: two lists that had
# to agree by hand, and only one of them ever moved.
#
# `body` earned its place the hard way — the entire onboarding tour, both
# variants, 15 of its 17 strings, taught every new boss "agents" and
# "sub-agent" on the first screen under titles that already said "coworkers".
DISPLAY_KEYS = ('text|desc|label|hint|doc|docShort|summary|placeholder|title|'
                'body|subtitle|empty|emptySub|emptyHint|cta|hireTitle|tip|aria-label')

DISPLAY_RE = re.compile(r'\b(?:' + DISPLAY_KEYS + r')\s*(?::|=)\s*\{?(' + _STR + r')', re.S)

# JSX text nodes: >Some words< — the other way copy reaches the screen.
JSX_TEXT_RE = re.compile(r'>\s*([A-Za-z][^<>{}]{2,120}?)\s*<')

# …and the third way, which is how "3 iter · 5 notes" stayed on screen: text
# sandwiched BETWEEN two interpolations — `{r.iterations} iter · {n} notes`.
# It never touches a `>` or a `<`, so both patterns above walk straight past
# it, even though it is as visible as any other label.
#
# Excluding code punctuation and requiring the fragment to read like prose (a
# space or a separator dot) is what keeps this from matching every `import …
# from` line and every object literal. A few object literals survive that
# filter; they are harmless, because a scanned fragment only FAILS when it
# contains a banned word.
JSX_BETWEEN_RE = re.compile(r'\}([^\n<>{}=;\'"`()\[\]]{2,120}?)\{')


def _reads_like_copy(t):
    return bool(re.search(r'[A-Za-z]', t)) and (' ' in t.strip() or '·' in t)


# The fourth way copy reaches a person, and the loudest: a blocking dialog.
# These are not props and not JSX text, so every pattern above walked past
# them — which is how "/who-can" shipped with the label "find the right
# coworker for a job" sitting one line above a prompt reading "Find agents
# who can do…". Same command, two vocabularies.
DIALOG_RE = re.compile(r'window\.(?:confirm|alert|prompt)\s*\(\s*(' + _STR + r')', re.S)

# The fifth way, and the one that hid on an APPROVAL CARD: a fallback. Not a
# display prop and not JSX text — a default that only appears when the real
# value is missing, which is exactly when nobody is looking.
#
# `by: d.agentName || 'agent'` sat on the card where the boss stamps a
# publish to the public internet, and the emitter and the renderer defaulted
# to the same banned word, so all three layers agreed on the wrong noun.
#
# Slug-building is excluded, and it is recognisable rather than guessed at:
# `String(agent.name || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_')` is making
# an identifier, not a sentence. Those were the only three false positives in
# 169 fallbacks, and each carries that replace on the same line.
FALLBACK_RE = re.compile(r"\|\|\s*('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")")
SLUG_RE = re.compile(r"replace\(\s*/\[\^A-Za-z0-9_-\]")


def _fallback_spots(body):
    for m in FALLBACK_RE.finditer(body):
        inner = m.group(1)[1:-1]
        if len(inner) < 2 or not re.search(r'[A-Za-z]', inner):
            continue
        ls = body.rfind('\n', 0, m.start(1)) + 1
        le = body.find('\n', m.start(1))
        if SLUG_RE.search(body[ls:le if le > 0 else len(body)]):
            continue          # building an id, not copy
        yield m.start(1), m.group(1)


# The sixth surface, and the one this whole test was written about: the
# PROMPT ITSELF. The docstring above says layer 1 is "the prompt tells the
# model its colleagues are sub-agents" — and the rule scanned prompt PROSE
# built inline, while missing prompts assigned to a key or pushed through a
# setter. Two were still live:
#
#   · the transient helper's systemPrompt, "You are a transient one-shot
#     sub-agent… You CANNOT spawn further sub-agents"
#   · the hire modal's DEFAULT job description, "You are a helpful
#     sub-agent" — which the model reads AND the boss sees in the job
#     description field while hiring, so it leaks on both layers at once
#
# 12 prompt literals in the codebase, 2 of them wrong. Protocol tokens are
# stripped by TOKEN_RE as everywhere else, so SPAWN_SUBAGENT stays safe.
PROMPT_RE = re.compile(
    r'\b(?:systemPrompt|persona|prompt)\s*:\s*(' + _STR + r')'
    r'|\bset(?:System)?Prompt\s*\(\s*(' + _STR + r')', re.S | re.I)


def _prompt_spots(body):
    for m in PROMPT_RE.finditer(body):
        raw = m.group(1) or m.group(2)
        yield (m.start(1) if m.group(1) else m.start(2)), raw


# SPAWN_SUBAGENT, HIRE_AGENT, MEMORY_LIST… — the wire protocol. Stripped
# before matching so the tokens can never trip this test.
TOKEN_RE = re.compile(r'\b[A-Z][A-Z0-9_]{3,}\b')

# `${a.elevated ? ' · has file and shell access' : ''}` — the CONDITION is a
# property, the branches are prose. Drop the expression head but keep any
# quoted strings inside it, or correct copy gets flagged for the property
# that chooses it.
INTERP_RE = re.compile(r'\$\{([^{}]*)\}')


def drop_interpolations(text):
    def keep_strings(m):
        return ' '.join(re.findall(r"'[^']*'|\"[^\"]*\"", m.group(1)))
    return INTERP_RE.sub(keep_strings, text)


def main():
    print('floor vocabulary')
    fails = []
    checked = 0
    for glob in GLOBS:
        for path in sorted(ROOT.glob(glob)):
            rel = str(path.relative_to(ROOT))
            if rel in ALLOW:
                continue
            body = blank_comments(path.read_text(encoding='utf-8'))
            checked += 1
            spots = [(m.start(), m.group(0)) for m in DISPLAY_RE.finditer(body)]
            spots += [(m.start(1), m.group(1)) for m in JSX_TEXT_RE.finditer(body)]
            spots += [(m.start(1), m.group(1)) for m in JSX_BETWEEN_RE.finditer(body)
                      if _reads_like_copy(m.group(1))]
            spots += [(m.start(1), m.group(1)) for m in DIALOG_RE.finditer(body)]
            spots += list(_fallback_spots(body))
            spots += list(_prompt_spots(body))
            for start, raw in spots:
                prose = TOKEN_RE.sub('', drop_interpolations(raw))
                checks = list(BANNED)
                if rel not in CONFIG_SURFACES and not any(ok in raw for ok in AGENT_OK):
                    checks.append((AGENT_RE, AGENT_WHY))
                for pattern, why in checks:
                    m = pattern.search(prose)
                    if not m:
                        continue
                    line = body[:start].count('\n') + 1
                    snippet = ' '.join(raw.split())[:70]
                    fails.append(f'{rel}:{line} — {m.group(0)!r} {why}\n'
                                 f'            in: {snippet}')

    if fails:
        for f in fails:
            print(f'  FAIL  {f}')
        print()
        print(f'floor vocabulary: {len(fails)} FAILED')
        return 1
    print(f'  ok    {checked} files carry no office jargon in any string a person reads')
    print()
    print('floor vocabulary: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""The room where work lands has one name at the boss, and it is the Library.

It used to be the Vault, and the rename is not cosmetic. Two things were
wrong with the old name at once. It described a safe — a place things go to
be locked away — for a room whose whole job is that coworkers put work IN
and the boss and their teammates take it OUT; and the header over it read
MARKDOWN VAULT above a folder holding .pptx decks, .docx documents, .pdfs,
generated images and .mp4s, so the one line naming the room was wrong about
what was in it.

The risk in any rename this wide is a HALF rename, which is worse than
either name: the chrome says Library, the coworker filing into it says "I
saved it to the vault", and the boss now has two rooms to look for one file
in. This file's whole purpose is that the office cannot drift back into
speaking both. `primitives.jsx` already carries the scar of the same bug for
a different room — "One destination had two names", Projects vs Workspace,
one of which was also a mode INSIDE that view.

So the split this pins, in two halves:

  · THE BOSS AND THE COWORKERS READ ONE WORD. Nav rail, mobile tab bar,
    command palette, view header, the tool checkbox, the tour, the
    honesty notes, and every specialist's system prompt say Library.

  · THE WIRE NEVER MOVED. `[VAULT_NEW:]` and its siblings are marker names
    a model emits and a regex matches; `vault` is a tool id stored in every
    hired coworker's record; `/vault/*` are serve.py routes; `vault:list`
    and friends are postMessage types the SvelteKit shell answers; `vault-*`
    are CSS class names; `vault/` is a directory on disk. Every one of those
    is a contract with offices that already exist. Renaming them buys the
    boss nothing and costs them their files.

Three names keep "vault" honestly and are allowlisted below: an OBSIDIAN
vault is a real product's real word for its own thing, the browser's
encrypted KEY vault is a different store entirely, and the pixel office's
VAULT · TREASURY room holds money, not documents.

Static source checks. Run:
    python3 scripts/test_the_library_has_one_name.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def strip_comments(src):
    """Drop comments but keep line numbering, so reports stay useful."""
    src = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group().count('\n'), src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


# Every string literal and every run of JSX text.
STRINGS = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`", re.S)
# JSX text is prose between two tags. The quote/;/= exclusions are what keep
# this from swallowing the CODE between a `return <…>;` and the next
# `case 'vault':` — which is a `>` followed by a `<` with a matching word in
# between, and is not something any boss reads.
JSXTEXT = re.compile(r'>([^<>{}\'";=]*vault[^<>{}\'";=]*)<', re.I)

# `${…}` inside a template literal is code, not words. `${vault ? …}` is the
# same identifier the wire uses; only the prose around it is read out loud.
SUBST = re.compile(r'\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')

# Two literal shapes are never prose no matter what they contain, and both
# are recognised by what precedes them rather than by their own text: a
# className value ("px-room vault" is CSS) and a module specifier
# ('./views/vault.jsx' is a file on disk). Matching on the text alone would
# mean allowing a bare "vault" token anywhere, which is the exact word this
# file exists to catch in prose.
PRECEDES_CLASS = re.compile(r'class(?:Name)?\s*(?:=\s*\{?|:)\s*$')
PRECEDES_MODULE = re.compile(r'\b(?:from|import|require\s*\()\s*$')
# A settings-search keyword blob is typed AT, never read. The old word is
# kept in it deliberately (settings.jsx, the Library entry): a boss who
# learned "vault" has to still be able to find the door under its new name.
PRECEDES_KW = re.compile(r'\bkw\s*:\s*$')

# Files the boss's words come out of. Written out rather than globbed, so a
# new module that starts saying "vault" has to be added here on purpose —
# which is the moment somebody re-reads this note. The cost of a hand-kept
# list is that it can be quietly shortened, and a shorter list makes this
# whole file greener, so `SPEAKING_DIRS` below is what the list is measured
# against: every .jsx in these directories that says "vault" at all has to
# appear here. Deleting a name is then a failing test, not a clean run.
SPEAKING_DIRS = ['.', 'views', 'ui', 'app', 'modals']
SPEAKING_FILES = [
    'agent_runner.jsx', 'app.jsx', 'claude-client.jsx', 'cooccur.jsx',
    'features.jsx', 'hq-runtime.jsx', 'missions.jsx', 'modals.jsx',
    'tweaks-panel.jsx', 'views.jsx',
    'views/core.jsx', 'views/vault.jsx', 'views/graph.jsx',
    'views/projects.jsx', 'views/ide.jsx',
    'ui/primitives.jsx', 'ui/office.jsx', 'ui/chat.jsx', 'ui/panels.jsx',
    'app/cast.jsx', 'app/commands.jsx', 'app/floor.jsx', 'app/artifacts.jsx',
    'app/storage.jsx', 'app/windows.jsx',
    'modals/providers.jsx', 'modals/settings.jsx', 'modals/starter.jsx',
    'modals/delivery.jsx', 'modals/hire.jsx',
]

# The three places "vault" is the RIGHT word, each with the reason.
ALLOWED = [
    # Obsidian's own product noun. Renaming another product's vocabulary in
    # our UI would send the boss looking for a "Library" setting Obsidian
    # does not have.
    (re.compile(r'Obsidian vault|Obsidian vaults|its vault may be a different folder'),
     "Obsidian's own word for its own thing"),
    # The browser-side encrypted key store. A different store, and the only
    # thing in the product that IS a safe.
    (re.compile(r'encrypted (key )?vault|key vault'),
     'the encrypted key store, not the Library'),
    # The pixel office's treasury room — on-chain balances, display only.
    (re.compile(r'VAULT · TREASURY|Vault Room'),
     'the treasury room holds money, not documents'),
    # A verbatim reproduction of a malformed emission, quoted back at the
    # model as the thing NOT to do. A model writes "**Vault Path:**" because
    # the marker it is labelling is VAULT_NEW — so the example is only
    # realistic while the marker keeps its name, and renaming the example
    # would leave the rule describing output nothing has ever produced.
    (re.compile(r'\*\*Vault Path:\*\*'),
     'a quoted example of what a model wrongly emits, not our own label'),
]

# Identifier-shaped: a route, a message type, a class name, a marker, a key.
IDENTISH = re.compile(
    r'^[\'"`]?/?(vault|vaults)([/:][\w\-{}$.]*)*[\'"`]?$'
    r'|vault[A-Z_]|[A-Za-z_$]vault|VAULT_[A-Z]+'
    r'|vault-[a-z0-9-]+|vault:[a-z]+|/vault/|is-vault|px-vaultdoor|vaultdoor'
    # A dotted member or command id — `nav.vault`, `hq.vault.x`.
    r'|[\w$]\.vaults?\b|\bvaults?\.[\w$]'
    # A path tail. The state directory on disk really is `vault/`, and a
    # panel printing `hq-state/vault` as the default root is telling the
    # boss where their files are, not what the room is called.
    r'|[\w.\-]+[/\\]vaults?\b'
    # An environment variable serve.py actually reads — CAFRESOHQ_VAULT,
    # CAFRESOHQ_VAULT_BACKEND, OCI_VAULT_NAMESPACE/BUCKET/PREFIX. Printing
    # one in a settings tip is quoting a real name, and renaming it would
    # silently un-configure every office already started with it set.
    r'|[A-Z0-9]_VAULT\b'
)


def speaks_of_the_old_room(text, before=''):
    """True when this literal names OUR room with the word vault.

    `before` is the source immediately preceding it, which is the only way
    to tell a class list from a sentence made of the same characters.
    """
    # Case-INSENSITIVE, and that is the whole point: the first spelling of
    # this gate was `[Vv]ault`, which quietly excused every heading in the
    # product — MARKDOWN VAULT, 📓 VAULT, VAULT NOTES — because those are
    # the places a room's name is printed largest.
    if not re.search(r'vault', text, re.I):
        return False
    if (PRECEDES_CLASS.search(before) or PRECEDES_MODULE.search(before)
            or PRECEDES_KW.search(before)):
        return False
    for pat, _why in ALLOWED:
        if pat.search(text):
            return False
    # `${…}` is code inside a sentence; drop it before reading the sentence.
    text = SUBST.sub('', text)
    # Strip every identifier-shaped mention; if nothing is left, it was wire.
    residue = re.sub(IDENTISH, '', text)
    return bool(re.search(r'vault', residue, re.I))


# Every relaxation above buys the sweep a way to go quiet. `${…}` stripping,
# the path tail, the dotted id, the class/module/keyword contexts and three
# allowlist entries were each added to clear a real false positive, and each
# one is also a hole somebody could widen until this file passes by seeing
# nothing. So the sweep is measured before it is trusted: these are sentences
# it MUST still catch, sat next to the wire it must keep ignoring, several
# pairs deliberately differing only in the thing the heuristic keys on.
MUST_CATCH = [
    ("'Search the vault…'", ''),
    ("'No vault yet.'", ''),
    ('"Upload files into the vault"', ''),
    ("'read your vault once you connect one'", ''),
    ("`Saved to the boss's vault`", ''),
    ("`_(${agent.name} reached for the vault.)_`", ''),
    ("'the vault holds decks and documents'", ''),
    # All-caps arms. The gate was `[Vv]ault` on the first pass and these
    # five all slipped it — a heading, a briefing field, a section title.
    ('>📓 VAULT<', ''),
    ('>MARKDOWN VAULT<', ''),
    ('`VAULT FOLDER: ${folder}/`', ''),
    ("'🧠 VAULT GRAPH · POPOUT'", ''),
    ("'Vault Notes'", ''),
    # Same characters as a class list, but it is a sentence and the thing in
    # front of it is not a className.
    ("'px-room vault'", '<div title='),
    # Same shape as the keyword blob, in a field the boss reads.
    ("'files land in the vault'", '  { tab:\'connections\', hint:'),
]
MUST_IGNORE = [
    ("'vault'", ''),
    ("'nav.vault'", ''),
    ("'VAULT_NEW'", ''),
    ("'vault:list'", ''),
    ("'/vault/note?path='", ''),
    ("'vault-tree-pane'", ''),
    ("'C:/Users/you/Documents/cafresohq/hq-state/vault'", ''),
    ('"px-room vault"', 'className='),
    ("'media image video key api vault openai'", 'kw:'),
    ("'./views/vault.jsx'", 'import { VaultView } from '),
    ("'Obsidian vault'", ''),
    ("'stored in the encrypted vault'", ''),
    ("'VAULT · TREASURY'", ''),
    ("'CAFRESOHQ_VAULT'", ''),
    ("'CAFRESOHQ_VAULT_BACKEND=oci'", ''),
    ("'OCI_VAULT_BUCKET'", ''),
]


def main():
    print('the Library has one name')

    # ── 0. the sweep can still see ──────────────────────────────────────
    blind = [t for t, b in MUST_CATCH if not speaks_of_the_old_room(t, b)]
    noisy = [t for t, b in MUST_IGNORE if speaks_of_the_old_room(t, b)]
    check('the sweep below still catches the word it is looking for',
          not blind, f'{blind} — every one of these should have been flagged; '
          'a sweep that sees nothing passes for the same reason a clean '
          'codebase does, and only one of those is worth shipping')
    check('...without flagging the wire it has to leave alone',
          not noisy, f'{noisy} — these are ids, routes, class names, paths '
          'and the three honest vaults')

    # ── 0b. …and it is still reading everything it should ───────────────
    speaking = {str(p) for d in SPEAKING_DIRS
                for p in sorted(Path(d).glob('*.jsx'))
                if re.search(r'vault', p.read_text(encoding='utf-8'), re.I)}
    speaking = {s[2:] if s.startswith('./') else s for s in speaking}
    unswept = sorted(speaking - set(SPEAKING_FILES))
    check('every module that says the word at all is in the sweep',
          not unswept, f'{unswept} — SPEAKING_FILES is hand-kept, and the '
          'cheapest way to make this file green is to shorten it; a name '
          'may only leave the list when the file stops saying "vault"')

    # ── 1. the boss reads ONE word, everywhere ──────────────────────────
    offenders = []
    for rel in SPEAKING_FILES:
        bare = strip_comments(read(rel))
        for m in list(STRINGS.finditer(bare)) + list(JSXTEXT.finditer(bare)):
            t = m.group()
            if speaks_of_the_old_room(t, bare[max(0, m.start() - 60):m.start()]):
                offenders.append(f'{rel}:{bare[:m.start()].count(chr(10)) + 1}: {t.strip()[:90]}')
    check('nothing the boss or a coworker reads still calls the Library a vault',
          not offenders,
          '\n              '.join(offenders[:6]) if offenders else '')

    # ── 2. the four chrome surfaces agree, and keep the id ──────────────
    core = read('views/core.jsx')
    check('the view header reads LIBRARY',
          re.search(r"vault:\s*'LIBRARY',", core) is not None,
          "views/core.jsx VIEW_LABELS — a room named twice is a room the boss "
          "has to search twice")
    check("...and the graph over it reads LIBRARY GRAPH",
          re.search(r"graph:\s*'LIBRARY GRAPH',", core) is not None, 'views/core.jsx')

    check('the sidebar rail reads Library',
          "['vault', 'Library']" in read('ui/primitives.jsx'),
          'ui/primitives.jsx NAV_ITEMS')
    check('the mobile tab bar reads Library',
          "['vault',    '📓', 'Library']" in read('ui/office.jsx'),
          'ui/office.jsx TAB_BOOKMARKS')

    cmds = read('app/commands.jsx')
    check('the command palette reads Library',
          "label: 'Switch view: Library'" in cmds and "['vault','Library']" in cmds,
          "app/commands.jsx — this file already managed one id under two names "
          "once (Projects/Workspace); it does not get to do it again")

    # The id is the thing every one of those four looks the label up BY.
    check('all four still key off the `vault` view id',
          all(s in (core + read('ui/primitives.jsx') + read('ui/office.jsx') + cmds)
              for s in ("vault:     'LIBRARY'", "['vault', 'Library']",
                        "['vault',    '📓', 'Library']", "['vault','Library']")),
          'a renamed id would strand every office whose saved view is "vault"')

    # ── 3. the tool the boss ticks ──────────────────────────────────────
    rt = read('hq-runtime.jsx')
    check('the roster checkbox reads Library',
          re.search(r"\{ id: 'vault',\s*label: 'Library'\s*\}", rt) is not None,
          'hq-runtime.jsx TOOLS_CATALOG')
    check('...and Night Shift calls the same box the same thing',
          "vault: 'Library'" in read('missions.jsx'),
          "missions.jsx TOOL_LABEL — one checkbox, one name, or the boss goes "
          "looking for a second box to tick")

    # ── 4. the coworkers say it too ─────────────────────────────────────
    bare_rt = strip_comments(rt)
    check('the FILE-DELIVERY rule every coworker is handed says Library',
          'MUST be saved to the Library using [VAULT_NEW:' in bare_rt,
          'hq-runtime.jsx — the sentence that decides where long work goes')
    check('...and the no-Library variant does too',
          'There is no Library wired up this session' in bare_rt, 'hq-runtime.jsx')
    check('the chief of staff cites a Library path when relaying',
          'cite the Library path' in bare_rt, 'hq-runtime.jsx')
    for who, needle in [('Kip', 'executive summary + the Library path'),
                        ('Dax', 'headline numbers + the Library path'),
                        ('Sloan', 'the .pptx Library path'),
                        ('Quill', 'word count + the Library path'),
                        ('Pixel', "the image's Library path"),
                        ('Reel', 'duration + the Library path')]:
        check(f'...and so does {who}', needle in bare_rt,
              f'hq-runtime.jsx: {who} still names the old room to the boss')

    # ── 5. the wire never moved ─────────────────────────────────────────
    for marker in ('VAULT_NEW', 'VAULT_APPEND', 'VAULT_SEARCH', 'VAULT_READ'):
        check(f'the {marker} marker name is untouched',
              f"name: '{marker}'" in rt,
              'hq-runtime.jsx: a model emits this and a regex matches it — '
              'renaming it silently stops every filing in the product')
    client = read('claude-client.jsx')
    check('the /vault/* routes are untouched',
          all(r in client for r in ("'/vault/note?path='", "'/vault/search?q='")),
          'claude-client.jsx: serve.py answers these paths')
    check('the vault:* bridge messages are untouched',
          all(f"'vault:{m}'" in client for m in ('list', 'read', 'write', 'create', 'delete')),
          'claude-client.jsx: the SvelteKit shell answers these types')
    vv = read('views/vault.jsx')
    check('the vault-* CSS class names are untouched',
          all(c in vv for c in ('vault-tree-pane', 'vault-edit-pane', 'vault-graph-pane',
                                'vault-toolbar', 'vault-preview')),
          'views/vault.jsx: styles.css matches on these')

    # ── 6. the three honest vaults keep their word ──────────────────────
    check('Obsidian keeps its own vocabulary',
          'Obsidian vault' in read('agent_runner.jsx')
          and 'no Obsidian vaults found' in read('modals/providers.jsx'),
          'a boss sent to a "Library" setting Obsidian does not have is a '
          'wrong door, which §5 rates worse than a locked one')
    check('the encrypted key store is still a vault',
          'stored in the encrypted vault' in read('modals/settings.jsx'),
          'modals/settings.jsx: media API keys live in the key store, not the Library')
    check('the treasury room is still a vault',
          'VAULT · TREASURY' in read('ui/office.jsx'),
          'ui/office.jsx: that room holds money')

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

#!/usr/bin/env python3
"""The office captioned failed tool calls as successes.

Watched live 2026-08-13, in a project room with two coworkers assigned. A
coworker ran DIR_LIST on a path that did not exist, and the chat rendered:

    📁 Opened ./site
    Not a directory: ./site

The head is the OFFICE speaking, in its own voice, asserting that a
directory was opened — directly above its own evidence that it wasn't. A
boss skims headers (that is what headers are for) and reads "Opened".

The cause is that a tool can fail WITHOUT raising. A missing file, a path
that isn't a directory, and a command that exits non-zero are ordinary
answers to ordinary questions, so serve.py answered 200 with the
explanation AS the result — deliberately, because the coworker needs that
text to try something else. But that made "there is a result" the only
signal available, and every surface downstream read it as "it worked":

  · the chat visit card captioned it in the past tense with a prop icon,
  · the Workspace ledger filed a failed write as "wrote index.html",
    claiming the file on disk had changed when it had not,
  · the receipts tray filed a receipt and the corkboard pinned a
    deliverable for an artifact that was never produced.

Fix: serve.py reports `failed` out of band (ok stays True, so the text
still reaches the model), the client stamps it onto a caller-owned `meta`,
the runtime puts it on the `done` event, and every surface reads it.

Run: python3 scripts/test_failed_tools_arent_wins.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def read(rel):
    return (ROOT / rel).read_text()


# ── 1. the server has to say so ─────────────────────────────────────────────
serve = read('serve.py')
check(
    re.search(r'^\s*failed = False\s*$', serve, re.M),
    "serve.py: the tool handler must track a `failed` flag — without it the "
    "only signal is 'a result came back', which is true of every failure "
    "this endpoint reports as a 200.",
)
check(
    re.search(r"result = f'File not found: \{arg\}'\s*\n\s*failed = True", serve),
    "a FILE_READ of a missing file must set failed — it returns the "
    "explanation as its result, so nothing else can tell it apart from a "
    "file that was read successfully.",
)
check(
    re.search(r"result = f'Not a directory: \{arg\}'\s*\n\s*failed = True", serve),
    "a DIR_LIST of a non-directory must set failed — this is the exact call "
    "that rendered as \"Opened ./site\" over \"Not a directory: ./site\".",
)
check(
    re.search(r"result \+= f'\\n\(exit \{proc\.returncode\}\)'\s*\n\s*failed = True", serve),
    "a BASH command that exits non-zero must set failed — 'ran' is a claim "
    "about the outcome, not just about the attempt.",
)
check(
    "'ok': True, 'result': result, 'failed': failed" in serve,
    "the tool response must carry `failed` alongside the result. `ok` stays "
    "True on purpose: the coworker needs the explanatory text to recover, so "
    "this must NOT be reported by failing the request.",
)

# ── 2. the client has to carry it without changing its return type ──────────
client = read('claude-client.jsx')
check(
    re.search(r'async function toolExec\(tool, arg, \{ body = .{0,4}, signal, cwd, meta \} = \{\} \)?', client)
    or 'signal, cwd, meta }' in client,
    "toolExec must accept a `meta` object — the failure signal cannot ride "
    "the return value without breaking every caller that wants the string.",
)
check(
    re.search(r'if \(meta\) meta\.failed = !!j\.failed;', client),
    "toolExec must stamp `failed` onto the caller's meta object.",
)

# ── 3. the runtime has to put it on the event ───────────────────────────────
rt = read('hq-runtime.jsx')
for tool in ('FILE_READ', 'DIR_LIST', 'FILE_WRITE', 'BASH'):
    check(
        re.search(r"toolExec\('" + tool + r"'[^\n]*meta[^\n]*\)", rt),
        f"the {tool} tool must forward `meta` to toolExec, or its failures "
        "stay invisible to every surface.",
    )
check(
    rt.count('const meta = {};') == 2,
    "BOTH tool-running paths in hq-runtime must create a `meta` — there are "
    f"two loops and they drift; found {rt.count('const meta = {};')}.",
)
check(
    rt.count('meta.failed = true;') == 2,
    "BOTH catch blocks must mark the visit failed — a thrown tool error is "
    f"a failure too; found {rt.count('meta.failed = true;')}.",
)
check(
    rt.count('failed: !!meta.failed,') == 2,
    "BOTH `done` events must carry `failed`; found "
    f"{rt.count('failed: !!meta.failed,')}.",
)

# ── 4. the office's vocabulary needs a word for "it didn't work" ────────────
floor = read('app/floor.jsx')
words = re.search(r'const VISIT_WORDS = \[(.*?)\n\];', floor, re.S)
check(words, "app/floor.jsx: VISIT_WORDS is gone.")
if words:
    entries = [ln for ln in words.group(1).splitlines() if 'now:' in ln]
    check(len(entries) >= 6, f"expected the full visit vocabulary, found {len(entries)} entries.")
    for ln in entries:
        check(
            'fail:' in ln,
            "every VISIT_WORDS entry needs a `fail` verb — an entry without "
            "one falls back to the past tense and re-asserts success for a "
            f"trip that failed. Offending entry: {ln.strip()[:70]}",
        )
check(
    re.search(r'const VISIT_DEFAULT = \{[^}]*fail:', floor),
    "VISIT_DEFAULT needs a `fail` verb too — unknown tools fail as well, and "
    "'Checked X' for a failed check is the same lie in a quieter voice.",
)
check('const VISIT_FAIL_ICON' in floor,
      "failed visits need their own icon — a boss skims icons before words.")
check(
    re.search(r"const tense = ev\.failed \? 'fail' : 'past';", floor),
    "toVisit must pick its tense from ev.failed — this is the single line "
    "that decides whether the office tells the truth about the trip.",
)
check(
    re.search(r"icon: ev\.failed \? VISIT_FAIL_ICON", floor),
    "a failed visit must not wear the prop's success icon.",
)
check(
    re.search(r"for \(const v of \[w\.past, w\.now, w\.fail\]\)", floor),
    "the office-voice stripper must cover the `fail` verbs too — they are "
    "office voice, so a coworker must not be able to type one and have it "
    "render as the office reporting. A forged failure blames the tools for "
    "work they never declined to do.",
)
check(
    re.search(r"if \(tense === 'fail'\) return \"couldn't do that\";", floor),
    "visitPlace must not hand a failed trip the prop placard — \"the "
    "bookshelf\" reads as a place they got to.",
)

# ── 5. every surface that files a record must check it ──────────────────────
app = read('app.jsx')
check(
    re.search(r'failed: !!ev\.failed,', app),
    "the floor event must forward `failed` — the Workspace ledger and the "
    "office floor both listen on it.",
)
check(
    re.search(r'if \(ev\.failed\) return;', app),
    "recordToolReceipt must skip failed tools — otherwise the receipts tray "
    "files \"Wrote index.html\" for a file that was never written, and the "
    "corkboard pins a deliverable that cannot be opened.",
)
proj = read('views/projects.jsx')
check(
    re.search(r'if \(d\.failed\) return;', proj),
    "the Workspace ledger must skip failed tools — a failed write filed as "
    "\"wrote index.html\" claims the folder changed, and the tree pulse and "
    "follow-along that follow would chase a file that was never written.",
)
check(
    re.search(r'if \(!ev\.failed && \(ev\.name === .VAULT_NEW. \|\| ev\.name === .VAULT_APPEND.\)\)', app),
    "the inbox artifact must skip failed writes — an artifact is a claim "
    "about a file on disk, shown as the message's DELIVERABLE, so a failed "
    "write filed here reads as a finished note the user can go open.",
)
missions = read('missions.jsx')
check(
    re.search(r'if \(!ev\.failed && \(ev\.name === .VAULT_NEW. \|\| ev\.name === .VAULT_APPEND.\)\)', missions),
    "a mission must not count a failed write in notesWritten — that number "
    "is what the mission card and the calendar both report as the night's "
    "output, and each entry is a path the user can go looking for.",
)

# ── 5b. and the activity feed must not be written before the outcome ────────
# This one is not a missing guard; it is a tense error. Both call sites filed
# the PAST tense from the `start` phase — "saved report.md" before the save
# was attempted, with no correction when it failed.
starts = re.findall(r"if \(ev\.phase === 'start'\) \{(.*?)\n\s*\} else if", app, re.S)
check(len(starts) >= 2, f"expected both tool-stream start branches in app.jsx; found {len(starts)}.")
for i, body in enumerate(starts):
    check(
        'logActivity' not in body,
        "a tool's activity line must NOT be filed on the `start` phase "
        f"(branch {i + 1}): the feed is a record, and at `start` the outcome "
        "it records does not exist yet. The live 'what are they doing right "
        "now' signal is the agent's `task` field, which is set here already.",
    )
check(
    app.count('logActivity(toolActivity(') == 2,
    "BOTH tool streams must file their activity line through toolActivity on "
    f"`done`; found {app.count('logActivity(toolActivity(')}. Hand-built "
    "objects at each site are how the two drifted into the same tense bug.",
)
check(
    'logActivity(toolActivity(agent, ev, { taskId }))' in app,
    "the task-stream line must keep riding `taskId` so the task card can "
    "still show the trips made for it.",
)

# ── 6. and it has to look like a failure ────────────────────────────────────
chat = read('ui/chat.jsx')
check(
    re.search(r"'msg-visit' \+ \(v\.failed \? ' failed' : ''\)", chat),
    "the visit card must take a `failed` class, or the honest wording lands "
    "in styling that still reads as a success.",
)
check('.msg-visit.failed' in read('styles.css'),
      "styles.css needs a `.msg-visit.failed` rule.")

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")

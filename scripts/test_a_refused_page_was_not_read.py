#!/usr/bin/env python3
"""The office's own record called its coworker a liar for telling the truth.

Measured 2026-08-14 on a two-brain office, driving the flow a boss actually
drives: task board → assign to Llama → START. The task named two URLs. All
three pages the coworker reached for answered with a refusal — Gartner 403,
Forrester 404, McKinsey 403 — which I confirmed twice, once in serve.py's
own request log and once by re-running the fetches by hand:

    {"status": 403, "error": "HTTP 403: Forbidden", "text": "", "length": 0}

The coworker reported that accurately. The filed delivery's footer said:

    - Read www.gartner.com/en/research/ai-agency-ai
    - Read www.forrester.com/agentic-ai
    - Read www.mckinsey.com/industries/…/agentic-ai

Nothing was read. Zero bytes came back from any of them. So a boss reading
the delivery top to bottom sees a coworker claiming a 403 directly above the
office's own record that the page was read, and concludes the coworker
invented the error. The office had the truth and printed its opposite.

The maddening part is that this was already fixed once. `failed` has been on
the done event since 2026-08-13 — the "📁 Opened ./site" over "Not a
directory: ./site" post-mortem — and `visitLine` has carried a `fail` tense
since the same day, with the right verb already written for every prop
("Couldn't read", "Couldn't open"). Every live surface was taught to ask for
it. Two things weren't:

- all three `toolVisits.push` sites in app.jsx dropped `ev.failed` on the
  floor, so the flag never reached the filing code at all, and
- `workingNotes` asked for `'past'` unconditionally.

Which makes this the §3.1 shape again, one layer down: the fix reached four
surfaces and stopped at the fifth — the one that outlives the session. The
comment four lines above the bug says exactly that about under-reporting
("the filed note is the one that outlives the session, so it least of all
should be the surface that forgets") and the code beneath it was over-
reporting the whole time.

Two smaller repairs ride along, both found in the same drive:

- `citesOutside` missed `(Gartner, 2027)`. It knew URLs and "Source:" tags,
  and author-year is the most ordinary citation form there is. A brief came
  back with four of them on an empty record and the contradiction line never
  printed.
- The empty-record gate asked whether the record was EMPTY. Three refused
  fetches fill the record three rows deep and consult nothing, so a note
  citing sources on top of them slipped through a check written for it.
  The question is whether any trip arrived, not whether any was attempted.

And one new sentence the office can say without judging anyone: a citation
dated 2027, filed on 2026-08-14, cannot have been read by anybody. That is
arithmetic, not an accusation, and it holds no matter what the record says.

Run: python3 scripts/test_a_refused_page_was_not_read.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
# The sibling suite already lifts the real artifacts.jsx + floor.jsx pair and
# runs them under node. Reuse it rather than growing a second copy that could
# drift: a footer test that stops testing the shipped phrasing table is worse
# than no footer test.
from test_artifacts import pure_source, run_js  # noqa: E402

APP = ROOT / 'app.jsx'
SRC = ROOT / 'app' / 'artifacts.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a refused page was not read')
    app = APP.read_text(encoding='utf-8')
    src = SRC.read_text(encoding='utf-8')

    # ── the flag has to survive the trip ─────────────────────────────────
    pushes = re.findall(r'toolVisits\.push\(\{([^}]*)\}\)', app)
    check('every visit collection point still exists', len(pushes) == 3,
          f'{len(pushes)} found — if a fourth path appeared it needs the '
          'flag too, and this check is how you find out')
    missing = [p.strip()[:60] for p in pushes if 'failed' not in p]
    check('...and each one carries `failed`', not missing,
          f'{missing} — a site that drops it silently reverts the filed '
          'footer to claiming every refused page was read')

    # CHANGED by `#313`, stricter rather than looser. This used to pin the
    # literal `v.failed ? 'fail' : 'past'`, which was the whole tense
    # decision when a trip could only have arrived or not. It can now also
    # have been REFUSED by the boss or be PENDING their stamp — three facts
    # that the filed note, read weeks later by someone deciding whether to
    # send money again, must not collapse into one. `visitTense` is the same
    # reading the desk bubble and the feed take, so the requirement is
    # unchanged and now includes "and it agrees with the live surfaces".
    # The old pattern would have banned that.
    check('the footer picks its tense from the visit',
          re.search(r"const tense = visitTense\(v\);", src),
          "workingNotes asks for 'past' unconditionally again")
    check('...from the same reading the live surfaces take',
          re.search(r"import \{[^}]*visitTense[^}]*\} from '\./floor\.jsx';", src),
          'a second copy of the tense rule here is how the filed record and '
          'the desk bubble end up disagreeing about the same event')
    check('...and asks the shared phrasing table for both',
          re.search(r'visitLine\(v\.name, v\.arg, tense\) \|\| visitPlace\(v\.name, tense\)', src),
          'a hand-written "Couldn\'t read" here would drift from the verb '
          'the chat card and the desk bubble use')
    check('the source gate asks what ARRIVED, not what was tried',
          re.search(r'const consulted = \(visits \|\| \[\]\)\.some\(v => v && v\.name && !v\.failed\);', src),
          'back to `!working.length`, which reads three refusals as a full '
          'day of research')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    FETCH = 'BROWSER_FETCH'
    GARTNER = 'https://www.gartner.com/en/research/ai-agency-ai'
    # The measured body, trimmed. Four author-year citations, two of them
    # dated a year that has not happened.
    CITED = ('According to a report by Gartner, "agentic AI will become the '
             'dominant form of AI in enterprise environments" (Gartner, 2027). '
             'A report by Forrester found that 70% of companies plan to '
             'implement agentic AI by the end of 2026 (Forrester, 2026).')
    js = """
const R = {};
const refused = [{ name: %s, arg: %s, failed: true }];
const arrived = [{ name: %s, arg: %s, failed: false }];
R.refused = workingNotes(refused);
R.arrived = workingNotes(arrived);
R.mixed = workingNotes(refused.concat(arrived));
R.citesAuthorYear = citesOutside(%s);
R.citesQ3 = citesOutside('Revenue landed short (Q3, 2026) against plan.');
R.citesAcronym = citesOutside('The finding is well known (HBR, 2026).');
R.citesMonth = citesOutside('We shipped it (January, 2026) and moved on.');
R.citesPlainProse = citesOutside('Small teams miss deadlines because scope creeps.');
R.citesOwnHead = citesOutside('Three reasons, from memory. (Source: what I already know)');
R.citesUrl = citesOutside('See https://example.com/report for the numbers.');
R.aheadOf2026 = citedFutureYears(%s, new Date(2026, 7, 14));
R.aheadOf2030 = citedFutureYears(%s, new Date(2030, 0, 1));
R.aheadForecastProse = citedFutureYears('Adoption should reach 50%% by 2030.', new Date(2026, 7, 14));
console.log(JSON.stringify(R));
""" % (json.dumps(FETCH), json.dumps(GARTNER), json.dumps(FETCH), json.dumps(GARTNER),
       json.dumps(CITED), json.dumps(CITED), json.dumps(CITED))
    r = run_js(js)

    check('a refused page is not filed as read',
          r['refused'] and "Couldn't read" in r['refused'][0]
          and not re.search(r'^- Read ', r['refused'][0]),
          f"{r['refused']} — this is the measured line, verbatim from a 403")
    check('...and the URL is still named, so the boss can try it themselves',
          r['refused'] and 'gartner.com' in r['refused'][0], r['refused'])
    check('a page that did come back is unchanged',
          r['arrived'] and r['arrived'][0].startswith('- Read'),
          f"{r['arrived']} — the honest half must not become a casualty "
          'of fixing the dishonest half')
    check('a run that did both says both',
          len(r['mixed']) == 2 and any("Couldn't" in x for x in r['mixed'])
          and any(x.startswith('- Read') for x in r['mixed']), r['mixed'])

    check('an author-year citation counts as pointing outside',
          r['citesAuthorYear'] is True,
          '(Gartner, 2027) is a citation; missing it is what let four of '
          'them file under an empty record with no contradiction line')
    check('...but a quarter label does not',
          r['citesQ3'] is False,
          '"(Q3, 2026)" is a finance sentence, not a source. The rule that '
          'excludes it is the no-digits one — a fire arm that relaxed the '
          'lowercase rule instead changed nothing, which is how this got '
          'written down correctly')
    check('...and a bare acronym is missed, on purpose',
          r['citesAcronym'] is False,
          '"(HBR, 2026)" IS a citation and this is a real miss. Pinned so '
          'that widening the name later is a decision someone makes with '
          'the false-alarm cost in front of them, not an accident')
    check('...nor does a month',
          r['citesMonth'] is False, '"(January, 2026)" is a date, not a source')
    check('ordinary prose is still left alone',
          r['citesPlainProse'] is False, r['citesPlainProse'])
    check('and so is a coworker citing their own head',
          r['citesOwnHead'] is False,
          'the brief invites "(Source: what I already know)" — firing on '
          'the compliant answer is the worst possible false alarm')
    check('a URL still counts', r['citesUrl'] is True, r['citesUrl'])

    check('a citation dated next year is caught',
          r['aheadOf2026'] == [2027],
          f"{r['aheadOf2026']} — filed 2026-08-14; nobody has read a 2027 "
          'publication')
    check('...and the same text is unremarkable once that year arrives',
          r['aheadOf2030'] == [],
          f"{r['aheadOf2030']} — the office reads its own clock, so this "
          'must not be a hardcoded year')
    check('a forecast in prose is not a citation',
          r['aheadForecastProse'] == [],
          '"by 2030" is an ordinary sentence; a detector that read every '
          'four-digit number would flag every roadmap the office writes')

    # ── the two lines actually reach the file ────────────────────────────
    # buildDelivery reads the real clock, so the measured body's 2027 stops
    # being the future in 2027 and would quietly take these arms with it.
    # A year nobody will live to see keeps them honest without pretending
    # the fixture is still the verbatim measurement.
    FUTURE = CITED + ' A later Gartner note revisits the same ground (Gartner, 2087).'
    doc = """
const R = {};
const visits = [{ name: %s, arg: %s, failed: true }];
R.allRefused = buildDelivery({ title: 'Analyst brief' }, { name: 'Llama' }, %s, visits).content;
R.noRecord = buildDelivery({ title: 'Analyst brief' }, { name: 'Llama' }, %s, []).content;
R.clean = buildDelivery({ title: 'Notes' }, { name: 'Llama' }, 'Three plain sentences with no citation in them at all.', []).content;
console.log(JSON.stringify(R));
""" % (json.dumps(FETCH), json.dumps(GARTNER), json.dumps(FUTURE), json.dumps(FUTURE))
    d = run_js(doc)

    check('a delivery whose every source was refused says so',
          'Every source this run tried to open was refused' in d['allRefused'],
          d['allRefused'][-400:])
    check('...and a delivery that tried nothing keeps its own wording',
          'nothing was opened or searched while it was written' in d['noRecord']
          and 'Every source this run tried' not in d['noRecord'],
          d['noRecord'][-400:])
    # Match the part that does not inflect: the fixture cites two future
    # years, so the sentence reads "have not happened yet".
    check('the future-year line lands in the filed note',
          'not happened yet' in d['allRefused']
          and 'not happened yet' in d['noRecord'],
          'it is true regardless of the record, so it must not be gated '
          'on one')
    check('...and it counts every future year it was given',
          '2027 and 2087' in d['noRecord'],
          d['noRecord'][-200:] + ' — reporting one of two leaves the boss '
          'checking the citation the office already cleared')
    check('a clean delivery gains none of it',
          'not happened yet' not in d['clean']
          and 'treat those as recalled' not in d['clean']
          and 'Nothing opened, saved or looked up' in d['clean'],
          d['clean'][-300:])

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

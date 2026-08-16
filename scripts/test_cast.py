#!/usr/bin/env python3
"""The cast (app/cast.jsx) — pure-function suite.

§2's card rules are product promises: the vendor is a chip, never the
identity (and NEVER a wrong brand — unknown vendors get no chip); the four
bars are coarse honest class judgements bounded 1..4; an earned XP affinity
always beats the class hunch. Same node-under-Python pattern as the other
jsx suites.
"""
import json
import shutil
import subprocess
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'cast.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('the cast — coworker card helpers')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const A = (model) => ({ model });
// ── poweredBy — chip, never identity, never a wrong brand ──────────────
R.vOllama     = poweredBy(A('ollama:llama3.1:latest'));
R.vLmStudio   = poweredBy(A('lmstudio:qwen2.5'));
R.vOpenRouter = poweredBy(A('openrouter:meta-llama/llama-3.1-8b'));
R.vGroq       = poweredBy(A('groq:llama-3.3-70b'));
R.vClaude     = poweredBy(A('sonnet'));
R.vClaudeCode = poweredBy(A('claude-code'));
R.vCodex      = poweredBy(A('codex'));
R.vGemini     = poweredBy(A('gemini-api:gemini-2.5-pro'));
R.vHermes     = poweredBy(A('hermes-4-405b'));
R.vUnknown    = poweredBy(A('mystery-model-9000'));
R.vEmpty      = poweredBy(A(''));
R.vNull       = poweredBy(null);
// ── statBars — 1..4, honest classes, prefix-stripped ────────────────────
const all = [];
for (const m of ['fable', 'claude-opus-5', 'sonnet', 'haiku', 'codex', 'claude-code',
                 'gemini-api:gemini-2.5-flash', 'ollama:llama3.1:latest',
                 'openrouter:qwen/qwen-2.5-72b', 'mystery-model-9000', '', null]) {
  const b = statBars(A(m));
  all.push([b.speed, b.depth, b.code, b.cost].every(v => v >= 1 && v <= 4) && typeof b.tag === 'string' && b.tag.length > 0);
}
R.allBounded   = all.every(Boolean);
R.localCheap   = statBars(A('ollama:llama3.1:latest')).cost;           // 4 — free-local
R.nanoSpeed    = statBars(A('lmstudio:nvidia/nemotron-3-nano')).speed;  // 4 — small class
R.nanoTag      = statBars(A('lmstudio:nvidia/nemotron-3-nano-4b')).tag;
R.gemmaTag     = statBars(A('lmstudio:google/gemma-4-e4b')).tag;
R.opusDeep     = statBars(A('claude-opus-5')).depth;                   // 4
R.haikuFast    = statBars(A('haiku')).speed;                           // 4
R.prefixStrip  = statBars(A('openrouter:meta-llama/llama-3.1-8b')).cost; // llama class through the prefix
R.flashIsFast  = statBars(A('gemini-api:gemini-2.5-flash')).speed;     // 'flash' → quick class
R.unknownTag   = statBars(A('mystery-model-9000')).tag;
// ── specialtyTag — earned beats hunch ───────────────────────────────────
R.earnedWins   = specialtyTag(A('ollama:llama3.1'), '12 research briefs');
R.hunchDefault = specialtyTag(A('ollama:llama3.1'), '');
// ── brainName — §6: no raw model ids on a card ─────────────────────────
R.bnPrefix   = brainName(A('openrouter:google/gemma-3-27b-it'));
R.bnLocal    = brainName(A('ollama:llama-3.3-70b-instruct'));
R.bnDated    = brainName(A('claude-haiku-4-5-20251001'));
R.bnGpt      = brainName(A('gpt-5'));
R.bnFree     = brainName(A('openrouter:qwen/qwen-2.5-7b-instruct:free'));
R.bnNone     = brainName(A(''));
R.bnMissing  = brainName({});
R.bnNoColon  = brainName(A('mystery-model-9000'));
// Formatting only — every word of the id's identity must survive.
R.bnKeepsAll = ['gemma','3','27']
  .every(t => brainName(A('openrouter:google/gemma-3-27b-it')).toLowerCase().includes(t));
R.bnNoPrefixLeak = ['openrouter','ollama','gemini-api','google/','meta-llama/']
  .every(p => !brainName(A('openrouter:google/gemma-3-27b-it')).toLowerCase().includes(p)
           && !brainName(A('ollama:llama-3.3-70b-instruct')).toLowerCase().includes(p));
// ── the coworker's notebook ─────────────────────────────────────────────
R.mrPlain  = memoryRoot({ name: 'Llama' });
R.mrSpaces = memoryRoot({ name: 'Ada Lovelace' });
R.mrPunct  = memoryRoot({ name: 'K.I.T.T./9' });
R.mrEmpty  = memoryRoot({});
const PATHS = ['Agents/Llama/prefs/boss.md', 'Agents/Llama/decisions/x.md',
               'Agents/Llamabot/other.md', 'Deliveries/note.md', 'Agents/Llama/'];
R.mnMine   = memoryNotes({ name: 'Llama' }, PATHS);
R.mnNoBleed= memoryNotes({ name: 'Llamabot' }, PATHS);
R.mnNone   = memoryNotes({ name: 'Nobody' }, PATHS);
R.mnNull   = memoryNotes({ name: 'Llama' }, null);
R.mlTwo    = memoryLabel({ name: 'Llama' }, PATHS);
R.mlOne    = memoryLabel({ name: 'Llamabot' }, PATHS);
R.mlZero   = memoryLabel({ name: 'Nobody' }, PATHS);
R.mlUnread = memoryLabel({ name: 'Llama' }, null);
// ── payroll: three honest answers, no invented fourth ───────────────────
R.payLocalOllama = payrollLabel({ model: 'ollama:llama3.1' }).text;
R.payLocalLm     = payrollLabel({ model: 'lmstudio:qwen' }).text;
R.payClaudeCode  = payrollLabel({ model: 'claudecode:sonnet' }).text;
R.payCodex       = payrollLabel({ model: 'codex:gpt-5' }).text;
R.payHouse       = payrollLabel({ model: 'cafresohq:default' }).text;
R.payMetered     = payrollLabel({ model: 'openrouter:google/gemma-3-27b-it' }).text;
R.payAnthropic   = payrollLabel({ model: 'anthropic:claude-sonnet-5' }).text;
R.payNoBrain     = payrollLabel({}).text;
R.payNoBrainTitle= payrollLabel({}).title;
R.payAllTitles   = ['ollama:x','claudecode:x','openrouter:x',''].map(m => payrollLabel({model:m}).title).join(' | ');
// A local brain must never be described as costing money.
R.payLocalTitle  = payrollLabel({ model: 'ollama:llama3.1' }).title;
// Case shouldn't matter — prefixes are written by config, not by us.
R.payUpper       = payrollLabel({ model: 'Ollama:Llama3.1' }).text;

/* officeHasBrain — gates the PINNED "add a key" alarm, so a false positive
   here is a permanent lie on the topbar. Fake client: the default provider
   is unconfigured, but a pinned ollama brain is usable. */
const fakeC = {
  getSettings: () => ({ provider: 'hermes', ollamaModel: '', lmstudioModel: '' }),
  parseModelId: (id) => {
    const m = /^([a-z]+):(.+)$/i.exec(String(id || ''));
    return m ? { provider: m[1].toLowerCase(), model: m[2] } : {};
  },
  hasUsableKey: (s) => {
    s = s || { provider: 'hermes' };
    if (s.provider === 'ollama')   return !!s.ollamaModel;
    if (s.provider === 'lmstudio') return !!s.lmstudioModel;
    if (s.provider === 'anthropic') return !!s.anthropicKey;
    return false;                                  // default: not signed in
  },
};
R.brainNoAgents   = officeHasBrain([], fakeC);
R.brainLocalAgent = officeHasBrain([{ model: 'ollama:llama3.1:latest' }], fakeC);
R.brainDeadAgent  = officeHasBrain([{ model: 'anthropic:claude' }], fakeC);
R.brainMixed      = officeHasBrain([{ model: 'anthropic:claude' }, { model: 'ollama:llama3.1' }], fakeC);
R.brainNoModel    = officeHasBrain([{ }], fakeC);
R.brainNoClient   = officeHasBrain([], null);
R.brainThrows     = officeHasBrain([], { hasUsableKey: () => { throw new Error('x'); } });
R.brainGlobalOk   = officeHasBrain([], Object.assign({}, fakeC, { hasUsableKey: () => true }));

/* §7's third route. The diagnosis ends mid-thought, so the JOIN is the part
   that goes wrong — it shipped as a run-on the first time. */
const ROSTER = [{ name: 'Llama', model: 'ollama:llama3.1' }, { name: 'Mika', model: 'ollama:llama3.1:latest' }];
const DEAD   = [{ name: 'Ghost', model: 'anthropic:claude' }];
R.hintTwo    = handoffHint(ROSTER, fakeC);
R.hintOne    = handoffHint([ROSTER[0]], fakeC);
R.hintNone   = handoffHint(DEAD, fakeC);
R.hintFour   = handoffHint(ROSTER.concat([{name:'Sora',model:'ollama:x'},{name:'Kip',model:'ollama:y'}]), fakeC);
R.joinOpen   = withHandoff('⚠ it looks offline from here', ROSTER, fakeC);
R.joinClosed = withHandoff('⚠ it looks offline from here.', ROSTER, fakeC);
R.joinEllip  = withHandoff('⚠ give this to someone else…', ROSTER, fakeC);
R.joinNone   = withHandoff('⚠ it looks offline from here', DEAD, fakeC);
/* The rest of the ladder. withHandoff stops after rung one, which is fine
   for the hand-off surfaces (somebody is always hired there) and was a dead
   end everywhere else — most sharply on an office with nobody in it. */
const DIAG   = '⚠ Couldn’t reach that brain — it looks offline from here';
R.rungName   = withRouteOut(DIAG, ROSTER, fakeC, ROSTER);
R.rungHire   = withRouteOut(DIAG, [], fakeC, []);
R.rungKey    = withRouteOut(DIAG, DEAD, fakeC, DEAD);
// Filtered candidates, non-empty roster: the coworker who just fell over is
// the only one hired, so there is nobody to name AND nobody to hire.
R.rungLastMan = withRouteOut(DIAG, [], fakeC, DEAD);
// A client that cannot answer must not produce a guess.
R.rungMute   = withRouteOut(DIAG, DEAD, { parseModelId: fakeC.parseModelId,
                                          getSettings: fakeC.getSettings }, DEAD);
// ── what a coworker can DO, in the boss's words ─────────────────────────
// Grammar is tested with every condition satisfied, so the joining rules
// are exercised on their own. The gating gets its own fixtures below.
const ALL_ON = { canSearch: true, elevated: true, canMakeImages: true, moneyOn: true, vaultOn: true };
R.cdOne    = canDoPhrase(['web'], ALL_ON);
R.cdTwo    = canDoPhrase(['web','vault'], ALL_ON);
R.cdThree  = canDoPhrase(['files','vault','code'], ALL_ON);
R.cdFour   = canDoPhrase(['web','vault','files','code'], ALL_ON);
R.cdNone   = canDoPhrase([], ALL_ON);
R.cdNull   = canDoPhrase(null, ALL_ON);
R.cdJunk   = canDoPhrase(['nope','web'], ALL_ON);
R.cdAllJunk= canDoPhrase(['nope','zzz'], ALL_ON);
// ── and what it refuses to promise ──────────────────────────────────────
// The four with no tool behind them anywhere, even with every flag on.
R.cdPhantom  = canDoPhrase(['email','cal','db','slack'], ALL_ON);
// Vera as the front desk actually ships her.
R.cdVera     = canDoPhrase(['web','email','cal','vault'], { canSearch: true, vaultOn: true });
// …and the same Vera on a machine whose vault does not answer. 'vault' has
// been conditional since 2026-08-16: the claim alone never bought the
// VAULT_* tools, `toolsForAgent` also awaits isVaultReady().
R.cdVaultOff = canDoPhrase(['web','email','cal','vault'], { canSearch: true, vaultOn: false });
// No key: 'web' still buys a real fetch, so say the smaller true thing.
R.cdWebNoKey = canDoPhrase(['web'], {});
// No elevation: there is no lesser form of file access to fall back to.
R.cdFilesFlat= canDoPhrase(['files','code'], {});
// No ctx at all — unknowable, so promise nothing beyond the unconditional.
R.cdNoCtx    = canDoPhrase(['web','files','vault']);
// The gate on the hire shelf: do the four bars tell these cards apart?
const barKey = (t) => { const b = statBars(t); return `${b.speed}${b.depth}${b.code}${b.cost}`; };
const SEED   = ['cafreso:sonnet','cafreso:sonnet','cafreso:sonnet'].map(m => ({ model: m }));
const MIXED  = ['cafreso:sonnet','ollama:llama3.1','anthropic:claude-opus'].map(m => ({ model: m }));
R.barsSeed   = new Set(SEED.map(barKey)).size > 1;
R.barsMixed  = new Set(MIXED.map(barKey)).size > 1;
console.log(JSON.stringify(R));
''')

    check('ollama chips as your hardware', out['vOllama'] == 'your hardware')
    check('lmstudio chips as your hardware', out['vLmStudio'] == 'your hardware')
    check('openrouter chips as OpenRouter', out['vOpenRouter'] == 'OpenRouter')
    check('groq chips as Groq', out['vGroq'] == 'Groq')
    check('sonnet chips as Claude', out['vClaude'] == 'Claude')
    check('claude-code chips as Claude', out['vClaudeCode'] == 'Claude')
    check('codex chips as OpenAI', out['vCodex'] == 'OpenAI')
    check('gemini chips as Google', out['vGemini'] == 'Google')
    check('hermes chips as Nous Research', out['vHermes'] == 'Nous Research')
    check('unknown model gets NO chip (never a wrong brand)', out['vUnknown'] is None)
    check('empty model gets no chip', out['vEmpty'] is None)
    check('null agent tolerated', out['vNull'] is None)

    check('every class is bounded 1..4 with a tagline', out['allBounded'])
    check('local models read as cheap (cost 4)', out['localCheap'] == 4)
    check('opus-class reads deep (depth 4)', out['opusDeep'] == 4)
    check('haiku-class reads fast (speed 4)', out['haikuFast'] == 4)
    check('class resolves through a driver prefix', out['prefixStrip'] == 4,
          str(out['prefixStrip']))
    check('flash resolves to the quick class', out['flashIsFast'] == 4)
    check('unknown model falls back to the generalist row',
          out['unknownTag'] == 'steady generalist', out['unknownTag'])

    check('an earned affinity beats the class hunch',
          out['earnedWins'] == '12 research briefs')
    check('no affinity yet → the class tagline',
          out['hunchDefault'] == 'cheap and tireless')

    # §6: the card shows a NAME, never the raw id. Formatting only — the
    # identity the id carries must survive, the plumbing around it must not.
    check('routing prefix + org path are dropped',
          out['bnPrefix'] == 'Gemma 3 27B', out['bnPrefix'])
    check('local model keeps its size marker',
          out['bnLocal'] == 'Llama 3.3 70B', out['bnLocal'])
    check('trailing date stamp is dropped',
          out['bnDated'] == 'Claude Haiku 4 5', out['bnDated'])
    check('gpt keeps its casing', out['bnGpt'] == 'GPT 5', out['bnGpt'])
    check(':free tier suffix is dropped',
          out['bnFree'] == 'Qwen 2.5 7B', out['bnFree'])
    check('no model set says so, never invents one',
          out['bnNone'] == 'not set yet' and out['bnMissing'] == 'not set yet',
          f"{out['bnNone']} / {out['bnMissing']}")
    check('an unrecognised id still yields a name',
          out['bnNoColon'] == 'Mystery Model 9000', out['bnNoColon'])
    check('every identity token of the id survives', out['bnKeepsAll'])
    check('no routing prefix or org path ever leaks to the card',
          out['bnNoPrefixLeak'])

    # the coworker's notebook
    check('memory root is the agent folder', out['mrPlain'] == 'Agents/Llama')
    check('spaces become underscores', out['mrSpaces'] == 'Agents/Ada_Lovelace')
    check('punctuation is collapsed, not dropped silently',
          out['mrPunct'] == 'Agents/K_I_T_T_9', out['mrPunct'])
    check('a nameless agent still gets a folder', out['mrEmpty'] == 'Agents/agent')
    check('notes are relative to their own folder',
          out['mnMine'] == ['decisions/x.md', 'prefs/boss.md'], str(out['mnMine']))
    check('a same-prefix neighbour does not bleed in',
          out['mnNoBleed'] == ['other.md'], str(out['mnNoBleed']))
    check('the folder entry itself is not a note', 'Agents/Llama/' not in str(out['mnMine']))
    check('an agent with nothing saved has no notes', out['mnNone'] == [])
    check('an unreadable cabinet yields no notes', out['mnNull'] == [])
    check('the label pluralises', out['mlTwo'] == '2 notes' and out['mlOne'] == '1 note')
    check('nothing saved reads as 0 notes', out['mlZero'] == '0 notes')
    check('an UNREADABLE cabinet reads as nothing at all, not "0 notes"',
          out['mlUnread'] is None, str(out['mlUnread']))

    # payroll
    check('a local brain is in-house, not a dollar figure',
          out['payLocalOllama'] == 'in-house' and out['payLocalLm'] == 'in-house',
          str(out['payLocalOllama']))
    check('…and its tooltip never implies a charge',
          'no per-word charge' in out['payLocalTitle'], out['payLocalTitle'])
    check('a CLI/subscription hire is on your plan',
          out['payClaudeCode'] == 'on your plan' and out['payCodex'] == 'on your plan')
    check('the house brain is on your plan too', out['payHouse'] == 'on your plan')
    check('a metered brain shows no invented number',
          out['payMetered'] == '—' and out['payAnthropic'] == '—')
    check('no brain assigned bills nothing', out['payNoBrain'] == '—')
    check('the no-brain tooltip says WHY, not just a dash',
          'nothing to bill' in out['payNoBrainTitle'], out['payNoBrainTitle'])
    check('no payroll tooltip anywhere invents a rate',
          '0.0000015' not in out['payAllTitles'] and '$' not in out['payAllTitles'],
          out['payAllTitles'])
    check('the prefix match is case-insensitive', out['payUpper'] == 'in-house')

    # officeHasBrain — the alarm gate
    check('an empty office with no default brain really has none',
          out['brainNoAgents'] is False)
    check('ONE coworker on their own local brain means the office can work',
          out['brainLocalAgent'] is True)
    check('…even though the DEFAULT provider is still unconfigured',
          out['brainNoAgents'] is False and out['brainLocalAgent'] is True)
    check('a coworker whose brain is NOT signed in does not count',
          out['brainDeadAgent'] is False)
    check('one working brain among several is enough', out['brainMixed'] is True)
    check('a coworker with no brain assigned counts for nothing',
          out['brainNoModel'] is False)
    check('unknowable never fires the alarm (no client)', out['brainNoClient'] is True)
    check('unknowable never fires the alarm (client throws)', out['brainThrows'] is True)
    check('a configured default short-circuits to yes', out['brainGlobalOk'] is True)

    # handoffHint / withHandoff — §7's "pick another coworker"
    check('two working coworkers are named and joined with "and"',
          out['hintTwo'].strip().startswith('Llama and Mika are still working'), out['hintTwo'])
    check('one coworker reads in the singular',
          'Llama is still working' in out['hintOne'], out['hintOne'])
    check('nobody working offers no route at all', out['hintNone'] == '')
    # counts the NAME list only — the sentence has its own comma in
    # "working, though", which the first version of this check tripped over
    check('never names more than three',
          out['hintFour'].split(' are still working')[0].strip() == 'Llama, Mika and Sora'
          and 'Kip' not in out['hintFour'],
          out['hintFour'])
    check('an unpunctuated diagnosis gets closed before the hint',
          'here. Llama' in out['joinOpen'], out['joinOpen'])
    check('…and an already-closed one is not double-punctuated',
          'here. Llama' in out['joinClosed'] and 'here.. ' not in out['joinClosed'], out['joinClosed'])
    check('an ellipsis counts as closed', 'else… Llama' in out['joinEllip'], out['joinEllip'])
    check('no hint means the text is returned untouched',
          out['joinNone'] == '⚠ it looks offline from here')

    # ── the rest of the ladder ───────────────────────────────────────────
    # §7 wants every failure to end in a way forward, and "pick another
    # coworker" is the one route that stops existing exactly when the office
    # is emptiest. Driven on a genuine first run — nobody hired, no key —
    # the boss's first ever message came back "⚠ hit a snag — couldn't reach
    # that brain — it looks offline from here" and stopped there: no route,
    # and a diagnosis promising a brain would return when none was ever
    # configured, two bubbles under the office's own "We don't have a shared
    # brain here".
    check('somebody who can work is still named first',
          'Llama and Mika are still working' in out['rungName'], out['rungName'])
    check('an empty office is told how to stop being empty',
          "Nobody's hired yet" in out['rungHire']
          and 'Team tab' in out['rungHire']
          and 'Settings → Keys' in out['rungHire'],
          repr(out['rungHire']) + ' — with nobody hired, "pick another '
          'coworker" is not a route; hiring and bringing a brain are')
    check('...offering both routes rather than guessing between them',
          out['rungHire'].count(' or ') == 1,
          repr(out['rungHire']) + ' — the client cannot answer "is there a '
          'brain on this machine" without an async probe, and a route-out '
          'that turns out to be a dead end is worse than two honest ones')
    check('a hired-but-keyless office is pointed at a brain',
          'shared Cafreso brain' in out['rungKey'], out['rungKey'])
    check('the last coworker falling over is not "nobody is hired"',
          "Nobody's hired" not in out['rungLastMan']
          and 'shared Cafreso brain' in out['rungLastMan'],
          repr(out['rungLastMan']) + ' — callers pass a FILTERED candidate '
          'list, so an empty one means nobody is available, not that the '
          'floor is empty; rung 2 must read the roster instead')
    check('a client that cannot be asked adds no guess',
          out['rungMute'] == '⚠ Couldn’t reach that brain — it looks offline from here',
          repr(out['rungMute']))
    check('the join still closes the clause on every rung',
          all('here. ' in out[k] for k in ('rungName', 'rungHire', 'rungKey')),
          'centralising the SENTENCE but not the JOIN is what put a run-on '
          'in the first version of this')

    # ── the call site, not the helper ────────────────────────────────────
    # handoffHint only asks whose brain is ready; it cannot know that one of
    # them just refused the job. So the exclusion has to live where the
    # failure is known, and only a source check can defend it.
    #
    # Without the filter the office answers "Llama couldn't take the handoff"
    # with "Llama and Mika are still working, though — @mention one of them",
    # naming the coworker who just said no. That is worse than offering no
    # route at all, which is the one outcome §7 was written to prevent.
    chat = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
    m = re.search(r"couldn't take the handoff[\s\S]{0,400}?\}\]\);", chat)
    check("the refused coworker is left out of their own hand-off hint",
          bool(m) and 'agents.filter(a => a.id !== target.id)' in m.group(0),
          'ui/chat.jsx: withHandoff must get a roster without `target`')

    # ── the front door ───────────────────────────────────────────────────
    # The CEO's own failure bubble. ui/chat.jsx's comment says it plainly:
    # "agent dispatches and the CEO stream have always been two different
    # error-copy paths" — written the last time something was fixed in one
    # and not the other, and true again the next time. This is the one
    # bubble a brand-new office can produce before anything else exists, so
    # it is the one that most needs the whole ladder.
    ceo = re.search(r"const stopped = err\.name === 'AbortError';[\s\S]{0,3000}?: m\)\);", chat)
    check('the CEO failure bubble is still where it was', bool(ceo),
          'ui/chat.jsx: could not find the CEO stream catch')
    cb = ceo.group(0) if ceo else ''
    check('the CEO climbs the same ladder as the floor',
          'withRouteOut(' in cb and 'withHandoff(' not in cb,
          'ui/chat.jsx: withHandoff stops after rung one, and on an empty '
          'floor rung one does not exist — the bubble ended at the diagnosis')
    check('...and is handed the roster, not just the candidates',
          re.search(r'withRouteOut\([\s\S]{0,220}?agents, CafresoHQClient, agents\)', cb),
          'ui/chat.jsx: the fourth argument is who is HIRED')
    check('the front door speaks in the same shape as the floor',
          'snagOpener(' in cb and 'snagSentence(' not in cb,
          'ui/chat.jsx: snagSentence is the INBOX shape — those rows render '
          '"NAME + text" and need the verb. In a bubble the CEO is speaking, '
          'so it loses its subject and reads "⚠ hit a snag — couldn\'t reach '
          'that brain — it looks offline from here": a log line with two '
          'dashes in it, where the coworker bubble beside it has always used '
          'the bare capitalised clause')

    # Same trap, second door. `chatErrorText` also ends in a hand-off hint,
    # and for a long time it handed `agents` straight through — so when Pip
    # died on a model that is not installed, the bubble read "Llama and Pip
    # are still working, though — @mention one of them". Local brains make
    # this easy to miss: agentBrainReady() only asks whether a key is needed,
    # and Ollama needs none, so the dead coworker probes as READY.
    #
    # Pin the arity rather than the filter — the exclusion lives inside
    # chatErrorText now, but only if every call site says who fell over.
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    calls = re.findall(r'chatErrorText\(([^()]*(?:\([^()]*\)[^()]*)*)\)', app)
    check('every chatErrorText call names the coworker who failed',
          bool(calls) and all(c.count(',') >= 2 for c in calls),
          'app.jsx: chatErrorText(err, agents, <failing>.id) — %d call(s): %s'
          % (len(calls), '; '.join(calls)))

    store = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
    m2 = re.search(r'const chatErrorText = \(([^)]*)\)[\s\S]{0,2000}', store)
    check('chatErrorText drops the failing coworker before hinting',
          bool(m2) and 'selfId' in m2.group(1)
          and 'a.id !== selfId' in m2.group(0)
          and re.search(r'withRouteOut\(out, others,\s*C,\s*agents\)', m2.group(0)),
          'app/storage.jsx: filter `selfId` out, hint from the remainder — and '
          'hand the FULL roster as the fourth argument, or a one-coworker '
          'office tells a boss who has hired somebody that nobody is hired')

    # A real LM Studio shelf turned these up falling through to the generic
    # row: a model whose own name says nano is the small-and-quick class.
    check('a nano model is quick, not a steady generalist', out['nanoSpeed'] == 4)
    check('...and says so', out['nanoTag'] == 'quick with the small stuff')
    # ...without swallowing the open-weights row that follows it.
    check('gemma still reads as cheap and tireless', out['gemmaTag'] == 'cheap and tireless')

    # ── what they can DO ────────────────────────────────────────────────
    # Section 6: "tool call -> shown as the action itself". The card used to
    # say "4 tools", which is a number about a machine concept.
    check('one tool reads as one action', out['cdOne'] == 'search the web')
    check('two are joined with "and"', out['cdTwo'] == 'search the web and read your notes')
    check('three are joined with a comma then "and"',
          out['cdThree'] == 'work with your files, read your notes and run code')
    check('a card is a glance, so it stops at three and counts the rest',
          out['cdFour'] == 'search the web, read your notes and work with your files +1 more')
    # A coworker with no tools still DOES something -- the card must not
    # imply they are useless, and must never render an empty clause.
    check('no tools still reads as a capability', out['cdNone'] == 'talk things through')
    check('a null tool list does not crash the card', out['cdNull'] == 'talk things through')
    check('an unknown tool id is dropped, not printed raw', out['cdJunk'] == 'search the web')
    check('all-unknown falls back rather than emitting "Can "', out['cdAllJunk'] == 'talk things through')

    # A card may only promise what the office can deliver. There is no
    # EMAIL_SEND, CALENDAR, DATABASE or SLACK tool anywhere in the app; an
    # earlier audit established that and hid the four from the hiring and
    # roster checkboxes, but did not reach this line, so the front desk went
    # on selling them. Measured on a fresh office before the fix: Vera's card
    # read "CAN SEARCH THE WEB, SEND EMAIL AND MANAGE YOUR CALENDAR +1 MORE".
    check('a capability with nothing behind it is not spoken at all',
          out['cdPhantom'] == 'talk things through', out['cdPhantom'])
    check('...so Vera advertises the two she really has',
          out['cdVera'] == 'search the web and read your notes', out['cdVera'])
    check('...and does not count the phantoms in "+N more"',
          'more' not in out['cdVera'], out['cdVera'])
    # The notes half of that sentence is only true while the vault answers.
    # Switch Settings → Connections → MARKDOWN VAULT to OBSIDIAN REST with
    # Obsidian closed and toolsForAgent hands over none of VAULT_SEARCH /
    # READ / APPEND / NEW, nor the three EXPORT_* that ride the same claim.
    check('...and stops advertising the notes when the vault stops answering',
          out['cdVaultOff'] == 'search the web and read your notes once you '
          'connect a Markdown vault in Settings → Connections',
          out['cdVaultOff'] + ' — pinned whole, because "read your notes" is '
          'a substring of its own unlock line: a containment check here '
          'passes on the exact sentence it is meant to forbid')
    # The conditional ones. 'web' always buys BROWSER_FETCH, so there is a
    # smaller true thing to say; file access has no lesser form.
    check('without a search key, the card names the fetch it does have',
          out['cdWebNoKey'] == 'read a web page you name', out['cdWebNoKey'])
    check('without elevation, files and code promise nothing',
          out['cdFilesFlat'] == 'talk things through', out['cdFilesFlat'])
    # Was 'read a web page you name and read your notes' until 2026-08-16,
    # when 'vault' gained a condition of its own. With no ctx there is no
    # unconditional capability left in the table at all — the one phrase that
    # survives is web's smaller-true claim, which holds with or without a key.
    # Nothing is promised on unknown, and nothing is denied on unknown either:
    # no unlock line appears for vault or files here.
    check('with no context at all, it promises only the unconditional',
          out['cdNoCtx'] == 'read a web page you name',
          out['cdNoCtx'] + ' — unknowable → do not promise, the mirror of '
          'officeHasBrain\'s unknowable → do not alarm')

    # The bars key off the BRAIN. Every seed candidate pins one brain, so
    # rendering them produced eight identical stat blocks on the one surface
    # whose job is choosing. The gate must be false there and true when the
    # shelf actually holds different brains -- both directions, because a
    # gate that is always false is just deleted code.
    check('identical brains: the bars are suppressed', out['barsSeed'] is False)
    check('different brains: the bars are shown', out['barsMixed'] is True)

    # ── the park list is binding (north-star section 5) ─────────────────
    # "Exporter zoo (video gen, ComfyUI/A1111 wiring)" is parked: it must
    # leave the core path, the onboarding and the pitch. The candidate shelf
    # is where a first-run stranger meets the cast, so it is all three — and
    # Reel (Video Generation) was standing on it. Parked is NOT deleted: the
    # template keeps its full definition, it just is not offered.
    #
    # Read the row from the doc rather than trusting memory — the same row
    # also does NOT park pptx/docx/pdf, which is easy to misremember and
    # would wrongly strip Sloan and Quill off the shelf.
    ns = (ROOT / 'docs' / 'strategy' / '08-north-star-real-product.md').read_text(encoding='utf-8')
    row = re.search(r'\|\s*Exporter zoo \(([^)]*)\)', ns)
    check('the park row still names what we think it names',
          bool(row) and 'video gen' in row.group(1).lower(),
          'north-star section 5: exporter-zoo row changed — re-read before trusting this rule')

    rt = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')

    def shelf_entry(name):
        """One template, bounded by where the object actually closes.

        These two were `[\\s\\S]{0,900}?systemPrompt` and `{0,1200}?`. A
        length in a window is a guess about how long the code will stay,
        and on 2026-08-15 the Pixel entry's comment grew past 1200 — the
        regex stopped matching, `pixel` came back None, and the check
        reported "still parked" about an entry that is not parked. A
        window that can miss is the same defect as a window that can
        collapse: it answers a question it never looked at.
        """
        m = re.search(r"name: '%s',[\s\S]*?\n  \},\n" % re.escape(name), rt)
        return m.group(0) if m else ''

    reel = shelf_entry('Reel')
    check('the shelf entries were found where the check expects them',
          reel and shelf_entry('Pixel'),
          'hq-runtime.jsx: the AGENT_TEMPLATES shelf moved or was '
          'reshaped, so the two parked checks below are measuring nothing')
    check('Reel (video generation) is marked parked',
          bool(reel) and 'parked: true' in reel,
          'hq-runtime.jsx: the parked template must say so')
    # Pixel was parked for the SAME reason Reel is (section 5's exporter-zoo
    # row), plus a live-relevant one: toolsForAgent only ever granted
    # GENERATE_IMAGE when getSettings().imageProvider was set, and no
    # Settings screen in the app could ever set it — Pixel's own job
    # description permanently pointed at a settings page that did not
    # exist. modals/providers.jsx's MediaTab (mounted at Settings -> Media,
    # see scripts/test_media_settings_wired.py) closed that gap 2026-08-13,
    # so Pixel is un-parked: the promise its prompt makes is real now.
    pixel = shelf_entry('Pixel')
    check('Pixel (image generation) is no longer parked',
          bool(pixel) and 'parked: true' not in pixel,
          'hq-runtime.jsx: Settings -> Media exists now (modals/providers.jsx MediaTab) '
          '— Pixel should not still be marked parked')
    settings_src = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    check('the Settings -> Media screen actually sets imageProvider',
          "activeTab === 'media'" in settings_src and 'imageProvider' in
          (ROOT / 'modals' / 'providers.jsx').read_text(encoding='utf-8'),
          'modals/settings.jsx / modals/providers.jsx: MediaTab must write imageProvider '
          '— otherwise Pixel is un-parked onto the same dead end it was parked to avoid')
    check('the seed-swarm hire skips parked templates',
          'if (tpl.parked) continue;' in rt,
          'hq-runtime.jsx: spawnOpenswarmRoster must skip parked')

    hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
    check('the candidate shelf skips parked templates',
          re.search(r'OPENSWARM_ROSTER \|\| \[\]\)\s*\n?\s*\.filter\(t => !t\.parked', hire),
          'modals/hire.jsx: the shelf must filter parked')
    # A hand-written name list drifts the moment the shelf changes — this one
    # already said "Vera, Kip, Dax, Sloan, Quill, Pixel, Reel" beside a count
    # that no longer included Reel.
    check('the seed-swarm tooltip is derived, not hand-listed',
          'Vera, Kip, Dax' not in hire and 'candidates.map(c => c.name)' in hire,
          'modals/hire.jsx: derive the tooltip from the same filtered list')
    # ...and the parked one keeps its definition, so un-parking is one line.
    check('parking did not delete the template',
          "name: 'Reel'" in rt and 'GENERATE_VIDEO' in rt,
          'hq-runtime.jsx: parked means shelved, not removed')

    # The PTY terminal is parked too — "stays in Living Floor desktop mode
    # for devs" per north-star §5. MobileTabBar only renders on a narrow
    # viewport, where app.jsx's desktopMode is unconditionally false
    # (`windowsEnabled && !isNarrowViewport`), and the terminal view switch
    # itself has no desktopMode gate. ALL_VIEWS drives that component's
    # horizontal swipe cycle on `.view-area` — so 'terminal' sitting in it
    # was a fully working, un-parked door on the one surface guaranteed to
    # never be desktop mode. The mobile drawer/tab bookmarks were already
    # correctly excluding it; the swipe array was the one door left open.
    office_src = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')
    all_views = re.search(r"const ALL_VIEWS = \[([^\]]*)\];", office_src)
    check('the mobile swipe cycle does not include the parked terminal',
          bool(all_views) and 'terminal' not in all_views.group(1),
          'ui/office.jsx: ALL_VIEWS drives MobileTabBar\'s swipe — a phone '
          'user could swipe straight into the PTY terminal')

    # A second door into the same park violation, found by checking every
    # OTHER NAV_ITEMS consumer rather than assuming the swipe fix covered
    # the surface. app.jsx's mobile "app switcher" launcher grid renders
    # when windowsEnabled (default TRUE for every user) && isNarrowViewport
    # — i.e. the default state for a first-run phone visitor, not an
    # opt-in "desktop mode" — and its "Launch" section listed every
    # NAV_ITEMS entry as an equal-weight tappable icon, Terminal included.
    app_src_early = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    switcher_grid = re.search(
        r"<div className=\"hq-switcher-head\"><span>Launch</span></div>\s*"
        r"<div className=\"hq-switcher-grid\">([\s\S]*?)</div>", app_src_early)
    check('the mobile app-switcher Launch grid does not include the parked terminal',
          bool(switcher_grid)
          and "k !== 'terminal'" in switcher_grid.group(1),
          "app.jsx: the switcher's Launch grid offers every NAV_ITEMS icon — "
          "a phone user with windowsEnabled on (the default) could tap "
          "straight into the PTY terminal")

    # ── no runtime is privileged in the picker (section 3.1, park row 1) ─
    # "No agent runtime gets special treatment - not in code, not in copy,
    # not in defaults", and the park list's FIRST row retires
    # "Hermes-as-default". The model picker violated all three readings at
    # once: Hermes was hard-coded to position 0 under the comment "surface
    # first" (code), and labelled "Hermes Agent (default · Nous Research)"
    # (copy). Both are fixed; the settings FALLBACK stays, because §3.3
    # requires a zero-key visitor to reach a working brain.
    client = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
    picker = re.search(r'const groups = \[\];[\s\S]*?return groups', client)
    check('the model picker exists to be checked', bool(picker),
          'claude-client.jsx: could not locate the picker group assembly')
    body = picker.group(0) if picker else ''
    labels = re.findall(r"label: '([^']+)'", body)
    check('no picker label crowns a default',
          not any(re.search(r'\bdefault\b', l, re.I) for l in labels),
          'claude-client.jsx: picker labels claiming "default": %s'
          % [l for l in labels if re.search(r'default', l, re.I)])
    # Position is code. Whoever is first is being promoted, so pin that it
    # is not the one the doc names.
    check('Hermes is not first in the picker',
          bool(labels) and 'hermes' not in labels[0].lower(),
          'claude-client.jsx: first picker group is %r' % (labels[0] if labels else None))
    check('...but Hermes is still offered, as a peer',
          any('hermes' in l.lower() for l in labels),
          'claude-client.jsx: parking the privilege must not remove the driver')
    # The zero-key safety net §3.3 mandates is NOT the thing being parked.
    # ── what the boss already has comes first (section 3.3) ─────────────
    # "The default backend is whatever the user ALREADY HAS... We never
    # make someone buy a new key to feel the product." Found by opening
    # the picker live rather than reading the source order: it led with
    # "Anthropic (Claude API · credits)" and "Google (Gemini API ·
    # credits)" - both unconditional, both requiring a purchase - while
    # Ollama and LM Studio, running on the machine with 13 models between
    # them, sat at the bottom. The top of a list is an endorsement.
    keyed_labels = [l for l in labels if 'credits' in l.lower()]
    detected_labels = [l for l in labels if 'credits' not in l.lower()]
    check('the picker still offers the paid services', len(keyed_labels) >= 2,
          'claude-client.jsx: a paid API is a legitimate choice, do not hide it')
    check('nothing you must buy outranks something you already have',
          bool(detected_labels) and bool(keyed_labels)
          and max(labels.index(l) for l in detected_labels)
              < min(labels.index(l) for l in keyed_labels),
          'claude-client.jsx: detected runtimes must precede key-required ones — got %s' % labels)
    check('the two lists are assembled separately, not hand-ordered',
          'const keyed = []' in client and 'groups.concat(keyed)' in client,
          'claude-client.jsx: keep the split structural so a new push cannot land in the wrong half')
    # The picker decides its order in TWO places, and only one was checked:
    # ModelPicker's catch-fallback builds its own static list when the proxy
    # is unreachable. It had the same inversion (paid first) and would have
    # sailed past a rule that only read localModelOptions — the same
    # two-sources-one-rule gap as the seed-swarm tooltip beside its count.
    base = (ROOT / 'modals' / 'base.jsx').read_text(encoding='utf-8')
    fb = re.search(r'const fallback = \[[\s\S]*?\n        \];', base)
    check('the offline fallback list exists to be checked', bool(fb),
          'modals/base.jsx: could not find ModelPicker\'s static fallback')
    fb_labels = re.findall(r"label: '([^']+)'", fb.group(0) if fb else '')
    check('the offline fallback obeys the same ordering rule',
          bool(fb_labels) and 'credits' not in fb_labels[0].lower()
          and not re.search(r'anthropic|google', fb_labels[0], re.I),
          'modals/base.jsx: fallback leads with %r — a key-required service '
          'should not head the list shown when the proxy is down' % (fb_labels[0] if fb_labels else None))

    check('the zero-key fallback survives the un-privileging',
          re.search(r"^\s*provider: 'hermes',", client, re.M),
          "claude-client.jsx: §3.3 needs a working brain for a visitor with no keys")

    # ── the Gemini CLI driver is reachable end-to-end, not just registered ─
    # drivers/gemini_cli.py landed with serve.py delegation and 15 pinned
    # checks — but a driver nobody can dispatch to is decoration. Three
    # doors, each a separate file, each individually forgettable:
    #   1. stream(): 'gemini:' model ids must route via the contract.
    #   2. the front desk: a detected Gemini CLI must be offerable
    #      (FRONT_DESK['gemini']), with the model riding the CLI driver.
    #   3. app.jsx's CLI-sync map: a_cli_gemini needs an entry there or a
    #      hired Gemini card never refreshes its version and login state.
    #
    # Door 3 used to be pinned as "and its model must be 'gemini:', not
    # 'google:'" — the browser-key path, which needs an API key the "we
    # found your sign-in" card never mentions. That check was correct when
    # the effect still HIRED from this map. It is refresh-only now and reads
    # `id` alone, so the model there was a spec nothing applied, and pinning
    # it made a dead field look load-bearing to the next reader (2026-08-16:
    # the same map's dead `tools` was the last live copy of a tool id that
    # is not in TOOLS_CATALOG). The brain is pinned where it is actually
    # read — the front desk, two checks up.
    check("stream() dispatches the 'gemini:' prefix through the contract",
          re.search(r"provider === 'gemini'\)?\s*return streamAgentContract\('gemini'", client),
          'claude-client.jsx: gemini: model ids have no route to the CLI driver')
    check("parseModelId knows the 'gemini:' prefix",
          "'gemini:'" in client,
          'claude-client.jsx: without the prefix, gemini: ids fall through to the global provider')
    hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
    fd_gem = re.search(r"'gemini':\s*\{[^}]*\}", hire)
    check('the front desk offers a detected Gemini CLI',
          bool(fd_gem) and 'a_cli_gemini' in fd_gem.group(0),
          "modals/hire.jsx: FRONT_DESK has no 'gemini' card — detected but unhirable")
    check("...and the card's brain is the CLI driver, not the keyed API",
          bool(fd_gem) and "model: 'gemini:" in fd_gem.group(0),
          'modals/hire.jsx: the card claims the sign-in but the model needs a key')
    app_src = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    defs_gem = re.search(r"'gemini':\s*\{[^}]*a_cli_gemini[^}]*\}", app_src)
    check("app.jsx's CLI-sync map can still refresh a hired Gemini card",
          bool(defs_gem),
          "app.jsx: no 'gemini' entry — a hired a_cli_gemini never learns it "
          'was logged in')
    check('...and names no second brain there to get wrong',
          bool(defs_gem) and 'model' not in defs_gem.group(0),
          "app.jsx: the sync reads `id` alone, so a model here applies to "
          'nothing and only offers a second place to disagree with the front desk')

    # ── the Roster model picker can actually select the driver-contract
    #    cloud providers, not just get them via a fresh front-desk hire ────
    # Found while reviewing the CONNECTIONS panel (7221c05): it tells a
    # self-hosted boss to set GROQ_API_KEY etc., but localModelOptions()
    # (which feeds the Roster tab's per-agent Model <select>) never listed
    # openrouter/groq/gemini-api at all — only reachable by being hired
    # FRESH through modals/hire.jsx's FRONT_DESK card, whose model string
    # is hard-coded. An existing coworker could never be REPOINTED to a
    # cloud driver via the picker — the dropdown silently never offered
    # it. Telling someone to set a key is only half true if nothing then
    # lets them pick the thing the key unlocks.
    lmo = re.search(r'async function localModelOptions\(\)[\s\S]*?\n}\n', client)
    lmo_body = lmo.group(0) if lmo else ''
    check('localModelOptions() offers the three driver-contract cloud providers',
          all(f"'{p}'" in lmo_body or f'`{p}' in lmo_body for p in ('openrouter', 'groq', 'gemini-api')),
          'claude-client.jsx: the Roster picker must be able to select what '
          'CONNECTIONS just told the boss to go set up')
    check('...each gated on its OWN authenticated flag, not on any other',
          bool(re.search(r"if \(det && det\.authenticated\)", lmo_body)),
          'claude-client.jsx: one configured key must not make the other two '
          'look available too')
    check('...and this group sits before the paid "credits" tier',
          lmo_body.find('CLOUD_DRIVER_DEFAULTS') < lmo_body.find("'Anthropic (Claude API"),
          'claude-client.jsx: section 3.3 — what the boss already configured '
          'must precede what they would have to buy')

    # ── CDP screenshots do not ride the default web claim (section 5) ────
    # "CDP browser screenshots | Niche, heavy, off-thesis for v1." It was
    # bundled onto claimed.has('web') alongside plain BROWSER_FETCH -- so
    # any coworker with the cheapest, most-hired checkbox on the form
    # silently also got a tool that requires the BOSS to be running Chrome
    # with a debug flag, and can fire from an LLM's own initiative, not a
    # menu the boss has to go find. Confirmed against the doc row, not
    # memory.
    row = re.search(r'\|\s*CDP browser screenshots\s*\|([^\n|]*)\|', ns)
    check('the CDP-screenshot park row still says what we think it says',
          bool(row) and 'niche' in row.group(1).lower(),
          'north-star section 5: CDP row changed — re-read before trusting this rule')

    grant = re.search(r"if \(agent\.elevated \|\| claimed\.has\('web'\)[\s\S]{0,80}?\{\s*\n\s*out\.push\(TOOL_REGISTRY\.browser_fetch\);", rt)
    check('plain fetch still rides the web claim',
          bool(grant),
          'hq-runtime.jsx: BROWSER_FETCH has no CDP dependency and no jargon on failure — fine to bundle')
    shot = re.search(r"if \(agent\.elevated\) \{\s*\n\s*out\.push\(TOOL_REGISTRY\.browser_screenshot\);", rt)
    check('screenshot rides elevation, not the web claim',
          bool(shot),
          'hq-runtime.jsx: browser_screenshot must not be granted by claimed.has(\'web\') alone')

    # ── the Obsidian bridge: the promise and the door ship together
    #    (section 5) ────────────────────────────────────────────────────
    # These two checks used to read the other way round — "the Obsidian
    # settings surface is still excluded from the bundle" and "the vault
    # view has no dangling Open in Obsidian affordance". Between them they
    # made #123 unfixable without editing a test, which is how a premise
    # gets to outlive its facts.
    #
    # The first was ALREADY FALSE while passing, which is the interesting
    # part. It tested that modals.jsx has no `import ... providers.jsx` —
    # true — and concluded VaultTab is out of the bundle — not true, and
    # not since #37/#39/#40/#60: modals/settings.jsx imports it by name and
    # renders it under Connections. So the product shipped a switch whose
    # own hint promises "open-in-Obsidian", and a test forbidding any
    # control that delivers it.
    #
    # Section 5 does not say park the promise OR park the door. It says a
    # wrong door is worse than a locked one. Either both ship or neither
    # does — that is the invariant, and it is what these pin now. The
    # detail of the gate belongs to test_the_promised_door_exists.py; what
    # is here is the §5 rule the cast has to keep.
    providers_src = (ROOT / 'modals' / 'providers.jsx').read_text(encoding='utf-8')
    settings_src = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    vault_src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    promised = ('open-in-Obsidian' in providers_src
                and bool(re.search(r"^import \{ VaultTab \} from '\./providers\.jsx';",
                                   settings_src, re.M)))
    doored = bool(re.search(r'const openInObsidian = ', vault_src))
    check('the Obsidian promise and the Obsidian door ship together',
          promised == doored,
          f'promised={promised} doored={doored} — Connections sells "open-in-Obsidian" from a '
          'switch that really flips the backend, so views/vault.jsx must carry the control, or '
          'the sentence must come off the wall')
    btn_lines = re.findall(r'[^\n]*onClick=\{openInObsidian\}', vault_src)
    check('...and the door is gated on the backend that can open it',
          not doored or (
              "const _obsidianOn = !!status && status.backend === 'rest'" in vault_src
              and btn_lines and all('_obsidianOn &&' in l for l in btn_lines)),
          'views/vault.jsx: POST /vault/open 400s for every backend but rest, so an ungated button '
          'is a control whose only possible outcome is a snag — and its old alert() read the raw '
          'cause ("REST backend") on the single most-visited pane in the vault (see cabinet, '
          'section 3.6)')

    # ── the "Arcade" Easter egg must never destroy the boss's session ─────
    # Live-clicked in a real browser this session: <a href="https://ai.
    # cafreso.com/workspaces"> with no target — a plain same-tab navigation
    # that took the WHOLE TAB off the local self-hosted app to the real
    # production domain, which 404s ("This page wandered off the farm").
    # For a real self-hosted install that is total, silent data loss: any
    # unsaved chat draft or in-flight task view is gone the instant the top
    # frame navigates away, with no confirmation and no way back except
    # browser Back (which does not restore in-memory state). A link this
    # destructive must open in a new tab regardless of whether its
    # destination is ever fixed.
    office_full_src = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')
    panels_src = (ROOT / 'ui' / 'panels.jsx').read_text(encoding='utf-8')
    needle = 'https://ai.cafreso.com/workspaces'
    for label, src in (
        ('office-floor arcade cabinet', office_full_src),
        ('desk-side PAC-MAN cabinet / CEO panel Workspaces action', panels_src),
    ):
        occurrences = list(re.finditer(re.escape(needle), src))
        for m in occurrences:
            # The <a ...> tag containing this href, opening tag only.
            tag_start = src.rfind('<a ', 0, m.start())
            tag_end = src.find('>', m.end())
            tag = src[tag_start:tag_end]
            check(f'{label}: link to {needle} opens in a new tab',
                  'target="_blank"' in tag and 'noopener' in tag,
                  'a same-tab external <a href> to a link that 404s is a full-session-destroying '
                  'trap for a self-hosted install — found live by clicking it')
        check(f'{label}: the link still exists to be checked', bool(occurrences),
              f'{label}: expected at least one {needle} link — did it move?')

    # ── Settings must not claim a paid managed plan on a self-hosted box ──
    # Live-checked on a bare `python3 serve.py` install (CAFRESOHQ_FLEET_MODE
    # unset): /health correctly reports managed:false, brain:null — but
    # AccountTab's "YOUR PLAN" panel hardcoded "Cafreso HQ Premium ...
    # active" with NO gate on health.managed at all. A self-hosted user (the
    # audience north-star §1 names first) opened Settings and was told they
    # had an active paid subscription they don't have. The exact
    # fabricated-state failure this same panel had already been caught
    # doing twice before, per its own in-file "false span" comment on the
    # Usage row — just not caught here.
    settings_src = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    account_tab = re.search(r'function AccountTab\([\s\S]*?\n}\n', settings_src)
    check('AccountTab reads the settings source to be checked', bool(account_tab),
          'modals/settings.jsx: could not find AccountTab — did it move or rename?')
    body = account_tab.group(0) if account_tab else ''
    check('the managed-plan panel is gated on health.managed',
          bool(re.search(r'const managed = .*health\.managed', body)),
          'modals/settings.jsx: AccountTab must branch on health.managed before '
          'claiming an active paid plan')
    check('"Cafreso HQ Premium ... active" only renders inside that gate',
          bool(re.search(r'\{managed \? \([\s\S]*?Cafreso HQ Premium', body)),
          'modals/settings.jsx: the premium claim must be inside the managed-only branch')
    check('a self-hosted box gets an honest label instead',
          # A distinct CSS hook, not prose — a comment mentioning
          # "self-hosted" would satisfy a plain substring check even with
          # the real branch deleted (caught live: fire-testing the PREVIOUS
          # two checks left this one green because it was reading the
          # explanatory comment above the branch, not the branch itself).
          'plan-selfhosted' in body,
          'modals/settings.jsx: the false branch must say what is actually true')
    check('the settings-search hint for Plan & hosting does not presume managed',
          "hint:'your managed HQ on Cafreso cloud'" not in settings_src,
          "modals/settings.jsx: SETTINGS_INDEX's search hint is a static string "
          "(no health check reaches it) — it must not presume the answer either")

    # ── the vault's New/Rename/Delete use the in-app dialog, not natives ──
    # Found live: clicking "+ New note" threw an uncaught "prompt() is not
    # supported" in this test browser. ui/feedback.jsx's DialogHost exists
    # BECAUSE native window.confirm/window.prompt "on some hosts (iframe
    # sandboxes) are silently disabled" — its own docstring — and this app
    # is explicitly designed to run inside the ai.cafreso.com iframe shell.
    # views/projects.jsx already made the switch for its identical New
    # Folder / Rename / Delete flows; views/vault.jsx — the single most
    # important data surface in the app, per the park list's "stays
    # first-class" row — had not, for its New/Rename/Delete note actions.
    vault_full_src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    check('vault "new note" uses the in-app prompt dialog',
          'await window.hqPrompt(' in vault_full_src
          and re.search(r'const newNote = async[\s\S]{0,120}await window\.hqPrompt', vault_full_src),
          'views/vault.jsx: newNote() must use hqPrompt, not the native window.prompt')
    check('vault "rename" uses the in-app prompt dialog',
          bool(re.search(r'const renameNote = async[\s\S]{0,600}await window\.hqPrompt', vault_full_src)),
          'views/vault.jsx: renameNote() must use hqPrompt, not the native window.prompt')
    check('vault "delete" uses the in-app confirm dialog',
          bool(re.search(r'const deleteNote = async[\s\S]{0,200}await window\.hqConfirm', vault_full_src)),
          'views/vault.jsx: deleteNote() must use hqConfirm, not the native window.confirm')
    check('no raw window.prompt/window.confirm remain in the vault view',
          not re.search(r'\bwindow\.prompt\(|\bwindow\.confirm\(', vault_full_src),
          'views/vault.jsx: a native dialog call slipped back in')

    # ── sibling of 738f931: the CEO desk's sticky-note prompt ─────────────
    # onAddSticky is the "+ NOTE" action always visible on the office floor
    # (also bound to the 'n' shortcut) — same silently-disabled-on-iframe-
    # hosts risk as the vault, on an even more prominent, always-present
    # surface.
    check('the CEO-desk sticky note uses the in-app prompt dialog',
          bool(re.search(r'const onAddSticky = async[\s\S]{0,600}await window\.hqPrompt', app_src)),
          "app.jsx: onAddSticky() must use hqPrompt, not the native prompt()")

    # ── the full sweep: no native dialog remains anywhere in the app ──────
    # The two prior checks fixed the vault and the sticky note; grepping
    # afterward turned up 18+ MORE raw window.prompt/window.confirm sites
    # across app.jsx, modals/settings.jsx, modals/hire.jsx, app/commands.jsx,
    # ui/onboarding.jsx, features.jsx, claude-client.jsx — several guarding
    # destructive actions (STOP ALL, task/workspace delete, granting a
    # coworker computer access). Converted every one, checking each call
    # site's caller first (a plain onClick/fire-and-forget run() is safe to
    # make async; a chained synchronous call like `onDismiss(id);
    # onClose();` needs a beat of thought about ordering, not a blind
    # find-replace). ui/feedback.jsx's OWN fallback definitions
    # (`window.hqConfirm = (m) => Promise.resolve(window.confirm(m))`) are
    # the one legitimate use of the natives — DialogHost's degrade-gracefully
    # path — so this scan excludes that one file.
    all_jsx_dirs = ['app', 'ui', 'modals', 'views']
    offenders = []
    root_jsx = [p for p in ROOT.glob('*.jsx')]
    dir_jsx = [p for d in all_jsx_dirs for p in (ROOT / d).glob('*.jsx')]
    for f in root_jsx + dir_jsx:
        if f.name == 'feedback.jsx':
            continue
        src = f.read_text(encoding='utf-8')
        for m in re.finditer(r'(?<!hq)\bwindow\.(prompt|confirm)\(|(?<![.\w])\b(?:prompt|confirm)\(', src):
            line_no = src.count('\n', 0, m.start()) + 1
            line = src.splitlines()[line_no - 1]
            if line.strip().startswith(('//', '*')):
                continue
            offenders.append(f'{f.relative_to(ROOT)}:{line_no}')
    check('no raw window.prompt/window.confirm remains anywhere in the app',
          not offenders,
          f'native dialog calls found (silently disabled on iframe-sandboxed '
          f'hosts — see ui/feedback.jsx DialogHost docstring): {offenders}')

    # ── self-host CONNECTIONS panel (north-star §1) ───────────────────────
    # The gap: hire.jsx only shows a cloud provider's card when
    # detect.authenticated, so with no key set the card is ABSENT and a
    # self-hosted boss is never told the provider exists or how to enable
    # it. Closed with a read-only status panel, NOT a key form — the
    # drivers refuse runtime key config on purpose
    # (drivers/local_http.py configure() → 400 "no runtime settings") and
    # hire.jsx notes keys "never reach the browser". A form would need a
    # new secret-accepting endpoint, i.e. fighting the security posture.
    check('a CONNECTIONS tab exists for self-hosted installs',
          "id: 'connections'" in settings_src and 'function ConnectionsPanel' in settings_src,
          'modals/settings.jsx: the self-host connections surface is missing')
    check('the CONNECTIONS tab is hidden on managed installs',
          "t.id !== 'connections' || managed === false" in settings_src,
          'modals/settings.jsx: managed containers hold the keys — an env-var '
          'panel there is noise; must be gated on health.managed')
    check('...and gated on managed === false, never merely falsy',
          "activeTab === 'connections' && managed === false" in settings_src,
          'modals/settings.jsx: null means /health has not answered yet — a '
          'managed box must not flash a self-host panel mid-probe')
    check('a hidden tab cannot strand the modal on an empty body',
          'const activeTab = visibleTabs.some' in settings_src,
          'modals/settings.jsx: a managed box whose saved tab was CONNECTIONS '
          'would render no panel at all without a fallback')
    check('the panel names the real env var for each provider',
          all(v in settings_src for v in
              ('OPENROUTER_API_KEY', 'GROQ_API_KEY', 'GEMINI_API_KEY')),
          'modals/settings.jsx: telling someone to "add a key" without naming '
          'the variable is the same silence in a different font')
    # The ⚠ ADD AI KEY chip's tooltip has always said "Click to open
    # Settings → Connections", and the onboarding checklist's first step
    # ("Your AI brain") uses the same openSettings('keys') deep-link. Both
    # aliased to ACCOUNT because CONNECTIONS did not exist. It does now, so
    # the promise the tooltip already makes should be the one kept.
    check("the 'add a key' deep-link lands on CONNECTIONS",
          "keys: 'connections'" in settings_src,
          "modals/settings.jsx: openSettings('keys') is what the ADD AI KEY "
          "chip and the onboarding brain step both call — it must reach the "
          'tab about connecting a brain')
    check('the old CODE AGENTS deep-link lands there too',
          "agentcli: 'connections'" in settings_src,
          "modals/settings.jsx: the old CLI tab is now the 'on this machine' panel")
    # A failed or in-flight probe must not be reported as "not set". det is
    # null in BOTH cases, so the naive `!!(det && det.authenticated)` told a
    # user whose key IS set to go set it again — asserting absence when the
    # honest answer is "don't know yet" (§0: if unsure, be quiet about the
    # claim). Three states: on / off / checking-or-unknown.
    conn_src = re.search(r'function ConnectionsPanel[\s\S]*?\n}\n', settings_src)
    conn_body = conn_src.group(0) if conn_src else ''
    check('the cloud-key rows distinguish unknown from not-set',
          "'unknown'" in conn_body and "'checking'" in conn_body,
          'modals/settings.jsx: a probe that failed or has not answered must '
          'not be rendered as a confident "not set"')
    check('...and that distinction keys off the error, not just null',
          bool(re.search(r"!det \? \(err \?", conn_body)),
          'modals/settings.jsx: null det means BOTH in-flight and failed — '
          'the error flag is what tells them apart')
    check('the probe does not go through the error-swallowing client wrapper',
          # Checks for an actual CALL, not a mention — the fix's own
          # explanatory comment names CafresoHQClient.agentDrivers() to say
          # why it is avoided, which a plain substring check can't tell
          # apart from a live call (same class of false-positive already
          # caught once this session on "self-hosted" prose vs. a real
          # branch — see 7221c05's ConnectionsPanel check history).
          not re.search(r'await\s+CafresoHQClient\.agentDrivers\(', conn_body)
          and 'fetch(' in conn_body,
          "modals/settings.jsx: CafresoHQClient.agentDrivers() always resolves "
          "{drivers:[]} on failure and never throws — a catch keyed on it can "
          "never run. Confirmed live: killing the request left the panel "
          'reading "checking…" forever instead of switching to "unknown".')
    check('the panel never offers to take a key in the browser',
          not re.search(r'ConnectionsPanel[\s\S]*?\n}', settings_src)
          or 'type="password"' not in re.search(r'function ConnectionsPanel[\s\S]*?\n}\n', settings_src).group(0),
          'modals/settings.jsx: keys are env/operator config — the drivers '
          'reject runtime key settings, so a browser form would be a lie')

    # ── Night Shift's COWORKER picker must say the brain is shared ────────
    # Confirmed live by actually running a mission: night_runner.py's
    # llm_call() -> resolve_backend(ctx.hermes_home) reads ONE shared,
    # operator-configured backend with no per-agent override.
    # sched.get('agentName') feeds only the persona line and the run's
    # byline. Every OTHER surface in the office ties a coworker to their
    # own brain (powered-by chip, model picker, front-desk card) — this
    # was the one picker that silently didn't, and the sibling browser-tab
    # Research picker a few hundred lines up (which genuinely does use
    # each agent's own model via HQ.agentStream) made the omission read as
    # an oversight rather than a deliberate difference.
    missions_src = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
    ns_section = missions_src[missions_src.find('NIGHT SHIFT · runs in your office'):]
    ns_coworker = ns_section[:ns_section.find("VAULT FOLDER")]
    check("Night Shift's coworker picker discloses the shared brain",
          'share one brain' in ns_coworker or 'shared brain' in ns_coworker,
          "missions.jsx: the Night Shift COWORKER select has no hint at all — "
          "picking a coworker there changes only whose name signs the notes, "
          "not which brain runs them, and nothing says so")

    # ── Workflow chaining must survive its own step's stale closure ───────
    # Found by actually running a 2-step workflow live: step one (Llama)
    # finished, filed, moved to DONE — and step two just sat unassigned in
    # the inbox forever, no approval prompt, no auto-dispatch, no error.
    # onTaskDropOnAgent's chain check runs after an LLM stream that can take
    # minutes; `tasks` in that closure is frozen from the moment the run
    # STARTED. A chained step's dependsOn is [the step that just ran] — so
    # depsReady looked the dependency up in the stale snapshot, found it
    # still 'inbox' (it flips to 'doing' then 'done' via setTasks, which
    # never touches the closed-over `tasks` binding), and silently treated
    # the chain as not ready. Confirmed via localStorage on the live run:
    # chainTo was correctly set to the next task's id, but nothing ever
    # read a state where the predecessor showed 'done'.
    check('a tasksRef exists to dodge onTaskDropOnAgent\'s stale-tasks-closure bug',
          bool(re.search(r'tasksRef\s*=\s*useRefA\(tasks\)', app)),
          'app.jsx: needs the same ref pattern as agentsRef — a plain `tasks` '
          'closure inside a multi-minute async run never sees its own step '
          'flip to "done"')
    chain_block = app[app.find('// Chain: if this task has a chainTo'):]
    chain_block = chain_block[:chain_block.find('\n      }\n')]
    check('the chain-step lookup reads tasksRef, not the stale closure',
          'tasksRef.current.find' in chain_block and 'tasks.find' not in chain_block,
          'app.jsx: both the nextTask lookup and the dependsOn lookup inside '
          'the chain check must read tasksRef.current — a chained step\'s own '
          'dependsOn is typically [itself, moments ago], which the frozen '
          '`tasks` closure still shows as not-done')

    # ── Add Project's manual path field must agree with its own Browse button ─
    # Found live: typed C:\Users\You\projects\myrepo as the placeholder, then
    # clicked Browse two inches away in the same form and got real paths back
    # slash-style (Users/anthonym/…) — the one server this modal can ever
    # talk to. The static hint and the live picker disagreed about path
    # syntax inside the same form.
    proj_src = (ROOT / 'views' / 'projects.jsx').read_text(encoding='utf-8')
    check("Add Project's path placeholder is POSIX, matching its own Browse picker",
          'C:\\\\Users' not in proj_src and '/Users/you/projects/myrepo' in proj_src,
          r"views/projects.jsx: placeholder='C:\Users\You\projects\myrepo' — "
          "wrong syntax for the only filesystem this modal ever browses "
          "(_cafresohq_allowed_dirs defaults to expanduser('~'))")

    print()
    if FAILS:
        print(f'the cast: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('the cast: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

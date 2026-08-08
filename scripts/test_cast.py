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
// ── what a coworker can DO, in the boss's words ─────────────────────────
R.cdOne    = canDoPhrase(['web']);
R.cdTwo    = canDoPhrase(['web','vault']);
R.cdThree  = canDoPhrase(['files','vault','db']);
R.cdFour   = canDoPhrase(['web','email','cal','vault']);
R.cdNone   = canDoPhrase([]);
R.cdNull   = canDoPhrase(null);
R.cdJunk   = canDoPhrase(['nope','web']);
R.cdAllJunk= canDoPhrase(['nope','zzz']);
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
          and 'handoffHint(others' in m2.group(0)
          and 'withHandoff(out, others' in m2.group(0),
          'app/storage.jsx: filter `selfId` out, then hint from the remainder')

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
          out['cdThree'] == 'work with your files, read your notes and query your database')
    check('a card is a glance, so it stops at three and counts the rest',
          out['cdFour'] == 'search the web, send email and manage your calendar +1 more')
    # A coworker with no tools still DOES something -- the card must not
    # imply they are useless, and must never render an empty clause.
    check('no tools still reads as a capability', out['cdNone'] == 'talk things through')
    check('a null tool list does not crash the card', out['cdNull'] == 'talk things through')
    check('an unknown tool id is dropped, not printed raw', out['cdJunk'] == 'search the web')
    check('all-unknown falls back rather than emitting "Can "', out['cdAllJunk'] == 'talk things through')

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
    reel = re.search(r"name: 'Reel',[\s\S]{0,900}?systemPrompt", rt)
    check('Reel (video generation) is marked parked',
          bool(reel) and 'parked: true' in reel.group(0),
          'hq-runtime.jsx: the parked template must say so')
    # Pixel is parked too. Not the same row literally, but the SAME
    # sentence: section 5's exporter-zoo row ends "image gen can return
    # post-core" — and independent of the doc, toolsForAgent only grants
    # GENERATE_IMAGE when getSettings().imageProvider is set, which no
    # Settings screen in the app can ever set. A hired coworker whose job
    # description permanently points at a settings page that does not
    # exist is a worse failure than a capability that is honestly absent.
    pixel = re.search(r"name: 'Pixel',[\s\S]{0,1200}?systemPrompt", rt)
    check('Pixel (image generation) is marked parked',
          bool(pixel) and 'parked: true' in pixel.group(0),
          'hq-runtime.jsx: the parked template must say so')
    settings_src = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    check("the dead end is real: no Settings screen sets imageProvider",
          'imageProvider' not in settings_src,
          'modals/settings.jsx: a Media settings screen now exists — Pixel can be un-parked '
          '(this check should be REMOVED, not made to pass some other way)')
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

    # ── the Obsidian bridge is parked, and nothing on the core path still
    #    points at it (section 5) ─────────────────────────────────────────
    modals_src = (ROOT / 'modals.jsx').read_text(encoding='utf-8')
    check('the Obsidian settings surface is still excluded from the bundle',
          not re.search(r"^\s*import\b[^\n]*providers\.jsx", modals_src, re.M),
          'modals.jsx: modals/providers.jsx (VaultTab, the REST bridge UI) must stay out of the barrel')
    vault_src = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    check('the vault view has no dangling "Open in Obsidian" affordance',
          not re.search(r'onClick=\{openInObsidian\}', vault_src)
          and not re.search(r'const openInObsidian = ', vault_src),
          'views/vault.jsx: the wiring is parked, so the button that always 400s must not be either — '
          'a native alert() reading raw backend cause text ("REST backend") on the single most-visited '
          'pane in the vault (see cabinet, section 3.6)')

    print()
    if FAILS:
        print(f'the cast: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('the cast: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

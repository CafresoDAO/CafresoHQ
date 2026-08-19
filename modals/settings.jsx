import { CafresoHQChain, CafresoHQClient } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
import { Modal, ModelPicker } from './base.jsx';
/* cleanCause, NOT snagCause. Every sentence in snagCause's table names a
   BRAIN, and nothing on this screen is one: the probe below asks the
   office's own backend which brains exist, and the modules panel talks to
   the chain bridge. Routed through snagCause, a dead probe reported
   "couldn't reach that brain — it looks offline from here", which is a
   confident diagnosis of the wrong subject. cleanCause strips the raw
   error without inventing a cause. */
import { cleanCause } from '../app/floor.jsx';
/* VaultTab was written for this exact panel — Settings → Connections —
   but never actually mounted anywhere: `modals/providers.jsx`, the file
   it lives in, had zero real `import` sites anywhere in the app (one grep
   hit, a comment) until the line below this note.
   `vaultConfigure`/`vaultDiscover` — the ONLY way
   to point CafresoHQ at an existing Obsidian vault, switch to the REST
   backend, or move the vault root — were consequently unreachable by
   ANY control a boss could press; the only way in was the
   `CAFRESOHQ_VAULT`/`CAFRESOHQ_VAULT_BACKEND` env vars, set before the
   process starts. The component itself needed no changes — it already
   uses only `CafresoHQClient` and `HQ`, both already imported here. */
import { VaultTab } from './providers.jsx';
/* MediaTab: Settings -> Media, the missing door onto GENERATE_IMAGE/
   GENERATE_VIDEO — see the comment above MediaTab's own definition in
   providers.jsx for the full unreachable-tool story. */
import { MediaTab } from './providers.jsx';
/* BraveTab — the third door left behind in the same unmounted file, and
   the one that was doing the most damage. It holds the ONLY controls that
   set `braveEnabled` and `braveKey`, and those two are exactly what
   `TOOL_REGISTRY.search.requires()` reads. Unmounted, no boss could ever
   turn web search on by pressing anything, so no coworker was ever handed
   `[SEARCH: query]` — while the front desk hires them saying "can search
   the web" and the roster card stamps them CAN USE: WEB.

   What a coworker DOES get is BROWSER_FETCH, which is handed to anyone
   claiming 'web' unconditionally. Measured live on a fresh office: asked
   to search, Llama did the only thing left and fetched
   google.com/search?q=… — which answers 200 with a bot-check page — and
   then wrote three headlines attributed to the Guardian, CNBC and Forbes
   out of a page that contained none. See the note on BROWSER_FETCH in
   hq-runtime for the other half of that.

   Connections, not Media: this is a key the boss supplies, and on a
   managed box Cafreso holds it — the same argument the panel's own
   comment makes about why CONNECTIONS is self-hosted-only. */
import { BraveTab } from './providers.jsx';
/* BrowserKeysTab — the fourth and last panel out of that unmounted file,
   and the only one whose absence the office was already complaining about
   out loud. The brain picker offers Anthropic and Google on every install;
   the manual hire form defaults to one of them; the form then says "can't
   work until you add it in Settings → Connections" and sends the boss to a
   tab that had no field for either. See the note on the component. */
import { BrowserKeysTab } from './providers.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM,
        useCallback: useCallbackM } = React;
const SETTINGS_TABS = [
  { id: 'account',     ico: '⭐', label: 'ACCOUNT',     desc: 'plan · hosting · usage' },
  /* Self-hosted installs only (filtered out when health.managed) — see
     ConnectionsPanel for why this is status-and-instructions, not a form. */
  { id: 'connections', ico: '🔌', label: 'CONNECTIONS', desc: 'brains found · cloud keys' },
  { id: 'agents',      ico: '👥', label: 'ROSTER',      desc: 'per-agent config' },
  { id: 'icp-services',ico: '🧩', label: 'MODULES',     desc: 'optional add-ons · money · publish' },
  { id: 'media',       ico: '🎬', label: 'MEDIA',       desc: 'image · video generation' },
  { id: 'appearance',  ico: '🖥', label: 'APPEARANCE',  desc: 'theme · vocab · ambience' },
];
// old/removed id → canonical id, so deep-links (openSettings('keys') from the
// old "add a key" chip, saved last-tab values, tour buttons) never dead-end.
/* `keys` and `agentcli` point at CONNECTIONS now that it exists. Both were
   parked on 'account' only because there was nowhere better to send them:
   the ⚠ ADD AI KEY chip's own tooltip has been promising "Settings →
   Connections" the whole time, and the onboarding checklist's FIRST step
   ("Your AI brain") lands here too — the two places a boss with no working
   brain is most likely to click. `agentcli` was the old CODE AGENTS tab,
   which is precisely the new "on this machine" panel.
   A managed install has no CONNECTIONS tab; SettingsModal's activeTab
   fallback catches that and lands on the first visible tab instead. */
const SETTINGS_TAB_ALIAS = {
  global: 'appearance', modules: 'icp-services',
  keys: 'connections', system: 'account', agentcli: 'connections',
};

/* Search index — one entry per meaningful control so "key", "model", "dark"
   etc. jump straight to the right drawer. kw = extra match terms. */
const SETTINGS_INDEX = [
  { tab:'account', label:'Plan & hosting', hint:'managed cloud or self-hosted — see which one this is', kw:'plan premium account subscription container backend health status gateway api runtime connected self-hosted' },
  { tab:'connections', label:'Brains found on this machine', hint:'which coworkers this box can already run', kw:'connections claude codex gemini ollama lmstudio cli detected found local brain' },
  { tab:'connections', label:'Cloud provider keys', hint:'OpenRouter · Groq · Gemini — set as environment variables', kw:'connections key api openrouter groq gemini google env environment variable byok self-hosted' },
  /* Two entries, not one, because a boss sent here by a hire warning is
     searching the brand on the brain they picked — "claude" or "gemini" —
     not a category name they have never seen. Both land on the same panel.
     `sk-ant` and `AIza` are in the keywords because pasting a key into the
     search box is a real thing people do when they cannot find the field. */
  { tab:'connections', label:'Claude API key (pay-per-token)', hint:'for coworkers pinned to an anthropic: brain — kept in this browser, sent straight to Anthropic', kw:'connections anthropic claude api key sk-ant opus sonnet haiku brain model credits pay token byok signed in' },
  { tab:'connections', label:'Gemini API key (pay-per-token)', hint:'for coworkers pinned to a google: brain — kept in this browser, sent straight to Google', kw:'connections google gemini api key aiza brain model credits pay token byok signed in' },
  { tab:'account', label:'Usage this session', hint:'tokens your crew has spent since load', kw:'usage tokens spend cost billing' },
  { tab:'account', label:'Copy diagnostics', hint:'one-click support snapshot', kw:'diagnostics debug support copy help' },
  { tab:'account', label:'Reset onboarding', hint:'replay the new-user guide', kw:'onboarding tour guide reset replay' },
  { tab:'icp-services', label:'Modules', hint:'optional add-ons — the OS works the same with all of them off', kw:'modules add-ons addons optional capabilities icp internet computer dfinity service catalog install marketplace on-chain blockchain' },
  { tab:'icp-services', label:'Money & payments (optional)', hint:'master switch for wallets, payroll, tips — off by default', kw:'money payments wallet payroll tips icrc icp ckusdt ckuni token balance fund send cap spend agent crypto enable disable optional' },
  { tab:'icp-services', label:'Agent wallet', hint:'per-agent on-chain wallet + spend cap', kw:'wallet icp ckusdt ckuni token balance fund send cap spend agent money crypto' },
  { tab:'icp-services', label:'Publish to canister', hint:'ship a site to a *.icp0.io URL', kw:'publish canister deploy site url icp0 web hosting' },
  { tab:'media', label:'Image generation', hint:'pick a provider to give coworkers GENERATE_IMAGE — off by default', kw:'media image generation dall-e dalle openai google gemini imagen fal automatic1111 a1111 stable diffusion picture pixel art' },
  { tab:'media', label:'Video generation', hint:'pick a provider to give coworkers GENERATE_VIDEO — off by default', kw:'media video generation fal sora veo comfyui seedance clip movie' },
  { tab:'media', label:'Media provider keys', hint:'API keys for image/video providers, stored in the encrypted vault', kw:'media image video key api vault openai google fal' },
  /* A boss looking for this types "search", and until now the settings
     search answered nothing because the panel was mounted nowhere. Both
     halves of `search.requires()` live behind this one entry. */
  /* The door the coworker cards send the boss to by name — "read your
     Library once you connect one in Settings → Connections" — and until
     #130 it was the one Connections panel with no entry here at all, so
     the settings search answered nothing for it. `vault` and `obsidian`
     stay in the keywords on purpose: a boss who learned the old word,
     or who came looking for the Obsidian folder, still lands on it. */
  { tab:'connections', label:'Library', hint:'the folder your coworkers file decks, documents, research and notes into', kw:'connections library vault markdown obsidian notes folder directory cabinet documents decks research artifacts rest oci bucket' },
  { tab:'connections', label:'Web search', hint:'give coworkers a real [SEARCH:] tool — without it they can only fetch a URL you name', kw:'connections brave search web internet google lookup research news key api tool' },
  { tab:'agents', label:'Coworker brain & creativity', hint:'per-coworker brain settings', kw:'roster model temperature creativity brain coworker' },
  { tab:'agents', label:'Agent tools', hint:'which tools each agent may use', kw:'tools catalog permissions' },
  { tab:'agents', label:'Tool call format', hint:'JSON vs bracket fallback', kw:'json bracket format' },
  { tab:'agents', label:'File and shell access', hint:'file/shell access per agent', kw:'elevated computer shell files access security' },
  { tab:'agents', label:'Dismiss an agent', hint:'remove a hire from the roster', kw:'dismiss fire let go remove' },
  { tab:'appearance', label:'Theme & vocabulary', hint:'reskin the whole OS — office, coffee shop, trading floor…', kw:'theme skin vocabulary preset sepia solarized dracula high contrast coffeeshop wallstreet barista broker customize personalize' },
  { tab:'appearance', label:'Density', hint:'compact · comfortable · spacious', kw:'density compact comfortable spacious spacing size' },
  { tab:'appearance', label:'Scanline overlay', hint:'soft CRT shimmer', kw:'scanlines crt overlay' },
  { tab:'appearance', label:'Sound FX', hint:'pixel blips on action', kw:'sound audio blips mute' },
  { tab:'appearance', label:'Night mode', hint:'dark pixel theme', kw:'night dark theme day light' },
  { tab:'appearance', label:'Terminal pop-out windows', hint:'let a terminal tab open a separate OS window — off by default', kw:'terminal popup pop-out pop out window spawn desktop multitask advanced' },
  { tab:'appearance', label:'Desktop window mode', hint:'apps open as floating windows instead of full-page — off by default', kw:'desktop window mode floating draggable windowsenabled multitask advanced full page fullpage' },
];

/* ── Modules ───────────────────────────────────────────────────────────────
   Optional capabilities, like enabling an MCP server. CafresoHQ is a
   deploy-agnostic agent OS: every module is OPT-IN and the OS works identically
   with all of them off. Money is deliberately just one module — nobody should
   have to think about tokens to use their agents. The MODULES tab renders each
   card inline (see the 'icp-services' tab below); there is no catalog array.

   Money master switch = settings.moneyEnabled (window.hqMoneyOn(), gates every
   money surface: wallet cards, payroll, P&L board, tip watcher, WALLET_* agent
   tools). When the shell bridge is present, enabling also flips the on-chain
   service flag in cafresohq_state; the flag mirrors to settings.icpServices so
   agent-tool gating stays synchronous. Turning money OFF never touches funds:
   balances live on-chain under the user's Internet Identity — the module hides
   them and pauses agent spending, nothing more. */

/* ── Self-host connections (north-star §1: "bring the subscriptions you
   already have") ───────────────────────────────────────────────────────
   The gap this closes: the front desk only shows a cloud provider's card
   when detect.authenticated is true (modals/hire.jsx — "a card that would
   fail its first task is worse than no card", which is right). But when
   the key ISN'T set the card is simply absent, so a self-hosted boss is
   never told those coworkers exist, let alone how to enable them. Silence,
   not a wrong answer — and silence on the one path north-star §1 names
   first.

   Why this is a read-only status panel and NOT a key-entry form: the
   drivers treat keys as env/operator config on purpose.
   drivers/local_http.py's configure() actively REFUSES runtime settings
   ("this driver has no runtime settings", 400), and hire.jsx's own note
   says the key "lives server-side, so … keys never reach the browser".
   A browser form would need a new secret-accepting endpoint — fighting a
   deliberate security posture rather than filling a gap. So: show what is
   connected, and for what isn't, name the exact environment variable and
   where to get the key. The boss sets it where secrets belong.

   Managed installs never see this tab (gated on health.managed in
   SettingsModal) — there the container already holds the keys. */
const SELF_HOST_PROVIDERS = [
  { id: 'openrouter', label: 'OpenRouter', env: 'OPENROUTER_API_KEY',
    where: 'openrouter.ai/keys', note: 'free open-weights models · no card needed to start' },
  { id: 'groq', label: 'Groq', env: 'GROQ_API_KEY',
    where: 'console.groq.com/keys', note: 'fastest free tier' },
  { id: 'gemini-api', label: 'Google Gemini', env: 'GEMINI_API_KEY',
    where: 'aistudio.google.com/apikey', note: 'generous free tier' },
];

function ConnectionsPanel() {
  const [drivers, setDrivers] = useStateM(null);   // null = still probing
  const [err, setErr] = useStateM('');
  /* Hoisted out of the effect so the boss can run it AGAIN. This probe is
     automatic — it fires once on mount and there is no button behind it — so
     when it failed the panel that answers "what brains do I have?" showed a
     red line and stayed empty for the rest of the session. Every other
     failure in this file is behind a control the boss can press a second
     time; this one had no way forward at all, which is the Track 6 P1
     ("error-recovery/retry UI on failed async ops") and §7's second half. */
  const [probing, setProbing] = useStateM(false);
  const probeDrivers = useCallbackM(async () => {
    /* NOT CafresoHQClient.agentDrivers() — it swallows every failure
       (bad status, network error, thrown exception) and always resolves
       { drivers: [] }, so a catch block here could never run and `err`
       could never be set. Caught live: killing the probe request left
       the panel reading "checking…" forever instead of switching to
       "couldn't check" — the state this whole panel exists to avoid,
       self-inflicted by trusting a wrapper built for a caller that is
       allowed to shrug off failure. Same fix as the health probe a
       few lines up in this same file: go around the wrapper. */
    setProbing(true);
    setErr('');
    /* Whether the office ANSWERED at all is the only distinction the boss can
       act on here, and it is knowable without printing anything raw: if the
       fetch itself threw, nothing is listening; if it resolved and something
       later failed, the office is up but could not answer this question. Two
       sentences, two different things to go and check. */
    let answered = false;
    try {
      const r = await fetch((window._API_BASE || '') + '/agent/drivers?probe=1',
        { cache: 'no-store', credentials: 'include' });
      answered = true;
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      setDrivers((j && j.drivers) || []);
    } catch (_e) {
      setErr(answered
        ? 'your office is running but couldn’t list what’s installed'
        : 'your office isn’t answering — is it still running?');
      setDrivers([]);
    } finally { setProbing(false); }
  }, []);
  useEffectM(() => { probeDrivers(); }, [probeDrivers]);
  const detectOf = (id) => {
    const d = (drivers || []).find(x => x.id === id);
    return (d && d.detect) || null;
  };
  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>ON THIS MACHINE</h4>
        <div className="muted" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          Coworkers run on brains you already have. Anything found here can be
          hired at the front desk.
        </div>
        {drivers === null && <div className="muted">Checking…</div>}
        {err && (
          <div className="tiny" style={{ color: '#c44', display: 'flex', flexWrap: 'wrap',
                                         alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span>Couldn’t check what’s on this machine — {err}</span>
            <button className="px-btn" style={{ fontSize: 8, padding: '5px 8px' }}
              disabled={probing} onClick={probeDrivers}>
              {probing ? 'CHECKING…' : '↻ CHECK AGAIN'}
            </button>
          </div>
        )}
        {drivers !== null && ['claude-code', 'codex', 'gemini', 'ollama', 'lmstudio'].map(id => {
          const det = detectOf(id);
          if (!det) return null;
          /* A local daemon counts as live only on a real probe
             (detect.version === 'reachable') — hire.jsx uses the same rule,
             because `installed` is true for these from the default URL
             alone. But "not found on this machine" is the wrong SENTENCE
             for that state: LM Studio may well be installed and simply not
             running, and telling someone their software is absent when it
             is merely closed sends them to a download page for something
             they already have. Say which it is. */
          const isDaemon = id === 'ollama' || id === 'lmstudio';
          /* `probeError` means the CLI was actually RUN and failed — not
             that it is missing. Both states used to collapse into
             `installed`, so a Codex shim whose vendored binary was gone
             read as "found · needs a sign-in": a confident diagnosis of
             the wrong problem, sending someone to a login screen for a
             program that cannot start. Keep it out of `live` so neither
             the sentence nor the dot claims readiness. */
          const broken = !isDaemon && !!det.probeError;
          const live = isDaemon ? det.version === 'reachable' : (!!det.installed && !broken);
          const label = { 'claude-code': 'Claude Code', codex: 'Codex', gemini: 'Gemini CLI',
                          ollama: 'Ollama', lmstudio: 'LM Studio' }[id];
          /* The daemon branch used to read "not answering — start it and
             reopen this" whenever `det.installed`. For this driver family
             `installed` is `bool(base_url)` and the base URL has a default,
             so it is true on every machine ever — including one where the
             software was never installed. Measured here: no LM Studio.app,
             no `lms` on PATH, and the office instructing me to start it.
             The other branch is unreachable.

             Nothing in the detection path can tell "installed and stopped"
             apart from "never installed", so the sentence must not pick
             one. It says what was observed — a configured address, nothing
             answering — and leaves both remedies open. */
          const offText = broken
            ? `installed, but it ${det.probeError} — a sign-in will not fix it`
            : isDaemon
              ? (det.installed
                  ? 'nothing answered — start it, or set it up if you have not yet'
                  : 'no address configured for it')
              : 'not found on this machine';
          return (
            <div className="row-knob" key={id}>
              <div>
                <div className="lbl">{label}</div>
                <div className="sub"
                     title={(broken && det.probeDetail) || (isDaemon && det.detail) || undefined}>
                  {live
                    /* A local daemon has no account to sign in to — its
                       `authenticated` is hardcoded true for exactly that
                       reason — so "signed in" describes a step that does
                       not exist. What was established is that it answered. */
                    ? (isDaemon ? 'answering on this machine'
                       : det.authenticated ? 'found · signed in'
                       : 'found · needs a sign-in before its first task')
                    : offText}
                </div>
              </div>
              <span className="tiny">
                {live ? (isDaemon ? '● running' : det.authenticated ? '● ready' : '● sign in')
                      : broken ? '○ broken' : (isDaemon ? '○ no answer' : '○ absent')}
              </span>
            </div>
          );
        })}
      </div>
      <div className="cb-panel">
        <h4>CLOUD KEYS</h4>
        <div className="muted" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          Optional. Set one as an environment variable where you start HQ, then
          restart it — the key stays on your machine and never passes through
          this page.
        </div>
        {SELF_HOST_PROVIDERS.map(p => {
          const det = detectOf(p.id);
          /* THREE states, not two. `det` is null both while the probe is in
             flight and when it failed outright — collapsing that into "not
             set" tells someone whose key IS set to go set it again, and makes
             a working config look broken. Same mistake as calling a stopped
             LM Studio "not found": asserting absence when the honest answer
             is "don't know yet". §0's rule — if a surface is unsure, be quiet
             about the CLAIM, not louder. */
          const state = !det ? (err ? 'unknown' : 'checking')
                             : (det.authenticated ? 'on' : 'off');
          const body = {
            on:       'connected — hire them at the front desk',
            checking: 'checking…',
            unknown:  'couldn’t check just now — reopen this tab to retry',
          }[state] || <>set <code>{p.env}</code> · key from {p.where}<br/>{p.note}</>;
          const badge = { on: '● connected', checking: '· checking', unknown: '· unknown' }[state] || '○ not set';
          return (
            <div className="row-knob" key={p.id} style={{ alignItems: 'flex-start' }}>
              <div>
                <div className="lbl">{p.label}</div>
                <div className="sub" style={{ maxWidth: 300 }}>{body}</div>
              </div>
              <span className="tiny" style={{ whiteSpace: 'nowrap' }}>{badge}</span>
            </div>
          );
        })}
      </div>
      {/* Directly under CLOUD KEYS, because a boss arriving here from the
          hire form's "this brain isn't signed in yet" is looking for a key
          and should not have to learn which of two key panels is theirs by
          reading both. Ordered after it because CLOUD KEYS covers the free
          tiers and this one is the pay-per-token pair. */}
      <BrowserKeysTab />
      <BraveTab />
      <VaultTab />
    </div>
  );
}

/* Tool chips shown in Hire + Roster. The wallet tool only appears when the
   Money module is on — with money off, agents shouldn't even be offerable a
   wallet (the runtime gate in hq-runtime.jsx enforces the same rule).

   NEVER_WIRED: four catalog entries with no tool behind them anywhere —
   audited 2026-08-13 by grepping every `claimed.has('<id>')` check in
   hq-runtime.jsx's toolsForAgent (the only place a claimed tool becomes a
   real one) and every TOOL_REGISTRY entry name. 'email'/'cal'/'db'/'slack'
   gate nothing, because EMAIL_SEND/CALENDAR/DATABASE/SLACK were never
   built as tools at all — not ungated, just absent. A boss checking these
   in Hire or Roster was granting nothing, silently: the model itself is
   protected (its prompt separates "claimed" from "wired up for real
   execution", so it correctly refuses to act on a phantom capability),
   but the boss saw a checkbox with no effect and no warning. Hidden
   rather than left half-true.

   DECOYS: 'code'/'files' were left visible by that audit, on the grounds
   that the capability behind them is real and removing them "needs a
   product decision this filter shouldn't make silently". Revisited
   2026-08-14, on this card, in this order:

     TOOLS   [ Web Search ] [ Vault Notes ] [ Code Exec ] [ File Access ]
     …
     🛡 File & shell access                              (•——)  ← the switch

   Real file and shell access is granted by that switch, twenty lines
   below the grid, and by nothing else. So the boss is shown three
   controls for one capability and two of them are decoys — tick both,
   watch nothing happen, and never look further down the card. That is
   not a product decision being deferred; it is a §5 wrong door being
   left in place, and it got worse when the unwired-tools hint started
   naming these two boxes by their printed labels and telling the boss to
   go and tick them.

   Hidden, therefore, on the same grounds as the four above — with one
   difference worth stating: nothing is lost. The four had no door
   anywhere; these two have a working one already on the same card, which
   is what makes hiding them safe rather than a capability removal. The
   hint now names that switch instead (hq-runtime.jsx, ELEVATION_DOOR).

   'img' stayed visible and stayed inert, as a genuinely different case:
   GENERATE_IMAGE/GENERATE_VIDEO are real tools that were gated on the
   imageProvider/videoProvider settings Settings → Media (MediaTab,
   providers.jsx) writes, so this checkbox's real door was on ANOTHER
   screen, not this card. Hiding it here would have left the coworker card
   silent about images altogether, so it was filed separately rather than
   guessed at.

   Settled 2026-08-15, and not by hiding it: the box is a real door now.
   `toolsForAgent` requires BOTH the claim and a provider, so ticking this
   grants and unticking it removes, which is the whole contract of a
   checkbox. The provider remains a second, separate requirement on
   another screen — and the hint channel now names whichever of the two is
   actually shut (hq-runtime.jsx, claimNeedsMediaDoor) rather than always
   sending the boss back to this card. */
const NEVER_WIRED_TOOL_IDS = new Set(['email', 'cal', 'db', 'slack']);
/* Real capability, but this checkbox is not its door — see DECOYS above. */
const GRANTED_ELSEWHERE_TOOL_IDS = new Set(['code', 'files']);
const visibleToolsCatalog = () =>
  HQ.TOOLS_CATALOG
    .filter(t => !NEVER_WIRED_TOOL_IDS.has(t.id))
    .filter(t => !GRANTED_ELSEWHERE_TOOL_IDS.has(t.id))
    .filter(t => t.id !== 'wallet' || (window.hqMoneyOn && window.hqMoneyOn()));

const WALLET_TOKEN_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8 };
function toBaseUnits(whole, decimals) {
  const s = String(whole == null ? '' : whole).trim();
  if (!s || isNaN(Number(s))) return '0';
  const neg = s.startsWith('-'); const body = neg ? s.slice(1) : s;
  const [i, f = ''] = body.split('.');
  const frac = (f + '0'.repeat(decimals)).slice(0, decimals);
  const digits = ((i || '0') + frac).replace(/^0+(?=\d)/, '') || '0';
  return (neg ? '-' : '') + digits;
}
function fromBaseUnits(raw, decimals) {
  try {
    const n = BigInt(raw);
    const base = BigInt(10) ** BigInt(decimals);
    const int = n / base; const frac = n % base;
    const fracStr = frac.toString().padStart(decimals, '0').replace(/0+$/, '');
    return fracStr ? `${int}.${fracStr}` : `${int}`;
  } catch { return '0'; }
}

function AgentWalletCard({ agent }) {
  const [policy, setPolicy] = useStateM(null);
  const [bals, setBals] = useStateM(null);
  const [busy, setBusy] = useStateM('');
  const [msg, setMsg] = useStateM('');
  const [capTok, setCapTok] = useStateM('ICP');
  const [capAmt, setCapAmt] = useStateM('0.1');
  const [capHrs, setCapHrs] = useStateM('24');
  const [fundTok, setFundTok] = useStateM('ICP');
  const [fundAmt, setFundAmt] = useStateM('0.05');
  const chain = () => CafresoHQChain;
  const agentId = agent.id || agent.name;

  // Payroll (Sprint 2): a standing salary/refill the state canister's timer
  // pays from the user's main account under the signed ICRC-2 budget below.
  const [sal, setSal] = useStateM(null);
  const [payMode, setPayMode] = useStateM('salary');
  const [payAmt, setPayAmt] = useStateM('0.01');
  const [payTok, setPayTok] = useStateM('ICP');
  const [payHrs, setPayHrs] = useStateM('24');
  const [payWm, setPayWm] = useStateM('0.05');

  const load = async () => {
    try {
      const p = await chain().wallet.policy(agentId);
      setPolicy(p || null);
      if (p) {
        setCapTok(p.token);
        setCapAmt(fromBaseUnits(p.spendCap, WALLET_TOKEN_DECIMALS[p.token] ?? 8));
        setCapHrs(String(Math.round((p.windowSecs || 0) / 3600) || 24));
      }
    } catch (_e) { /* not deployed / not signed in — leave defaults */ }
    try {
      const pr = await chain().payroll.list();
      const s = (pr.salaries || []).find(x => x.agentId === agentId) || null;
      setSal(s);
      if (s) {
        const dec = WALLET_TOKEN_DECIMALS[s.token] ?? 8;
        setPayTok(s.token); setPayMode(s.mode);
        setPayAmt(fromBaseUnits(s.amount, dec));
        setPayHrs(String(Math.round(s.periodSecs / 3600) || 24));
        setPayWm(fromBaseUnits(s.lowWatermark, dec));
      }
    } catch (_e) { /* canister not upgraded yet — payroll row still usable later */ }
  };
  useEffectM(() => { load(); }, []);

  const refreshBalances = async () => {
    setBusy('bal'); setMsg('');
    try { setBals(await chain().wallet.balances(agentId, Object.keys(WALLET_TOKEN_DECIMALS))); }
    catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const saveCap = async () => {
    setBusy('cap'); setMsg('');
    try {
      const dec = WALLET_TOKEN_DECIMALS[capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: capTok, spendCap: toBaseUnits(capAmt, dec),
        windowSecs: Math.max(0, Math.round(parseFloat(capHrs || '0') * 3600)),
        paused: policy?.paused || false,
      });
      setMsg('Saved.'); await load();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const fund = async () => {
    // Real money leaves the user's main account here — restate the exact
    // amount and destination and make them say yes.
    const amt = String(fundAmt || '').trim();
    if (!amt || isNaN(Number(amt)) || Number(amt) <= 0) { setMsg('Enter a valid amount first.'); return; }
    if (!(await window.hqConfirm(
      `Send ${amt} ${fundTok} from YOUR main account to ${agent.name}'s agent wallet?\n\nThis is a real on-chain transfer.`,
      { okLabel: `Send ${amt} ${fundTok}` }))) return;
    // Ledger transfers take a few seconds — say so, or the click feels dead.
    setBusy('fund'); setMsg('Funding — waiting for the ledger…');
    try {
      // Tell the tip watcher this credit is OURS before it can land on-chain —
      // a self-funded top-up must not rain coins as a "tip".
      try { window.dispatchEvent(new CustomEvent('cafresohq:walletLocalMove', { detail: { agentId } })); } catch (_e) {}
      const r = await chain().wallet.fund(agentId, fundTok, fundAmt);
      setMsg(r && r.ok != null ? `Funded (block ${r.ok}).` : (r && r.err ? `Fund failed: ${r.err}` : 'Fund sent.'));
      await refreshBalances();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const togglePause = async () => {
    setBusy('pause');
    try {
      const dec = WALLET_TOKEN_DECIMALS[policy?.token || capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: policy?.token || capTok,
        spendCap: policy?.spendCap || toBaseUnits(capAmt, dec),
        windowSecs: policy?.windowSecs || Math.round(parseFloat(capHrs || '0') * 3600),
        paused: !(policy?.paused),
      });
      await load();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };

  const savePay = async () => {
    setBusy('pay'); setMsg('');
    try {
      await chain().payroll.put({
        agentId, token: payTok, amount: parseFloat(payAmt) || 0,
        periodSecs: Math.max(60, Math.round(parseFloat(payHrs || '0') * 3600)),
        lowWatermark: payMode === 'refill' ? (parseFloat(payWm) || 0) : 0,
        mode: payMode, active: true,
      });
      setMsg('Payroll saved — first run in one period. Make sure a payroll budget is signed below.');
      await load();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const payNow = async () => {
    if (!(await window.hqConfirm(
      `Run payroll for ${agent.name} right now?\n\nPays ${payAmt} ${payTok} from your signed payroll budget (the budget cap still applies).`,
      { okLabel: 'Pay now' }))) return;
    setBusy('paynow'); setMsg('Running payroll — waiting for the chain…');
    try {
      const r = await chain().payroll.run(agentId);
      setMsg(`Payroll run: ${r}`);
      await load(); await refreshBalances();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const stopPay = async () => {
    if (!(await window.hqConfirm(
      `Stop payroll for ${agent.name}?\n\nNo further automatic payments will run. The agent's balance is untouched.`,
      { okLabel: 'Stop payroll', danger: true }))) return;
    setBusy('paystop'); setMsg('');
    try { await chain().payroll.remove(agentId); setSal(null); setMsg('Payroll stopped.'); }
    catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };

  const toks = Object.keys(WALLET_TOKEN_DECIMALS);
  return (
    <div className="cb-panel icp-wallet-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="lbl">👛 {agent.name} <span className="tiny">· {agent.role}</span></span>
        {policy && (
          <button className={`px-btn ${policy.paused ? 'primary' : 'secondary'}`} style={{ fontSize: 8 }} disabled={busy === 'pause'} onClick={togglePause}>
            {policy.paused ? '▶ RESUME' : '⏸ PAUSE'}
          </button>
        )}
      </div>
      {!policy && <div className="sub" style={{ marginTop: 4 }}>No wallet yet — set a spend cap to create one.</div>}
      <div className="stack" style={{ marginTop: 6 }}>
        <div className="row-knob icp-in-row">
          <span className="lbl">Spend cap</span>
          <input className="icp-in" style={{ width: 66 }} value={capAmt} onChange={e => setCapAmt(e.target.value)} />
          <select value={capTok} onChange={e => setCapTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <span className="tiny">per</span>
          <input className="icp-in" style={{ width: 40 }} value={capHrs} onChange={e => setCapHrs(e.target.value)} />
          <span className="tiny">h</span>
          <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'cap'} onClick={saveCap}>{policy ? 'SAVE' : 'CREATE'}</button>
        </div>
        <div className="row-knob icp-in-row">
          <span className="lbl">Fund</span>
          <input className="icp-in" style={{ width: 66 }} value={fundAmt} onChange={e => setFundAmt(e.target.value)} />
          <select value={fundTok} onChange={e => setFundTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <button className="px-btn" style={{ fontSize: 8 }} disabled={busy === 'fund'} onClick={fund}>⬆ FUND</button>
        </div>
        <div className="row-knob">
          <span className="lbl">Balances</span>
          <button className="px-btn secondary" style={{ fontSize: 8 }} disabled={busy === 'bal'} onClick={refreshBalances}>↻ REFRESH</button>
        </div>
        {bals && (
          <div className="tiny icp-bal-grid">
            {toks.map(t => <div key={t}>{t}: <b>{bals[t] == null ? '—' : fromBaseUnits(bals[t], WALLET_TOKEN_DECIMALS[t])}</b></div>)}
          </div>
        )}
        <div className="row-knob icp-in-row" style={{ flexWrap: 'wrap' }}>
          <span className="lbl">Payroll</span>
          <select value={payMode} onChange={e => setPayMode(e.target.value)}>
            <option value="salary">salary</option>
            <option value="refill">refill</option>
          </select>
          <input className="icp-in" style={{ width: 56 }} value={payAmt} onChange={e => setPayAmt(e.target.value)} />
          <select value={payTok} onChange={e => setPayTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <span className="tiny">per</span>
          <input className="icp-in" style={{ width: 40 }} value={payHrs} onChange={e => setPayHrs(e.target.value)} />
          <span className="tiny">h</span>
          {payMode === 'refill' && (<>
            <span className="tiny">below</span>
            <input className="icp-in" style={{ width: 56 }} value={payWm} onChange={e => setPayWm(e.target.value)} />
          </>)}
          <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'pay'} onClick={savePay}>{sal ? 'SAVE' : 'START'}</button>
          {sal && <button className="px-btn" style={{ fontSize: 8 }} disabled={busy === 'paynow'} onClick={payNow}>⚡ NOW</button>}
          {sal && <button className="px-btn danger" style={{ fontSize: 8 }} disabled={busy === 'paystop'} onClick={stopPay}>✕ STOP</button>}
        </div>
        {sal && sal.stalledSince && (
          <div className="tiny" style={{ color: '#c44' }}>
            ⚠ PAYROLL STALLED ({sal.lastResult}) — sign or top up the payroll budget below, then ⚡ NOW.
          </div>
        )}
        {sal && !sal.stalledSince && sal.lastResult && (
          <div className="tiny" style={{ opacity: .7 }}>payroll: {sal.lastResult} · {sal.mode}</div>
        )}
        {msg && <div className="tiny" style={{ color: 'var(--accent-leaf)' }}>{msg}</div>}
      </div>
    </div>
  );
}

/* Payroll budget = the ONE real signature (icrc2_approve, spender = the state
   canister). It is the hard ceiling on everything the payroll timer can move;
   the shell shows a confirm dialog before signing. Start tiny (0.05 ICP). */
function PayrollBudgetPanel() {
  const [allow, setAllow] = useStateM(null);
  const [rows, setRows] = useStateM([]);
  const [paused, setPaused] = useStateM(false);
  const [tok, setTok] = useStateM('ICP');
  const [amt, setAmt] = useStateM('0.05');
  const [days, setDays] = useStateM('30');
  const [busy, setBusy] = useStateM('');
  const [msg, setMsg] = useStateM('');
  const chain = () => CafresoHQChain;

  const load = async () => {
    try {
      const [a, po, pr] = await Promise.all([
        chain().payroll.allowance(tok),
        chain().payroll.payouts(),
        chain().payroll.list(),
      ]);
      setAllow(a || null);
      setRows((po || []).slice(-6).reverse());
      setPaused(!!pr.paused);
    } catch (_e) { /* canister not upgraded yet */ }
  };
  useEffectM(() => { load(); }, [tok]);

  const approve = async () => {
    setBusy('appr'); setMsg('');
    try {
      const r = await chain().payroll.approve(tok, parseFloat(amt) || 0, parseInt(days, 10) || 0);
      setMsg(r.status === 'ok' ? `Budget signed (block ${r.block}).`
        : r.status === 'declined' ? 'Declined in the shell.'
        : `Failed: ${r.error || '?'}`);
      await load();
    } catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
    setBusy('');
  };
  const togglePause = async () => {
    try { await chain().payroll.pause(!paused); setPaused(!paused); }
    catch (e) { setMsg(cleanCause(e && e.message ? e.message : e)); }
  };

  const dec = (t) => WALLET_TOKEN_DECIMALS[t] ?? 8;
  const toks = Object.keys(WALLET_TOKEN_DECIMALS);
  return (
    <div className="cb-panel icp-wallet-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="lbl">🏦 PAYROLL BUDGET</span>
        <button className={`px-btn ${paused ? 'primary' : 'secondary'}`} style={{ fontSize: 8 }} onClick={togglePause}>
          {paused ? '▶ RESUME PAYROLL' : '⏸ PAUSE PAYROLL'}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 4 }}>
        One signature caps everything payroll can move. Allowance left:{' '}
        <b>{allow ? `${fromBaseUnits(allow.allowance, dec(tok))} ${tok}` : '— none signed —'}</b>
        {allow?.expiresAtNs ? <span className="tiny"> (expires {new Date(Number(BigInt(allow.expiresAtNs) / BigInt(1000000))).toLocaleDateString()})</span> : null}
      </div>
      <div className="row-knob icp-in-row" style={{ marginTop: 6 }}>
        <span className="lbl">Approve</span>
        <input className="icp-in" style={{ width: 66 }} value={amt} onChange={e => setAmt(e.target.value)} />
        <select value={tok} onChange={e => setTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
        <span className="tiny">for</span>
        <input className="icp-in" style={{ width: 40 }} value={days} onChange={e => setDays(e.target.value)} />
        <span className="tiny">days</span>
        <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'appr'} onClick={approve}>✍ SIGN</button>
      </div>
      <div className="tiny" style={{ opacity: .7, marginTop: 2 }}>
        Replaces the previous budget. Each payout also burns one ledger fee of allowance — size it as pay + runs × fee.
      </div>
      {rows.length > 0 && (
        <div className="stack" style={{ marginTop: 6 }}>
          <span className="lbl">Recent payouts</span>
          {rows.map(p => (
            <div key={p.key} className="tiny">
              {p.status === 'paid' ? '✓' : p.status === 'pending' ? '…' : '✗'}{' '}
              {p.agentId} · {fromBaseUnits(p.amount, dec(p.token))} {p.token} · {p.status}
              {p.blockIndex != null ? ` · block ${p.blockIndex}` : ''}
            </div>
          ))}
        </div>
      )}
      {msg && <div className="tiny" style={{ color: 'var(--accent-leaf)' }}>{msg}</div>}
    </div>
  );
}

function IcpServicesPanel({ agents }) {
  const [installed, setInstalled] = useStateM(() => {
    try { return CafresoHQClient.getSettings().icpServices || {}; } catch (_e) { return {}; }
  });
  const [moneyOn, setMoneyOn] = useStateM(() => !!(window.hqMoneyOn && window.hqMoneyOn()));
  const [available, setAvailable] = useStateM(false);
  const [pausedAll, setPausedAll] = useStateM(false);
  const [loading, setLoading] = useStateM(true);
  const [err, setErr] = useStateM('');
  const chain = () => CafresoHQChain;

  const load = async () => {
    setLoading(true); setErr('');
    const avail = !!(chain() && chain().isAvailable());
    setAvailable(avail);
    if (!avail) { setLoading(false); return; }
    try {
      const flags = await chain().services.list();
      const map = { ...installed }; (flags || []).forEach(f => { map[f.serviceId] = !!f.enabled; });
      setInstalled(map);
      CafresoHQClient.setSettings({ icpServices: map });
      setPausedAll(await chain().wallet.pausedAll());
    } catch (e) { setErr(cleanCause(e && e.message ? e.message : e)); }
    setLoading(false);
  };
  useEffectM(() => { load(); }, []);

  /* Money master switch. Both directions confirm in plain language; disabling
     ALSO best-effort-pauses all agent spending so nothing moves while the UI
     is hidden. Funds are never touched — the on-chain install flag stays set
     so re-enabling restores everything exactly as it was. */
  const toggleMoney = async () => {
    if (!moneyOn) {
      const ok = await window.hqConfirm(
        'Turn on Money & Payments?\n\n'
        + 'How it stays safe:\n'
        + '• Agents can NEVER take your funds — every allowance is signed by you, in your wallet.\n'
        + '• Each agent spends only within a cap you set; anything over asks you first.\n'
        + '• One global pause switch stops all agent spending instantly.\n'
        + '• Turning this off later hides money features and pauses spending — balances stay yours, on-chain.\n\n'
        + 'Tip: start tiny (0.05 ICP) until you trust the flow.',
        { okLabel: 'Turn on', cancelLabel: 'Not now' });
      if (!ok) return;
      CafresoHQClient.setSettings({ moneyEnabled: true });
      setMoneyOn(true);
      if (available) {
        try {
          await chain().services.set('wallet', true, '');
          const map = { ...installed, wallet: true };
          setInstalled(map);
          CafresoHQClient.setSettings({ icpServices: map });
        } catch (e) { setErr(cleanCause(e && e.message ? e.message : e)); }
      }
      return;
    }
    const ok = await window.hqConfirm(
      'Turn off Money & Payments?\n\n'
      + '• All agent spending is paused immediately.\n'
      + '• Balances are NOT deleted — they stay on-chain under your Internet Identity and reappear when you turn this back on.\n'
      + '• Scheduled payroll stops running.',
      { okLabel: 'Turn off', cancelLabel: 'Keep on' });
    if (!ok) return;
    if (available) {
      try { await chain().wallet.pauseAll(true); setPausedAll(true); } catch (_e) { /* best-effort */ }
    }
    CafresoHQClient.setSettings({ moneyEnabled: false });
    setMoneyOn(false);
  };

  const togglePublish = async () => {
    const next = !installed.publish;
    const map = { ...installed, publish: next };
    // Publish works without the bridge (container /fs path) — always store
    // locally; flip the on-chain flag too when the shell is reachable.
    setInstalled(map);
    CafresoHQClient.setSettings({ icpServices: map });
    if (available) {
      try { await chain().services.set('publish', next, ''); }
      catch (e) { setErr(cleanCause(e && e.message ? e.message : e)); }
    }
  };

  const togglePauseAll = async () => {
    try { const n = !pausedAll; await chain().wallet.pauseAll(n); setPausedAll(n); }
    catch (e) { setErr(cleanCause(e && e.message ? e.message : e)); }
  };

  const walletAgents = (agents || []).filter(a => (a.tools || []).includes('wallet'));

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>MODULES · OPTIONAL ADD-ONS</h4>
        <div className="sub" style={{ lineHeight: 1.6, marginBottom: 6 }}>
          Your HQ runs the same everywhere — laptop, cloud, or on-chain. Modules
          add capabilities on top; everything below is opt-in and off by default.
        </div>
        {/* A spine, because snagCause returns a bare CLAUSE — on its own this
            line read "couldn't reach that brain" with no subject and no verb.
            No retry button here on purpose: every error on this panel comes
            from a toggle the boss just pressed, and that toggle is still on
            screen. The way forward is the control itself; adding a second one
            would imply the first had stopped working. */}
        {err && <div className="tiny" style={{ color: '#c44' }}>Couldn’t save that change — {err}</div>}
        {loading && available && <div className="muted">Loading…</div>}
        <div className="stack">
          {/* Money — the master switch, styled as a first-class module card */}
          <div className="row-knob" style={{ alignItems: 'flex-start' }}>
            <div style={{ maxWidth: 300 }}>
              <div className="lbl">💰 Money &amp; Payments <span className="tiny" style={{ opacity: .7 }}>{moneyOn ? '· ON' : '· OFF'}</span></div>
              <div className="sub" style={{ marginTop: 2 }}>
                Agents can hold tokens (ICP, ckUSDT, …), earn tips and payroll, and spend
                within caps you set. Entirely optional — HQ works the same without it.
              </div>
              <div className="tiny" style={{ marginTop: 3, opacity: .75 }}>
                🔒 Non-custodial: you sign every allowance; agents can only request.
                Turning off pauses spending and hides money UI — funds are never touched.
              </div>
            </div>
            <div className={`pxswitch ${moneyOn ? 'on' : ''}`} role="switch" aria-checked={moneyOn} onClick={toggleMoney}><div className="nub" /></div>
          </div>

          <div className="row-knob" style={{ alignItems: 'flex-start' }}>
            <div style={{ maxWidth: 300 }}>
              <div className="lbl">🚀 Publish to Web <span className="tiny" style={{ opacity: .7 }}>{installed.publish ? '· ON' : '· OFF'}</span></div>
              <div className="sub" style={{ marginTop: 2 }}>
                Agents publish sites they build and hand back a verifiable link your users can click.
              </div>
            </div>
            <div className={`pxswitch ${installed.publish ? 'on' : ''}`} role="switch" aria-checked={!!installed.publish} onClick={togglePublish}><div className="nub" /></div>
          </div>
        </div>
      </div>

      {moneyOn && !available && (
        <div className="cb-panel">
          <h4>💰 MONEY &amp; PAYMENTS</h4>
          <div className="muted" style={{ lineHeight: 1.6 }}>
            The module is on, but balances and sends need your Internet Identity, which
            lives in the CafresoHQ shell. Open your HQ at <b>ai.cafreso.com</b> to manage
            wallets, caps, and payroll. Until then agents cannot move any funds.
          </div>
        </div>
      )}

      {moneyOn && available && (
        <div className="cb-panel">
          <h4>💰 AGENT WALLETS</h4>
          <div className="row-knob">
            <div><div className="lbl">Pause all agent spending</div><div className="sub">Global kill switch — blocks every agent send</div></div>
            <div className={`pxswitch ${pausedAll ? 'on' : ''}`} role="switch" aria-checked={pausedAll} onClick={togglePauseAll}><div className="nub" /></div>
          </div>
          {pausedAll && <div className="tiny" style={{ color: '#a9710f' }}>⏸ Everything is paused — no agent can spend until you resume.</div>}
          <PayrollBudgetPanel />
          {walletAgents.length === 0
            ? <div className="muted" style={{ marginTop: 6 }}>Grant an agent the <b>ICP Wallet</b> tool in <b>Roster</b> to give it a wallet.</div>
            : walletAgents.map(a => <AgentWalletCard key={a.id} agent={a} />)}
        </div>
      )}
    </div>
  );
}

/* Theme presets — color skins + "vocabulary" reskins that rename the whole
   OS metaphor (agents→baristas/brokers). Kept in sync with the command
   palette entries in app.jsx and THEME_VOCAB in ui.jsx. */
const THEME_PRESETS = [
  { id: 'default',      name: '🏢 Pixel Office',   sub: 'the classic HQ' },
  { id: 'sepia',        name: '📜 Sepia',          sub: 'warm parchment tones' },
  { id: 'solarized',    name: '🌊 Solarized',      sub: 'cool teal & amber' },
  { id: 'dracula',      name: '🦇 Dracula',        sub: 'dark purple neon' },
  { id: 'highcontrast', name: '◐ High Contrast',   sub: 'maximum legibility' },
  { id: 'coffeeshop',   name: '☕ Coffee Shop',     sub: 'agents become baristas' },
  { id: 'wallstreet',   name: '📈 Trading Floor',  sub: 'agents become brokers' },
];
const DENSITY_PRESETS = [
  { id: 'compact',     name: 'Compact' },
  { id: 'comfortable', name: 'Comfortable' },
  { id: 'spacious',    name: 'Spacious' },
];

function SettingsModal({ open, onClose, agents, onDismiss, onUpdateAgent, scanlines, setScanlines, sound, setSound, night, setNight, theme, setTheme, density, setDensity, initialTab, usageTokens = 0, windowsEnabled = false, setWindowsEnabled = () => {} }) {
  // Last-used tab survives reopen (and reload) — small thing, big QoL.
  const [tab, _setTab] = useStateM(() => {
    try {
      const t = localStorage.getItem('hq:settingsTab');
      if (t && SETTINGS_TABS.some(x => x.id === t)) return t;
    } catch (_e) {}
    return SETTINGS_TABS[0].id;
  });
  const setTab = (t) => {
    const id = SETTINGS_TAB_ALIAS[t] || t;
    _setTab(id);
    try { localStorage.setItem('hq:settingsTab', id); } catch (_e) {}
  };
  const [q, setQ] = useStateM('');
  const [selected, setSelected] = useStateM(agents[0]?.id || null);
  const sel = agents.find(a => a.id === selected) || agents[0];
  /* Same global localStorage key (and JSON.stringify'd shape) that
     views/terminal.jsx's useStoredV reads — this is the only place that
     ever writes it. Read/write it directly with the same JSON encoding
     rather than importing useStoredV from views/core.jsx: that import
     chains views/core.jsx -> features.jsx -> modals.jsx (the modals
     barrel) -> back to this file, and the circular import left `Modal`
     from './base.jsx' undefined at module-eval time, hard-crashing the
     whole app on load. Off by default: a fresh terminal tab should
     always land full-page in the app, not dead-end into a native OS
     window. Advanced, opt-in, for desktop/large-screen multitasking. */
  const POPOUT_KEY = 'cafresohq_terminal:popoutAllowed';
  const [popoutAllowed, setPopoutAllowed] = useStateM(() => {
    try {
      const raw = localStorage.getItem(POPOUT_KEY);
      return raw == null ? false : !!JSON.parse(raw);
    } catch (_e) { return false; }
  });
  const toggleTerminalPopout = () => {
    setPopoutAllowed(v => {
      const next = !v;
      try { localStorage.setItem(POPOUT_KEY, JSON.stringify(next)); } catch (_e) {}
      return next;
    });
  };

  // Live status for the nav rail: provider key state, CLI install count,
  // backend reachability. Refetched each time the modal opens.
  const [navStat, setNavStat] = useStateM({});
  /* null until /health answers. CONNECTIONS is for self-hosted installs
     only — on a managed container Cafreso holds the keys, so a panel about
     setting env vars would be noise at best and misleading at worst.
     Starts null (not false) so the tab doesn't flash in and out on a
     managed box during the probe. */
  const [managed, setManaged] = useStateM(null);
  useEffectM(() => {
    if (!open) return;
    let live = true;
    const C = CafresoHQClient;
    (async () => {
      // Managed premium: the only live status the nav needs is "is my
      // container up" — provider keys and CLI installs are Cafreso's job now.
      const stat = {};
      try { stat.backend = !!(await C.backendHealth()); } catch (_e) { stat.backend = false; }
      /* backendHealth() answers a BOOLEAN (reachable or not) — it does not
         hand back the body. The managed flag needs the body, so fetch it
         separately; AccountTab already does exactly this for the same
         reason. Leave `managed` null on any failure so a box we cannot
         classify never gets shown a panel aimed at the other kind. */
      let mg = null;
      try {
        const r = await fetch((window._API_BASE || '') + '/health',
          { cache: 'no-store', credentials: 'include' });
        const j = r.ok ? await r.json().catch(() => null) : null;
        if (j && typeof j === 'object') mg = !!j.managed;
      } catch (_e) { mg = null; }
      if (live) { setNavStat(stat); setManaged(mg); }
    })();
    return () => { live = false; };
  }, [open]);
  const visibleTabs = SETTINGS_TABS.filter(t => t.id !== 'connections' || managed === false);
  /* A managed box whose last-used tab was CONNECTIONS (self-hosted before,
     or the flag flipped) would land on a hidden tab and render an empty
     body — no nav item lit, nothing shown, no way to tell what went wrong.
     Fall back to the first visible tab instead. */
  const activeTab = visibleTabs.some(t => t.id === tab) ? tab : visibleTabs[0].id;

  // Deep-link: jump to a requested tab each time the modal is (re)opened
  // (e.g. the "no API key" chip opens straight to CONNECTIONS).
  const prevOpenRef = useRefM(false);
  useEffectM(() => {
    if (open && !prevOpenRef.current && initialTab) setTab(initialTab);
    prevOpenRef.current = open;
  }, [open, initialTab]);

  if (!open) return null;

  const update = (patch) => {
    if (!sel) return;
    onUpdateAgent(sel.id, patch);
  };

  // All query terms must match label+hint+kw (case-insensitive).
  const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hits = terms.length
    ? SETTINGS_INDEX.filter(e => {
        const hay = (e.label + ' ' + e.hint + ' ' + e.kw).toLowerCase();
        return terms.every(t => hay.includes(t));
      })
    : [];

  const navDot = (t) => {
    if (t.id === 'account' && navStat.backend !== undefined)
      return <span className={`sn-dot ${navStat.backend ? 'ok' : 'err'}`} title={navStat.backend ? 'office online' : 'office offline'}/>;
    return null;
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="SETTINGS"
      subtitle="preferences · connections · runtime"
      size="xl"
      footer={
        <>
          <div className="hint" style={{marginRight: 'auto'}}>Changes save automatically.</div>
          <button className="px-btn primary" onClick={onClose}>DONE</button>
        </>
      }
    >
      <div className="settings-shell">
        <aside className="settings-nav">
          <input className="settings-search" type="search" placeholder="🔍 search settings…"
            value={q} onChange={e => setQ(e.target.value)} aria-label="Search settings"/>
          {visibleTabs.map(t => (
            <button key={t.id} className={`sn-item ${activeTab===t.id && !terms.length ? 'active' : ''}`}
              onClick={() => { setQ(''); setTab(t.id); }}>
              <span className="sn-ico">{t.ico}</span>
              <span className="sn-txt">
                <span className="sn-label">{t.label}</span>
                <span className="sn-desc">{t.desc}</span>
              </span>
              {navDot(t)}
            </button>
          ))}
        </aside>
        <div className="settings-body">
          {terms.length > 0 && (
            <div className="cb-panel">
              <h4>SEARCH · {hits.length} RESULT{hits.length === 1 ? '' : 'S'}</h4>
              {hits.length === 0 && <div className="muted">Nothing matches “{q}”.</div>}
              {hits.map((e, i) => {
                const t = SETTINGS_TABS.find(x => x.id === e.tab);
                return (
                  <div key={i} className="row-knob" style={{cursor:'pointer'}}
                    onClick={() => { setQ(''); setTab(e.tab); }}>
                    <div>
                      <div className="lbl">{t ? t.ico : ''} {e.label}</div>
                      <div className="sub">{e.hint}</div>
                    </div>
                    <span className="tiny" style={{whiteSpace:'nowrap'}}>{t ? t.label : e.tab} →</span>
                  </div>
                );
              })}
            </div>
          )}

          {!terms.length && activeTab === 'icp-services' && (
            <IcpServicesPanel agents={agents} />
          )}

          {!terms.length && activeTab === 'media' && <MediaTab />}

          {!terms.length && activeTab === 'agents' && (
            <div className="control-board">
              <div className="cb-panel">
                <h4>ROSTER</h4>
                <div className="stack">
                  {agents.length === 0 && <div className="muted">No coworkers hired.</div>}
                  {agents.map(a => (
                    <div key={a.id} className={`row`} style={{
                      padding: '6px 8px',
                      background: selected===a.id ? 'var(--accent-sun)' : 'transparent',
                      border: '2px solid ' + (selected===a.id?'var(--ink)':'transparent'),
                      cursor: 'pointer',
                    }} onClick={()=>setSelected(a.id)}>
                      <Sprite data={a.color} scale={1.5}/>
                      <div className="grow" style={{display:'flex',flexDirection:'column',lineHeight:1.1}}>
                        <span style={{fontFamily:'Press Start 2P',fontSize:9}}>{a.name}</span>
                        <span className="tiny">{a.role}</span>
                      </div>
                      <button className="px-btn danger" style={{fontSize:8,padding:'6px 8px'}} onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="cb-panel">
                <h4>{sel ? `${sel.name.toUpperCase()} · CONFIG` : 'NO AGENT'}</h4>
                {sel && (
                  <div className="stack">
                    {/* §6's table, on the two rows that had been printing
                        the machine's word for years: `model (as a selector)`
                        → coworker, and `temperature` → hidden, or a
                        "creativity" dial if it ever surfaced. It surfaced.
                        The coworker card settled on **Brain** for the
                        selector in the 2026-08-06 audit; this is the same
                        control on a different screen and gets the same
                        word. Labels only — the stored fields are still
                        `model` and `temperature`, so nothing about an
                        agent's saved settings moves. */}
                    <div className="row-knob">
                      <span className="lbl">Brain</span>
                      <ModelPicker value={sel.model} onChange={v=>update({model:v})}/>
                    </div>
                    <div className="row-knob" style={{flexDirection:'column',alignItems:'stretch',gap:4}}>
                      <div className="row" style={{justifyContent:'space-between'}}><span className="lbl">Creativity</span><span className="sub">{sel.temperature?.toFixed(2)}</span></div>
                      <input type="range" className="pxslider" min="0" max="1" step="0.05" value={sel.temperature||0} onChange={e=>update({temperature:parseFloat(e.target.value)})}/>
                    </div>
                    <div style={{marginTop:6}}>
                      <div className="sub" style={{marginBottom:6}}>TOOLS</div>
                      <div className="tool-grid">
                        {visibleToolsCatalog().map(t => (
                          <div key={t.id} className={`tool-chk ${sel.tools.includes(t.id)?'on':''}`}
                               onClick={()=>update({tools: sel.tools.includes(t.id)?sel.tools.filter(x=>x!==t.id):[...sel.tools,t.id]})}>
                            <div className="box"/><span>{t.label}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="row-knob" style={{marginTop:6}}>
                      <div>
                        <div className="lbl">Tool call format</div>
                        <div className="sub">JSON = reliable for capable models; bracket = fallback for local OSS</div>
                      </div>
                      <select value={sel.toolFormat || 'auto'} onChange={e => update({ toolFormat: e.target.value })}>
                        <option value="auto">Auto-detect</option>
                        <option value="json">JSON ({"<<<TOOL>>>"})</option>
                        <option value="bracket">Bracket [TOOL: arg]</option>
                      </select>
                    </div>
                    <div className={`row-knob elevated-opt ${sel.elevated ? 'on' : ''}`} style={{marginTop:8,alignItems:'flex-start'}}>
                      <div>
                        <div className="lbl" style={{color: sel.elevated ? '#c44' : 'inherit'}}>🛡 File &amp; shell access</div>
                        <div className="sub" style={{maxWidth:240,marginTop:2}}>
                          Has file and shell access. Reachable by teammate DMs (noted in Team), missions opt-in, every action logged.
                        </div>
                      </div>
                      <div className={`pxswitch ${sel.elevated?'on':''}`} onClick={async ()=>{
                        if (!sel.elevated) {
                          if (!(await window.hqConfirm(
                            `Grant ${sel.name} COMPUTER ACCESS?\n\n` +
                            `They will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine. ` +
                            `Teammates can still send them DMs — each handoff is noted in the Team thread — missions require explicit authorization, and every tool call is logged.\n\n` +
                            `Continue?`, { danger: true, okLabel: 'Grant access' }
                          ))) return;
                        }
                        update({ elevated: !sel.elevated });
                      }}><div className="nub"/></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {!terms.length && activeTab === 'appearance' && (
            <div className="control-board">
              {setTheme && (
                <div className="cb-panel">
                  <h4>MAKE IT YOURS</h4>
                  <div className="sub" style={{ lineHeight: 1.6, marginBottom: 6 }}>
                    Reskin the whole OS — some presets change the vocabulary too
                    (your agents become baristas or brokers, the office becomes their floor).
                  </div>
                  <div className="tool-grid">
                    {THEME_PRESETS.map(t => (
                      <div key={t.id} className={`tool-chk ${theme === t.id ? 'on' : ''}`}
                           role="radio" aria-checked={theme === t.id}
                           onClick={() => setTheme(t.id)} title={t.sub}>
                        <div className="box" /><span>{t.name}</span>
                      </div>
                    ))}
                  </div>
                  <div className="tiny" style={{ marginTop: 4, opacity: .7 }}>
                    {(THEME_PRESETS.find(t => t.id === theme) || THEME_PRESETS[0]).sub}
                  </div>
                  {setDensity && (
                    <div className="row-knob" style={{ marginTop: 8 }}>
                      <div><div className="lbl">Density</div><div className="sub">how much breathing room the UI gets</div></div>
                      <div className="ws-seg">
                        {DENSITY_PRESETS.map(d => (
                          <button key={d.id} className={density === d.id ? 'on' : ''} onClick={() => setDensity(d.id)}>{d.name}</button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
              <div className="cb-panel">
                <h4>AMBIENCE</h4>
                <div className="row-knob">
                  <div><div className="lbl">Scanline overlay</div><div className="sub">soft CRT shimmer</div></div>
                  <div className={`pxswitch ${scanlines?'on':''}`} onClick={()=>setScanlines(!scanlines)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Sound FX</div><div className="sub">pixel blips on action</div></div>
                  <div className={`pxswitch ${sound?'on':''}`} onClick={()=>setSound(!sound)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">{night ? '☀ Day Mode' : '☾ Night Mode'}</div><div className="sub">{night ? 'switch to warm pastels' : 'switch to dark pixel theme'}</div></div>
                  <div className={`pxswitch ${night?'on':''}`} onClick={()=>setNight(v=>!v)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Keyboard shortcuts</div><div className="sub">1–8 switch views · S settings · D theme · Ctrl+K palette</div></div>
                  <span className="tiny">press Ctrl+K</span>
                </div>
              </div>
              <div className="cb-panel">
                <h4>ADVANCED</h4>
                <div className="row-knob">
                  <div>
                    <div className="lbl">Desktop window mode</div>
                    <div className="sub">open apps as draggable, resizable windows over the office floor instead of full-page. Off by default — for multitasking on Desktop/large screens.</div>
                  </div>
                  <div className={`pxswitch ${windowsEnabled?'on':''}`} role="switch" aria-checked={windowsEnabled} onClick={()=>setWindowsEnabled(v=>!v)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div>
                    <div className="lbl">Terminal pop-out windows</div>
                    <div className="sub">let a terminal tab open in a separate OS window, for multitasking on Desktop/large screens. Off by default — tabs stay full-page in the app.</div>
                  </div>
                  <div className={`pxswitch ${popoutAllowed?'on':''}`} role="switch" aria-checked={popoutAllowed} onClick={toggleTerminalPopout}><div className="nub"/></div>
                </div>
              </div>
            </div>
          )}

          {!terms.length && activeTab === 'account' && <AccountTab usageTokens={usageTokens} />}
          {/* managed === false, not just falsy: null means /health hasn't
              answered yet, and a managed box must never flash this panel. */}
          {!terms.length && activeTab === 'connections' && managed === false && <ConnectionsPanel />}
        </div>
      </div>
    </Modal>
  );
}

/* System tab — live backend/runtime visibility so "is it the key, the
   container, or the gateway?" is answerable from inside the app instead of
   the browser devtools. Read-only except the two action buttons. */
/* ACCOUNT — the managed-premium replacement for SYSTEM. Same /health probe,
   but speaks in plan/container/usage language instead of gateway internals.
   Everything a premium user might need when something feels off: is my HQ
   up, what brain am I on, what have I spent this session, and a one-click
   diagnostics copy for support. */
function AccountTab({ usageTokens = 0 }) {
  const [health, setHealth] = useStateM(null);   // null=loading · false=down · object=ok
  const [note, setNote] = useStateM('');
  const apiBase = (window._API_BASE || '');

  const load = async () => {
    try {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 3000);
      let r;
      try { r = await fetch(apiBase + '/health', { cache: 'no-store', credentials: 'include', signal: ctl.signal }); }
      finally { clearTimeout(t); }
      const j = r.ok ? await r.json().catch(() => null) : null;
      setHealth(j && typeof j === 'object' ? j : false);
    } catch (_e) { setHealth(false); }
  };
  useEffectM(() => { load(); }, []);

  const copyDiag = async () => {
    const diag = {
      when: new Date().toISOString(),
      apiBase: apiBase || '(same origin)',
      health: health || 'unreachable',
      usageTokensSinceHire: usageTokens,   // NOT per-session — see the label above
      ua: navigator.userAgent,
      url: location.href.split('?')[0],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setNote('✓ diagnostics copied — paste into a support chat');
    } catch (_e) { setNote('copy failed — clipboard blocked'); }
  };

  const resetOnboarding = async () => {
    if (!(await window.hqConfirm('Replay the new-user guide on next reload?'))) return;
    try {
      const kill = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && /tourseen|gettingstarted|coachseen|firstdeliveryseen/i.test(k)) kill.push(k);
      }
      kill.forEach(k => localStorage.removeItem(k));
      setNote(`✓ onboarding reset (${kill.length} flag${kill.length === 1 ? '' : 's'} cleared) — reload to replay`);
    } catch (_e) { setNote('reset failed'); }
  };

  const dot = (on) => <span className={`sn-dot ${on ? 'ok' : 'err'}`} style={{position:'static', marginRight:6}}/>;
  const uptime = health && health.uptime_seconds
    ? (health.uptime_seconds >= 3600
        ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m`
        : `${Math.floor(health.uptime_seconds / 60)}m`)
    : null;
  const fmtTokens = (n) => n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n);

  /* "Cafreso HQ Premium ... active" was hardcoded here with no gate at
     all — shown identically whether /health said managed:true or
     managed:false. A bare `python3 serve.py` self-host (health.managed
     false, health.brain null — confirmed live) got told it had an ACTIVE
     PAID plan with a brain "included", which is the exact fabricated-
     state failure this panel had already been caught doing twice before
     (see the "false span" note below, on Usage) — just not here yet.
     Self-hosted installs are the audience north-star §1 names first
     ("bring your own subscriptions"), so this is the first tab many of
     them will ever open. */
  const managed = !!(health && health.managed);
  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>YOUR PLAN</h4>
        {managed ? (
          <>
            <div className="row-knob">
              <div><div className="lbl">Cafreso HQ Premium</div><div className="sub">managed cloud — hosting, brain & updates included</div></div>
              <span className="tiny">{dot(true)}active</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">AI brain</div><div className="sub">included — no keys to manage</div></div>
              <span className="tiny">{health && health.brain && health.brain.model ? health.brain.model : 'not set yet'}</span>
            </div>
          </>
        ) : (
          <>
            <div className="row-knob plan-selfhosted">
              <div><div className="lbl">Self-hosted</div><div className="sub">running on your own machine — bring your own subscriptions or keys</div></div>
              <span className="tiny">{dot(!!health)}{health ? 'running' : 'unreachable'}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">AI brain</div><div className="sub">whatever your coworkers are configured with — see Roster</div></div>
              <span className="tiny">{health && health.brain && health.brain.model ? health.brain.model : 'no shared brain — per-coworker'}</span>
            </div>
          </>
        )}
        <div className="row-knob">
          {/* Third place this false span has been found today, after the
              roster card and the Situation Wall. `usageTokens` is
              app.jsx's `totalTokens` — ceoTokens plus the sum of every
              coworker's `tokens`, all of which live in the file-backed
              roster record and survive a reload byte for byte. It was
              labelled "this session", and the sub-line narrowed the lie
              further to "since this tab loaded".

              "tokens" stays: Settings is the config surface where naming
              the real unit is the point, the same reasoning that leaves
              raw model IDs visible here and banned on the floor. Only the
              SPAN was wrong, and it was wrong in both lines. */}
          <div><div className="lbl">Usage so far</div><div className="sub">tokens your crew has spent since you hired them</div></div>
          <span className="tiny">{fmtTokens(usageTokens || 0)} tokens</span>
        </div>
      </div>
      <div className="cb-panel">
        <h4>YOUR OFFICE</h4>
        <div className="row-knob">
          <div><div className="lbl">Status</div><div className="sub">{health === null ? 'checking…' : health ? 'online' : 'unreachable — we auto-reconnect'}</div></div>
          <span>{health === null ? '…' : dot(!!health)}</span>
        </div>
        {health && uptime && (
          <div className="row-knob">
            <div><div className="lbl">Up for</div><div className="sub">since your office last started</div></div>
            <span className="tiny">{uptime}</span>
          </div>
        )}
        <div className="row-knob">
          <div><div className="lbl">Diagnostics</div><div className="sub">snapshot for support — no keys included</div></div>
          <button className="px-btn" style={{fontSize:9,padding:'8px 10px'}} onClick={copyDiag}>COPY</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">New-user guide</div><div className="sub">replay the onboarding tour</div></div>
          <button className="px-btn" style={{fontSize:9,padding:'8px 10px'}} onClick={resetOnboarding}>RESET</button>
        </div>
        {note && <div className="hint" style={{marginTop:8}}>{note}</div>}
      </div>
    </div>
  );
}

function SystemTab() {
  const [health, setHealth] = useStateM(null);   // null=loading · false=down · object=ok
  const [prov, setProv] = useStateM(null);
  const [busy, setBusy] = useStateM(false);
  const [note, setNote] = useStateM('');
  const apiBase = (window._API_BASE || '');

  const load = async () => {
    setBusy(true);
    try {
      const r = await fetch(apiBase + '/health');
      setHealth(r.ok ? await r.json() : false);
    } catch (_e) { setHealth(false); }
    try {
      const C = CafresoHQClient;
      if (C.hermesGetProvider) setProv(await C.hermesGetProvider());
    } catch (_e) { setProv(null); }
    setBusy(false);
  };
  useEffectM(() => { load(); }, []);

  const copyDiag = async () => {
    const diag = {
      when: new Date().toISOString(),
      apiBase: apiBase || '(same origin)',
      health: health || 'unreachable',
      provider: prov || 'unknown',
      ua: navigator.userAgent,
      url: location.href.split('?')[0],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setNote('✓ diagnostics copied — paste into a support chat');
    } catch (_e) { setNote('copy failed — clipboard blocked'); }
  };

  // Agent-config portability (Hermes setup travels; keys never do).
  const importInputRef = useRefM(null);
  const [importBusy, setImportBusy] = useStateM(false);
  const exportConfig = async () => {
    try {
      const C = CafresoHQClient;
      const data = await C.hermesExportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'cafresohq-hermes-config.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      setNote('✓ config exported (keys not included)');
    } catch (e) { setNote('export failed: ' + e.message); }
  };
  const importConfig = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setImportBusy(true); setNote('');
    try {
      const text = await file.text();
      const C = CafresoHQClient;
      const r = await C.hermesImportConfig(text);
      setNote(r.restarted
        ? '✓ config imported — agent reloading (~10s). Re-enter your key in Connections if needed.'
        : '✓ config written (gateway restart pending)');
      load();
    } catch (er) { setNote('import failed: ' + er.message); }
    setImportBusy(false);
  };

  const resetOnboarding = async () => {
    if (!(await window.hqConfirm('Replay the new-user guide on next reload?'))) return;
    try {
      const kill = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && /tourseen|gettingstarted|coachseen|firstdeliveryseen/i.test(k)) kill.push(k);
      }
      kill.forEach(k => localStorage.removeItem(k));
      setNote(`✓ onboarding reset (${kill.length} flag${kill.length === 1 ? '' : 's'} cleared) — reload to replay`);
    } catch (_e) { setNote('reset failed'); }
  };

  const dot = (on) => (
    <span className={`sn-dot ${on ? 'ok' : 'err'}`} style={{position:'static', marginRight:6}}/>
  );
  const yn = (v) => v ? 'yes' : 'no';

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>OFFICE CONNECTION</h4>
        <div className="row-knob">
          <div><div className="lbl">API base</div><div className="sub">where this UI sends requests</div></div>
          <span className="tiny" style={{maxWidth:220, textAlign:'right', wordBreak:'break-all'}}>{apiBase || '(same origin)'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Status</div><div className="sub">{health === null ? 'checking…' : health ? 'serving' : 'unreachable'}</div></div>
          <span>{health === null ? '…' : dot(!!health)}</span>
        </div>
        {health && (
          <>
            <div className="row-knob">
              <div><div className="lbl">Runtime</div><div className="sub">where it's running</div></div>
              <span className="tiny">{health.runtime_env || 'unknown'}{health.auth_required ? ' · key-gated' : ''}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Hermes gateway</div><div className="sub">the built-in brain service</div></div>
              <span className="tiny">{dot(!!health.hermes)}{yn(!!health.hermes)}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Gemini CLI</div><div className="sub">installed here</div></div>
              <span className="tiny">{dot(!!health.gemini)}{yn(!!health.gemini)}</span>
            </div>
          </>
        )}
        <div className="row-knob">
          <div><div className="lbl">Re-check</div><div className="sub">probe /health again</div></div>
          <button className="px-btn secondary" disabled={busy} onClick={load}>{busy ? '…' : 'REFRESH'}</button>
        </div>
      </div>
      <div className="cb-panel">
        <h4>HERMES PROVIDER</h4>
        <div className="row-knob">
          <div><div className="lbl">Service</div><div className="sub">what Hermes is using right now</div></div>
          <span className="tiny">{prov ? prov.provider : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Model</div><div className="sub">current default</div></div>
          <span className="tiny" style={{maxWidth:200, textAlign:'right', wordBreak:'break-all'}}>{prov ? (prov.model || 'unknown') : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Key configured</div><div className="sub">set one in Connections if not</div></div>
          <span className="tiny">{prov === null ? '…' : <>{dot(!!(prov && prov.configured))}{yn(!!(prov && prov.configured))}</>}</span>
        </div>
      </div>
      <div className="cb-panel">
        <h4>AGENT CONFIG</h4>
        <div className="row-knob">
          <div><div className="lbl">Export setup</div><div className="sub">download your Hermes agent config (keys NOT included)</div></div>
          <button className="px-btn secondary" onClick={exportConfig}>EXPORT</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Import setup</div><div className="sub">apply an exported file or a raw ~/.hermes/config.yaml</div></div>
          <button className="px-btn secondary" disabled={importBusy}
            onClick={() => importInputRef.current && importInputRef.current.click()}>
            {importBusy ? '…' : 'IMPORT'}
          </button>
          <input ref={importInputRef} type="file" accept=".json,.yaml,.yml,.txt" style={{display:'none'}}
            onChange={importConfig}/>
        </div>
        <div className="hint">Moving between HQs (or from a local Hermes install)? Export here, import there — then re-enter your key in Connections.</div>
      </div>
      <div className="cb-panel">
        <h4>SUPPORT</h4>
        <div className="row-knob">
          <div><div className="lbl">Copy diagnostics</div><div className="sub">health + provider snapshot, no keys included</div></div>
          <button className="px-btn secondary" onClick={copyDiag}>COPY</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Reset onboarding</div><div className="sub">replay the new-user tour & checklist</div></div>
          <button className="px-btn secondary" onClick={resetOnboarding}>RESET</button>
        </div>
        {note && <div className="hint" style={{marginTop:6}}>{note}</div>}
      </div>
    </div>
  );
}

// Hermes backend services the user can pick (the free LLM behind Hermes). Each
// row adapts the key field's label / placeholder / "get a free key" link. Gemini
// direct is the most reliable free tier (≈15 RPM / 1500 per day) — the fix for
// OpenRouter :free's 20 RPM / 50-per-day throttling. Mirrors serve.py
// _HERMES_PROVIDERS + claude-client HERMES_PROVIDER_KEY_FIELD.

export { SettingsModal, visibleToolsCatalog };

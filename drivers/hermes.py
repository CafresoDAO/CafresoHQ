"""Hermes driver — Nous Research's agent gateway behind the driver contract.

Final extraction step (DRIVER_CONTRACT.md §5 step 3: "Hermes last"). Hermes
was the most privileged backend in serve.py — regex rewrites of
~/.hermes/config.yaml, .env secret writes, and four separate `hermes gateway
restart` call sites. ALL of that plumbing now lives here, driver-private:
serve.py's /hermes/* routes keep their HTTP shape (and the host-policy parts —
trial metering, the local-base_url allowlist) but every config/env/gateway
operation delegates to this module. Done-criterion from the contract doc:
zero hermes config/env/gateway knowledge outside drivers/hermes.py.

The runtime path is simple by comparison: the gateway exposes an
OpenAI-compatible API server on loopback (HERMES_HOST:HERMES_PORT), so
HermesDriver subclasses OpenAICompatDriver and fronts it like any other
HTTP backend, with the Bearer key injected from env/.env server-side.
"""
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys

from .local_http import OpenAICompatDriver

# The per-container `hermes gateway` OpenAI-compatible API server (enable via
# ~/.hermes/.env: API_SERVER_ENABLED=true, API_SERVER_KEY=…).
HERMES_HOST = os.environ.get('HERMES_API_HOST', '127.0.0.1')
HERMES_PORT = int(os.environ.get('HERMES_API_PORT', '8642') or '8642')

# Curated OpenRouter free open-weights ids verified to accept Hermes' large
# prompt. The UI offers these as one-click switches.
MODEL_PRESETS = [
    {'id': 'openai/gpt-oss-120b:free',                  'label': 'GPT-OSS 120B (default)'},
    {'id': 'nvidia/nemotron-3-super-120b-a12b:free',    'label': 'Nemotron 3 Super 120B'},
    {'id': 'nousresearch/hermes-3-llama-3.1-405b:free', 'label': 'Hermes 3 405B (Nous)'},
    {'id': 'meta-llama/llama-3.3-70b-instruct:free',    'label': 'Llama 3.3 70B'},
    {'id': 'qwen/qwen3-next-80b-a3b-instruct:free',     'label': 'Qwen3-Next 80B'},
]

# Backend providers the user can pick in HQ Settings. Each maps to the Hermes
# model block + the env var carrying its API key. OpenRouter is the
# zero-config default; Gemini (direct) is the most RELIABLE free tier; Groq is
# fast + free. 'local' backends are the operator's own hardware — they write
# `provider: lmstudio` either way (there is no `ollama` provider in
# hermes-agent; 'ollama' is a UI label, not a config value).
PROVIDERS = {
    'openrouter': {'env': 'OPENROUTER_API_KEY', 'model': 'openai/gpt-oss-120b:free',
                   're': r'^sk-or-[A-Za-z0-9_\-]{8,}$', 'label': 'OpenRouter'},
    'gemini':     {'env': 'GOOGLE_API_KEY',     'model': 'gemini-2.5-flash',
                   're': r'^AIza[A-Za-z0-9_\-]{30,}$', 'label': 'Google Gemini'},
    'groq':       {'env': 'GROQ_API_KEY',       'model': 'llama-3.3-70b-versatile',
                   're': r'^gsk_[A-Za-z0-9]{20,}$', 'label': 'Groq'},
    'lmstudio':   {'env': '', 'model': 'local-model', 're': None, 'local': True,
                   'label': 'LM Studio (local)', 'default_url': 'http://localhost:1234/v1'},
    'ollama':     {'env': '', 'model': 'llama3.1', 're': None, 'local': True,
                   'label': 'Ollama (local)', 'default_url': 'http://localhost:11434/v1'},
}


# ── paths ────────────────────────────────────────────────────────────────────
def home():
    return os.environ.get('HERMES_HOME', '').strip() or os.path.expanduser('~/.hermes')

def config_path():
    return os.path.join(home(), 'config.yaml')

def capability_file():
    return os.path.join(home(), 'capability_mode')


# ── binary / gateway lifecycle ───────────────────────────────────────────────
def resolve(binary_override=''):
    """Find the hermes binary. Returns absolute path or ''. Hermes is
    unix-only (gateway/pty_bridge import termios/pty/fcntl) so this never
    resolves on native Windows — run the stack in WSL instead."""
    override = binary_override or os.environ.get('CAFRESOHQ_HERMES_BIN', '').strip()
    if override and pathlib.Path(override).is_file():
        return override
    return shutil.which(override or 'hermes') or ''

def gateway_running():
    """True when the Hermes gateway is accepting connections on loopback."""
    try:
        with socket.create_connection((HERMES_HOST, HERMES_PORT), timeout=0.8):
            return True
    except OSError:
        return False

def gateway_restart(reason=''):
    """Best-effort `hermes gateway restart` (replaces the running singleton;
    the proxy keeps serving until the new gateway binds, ~10s). Returns
    whether the restart was launched. THE one restart call site."""
    try:
        subprocess.Popen(['hermes', 'gateway', 'restart'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        sys.stderr.write(f'[hermes] {reason or "gateway"} restart failed: {e}\n')
        return False

def api_server_key():
    """The gateway's Bearer key: API_SERVER_KEY env var, falling back to
    ~/.hermes/.env so the proxy works even when the var wasn't injected at
    container start."""
    key = os.environ.get('API_SERVER_KEY', '').strip()
    if key:
        return key
    try:
        with open(os.path.join(home(), '.env'), 'r', encoding='utf-8') as f:
            m = re.search(r'^API_SERVER_KEY\s*=\s*([^\r\n]+)', f.read(), re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"\'')
    except Exception:
        pass
    return ''


# ── config.yaml: model ───────────────────────────────────────────────────────
def read_model():
    """Current model.default from config.yaml, '' if unreadable."""
    try:
        with open(config_path(), 'r', encoding='utf-8') as f:
            m = re.search(r'^\s*default:\s*(.+)\s*$', f.read(), re.MULTILINE)
        return m.group(1).strip() if m else ''
    except Exception:
        return ''

def valid_model_id(model):
    """Presets OR any plausible model id. The vendor slash is OPTIONAL: cloud
    ids look like "vendor/model[:tag]" but local ones often don't — Ollama's
    are bare ("llama3.3:70b"), and requiring the slash 400'd every local
    backend."""
    return any(p['id'] == model for p in MODEL_PRESETS) or \
        bool(re.match(r'^[\w.\-]+(/[\w.\-]+)*(:[\w.\-]+)?$', model))

def write_model(model):
    """Rewrite config.yaml model.default (provider/base_url preserved) and
    restart the gateway. Returns (ok, restarted, error)."""
    try:
        with open(config_path(), 'r', encoding='utf-8') as f:
            cfg = f.read()
    except Exception as e:
        return False, False, f'read config: {e}'
    new_cfg, n = re.subn(r'(^\s*default:\s*).+$',
                         lambda m: m.group(1) + model, cfg,
                         count=1, flags=re.MULTILINE)
    if n == 0:
        return False, False, 'no model.default line in config'
    try:
        with open(config_path(), 'w', encoding='utf-8') as f:
            f.write(new_cfg)
    except Exception as e:
        return False, False, f'write config: {e}'
    return True, gateway_restart('model'), ''


# ── config.yaml: capability (lite/full system-prompt size) ──────────────────
def read_capability():
    try:
        with open(capability_file(), 'r', encoding='utf-8') as f:
            mode = (f.read().strip() or 'lite')
    except Exception:
        mode = 'lite'
    return mode if mode in ('lite', 'full') else 'lite'

def write_capability(mode):
    """Rewrite config.yaml's capability tail (everything from the first
    'toolsets:' line) + the mode file, then restart. The block layout matches
    docker/hermes-bootstrap.py:_capability_block so the two stay in sync.
    Returns (ok, restarted, error)."""
    if mode == 'full':
        block = ('toolsets:\n  - hermes-cli\n'
                 'agent:\n  environment_probe: true\n  task_completion_guidance: true\n'
                 'tools:\n  tool_search:\n    enabled: auto\n')
    else:
        block = ('toolsets:\n  - hermes-cli\n'
                 'agent:\n  environment_probe: false\n  task_completion_guidance: false\n'
                 'tools:\n  tool_search:\n    enabled: true\n    threshold_pct: 0\n')
    try:
        with open(config_path(), 'r', encoding='utf-8') as f:
            cfg = f.read()
    except Exception as e:
        return False, False, f'read config: {e}'
    idx = cfg.find('\ntoolsets:')
    new_cfg = (cfg[:idx + 1] if idx >= 0 else cfg.rstrip() + '\n') + block
    try:
        with open(config_path(), 'w', encoding='utf-8') as f:
            f.write(new_cfg)
        with open(capability_file(), 'w', encoding='utf-8') as f:
            f.write(mode)
    except Exception as e:
        return False, False, f'write config: {e}'
    return True, gateway_restart('capability'), ''


# ── config.yaml + .env: provider switch ──────────────────────────────────────
def model_block(provider, model, base_url=None):
    """The config.yaml model block (+ custom_providers) for a provider."""
    if provider in ('lmstudio', 'ollama'):
        # Mirrors docker/hermes-bootstrap.py's lmstudio block exactly:
        # no key_env, no custom_providers. Both UI labels write `lmstudio`.
        return (f'model:\n  default: {model}\n  provider: lmstudio\n'
                f'  base_url: {base_url}\n')
    if provider == 'gemini':
        return (f'model:\n  default: {model}\n  provider: google-openai\n'
                '  base_url: https://generativelanguage.googleapis.com/v1beta/openai\n'
                'custom_providers:\n'
                '  - name: google-openai\n'
                '    base_url: https://generativelanguage.googleapis.com/v1beta/openai\n'
                '    key_env: GOOGLE_API_KEY\n'
                '    api_mode: chat_completions\n')
    if provider == 'groq':
        return (f'model:\n  default: {model}\n  provider: groq\n'
                '  base_url: https://api.groq.com/openai/v1\n'
                'custom_providers:\n'
                '  - name: groq\n'
                '    base_url: https://api.groq.com/openai/v1\n'
                '    key_env: GROQ_API_KEY\n'
                '    api_mode: chat_completions\n')
    # openrouter — Hermes' native default provider (no custom_providers)
    return (f'model:\n  default: {model}\n  provider: openrouter\n'
            '  base_url: https://openrouter.ai/api/v1\n')

def key_configured(env_var):
    """Whether env_var carries a key — process env first, then ~/.hermes/.env."""
    if os.environ.get(env_var, '').strip():
        return True
    try:
        with open(os.path.join(home(), '.env'), 'r', encoding='utf-8') as f:
            return bool(re.search(r'(?m)^%s\s*=\s*\S' % re.escape(env_var), f.read()))
    except Exception:
        return False

def write_provider(provider, key, model, base_url):
    """Write the provider's key into ~/.hermes/.env (0600, replacing any prior
    line for THIS env var; skipped for local backends), REWRITE config.yaml's
    model block preserving the capability tail, export the key into THIS
    process env (the restarted gateway inherits it), and restart. The caller
    has already validated provider/key/base_url — this is pure plumbing.
    Returns (ok, restarted, error)."""
    spec = PROVIDERS[provider]
    local = bool(spec.get('local'))
    env_path = os.path.join(home(), '.env')
    try:
        os.makedirs(home(), exist_ok=True)
        if not local:
            lines = []
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = [l for l in f.read().splitlines()
                             if not l.startswith(spec['env'] + '=')]
            lines.append(f"{spec['env']}={key}")
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            try:
                os.chmod(env_path, 0o600)
            except Exception:
                pass
    except Exception as e:
        return False, False, f'write .env: {e}'

    try:
        cfg = ''
        if os.path.exists(config_path()):
            with open(config_path(), 'r', encoding='utf-8') as f:
                cfg = f.read()
        header = ('# CafresoHQ — Hermes config (provider set via HQ Settings).\n'
                  '# capability_mode controls system-prompt size (lite=free-tier-safe).\n')
        block = model_block(provider, model, base_url)
        m = re.search(r'^approvals:', cfg, re.MULTILINE)
        if m:
            new_cfg = header + block + cfg[m.start():]
        else:
            # fresh/unknown config — write a complete minimal one (lite caps)
            new_cfg = (header + block +
                       'approvals:\n  mode: manual\n'
                       'toolsets:\n  - hermes-cli\n'
                       'agent:\n  environment_probe: false\n  task_completion_guidance: false\n'
                       'tools:\n  tool_search:\n    enabled: true\n    threshold_pct: 0\n')
        with open(config_path(), 'w', encoding='utf-8') as f:
            f.write(new_cfg)
    except Exception as e:
        return False, False, f'write config: {e}'

    if not local:
        os.environ[spec['env']] = key
    return True, gateway_restart('provider'), ''


# ── config import/export (config.yaml holds NO secrets) ─────────────────────
def export_config():
    """(config_yaml, capability) — keys live in .env and are never exported."""
    cfg = ''
    try:
        with open(config_path(), 'r', encoding='utf-8') as f:
            cfg = f.read()
    except Exception:
        pass
    return cfg, read_capability()

def import_config(cfg, capability=''):
    """Replace config.yaml (keeping a .bak rollback copy), optionally set the
    capability mode file, restart. The caller has already refused key
    material and non-configs. Returns (ok, restarted, rollback_path, error)."""
    cfg_p = config_path()
    try:
        os.makedirs(home(), exist_ok=True)
        if os.path.exists(cfg_p):
            try:
                with open(cfg_p, 'r', encoding='utf-8') as f:
                    prev = f.read()
                with open(cfg_p + '.bak', 'w', encoding='utf-8') as f:
                    f.write(prev)
            except Exception:
                pass
        with open(cfg_p, 'w', encoding='utf-8') as f:
            f.write(cfg)
    except Exception as e:
        return False, False, cfg_p + '.bak', f'write config: {e}'
    if capability in ('lite', 'full'):
        try:
            with open(capability_file(), 'w', encoding='utf-8') as f:
                f.write(capability)
        except Exception:
            pass
    return True, gateway_restart('import'), cfg_p + '.bak', ''


# ── the driver ───────────────────────────────────────────────────────────────
class HermesDriver(OpenAICompatDriver):
    """Hermes as one driver among peers. The agent gateway IS an
    OpenAI-compatible HTTP backend from the contract's point of view; all the
    config surgery above is what configure() fronts."""
    MANIFEST = {
        'id': 'hermes',
        'displayName': 'Hermes',
        'sprite': 'coworker-hermes',
        'kind': 'http',
        'authMode': 'local-daemon',
        'models': [dict(p) for p in MODEL_PRESETS],
        'capabilities': {'streaming': True, 'tools': True,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'metered',
    }

    def __init__(self):
        super().__init__()
        self.binary_override = os.environ.get('CAFRESOHQ_HERMES_BIN', '').strip()

    def resolve(self):
        return resolve(self.binary_override)

    @staticmethod
    def detect_auth():
        """config.yaml present = configured (hermes has no login of its own —
        provider keys live in .env, written by configure)."""
        try:
            if os.path.isfile(config_path()):
                return True, 'config'
        except OSError:
            pass
        return False, ''

    def detect(self, probe_version=False):
        d = super().detect(probe_version=False)
        bin_ = self.resolve()
        authed, mech = self.detect_auth()
        d.update({'installed': bool(bin_), 'authenticated': authed,
                  'auth': mech, 'detail': bin_ or d['detail']})
        if probe_version:
            d['version'] = 'gateway up' if gateway_running() else ''
        return d

    def configure(self, settings):
        """The consolidation of serve.py's four privileged paths:
          {'model': id}                          → write_model
          {'capability': 'lite'|'full'}          → write_capability
          {'provider', 'key', 'model'?, 'baseUrl'?} → write_provider
        Validation (key regexes, the local-base_url allowlist, trial policy)
        stays with the HOST — this applies pre-validated changes."""
        from .base import DriverError
        settings = settings or {}
        if 'provider' in settings:
            ok, restarted, err = write_provider(
                settings['provider'], settings.get('key', ''),
                settings.get('model', ''), settings.get('baseUrl'))
        elif 'capability' in settings:
            ok, restarted, err = write_capability(settings['capability'])
        elif 'model' in settings:
            ok, restarted, err = write_model(settings['model'])
        else:
            raise DriverError('nothing to configure', status=400)
        if not ok:
            raise DriverError(err, status=500)
        d = self.detect()
        d['restarted'] = restarted
        return d

    def base_url(self):
        return self._base_override or f'http://{HERMES_HOST}:{HERMES_PORT}/v1'

    def api_key(self):
        return self._key_override or api_server_key()

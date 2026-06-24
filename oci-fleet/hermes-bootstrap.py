#!/usr/bin/env python3
"""CafresoHQ — in-container Hermes Agent bootstrap.

Runs once at container start (from entrypoint.sh) BEFORE `hermes gateway`.
Idempotently seeds $HERMES_HOME with:
  - .env       : API_SERVER_ENABLED + API_SERVER_KEY (+ backend key passthrough)
  - config.yaml: a minimal `model` block, backend chosen by key precedence

Backend precedence (first available wins):
  1. OPENROUTER_API_KEY -> provider=openrouter (DEFAULT; free tier has NO request
                           size cap, so Hermes' ~17k prompt fits. Groq free 413s.)
  1b GROQ_API_KEY       -> provider=groq (needs PAID tier for Hermes prompt size)
  2. LMSTUDIO_BASE_URL  -> provider=lmstudio (explicit OpenAI-compatible endpoint)
  3. ANTHROPIC_API_KEY  -> provider=anthropic (BYOK)
  4. GOOGLE_API_KEY     -> provider=gemini (BYOK)
  5. none               -> OpenRouter stub written; API server starts but calls
                           error until OPENROUTER_API_KEY is supplied. Non-fatal.

Never raises fatally — a bad bootstrap must not stop serve.py from serving the
app shell. All writes are skip-if-exists so user edits survive restarts.
"""
import os
import sys

HERMES_HOME = os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')


def _log(msg):
    sys.stderr.write(f'[hermes-bootstrap] {msg}\n')


def _write_env():
    """Write API server settings into $HERMES_HOME/.env (append missing keys)."""
    env_path = os.path.join(HERMES_HOME, '.env')
    existing = ''
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                existing = f.read()
        except Exception:
            existing = ''

    want = {
        'API_SERVER_ENABLED': os.environ.get('API_SERVER_ENABLED', 'true'),
        # API_SERVER_KEY comes from the container env (set per-principal by
        # fleet-manager.py). Same var serve.py reads to inject the Bearer token,
        # so proxy and gateway agree on the key.
        'API_SERVER_KEY': os.environ.get('API_SERVER_KEY', ''),
    }
    # Pass through whichever backend key is present so dotenv-only reads work too.
    for k in ('OPENROUTER_API_KEY', 'GROQ_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY'):
        v = os.environ.get(k, '').strip()
        if v:
            want[k] = v

    lines = []
    for k, v in want.items():
        if not v:
            continue
        if f'{k}=' in existing:
            continue  # don't clobber an existing definition
        lines.append(f'{k}={v}')

    if not lines:
        _log(f'.env already has required keys ({env_path})')
        return
    try:
        with open(env_path, 'a', encoding='utf-8') as f:
            if existing and not existing.endswith('\n'):
                f.write('\n')
            f.write('\n'.join(lines) + '\n')
        _log(f'wrote {len(lines)} key(s) to {env_path}')
    except Exception as e:
        _log(f'WARN could not write .env: {e}')


def _model_block():
    """Return YAML for the model block based on key precedence.

    DEFAULT for new HQ containers is **OpenRouter** (Hermes' native default) on a
    free open-weights model — its free tier has no per-request size cap, so
    Hermes' large system prompt fits (Groq free does not). New users get a capable
    model out of the box at no per-token cost. Users can later bring their own
    Claude / Gemini / other key via HQ settings, which writes a higher-precedence
    backend into this same config — proprietary providers are NEVER the out-of-box
    default; they apply only when the operator/user explicitly supplies that key.
    """
    # ── 1. OpenRouter (DEFAULT for new users) ───────────────────────────────
    # OpenRouter is Hermes' NATIVE default provider (no custom_providers needed).
    # Why it's the default over Groq: Groq's FREE tier caps request size at
    # ~5-6k tokens, but Hermes injects a ~17k-token agent system prompt → every
    # call 413s. OpenRouter's free tier has NO per-request size cap (only req/min
    # + req/day frequency limits), so Hermes' full prompt fits.
    #
    # Model: openai/gpt-oss-120b:free (131k ctx) — chosen because the :free
    # endpoint responds reliably AND accepts the 18k payload (verified). Override
    # with OPENROUTER_MODEL, e.g. nousresearch/hermes-3-llama-3.1-405b:free when
    # that provider isn't upstream-throttled.
    openrouter = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if openrouter:
        mdl = os.environ.get('OPENROUTER_MODEL', '').strip() or 'openai/gpt-oss-120b:free'
        _log(f'backend: OpenRouter (default open-weights, model={mdl})')
        return (
            'model:\n'
            f'  default: {mdl}\n'
            '  provider: openrouter\n'
            '  base_url: https://openrouter.ai/api/v1\n'
        )

    # ── 1b. Groq (alternate open-weights; only if explicitly keyed) ─────────
    # NOTE: Groq FREE tier 413s on Hermes' prompt — use a paid Groq key here.
    groq = os.environ.get('GROQ_API_KEY', '').strip()
    if groq:
        mdl = os.environ.get('GROQ_MODEL', '').strip() or 'openai/gpt-oss-120b'
        _log(f'backend: Groq (model={mdl}) — needs paid tier for Hermes prompt size')
        return (
            'model:\n'
            f'  default: {mdl}\n'
            '  provider: groq\n'
            '  base_url: https://api.groq.com/openai/v1\n'
            'custom_providers:\n'
            '  - name: groq\n'
            '    base_url: https://api.groq.com/openai/v1\n'
            '    key_env: GROQ_API_KEY\n'
            '    api_mode: chat_completions\n'
        )

    # ── 2. Explicit OpenAI-compatible endpoint (LM Studio / Ollama / vLLM) ──
    # Set LMSTUDIO_BASE_URL (e.g. http://host:1234/v1) + optional LMSTUDIO_MODEL.
    lm = os.environ.get('LMSTUDIO_BASE_URL', '').strip()
    if lm:
        mdl = os.environ.get('LMSTUDIO_MODEL', '').strip() or 'local-model'
        _log(f'backend: LM Studio / OpenAI-compatible at {lm} (model={mdl})')
        return (
            'model:\n'
            f'  default: {mdl}\n'
            '  provider: lmstudio\n'
            f'  base_url: {lm}\n'
        )

    # ── 3. User-supplied proprietary keys (BYOK) — never the default ─────────
    # These only apply when the user/operator has explicitly attached the key
    # (e.g. via HQ app settings after first provisioning). Order is preference,
    # not out-of-box behavior.
    if os.environ.get('ANTHROPIC_API_KEY', '').strip():
        _log('backend: anthropic (user-supplied key)')
        return (
            'model:\n'
            '  default: claude-haiku-4-5\n'
            '  provider: anthropic\n'
        )
    if os.environ.get('GOOGLE_API_KEY', '').strip():
        _log('backend: gemini (user-supplied GOOGLE_API_KEY)')
        return (
            'model:\n'
            '  default: gemini-2.5-flash\n'
            '  provider: gemini\n'
            '  base_url: https://generativelanguage.googleapis.com/v1beta\n'
        )
    # ── 4. No key at all ────────────────────────────────────────────────────
    # Write an OpenRouter stub so the model is correct the moment an
    # OPENROUTER_API_KEY is added; until then the API server starts but errors.
    _log('WARN no backend key found — defaulting to OpenRouter config; set OPENROUTER_API_KEY to enable')
    return (
        'model:\n'
        '  default: openai/gpt-oss-120b:free\n'
        '  provider: openrouter\n'
        '  base_url: https://openrouter.ai/api/v1\n'
    )


def _capability_block(mode: str) -> str:
    """Return the toolsets/tools/agent YAML for a capability mode.

    WHY THIS EXISTS:
      Hermes injects its full toolset + instructions into the system prompt on
      every call (~14-17k tokens). Free hosted tiers (e.g. Groq free) reject
      requests over ~5-6k tokens with HTTP 413 "request too large" — so the
      default MUST ship a trimmed prompt or no completion ever succeeds.

      'lite'  (DEFAULT): enables tool_search so tool schemas are DEFERRED
              (loaded on demand, not dumped into the prompt) and turns off the
              environment probe + completion-guidance preamble. Fits the free
              tier. Agents still work — they search for the tool they need.
      'full'  (opt-in via HQ Settings, best with BYOK / paid keys): tool_search
              auto, environment probe + guidance on — richer one-shot context for
              heavier workloads where the bigger prompt is affordable.

    The HQ Settings toggle calls serve.py /hermes/capability which rewrites this
    block and restarts the gateway (see serve.py _hermes_capability)."""
    mode = (mode or 'lite').strip().lower()
    if mode == 'full':
        return (
            'toolsets:\n'
            '  - hermes-cli\n'
            'agent:\n'
            '  environment_probe: true\n'
            '  task_completion_guidance: true\n'
            'tools:\n'
            '  tool_search:\n'
            '    enabled: auto\n'
        )
    # lite (default) — minimal prompt so the free tier fits
    return (
        'toolsets:\n'
        '  - hermes-cli\n'
        'agent:\n'
        '  environment_probe: false\n'
        '  task_completion_guidance: false\n'
        'tools:\n'
        '  tool_search:\n'
        '    enabled: true\n'      # force deferred tool schemas → small prompt
        '    threshold_pct: 0\n'   # always defer, never inline the toolset
    )


def _write_config():
    cfg_path = os.path.join(HERMES_HOME, 'config.yaml')
    if os.path.exists(cfg_path):
        _log(f'config.yaml exists — leaving as-is ({cfg_path})')
        return
    mode = os.environ.get('HERMES_CAPABILITY_MODE', 'lite').strip().lower()
    _log(f'capability mode: {mode}')
    body = (
        '# CafresoHQ — auto-generated minimal Hermes config (in-container).\n'
        '# Backend chosen by key precedence at first boot; edit to customize.\n'
        '# capability_mode controls system-prompt size (lite=free-tier-safe).\n'
        + _model_block() +
        'approvals:\n'
        '  mode: manual\n'   # surface flagged tools to the HQ ApprovalTray (Phase 2)
        + _capability_block(mode)
    )
    try:
        with open(cfg_path, 'w', encoding='utf-8') as f:
            f.write(body)
        _log(f'wrote {cfg_path}')
    except Exception as e:
        _log(f'WARN could not write config.yaml: {e}')


def main():
    try:
        os.makedirs(HERMES_HOME, exist_ok=True)
        if not os.environ.get('API_SERVER_KEY', '').strip():
            _log('WARN API_SERVER_KEY is empty — the API server requires it; '
                 'set it per-principal via fleet-manager.py')
        _write_env()
        _write_config()
        _log(f'done (HERMES_HOME={HERMES_HOME})')
    except Exception as e:
        _log(f'WARN bootstrap failed (non-fatal): {e}')


if __name__ == '__main__':
    main()

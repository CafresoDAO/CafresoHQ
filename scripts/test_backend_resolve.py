#!/usr/bin/env python3
"""Backend resolution tests — night_runner.resolve_backend + serve's base_url allowlist.

This is the seam that decides whether a plain model call goes DIRECT to the
operator's backend or falls back to the hermes agent gateway. Getting it wrong is
quiet: a bad resolve doesn't crash, it just silently routes every search back
through a gateway that costs ~13k prompt tokens and ignores max_tokens/model.

Covers the three bugs the old read_provider_config had (unanchored `default:`,
discarded base_url, keyless-local treated as unconfigured), the fleet-live
gemini base_url divergence, and the SSRF allowlist on the picker's base_url.

No network. Run: python3 scripts/test_backend_resolve.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SEARCH_WORKER', '')      # never start the worker loop
import night_runner as nr  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def home(config=None, env=None):
    d = tempfile.mkdtemp()
    if config is not None:
        with open(os.path.join(d, 'config.yaml'), 'w') as f:
            f.write(config)
    if env is not None:
        with open(os.path.join(d, '.env'), 'w') as f:
            f.write(env)
    return d


LMSTUDIO = '''# auto-generated
model:
  default: openai/gpt-oss-20b
  provider: lmstudio
  base_url: http://10.0.0.100:1234/v1
approvals:
  mode: manual
tools:
  tool_search:
    enabled: auto
'''

# The decoy: a `default:` OUTSIDE the model block. The old `^\\s*default:` search
# would happily return "manual" as the model.
DECOY = '''model:
  default: real/model
  provider: lmstudio
  base_url: http://127.0.0.1:1234/v1
approvals:
  default: decoy-should-lose
  mode: manual
'''

# hermes-bootstrap writes gemini's base_url as /v1beta; serve.py writes
# /v1beta/openai. Both are live in the fleet.
GEMINI_BOOTSTRAP = '''model:
  default: gemini-2.5-flash
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta
approvals:
  mode: manual
'''

ANTHROPIC = '''model:
  default: claude-haiku-4-5
  provider: anthropic
approvals:
  mode: manual
'''


def test_read_model_config():
    print('read_model_config')
    c = nr.read_model_config(home(LMSTUDIO))
    check('reads provider/model/base_url', (c['raw_provider'], c['model'], c['base_url'])
          == ('lmstudio', 'openai/gpt-oss-20b', 'http://10.0.0.100:1234/v1'), c)
    check('ok=True on a real config', c['ok'] is True)

    c = nr.read_model_config(home(DECOY))
    check('a `default:` outside the model block cannot win', c['model'] == 'real/model', c)

    check('absent config → ok=False, no raise', nr.read_model_config(home())['ok'] is False)
    check('garbage config → ok=False, no raise', nr.read_model_config(home('!!! not yaml'))['ok'] is False)
    check('config with no model block → ok=False', nr.read_model_config(home('approvals:\n  mode: manual\n'))['ok'] is False)


def test_resolve_local():
    print('resolve_backend — local')
    b = nr.resolve_backend(home(LMSTUDIO), env={})
    check('keyless lmstudio resolves (was: thrown away)', b is not None)
    check('marked local', b and b.local is True)
    check('base_url is kept and completed', b and b.url == 'http://10.0.0.100:1234/v1/chat/completions', b and b.url)
    check('no Authorization header when keyless', b and 'Authorization' not in b.headers, b and b.headers)
    check('model carried through', b and b.model == 'openai/gpt-oss-20b', b and b.model)

    b = nr.resolve_backend(home(LMSTUDIO), model_override='nvidia/nemotron-3-nano', env={})
    check('WORKER_MODEL override wins', b and b.model == 'nvidia/nemotron-3-nano', b and b.model)

    # An unknown provider that still says where it lives is usable.
    b = nr.resolve_backend(home('model:\n  default: m\n  provider: somethingnew\n  base_url: http://127.0.0.1:9/v1\n'), env={})
    check('unknown provider + base_url → local', b is not None and b.local, b)

    # ...but an unknown provider with nowhere to go is not.
    b = nr.resolve_backend(home('model:\n  default: m\n  provider: somethingnew\n'), env={})
    check('unknown provider without base_url → None', b is None, b)

    # Regression (audit): an inline YAML comment on the provider line must not
    # drop the provider and silently reroute a private local call to the
    # openrouter cloud on a stale key.
    COMMENTED = ('model:\n  default: openai/gpt-oss-20b\n'
                 '  provider: lmstudio  # local box, keep queries private\n'
                 '  base_url: http://10.0.0.100:1234/v1\n')
    check('inline comment does not drop the provider',
          nr.read_model_config(home(COMMENTED))['raw_provider'] == 'lmstudio')
    b = nr.resolve_backend(home(COMMENTED), env={'OPENROUTER_API_KEY': 'sk-or-stale'})
    check('commented-provider local stays local, not openrouter cloud',
          b is not None and b.local and b.provider == 'lmstudio' and b.local, b)
    # Even with NO provider line, a base_url must not default to the cloud.
    b = nr.resolve_backend(home('model:\n  default: m\n  base_url: http://10.0.0.9:1234/v1\n'),
                           env={'OPENROUTER_API_KEY': 'sk-or-stale'})
    check('base_url without a provider resolves local, not openrouter', b is not None and b.local, b)


def test_resolve_cloud():
    print('resolve_backend — cloud')
    b = nr.resolve_backend(home(GEMINI_BOOTSTRAP, env='GOOGLE_API_KEY=AIzaTESTKEY\n'), env={})
    check('gemini resolves from .env', b is not None)
    check('gemini alias applied', b and b.provider == 'gemini' and b.raw_provider == 'gemini', b)
    # The load-bearing one: bootstrap's base_url is /v1beta, which would 404.
    check('cloud IGNORES base_url, uses _PROVIDER_ENDPOINTS',
          b and b.url == nr._PROVIDER_ENDPOINTS['gemini'][1], b and b.url)
    check('cloud sends Authorization', b and b.headers.get('Authorization') == 'Bearer AIzaTESTKEY', b and b.headers)
    check('cloud not marked local', b and b.local is False)

    b = nr.resolve_backend(home(GEMINI_BOOTSTRAP), env={})
    check('cloud without a key → None (gateway)', b is None, b)

    b = nr.resolve_backend(home(GEMINI_BOOTSTRAP), env={'GOOGLE_API_KEY': 'AIzaFROMENV'})
    check('env key beats .env file', b and b.key == 'AIzaFROMENV', b and b.key)

    b = nr.resolve_backend(home('model:\n  default: x\n  provider: google-openai\n'),
                           env={'GOOGLE_API_KEY': 'k'})
    check('google-openai alias → gemini endpoint', b and b.url == nr._PROVIDER_ENDPOINTS['gemini'][1], b and b.url)
    check('alias keeps raw_provider for callers', b and b.raw_provider == 'google-openai', b and b.raw_provider)


def test_resolve_none():
    print('resolve_backend — no direct path')
    check('anthropic → None (gateway only)', nr.resolve_backend(home(ANTHROPIC), env={}) is None)
    check('absent config → None', nr.resolve_backend(home(), env={}) is None)
    check('garbage config → None, no raise', nr.resolve_backend(home('\x00\x01 not yaml'), env={}) is None)


def test_shim():
    print('read_provider_config shim (pins llm_call)')
    p, m, k = nr.read_provider_config(home(GEMINI_BOOTSTRAP, env='GOOGLE_API_KEY=AIzaK\n'))
    check('cloud still returns (provider, model, key)', (p, m, k) == ('gemini', 'gemini-2.5-flash', 'AIzaK'), (p, m, k))
    # llm_call does _PROVIDER_ENDPOINTS[alias(provider)] — raw_provider must survive.
    check('returned provider is a valid _PROVIDER_ENDPOINTS key after aliasing',
          nr._PROVIDER_ENDPOINTS.get({'google-openai': 'gemini'}.get(p, p)) is not None)
    # llm_call guards on `if not key: raise` — a keyless local must look unconfigured
    # to it, or the night shift would try to POST to a local box with no key.
    check('keyless local → (None,None,None) for the shim',
          nr.read_provider_config(home(LMSTUDIO)) == (None, None, None))
    check('anthropic → (None,None,None)', nr.read_provider_config(home(ANTHROPIC)) == (None, None, None))


def test_base_url_allowlist():
    print('_validate_local_base_url (SSRF allowlist)')
    try:
        import serve
    except Exception as e:
        check('import serve', False, e)
        return
    v = serve._validate_local_base_url
    for u in ('http://10.0.0.100:1234/v1', 'http://localhost:11434/v1',
              'http://127.0.0.1:1234/v1', 'http://192.168.1.50:8000/v1',
              'https://172.16.4.4:1234/v1'):
        ok, err = v(u)
        check('accept %s' % u, ok, err)
    for u, why in (
        # Any DNS name is rejected up front — not because it resolves public, but
        # because a name can rebind between write-time validation and call-time
        # use (the rebinding TOCTOU). This is the rule the docstring promises.
        ('https://example.com/v1', 'dns name (resolves public)'),
        ('http://rebind.attacker.example:1234/v1', 'dns name (could rebind to metadata)'),
        ('http://myhost.local:1234/v1', 'dns name (mdns)'),
        ('http://169.254.169.254/latest/meta-data/', 'cloud metadata'),
        ('file:///etc/passwd', 'scheme'),
        ('http://u:p@10.0.0.1/v1', 'userinfo'),
        ('http://10.0.0.1:1234/v1/../../x', 'path traversal'),
        ('http://10.0.0.1:1234/v1?x=1', 'query'),
        ('http://2130706433:1234/v1', 'int-encoded 127.0.0.1'),
        ('http://8.8.8.8:1234/v1', 'public IP literal'),
        ('', 'empty'),
        ('http://', 'no host'),
    ):
        ok, err = v(u)
        check('reject %s (%s)' % (u or '<empty>', why), not ok)
        if why.startswith('dns name'):
            check('  ...%s rejected as a hostname, before resolution' % u,
                  'IP literal' in err, err)
        if why == 'public IP literal':
            check('  ...and 8.8.8.8 is rejected for being PUBLIC, having passed the literal gate',
                  'public address' in err, err)

    # The documented escape hatch: an operator with a real internal DNS name can
    # opt into the rebinding risk. Verify it flips the hostname rule.
    _prev = os.environ.get('HQ_ALLOW_REMOTE_BACKEND')
    os.environ['HQ_ALLOW_REMOTE_BACKEND'] = '1'
    try:
        ok, err = v('http://gpu.internal.example:1234/v1')
        check('HQ_ALLOW_REMOTE_BACKEND=1 accepts an internal DNS name', ok, err)
    finally:
        if _prev is None:
            os.environ.pop('HQ_ALLOW_REMOTE_BACKEND', None)
        else:
            os.environ['HQ_ALLOW_REMOTE_BACKEND'] = _prev


def main():
    test_read_model_config()
    test_resolve_local()
    test_resolve_cloud()
    test_resolve_none()
    test_shim()
    test_base_url_allowlist()
    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'backend resolve: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())

"""OpenAI-compatible HTTP drivers — LM Studio, Ollama, OpenRouter.

Third extraction step (DRIVER_CONTRACT.md §5 step 2's `local_http.py`): the
backends that speak the OpenAI chat-completions protocol over HTTP share one
streaming client here. The raw same-origin relays in serve.py's ROUTES table
(`/lmstudio/`, `/ollama/`) stay for the legacy in-browser client; these
drivers are the contract-native path (`POST /agent/stream`) and — step 4 —
what night_runner's private HTTP client folds into.

Plain chat backends: no tool loop, no workspace. capabilities.tools=False, so
hosts never route elevated tasks here.
"""
import json
import os
import urllib.error
import urllib.request

from .base import (Driver, DriverError, TaskHandle, ev_done, ev_error,
                   ev_status, ev_token, ev_usage)


class OpenAICompatDriver(Driver):
    """Shared base: subclasses define the manifest plus base-URL/key policy.

    Constructor overrides exist for hosts that resolve the backend from their
    own config source (night_runner reads the operator's brain choice from
    hermes config.yaml + .env): a private instance with explicit base_url /
    api_key leaves the registry singletons' env-derived state untouched."""
    DEFAULT_MODEL = ''
    CONNECT_TIMEOUT = 300     # generous read window — local models can be slow

    def __init__(self, base_url='', api_key=''):
        self._base_override = (base_url or '').rstrip('/')
        self._key_override = api_key or ''

    # ── subclass surface ────────────────────────────────────────────────────
    def base_url(self):
        """OpenAI-compat API root (…/v1), no trailing slash. '' = unknown."""
        raise NotImplementedError

    def api_key(self):
        """Bearer key, '' for keyless local daemons."""
        return ''

    # ── lifecycle ───────────────────────────────────────────────────────────
    def detect(self, probe_version=False):
        base = self.base_url()
        reachable = False
        if base and probe_version:
            # /models is the cheapest universal liveness probe. Only on the
            # explicit probe — detect() runs on every /agent/drivers call and
            # a down daemon would otherwise add a timeout per page load.
            try:
                req = urllib.request.Request(base + '/models',
                                             headers=self._headers(json_body=False))
                with urllib.request.urlopen(req, timeout=2):
                    reachable = True
            except Exception:
                reachable = False
        key = self.api_key()
        needs_key = self.MANIFEST.get('authMode') == 'api-key'
        return {'installed': bool(base), 'authenticated': bool(key) if needs_key else True,
                'auth': 'api-key' if key else ('' if needs_key else 'local-daemon'),
                'version': 'reachable' if reachable else '', 'detail': base}

    def configure(self, settings):
        # Base URLs and keys are env/operator-configured; nothing runtime-
        # settable yet. Accepting (and ignoring) empty settings keeps the
        # host's configure path uniform across drivers.
        if settings:
            raise DriverError('this driver has no runtime settings', status=400)
        return self.detect()

    def _headers(self, json_body=True):
        h = {'Content-Type': 'application/json'} if json_body else {}
        key = self.api_key()
        if key:
            h['Authorization'] = 'Bearer ' + key
        return h

    def start_task(self, task):
        base = self.base_url()
        if not base:
            raise DriverError(f"{self.MANIFEST['id']}: no base URL configured",
                              status=503)
        if self.MANIFEST.get('authMode') == 'api-key' and not self.api_key():
            raise DriverError(f"{self.MANIFEST['id']}: no API key configured",
                              status=503)

        messages = []
        system = (task.get('system') or '').strip()
        if system:
            messages.append({'role': 'system', 'content': system})
        prompt = (task.get('prompt') or '').strip()
        if prompt:
            messages.append({'role': 'user', 'content': prompt})
        else:
            for m in (task.get('messages') or []):
                content = (m.get('content') or '').strip()
                if content:
                    messages.append({'role': m.get('role') or 'user',
                                     'content': content})
        if not any(m['role'] != 'system' for m in messages):
            raise DriverError('no prompt', status=400)

        body = {
            'model': (task.get('model') or '').strip() or self.DEFAULT_MODEL,
            'messages': messages,
            'stream': True,
        }
        max_tokens = (task.get('limits') or {}).get('maxTokens')
        if max_tokens:
            body['max_tokens'] = int(max_tokens)
        req = urllib.request.Request(base + '/chat/completions',
                                     data=json.dumps(body).encode('utf-8'),
                                     method='POST', headers=self._headers())
        try:
            resp = urllib.request.urlopen(req, timeout=self.CONNECT_TIMEOUT)
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = e.read().decode('utf-8', 'replace')[:300]
            except Exception:
                pass
            retry_after = None
            try:
                ra = e.headers.get('Retry-After') if e.headers else None
                retry_after = min(float(ra), 30.0) if ra else None
            except (TypeError, ValueError):
                pass
            raise DriverError(f'upstream {e.code}: {detail or e.reason}',
                              status=502, upstream=e.code,
                              retry_after=retry_after)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise DriverError(f'cannot reach {base}: {e}', status=502)

        handle = TaskHandle()
        handle.private['resp'] = resp
        return handle

    def events(self, handle):
        resp = handle.private['resp']
        yield ev_status('starting')
        in_tok = out_tok = 0
        emitted = False
        try:
            for raw in resp:
                if handle.cancelled.is_set():
                    break
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                for choice in (chunk.get('choices') or []):
                    text = (choice.get('delta') or {}).get('content') or ''
                    if text:
                        emitted = True
                        yield ev_token(text)
                u = chunk.get('usage')
                if u:
                    in_tok = u.get('prompt_tokens', in_tok)
                    out_tok = u.get('completion_tokens', out_tok)
        except (TimeoutError, OSError) as e:
            yield ev_error(f'stream dropped: {e}', recoverable=True)
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if in_tok or out_tok:
            yield ev_usage(in_tok, out_tok, self.MANIFEST['costHint'])
        if emitted:
            yield ev_done()
        else:
            yield ev_error('provider returned no content')

    def cancel(self, handle):
        handle.cancelled.set()
        resp = handle.private.get('resp')
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


class LMStudioDriver(OpenAICompatDriver):
    MANIFEST = {
        'id': 'lmstudio',
        'displayName': 'LM Studio',
        'sprite': 'coworker-local',
        'kind': 'http',
        'authMode': 'local-daemon',
        'models': [],
        'capabilities': {'streaming': True, 'tools': False,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'free-local',
    }
    DEFAULT_MODEL = 'local-model'

    def base_url(self):
        # LMSTUDIO_BASE_URL is what fleet provisioning injects for the managed
        # brain (see /health's `brain` field); localhost is the self-host norm.
        base = (self._base_override
                or os.environ.get('CAFRESOHQ_LMSTUDIO_URL', '').strip()
                or os.environ.get('LMSTUDIO_BASE_URL', '').strip()
                or 'http://localhost:1234/v1')
        return base.rstrip('/')

    def api_key(self):
        return self._key_override or os.environ.get('LMSTUDIO_API_KEY', '').strip()


class OllamaDriver(OpenAICompatDriver):
    MANIFEST = {
        'id': 'ollama',
        'displayName': 'Ollama',
        'sprite': 'coworker-local',
        'kind': 'http',
        'authMode': 'local-daemon',
        'models': [],
        'capabilities': {'streaming': True, 'tools': False,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'free-local',
    }
    DEFAULT_MODEL = 'llama3.1'

    def base_url(self):
        # Ollama serves the OpenAI-compat surface under /v1.
        base = (self._base_override
                or os.environ.get('CAFRESOHQ_OLLAMA_URL', '').strip()
                or 'http://localhost:11434/v1')
        return base.rstrip('/')


class OpenRouterDriver(OpenAICompatDriver):
    MANIFEST = {
        'id': 'openrouter',
        'displayName': 'OpenRouter',
        'sprite': 'coworker-cloud',
        'kind': 'http',
        'authMode': 'api-key',
        'models': [],
        'capabilities': {'streaming': True, 'tools': False,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'metered',
    }
    # night_runner's zero-config default — keep the two in step.
    DEFAULT_MODEL = 'openai/gpt-oss-120b:free'

    def base_url(self):
        return self._base_override or 'https://openrouter.ai/api/v1'

    def api_key(self):
        return self._key_override or os.environ.get('OPENROUTER_API_KEY', '').strip()


class GroqDriver(OpenAICompatDriver):
    MANIFEST = {
        'id': 'groq',
        'displayName': 'Groq',
        'sprite': 'coworker-cloud',
        'kind': 'http',
        'authMode': 'api-key',
        'models': [],
        'capabilities': {'streaming': True, 'tools': False,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'metered',
    }

    def base_url(self):
        return self._base_override or 'https://api.groq.com/openai/v1'

    def api_key(self):
        return self._key_override or os.environ.get('GROQ_API_KEY', '').strip()


class GeminiDriver(OpenAICompatDriver):
    """Gemini through Google's OpenAI-compat surface (API-key path). The id is
    'gemini-api' — 'gemini' stays reserved for the future gemini_cli driver,
    which is a different runtime (CLI agent vs plain chat API)."""
    MANIFEST = {
        'id': 'gemini-api',
        'displayName': 'Gemini (API)',
        'sprite': 'coworker-cloud',
        'kind': 'http',
        'authMode': 'api-key',
        'models': [],
        'capabilities': {'streaming': True, 'tools': False,
                         'artifacts': False, 'workspaces': False},
        'costHint': 'metered',
    }

    def base_url(self):
        # The exact URL night_runner's _PROVIDER_ENDPOINTS uses — bootstrap
        # writers disagree on /v1beta vs /v1beta/openai, so this is pinned
        # here, never taken from a config file's base_url.
        return self._base_override or 'https://generativelanguage.googleapis.com/v1beta/openai'

    def api_key(self):
        return (self._key_override
                or os.environ.get('GOOGLE_API_KEY', '').strip()
                or os.environ.get('GEMINI_API_KEY', '').strip())

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
import sys
import urllib.error
import urllib.request

from .base import (Driver, DriverError, TaskHandle, ev_done, ev_error,
                   ev_status, ev_token, ev_usage)


# ---- #411: the upstream body is a diagnostic, not an answer -------------
#
# `## 407` found six vault doors relaying Obsidian's own 4xx body verbatim
# into `error`, and asked whether Obsidian was the only such upstream. It was
# not. This driver did the identical thing one file away — `e.read()[:300]`
# folded into a DriverError that /agent/stream sends as `str(e)` — and it is
# the worse instance, because `_headers()` below puts the key in an
# `Authorization: Bearer` header and OpenRouter / Groq / Gemini reach the
# boss's real paid provider credentials through it, not a local daemon's.
#
# Driven against a stand-in OpenAI-compat upstream that quotes the request it
# turned down, the fake LM Studio key came back to the browser in full at
# `POST /agent/stream` -> 502. With the stand-in serialising its echo in
# insertion order the key fell one character outside the 300-slice; adding
# `sort_keys=True` — the most ordinary thing a JSON API does — moved it back
# inside. `## 407`'s note about `/vault/open` applies exactly: a bound that
# happens to exclude the secret today is not a defence.
#
# Same split as `_log_upstream` in serve.py: the sentence goes to the boss,
# the body goes to the server log, scrubbed on the way. Same two hard
# constraints as `## 403`/`## 407`'s refusals — digit-free, because
# app/floor.jsx's `officeCause` rewrites bare numbers into a sentence about
# the wrong subject (which is why the status code cannot stay in the text),
# and inside 90 characters, because `cleanCause` truncates there
# (app/floor.jsx:720).

def _upstream_refusal(status: int) -> str:
    """One honest sentence per class of upstream refusal. Digit-free, <=90."""
    if status in (401, 403):
        return 'that brain turned down the key — check it in the settings panel'
    if status == 404:
        return 'that brain has no such model — pick another one in the settings panel'
    if status == 429:
        return 'that brain is rate-limiting us — wait a moment and ask again'
    if status in (400, 405, 409, 415, 422):
        return 'that brain would not accept the request — try a shorter prompt'
    if status >= 500:
        return 'that brain is having trouble at its end — try again shortly'
    return 'that brain answered with an error instead of a reply — try again'


def _log_upstream(where: str, status: int, body: str, *secrets) -> None:
    """Keep the diagnostic, move it off the boss's screen.

    Deleting the body would cost a developer the only description of what the
    backend objected to; that split is the fix, not the deletion. Scrubbed of
    every key we hold on the way out, because the body that prompted this
    helper is one that quoted the Authorization header back at us, and a log
    file is not a place for somebody's credential either."""
    try:
        text = str(body or '')
        for s in secrets:
            s = (s or '').strip()
            if len(s) >= 8:            # see exporters._scrub: the short-key
                text = text.replace(s, '<redacted>')   # hole is deliberate
        sys.stderr.write('[driver] %s: upstream answered %s — %s\n'
                         % (where, status, ' '.join(text.split())[:300]))
    except Exception:
        pass    # a log line may never be the reason a request fails


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
            # #411: the body goes to the LOG, never to the boss. See the note
            # on _upstream_refusal — this relay handed a provider key back to
            # the browser when the upstream echoed the request it refused.
            detail = ''
            try:
                detail = e.read().decode('utf-8', 'replace')[:300]
            except Exception:
                pass
            _log_upstream(self.MANIFEST['id'], e.code, detail or e.reason,
                          self.api_key())
            retry_after = None
            try:
                ra = e.headers.get('Retry-After') if e.headers else None
                retry_after = min(float(ra), 30.0) if ra else None
            except (TypeError, ValueError):
                pass
            raise DriverError(_upstream_refusal(e.code),
                              status=502, upstream=e.code,
                              retry_after=retry_after)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # The base URL is a host:port — bare digits `officeCause` rewrites
            # — and `e` is an errno. Both belong in the log, not the toast.
            _log_upstream(self.MANIFEST['id'], 'unreachable',
                          '%s: %s' % (base, e), self.api_key())
            raise DriverError('that brain is not answering — check it is running',
                              status=502)

        handle = TaskHandle()
        handle.private['resp'] = resp
        return handle

    @staticmethod
    def _frame_error(chunk):
        """The message out of an in-band SSE error frame, '' if it isn't one.

        Three wire spellings, same as the browser reader handles (#258):
          {"error":{"message":"upstream connect error","type":"server_error"}}
          {"error":{"message":"Failed to load model","code":"model_not_found"}}
          {"error":"model requires more system memory than is available"}

        #411: the `or e` fallback used to stringify the WHOLE error dict when
        neither key was present — the same verbatim relay the pre-stream path
        had, and the branch through which a request-echoing upstream's
        Authorization header would arrive mid-stream. It is dropped: this
        helper exists to carry the backend's own SENTENCE ("Failed to load
        model", #258), and a dict with no message field has no sentence in it.
        """
        e = chunk.get('error')
        if isinstance(e, dict):
            return str(e.get('message') or e.get('code') or '')[:300]
        if isinstance(e, str) and e.strip():
            return e.strip()[:300]
        return ''

    def events(self, handle):
        resp = handle.private['resp']
        yield ev_status('starting')
        in_tok = out_tok = 0
        emitted = False
        # Every OpenAI-compatible backend opens with a 200 and then fails
        # LATER, in-band — that is what SSE is for. This loop only ever asked
        # for `choices` and `usage`, so an error frame matched nothing and was
        # dropped: a stream that died after a few tokens ended `emitted=True`
        # and terminated with ev_done(), i.e. the host filed a reply that
        # stops mid-sentence as a finished turn (night_runner's
        # run_task_text() returns the truncated text with no exception at
        # all). The socket-drop handler had the mirror of the same bug — it
        # yielded ev_error and then ev_done anyway. `err` latches the cause so
        # the terminal event below is a failure, not a certificate.
        err = ''
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
                if isinstance(chunk, dict):
                    err = self._frame_error(chunk)
                    if err:
                        break
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
            # #411: `{e}` here is an errno-and-address. Log it, say the
            # sentence — same split as the pre-stream path above.
            _log_upstream(self.MANIFEST['id'], 'stream dropped', str(e),
                          self.api_key())
            err = 'the reply stopped part-way — ask again'
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if in_tok or out_tok:
            yield ev_usage(in_tok, out_tok, self.MANIFEST['costHint'])
        if err:
            # Name the backend: "provider returned no content" sent a boss
            # looking at the wrong machine when the real line was
            # "Failed to load model" or a rate limit. recoverable=True when
            # some text already reached the screen — the tokens already
            # yielded stand, this only marks where the reply stops.
            # #411: this branch RELAYS the backend's own sentence on purpose
            # (#258 — "provider returned no content" sent a boss to the wrong
            # machine), so it cannot be replaced by a refusal we compose. It
            # is the one body in this file where redaction is the right
            # instrument rather than the wrong one, and the key we hold is
            # redacted out of it before it reaches the screen.
            _k = (self.api_key() or '').strip()
            if len(_k) >= 8:
                err = err.replace(_k, '<redacted>')
            yield ev_error(f"{self.MANIFEST['displayName']}: {err}",
                           recoverable=bool(emitted))
        elif emitted:
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

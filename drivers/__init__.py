"""Driver registry — one instance per backend, keyed by manifest id.

serve.py (and later night_runner) look drivers up here and speak only the
contract in base.py. Order matters only for display. DRIVER_CONTRACT.md §5's
decomposition plan is complete: Claude Code, Codex, the local-HTTP family
(ollama/lmstudio/openrouter/groq/gemini-api), Gemini CLI, and Hermes all sit
behind the same five calls now.
"""
from .base import Driver, DriverError, TaskHandle   # noqa: F401 — re-export
from .claude_code import ClaudeCodeDriver
from .codex import CodexDriver
from .gemini_cli import GeminiCliDriver
from .local_http import (GeminiDriver, GroqDriver, LMStudioDriver,
                         OllamaDriver, OpenRouterDriver)
from .hermes import HermesDriver

DRIVERS = {}
for _drv in (ClaudeCodeDriver(), CodexDriver(), GeminiCliDriver(),
             LMStudioDriver(), OllamaDriver(), OpenRouterDriver(),
             GroqDriver(), GeminiDriver(), HermesDriver()):
    DRIVERS[_drv.MANIFEST['id']] = _drv

def get(driver_id):
    """Driver instance for id, or None."""
    return DRIVERS.get(str(driver_id or '').strip())

"""Driver registry — one instance per backend, keyed by manifest id.

serve.py (and later night_runner) look drivers up here and speak only the
contract in base.py. Order matters only for display. Codex, the local-HTTP
family (ollama/lmstudio/openrouter), gemini-cli, and hermes join as the
decomposition proceeds (DRIVER_CONTRACT.md §5).
"""
from .base import Driver, DriverError, TaskHandle   # noqa: F401 — re-export
from .claude_code import ClaudeCodeDriver
from .codex import CodexDriver
from .local_http import (GeminiDriver, GroqDriver, LMStudioDriver,
                         OllamaDriver, OpenRouterDriver)
from .hermes import HermesDriver

DRIVERS = {}
for _drv in (ClaudeCodeDriver(), CodexDriver(),
             LMStudioDriver(), OllamaDriver(), OpenRouterDriver(),
             GroqDriver(), GeminiDriver(), HermesDriver()):
    DRIVERS[_drv.MANIFEST['id']] = _drv

def get(driver_id):
    """Driver instance for id, or None."""
    return DRIVERS.get(str(driver_id or '').strip())

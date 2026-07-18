// ── CafresoHQ AI Brain — friendly naming for the active model/provider ─────
// serve.py's GET /hermes/provider returns the raw {provider, model, base_url,
// configured} it feeds Hermes. Raw ids like "google/gemma-4-e4b" or
// "lmstudio" aren't something a non-technical user should have to parse —
// this maps the known managed default to a clean, branded label and falls
// back to a readable default for anything else (BYOK, local dev, etc).

// The gateway's private Gemma proxy — see fleet-manager.py env injection and
// gemma-proxy.service on cafreso-tls-gateway. Matching on base_url (not just
// provider === 'lmstudio') distinguishes "Cafreso's managed Gemma" from a
// self-hoster's own LM Studio/Ollama instance, which also reports 'lmstudio'.
const MANAGED_GEMMA_BASE_URL = 'http://10.0.1.6:8899/v1';

const KNOWN_MODELS = {
  'google/gemma-4-e4b': 'Gemma 4 (E4B)',
};

const PROVIDER_LABELS = {
  openrouter: 'OpenRouter',
  gemini: 'Google Gemini',
  groq: 'Groq',
  lmstudio: 'LM Studio (local)',
  ollama: 'Ollama (local)',
  anthropic: 'Anthropic',
};

/**
 * Describe the active brain for display. Returns:
 *   { label, sublabel, managed, providerLabel }
 * - managed: true when this is Cafreso's included Gemma (no BYOK needed)
 * - label: short branded name, e.g. "Gemma 4 (E4B)"
 * - sublabel: one-line explainer for the settings card
 */
export function describeBrain({ provider, model, base_url } = {}) {
  const managed = provider === 'lmstudio' && base_url === MANAGED_GEMMA_BASE_URL;
  if (managed) {
    return {
      managed: true,
      label: KNOWN_MODELS[model] || model || 'Gemma 4',
      sublabel: 'Included with your HQ — provided by Cafreso, no API key needed.',
      providerLabel: 'Cafreso',
    };
  }
  const providerLabel = PROVIDER_LABELS[provider] || provider || 'Unknown';
  return {
    managed: false,
    label: KNOWN_MODELS[model] || model || 'Unconfigured',
    sublabel: model
      ? `Your own ${providerLabel} key.`
      : 'No brain configured yet.',
    providerLabel,
  };
}

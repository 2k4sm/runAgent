"""Available models via LiteLLM.

Model string format: "provider/model-name"
  - gemini/...       -> Google AI Studio (GEMINI_API_KEY)
  - openai/...       -> OpenAI (OPENAI_API_KEY)
  - anthropic/...    -> Anthropic (ANTHROPIC_API_KEY)

Add any LiteLLM-supported provider by setting its env var in settings.
See: https://docs.litellm.ai/docs/providers
"""

from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    # Default — Gemini free tier (best balance of speed, quality, and cost)
    "gemini-flash": {
        "id": "gemini/gemini-3-flash",
        "name": "Gemini 3 Flash",
        "provider": "Google",
        "context_window": 1_000_000,
        "supports_tools": True,
        "supports_vision": True,
        "tier": "free",
    },
    # Budget — highest throughput, simpler tasks
    "gemini-flash-lite": {
        "id": "gemini/gemini-3.1-flash-lite",
        "name": "Gemini 3.1 Flash-Lite",
        "provider": "Google",
        "context_window": 1_000_000,
        "supports_tools": True,
        "supports_vision": True,
        "tier": "free",
    },
    # Reasoning-heavy
    "gemini-pro": {
        "id": "gemini/gemini-3.1-pro",
        "name": "Gemini 3.1 Pro",
        "provider": "Google",
        "context_window": 1_000_000,
        "supports_tools": True,
        "supports_vision": True,
        "tier": "free",
    },
}


def get_model_id(key: str) -> str:
    return MODELS[key]["id"]


def list_models_for_tier(tier: str) -> list[dict[str, Any]]:
    tiers = {"free": ["free"], "pro": ["free", "pro"], "team": ["free", "pro", "team"]}
    allowed = tiers.get(tier, ["free"])
    return [m for m in MODELS.values() if m["tier"] in allowed]

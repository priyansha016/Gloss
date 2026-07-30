"""Per-request LLM credentials (bring-your-own-key).

Every LLM call in the pipeline goes through `get_llm_client()` in `llm.py`, which
normally reads one server-wide key from settings. When a user supplies their own
key we need that key to reach ~45 call sites across glossary/verifier/visuals/
gatekeeper/cleanup/qa/study_tools without threading a parameter through all of
them, so the credentials live in a ContextVar instead.

Set it once at the entry point:
- API: an async dependency on the request (same task as the handler, so the value
  is visible to the whole endpoint).
- Worker: the first statement of the arq job, before any child tasks spawn.

`asyncio.gather` children copy the context at creation time, so parallel stages
(verifier repairs, visual generation) inherit whatever was set upstream.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.config import get_settings

# Presets so the frontend can send a short provider id instead of a base URL.
# Ollama/LM Studio are deliberately absent: a hosted backend cannot reach a
# user's localhost, so those only work when running Gloss locally via .env.
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-flash-lite-latest",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


@dataclass(frozen=True)
class LlmCreds:
    api_key: str
    base_url: str
    model: str

    def as_dict(self) -> dict[str, str]:
        """Serialize for the arq job payload (crosses a process boundary via Redis)."""
        return {"api_key": self.api_key, "base_url": self.base_url, "model": self.model}

    @classmethod
    def from_dict(cls, data: dict | None) -> "LlmCreds | None":
        if not data:
            return None
        api_key = str(data.get("api_key") or "").strip()
        base_url = str(data.get("base_url") or "").strip()
        model = str(data.get("model") or "").strip()
        if not (api_key and base_url and model):
            return None
        return cls(api_key=api_key, base_url=base_url, model=model)


_creds: ContextVar[LlmCreds | None] = ContextVar("llm_creds", default=None)


def set_llm_creds(creds: LlmCreds | None) -> None:
    _creds.set(creds)


def get_llm_creds() -> LlmCreds | None:
    return _creds.get()


def llm_available() -> bool:
    """True when some usable credentials exist — a user's key or the server's own.

    Pipeline stages guard on this instead of `settings.llm_configured` so a
    keyless server still works for users who bring their own key.
    """
    return _creds.get() is not None or get_settings().llm_configured


def build_creds(
    api_key: str | None,
    *,
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LlmCreds | None:
    """Resolve header values into credentials. None = no usable user key supplied.

    An explicit base_url/model always wins over the preset, so a user on a
    compatible endpoint we don't list can still bring their own.
    """
    key = (api_key or "").strip()
    if not key:
        return None
    preset = PROVIDER_PRESETS.get((provider or "").strip().lower(), {})
    resolved_base = (base_url or "").strip() or preset.get("base_url", "")
    resolved_model = (model or "").strip() or preset.get("model", "")
    if not (resolved_base and resolved_model):
        return None
    return LlmCreds(api_key=key, base_url=resolved_base, model=resolved_model)

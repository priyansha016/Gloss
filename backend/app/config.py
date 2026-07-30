from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://youtube_skim:youtube_skim@localhost:5432/youtube_skim"
    redis_url: str = "redis://localhost:6379"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    # Route all YouTube requests (captions + watch page) through this proxy.
    # Empty = direct (fine for local/residential IPs). Set to a residential/rotating
    # proxy URL in production, where YouTube blocks datacenter IPs. See PLAN.md §8.
    youtube_proxy_url: str = ""
    # Fallback LLM: when the primary provider rate-limits (429), chat calls retry
    # here automatically. Empty = no failover.
    fallback_openai_api_key: str = ""
    fallback_openai_base_url: str = ""
    fallback_openai_model: str = ""
    cors_origins: str = "http://localhost:3000"
    # FAST_PROCESSING controls the CHEAP knobs only: a smaller glossary (glossary.py)
    # and skipping glossary-primed transcript cleanup (cleanup.py). It does NOT gate the
    # verifier/visuals — use ENABLE_VERIFIER / ENABLE_VISUALS for those.
    fast_processing: bool = True
    # Expensive quality stages. Default on; turn off to cut LLM calls (e.g. dev, or a
    # cheap/rate-limited provider). enable_visuals implies the verifier already ran.
    enable_verifier: bool = True
    enable_visuals: bool = True
    llm_concurrency: int = 2
    # Per-request LLM timeout. Big local models (e.g. qwen2.5:14b on a laptop) can take
    # >90s for a single generation, so this is generous; cloud calls finish well under it.
    llm_timeout_s: int = 300
    max_glossary_terms: int = 15
    section_chunk_minutes: int = 6
    # Per-IP rate limits (fixed 1-hour window). Protects the free LLM quota on a public
    # deploy. Set RATE_LIMIT_ENABLED=false for local dev.
    rate_limit_enabled: bool = True
    rate_limit_submit_per_hour: int = 15
    rate_limit_ask_per_hour: int = 40
    rate_limit_practice_per_hour: int = 20
    # Bring-your-own-key. When true, endpoints that spend LLM tokens require an
    # X-LLM-Key header and the server's own key is never used for them. Flipping
    # this to true is how the hosted demo stops paying for strangers' videos.
    require_user_key: bool = False
    # Owner dashboard: GET /api/admin/stats with header X-Admin-Key. Empty = disabled.
    admin_secret: str = ""
    # Homepage showcase: comma-separated video UUIDs (ready docs). Empty = latest ready.
    showcase_video_ids: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.strip() and self.openai_model.strip() and self.openai_base_url.strip())

    @property
    def fallback_configured(self) -> bool:
        return bool(
            self.fallback_openai_api_key.strip()
            and self.fallback_openai_base_url.strip()
            and self.fallback_openai_model.strip()
        )

    @property
    def fallback_model_list(self) -> list[str]:
        """Comma-separated fallback models, tried in order (first = preferred)."""
        return [m.strip() for m in self.fallback_openai_model.split(",") if m.strip()]

    @property
    def showcase_id_list(self) -> list[str]:
        return [v.strip() for v in self.showcase_video_ids.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

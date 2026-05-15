from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    debug: bool = False
    app_name: str = "runAgent"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str  # Backend-only, for admin ops
    supabase_jwt_secret: str

    # LiteLLM (provider API keys)
    gemini_api_key: str
    default_model: str = "gemini/gemini-3-flash"
    fallback_model: str = "gemini/gemini-3.1-flash-lite"

    # Supabase Storage
    supabase_storage_bucket: str = "assets"

    # Tavily
    tavily_api_key: str

    # Rate limiting
    rate_limit_requests_per_minute: int = 30

    # Agent config
    max_react_iterations: int = 10
    max_tool_retries: int = 2


# Fields are populated from the environment / .env at runtime.
settings = Settings()  # type: ignore[call-arg]  # ty: ignore[missing-argument]

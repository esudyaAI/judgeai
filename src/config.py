from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_USER: str = "judgeai"
    POSTGRES_PASSWORD: str = "judgeai"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "judgeai"
    # Disable connection pooling (tests: every test gets its own event loop).
    DB_NULL_POOL: bool = False

    AUTH_COOKIE_SECURE: bool = True

    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_MB: int = 50
    UPLOAD_ALLOWED_EXTENSIONS: str = ".pdf,.docx,.dotx,.txt,.md"

    # "openai" = any OpenAI-compatible /chat/completions endpoint; "deepseek_web" = DeepSeek
    # web proxy (deepseek-stateful-wrapper); "fake" = fixed sample case for tests only.
    LLM_PROVIDER: Literal["openai", "deepseek_web", "fake"] = "openai"
    # The fake provider is refused unless this flag is set (tests, local UI work), so a
    # misconfigured server reports an error instead of showing a sample verdict.
    LLM_ALLOW_FAKE: bool = False
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: float = 120.0

    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384
    # "fastembed" = local model from the fastembed catalogue; "jina" = Jina cloud API
    # (EMBEDDING_MODEL e.g. jina-embeddings-v3, EMBEDDING_DIM 1024, key only in .env).
    EMBEDDING_PROVIDER: Literal["fastembed", "jina"] = "fastembed"
    JINA_API_BASE: str = "https://api.jina.ai/v1"
    JINA_API_KEY: str | None = None
    EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    EMBEDDING_CACHE_DIR: str = ".fastembed_cache"
    EMBEDDING_CHUNK_SIZE: int = 2500
    EMBEDDING_MAX_CHUNKS: int = 8

    # Explicit origins only for credentialed browser sessions.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5178"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.UPLOAD_ALLOWED_EXTENSIONS.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must use explicit origins with cookie authentication")
        return origins

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

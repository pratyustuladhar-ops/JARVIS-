import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "JARVIS Autonomous AI Agent Backend"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/jarvis"

    # CORS configuration
    FRONTEND_URL: str = "http://localhost:5173"
    ADDITIONAL_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    # AI/ML Agent Settings
    AI_ENGINE_MODE: str = "mock"
    AI_PROVIDER: str = "mock"  # mock, openai, local
    AI_MODEL: str = "cognition-llm-4.2"
    AI_MODEL_NAME: str = "cognition-llm-4.2"
    AI_API_KEY: Union[str, None] = None
    AI_TEMPERATURE: float = 0.2
    AI_REASONING_TEMPERATURE: float = 0.2
    AI_MAX_TOKENS: int = 2048
    INTENT_CONFIDENCE_THRESHOLD: float = 0.65

    # Multimodal & Vision Intelligence (Step 9)
    VISION_ENABLED: bool = True
    VISION_PROVIDER: str = "mock"  # mock, gemini, openai, local
    VISION_API_KEY: Union[str, None] = None
    VISION_MODEL: str = "gemini-2.0-flash"
    SCREEN_CAPTURE_ENABLED: bool = True
    OCR_ENABLED: bool = True
    VISUAL_CONTEXT_ENABLED: bool = True
    MAX_IMAGE_SIZE_MB: int = 10
    PRIVACY_MODE: bool = False

    # Wake Word & Hands-Free Settings (Step 10)
    WAKE_WORD_ENABLED: bool = False
    WAKE_WORD_PROVIDER: str = "local"  # local, porcupine, mock
    WAKE_WORD: str = "hey_jarvis"
    WAKE_PHRASE: str = "Hey JARVIS"
    WAKE_ACKNOWLEDGMENT: str = "Yes?"
    COMMAND_TIMEOUT_SECONDS: int = 8
    FOLLOW_UP_TIMEOUT_SECONDS: int = 8
    WAKE_WORD_SENSITIVITY: float = 0.7
    AUTO_RESUME_LISTENING: bool = True
    PORCUPINE_ACCESS_KEY: Union[str, None] = None

    # Network
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    @field_validator("ADDITIONAL_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        elif isinstance(v, list):
            return v
        return []

    @property
    def all_cors_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL]
        if isinstance(self.ADDITIONAL_CORS_ORIGINS, list):
            origins.extend(self.ADDITIONAL_CORS_ORIGINS)
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for o in origins:
            if o and o not in seen:
                seen.add(o)
                deduped.append(o)
        return deduped

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

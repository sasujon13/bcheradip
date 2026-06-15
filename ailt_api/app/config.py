"""Environment — load .env from ailt_api/ regardless of process cwd."""

from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_AILT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _AILT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8790
    database_url: str = "mysql+pymysql://root:@127.0.0.1:3306/ailanguagetutor?charset=utf8mb4"
    admin_seed_email: str = "sashafik.me@gmail.com"
    admin_seed_whatsapp: str = "+8801722710298"
    admin_seed_password: str = ""
    guest_ai_limit: int = 99
    trial_days: int = 30
    otp_ttl_minutes: int = 15
    session_ttl_days: int = 30
    dev_log_otp: bool = True
    smtp_enabled: bool = True
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_from: str = "admin@ailanguagetutor.com"
    smtp_user: str = "admin@ailanguagetutor.com"
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_use_ssl: bool = False
    support_whatsapp: str = "+8801722710298"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_paid_model: str = "claude-sonnet-4-5-20250929"
    groq_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_paid_model: str = "anthropic/claude-3.5-sonnet"
    packs_dir: Path = _AILT_ROOT / "packs"
    public_base_url: str = "https://cheradip.com/ailt/api"
    translate_api_responses: bool = True
    translate_api_timeout_seconds: float = 4.0
    home_ai_translate_url: str = "http://127.0.0.1:8787/translate-strings"

    def uses_local_postfix_direct(self) -> bool:
        """127.0.0.1:25 accepts mail locally but Gmail rejects with 550 5.7.1."""
        return self.smtp_host.strip().lower() in {"127.0.0.1", "localhost"} and self.smtp_port == 25

    def smtp_config_summary(self) -> str:
        tls = "tls" if self.smtp_use_tls else ("ssl" if self.smtp_use_ssl else "plain")
        return f"{self.smtp_host}:{self.smtp_port} ({tls}) from={self.smtp_from}"

    @model_validator(mode="after")
    def _submission_port_needs_tls(self) -> "Settings":
        """Postfix submission on 587 only offers AUTH after STARTTLS."""
        if self.smtp_port == 587 and not self.smtp_use_ssl and not self.smtp_use_tls:
            self.smtp_use_tls = True
        return self

    @field_validator(
        "dev_log_otp",
        "smtp_enabled",
        "smtp_use_tls",
        "smtp_use_ssl",
        "translate_api_responses",
        mode="before",
    )
    @classmethod
    def _parse_bool(cls, value: object) -> object:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized.startswith("t") or normalized in {"1", "yes", "on"}:
                return True
            if normalized.startswith("f") or normalized in {"0", "no", "off", ""}:
                return False
        return value


settings = Settings()

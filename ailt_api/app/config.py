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
    # Separate database for the Cheradip VS Code extension (users, billing, credits, payments)
    ext_database_url: str = "mysql+pymysql://root:@127.0.0.1:3306/extcheradip?charset=utf8mb4"
    admin_seed_email: str = "sashafik.me@gmail.com"
    admin_seed_whatsapp: str = "+8801722710298"
    admin_seed_password: str = ""
    # Cheradip extension admin (separate ext_users space). Blank email/password
    # falls back to the app admin credentials above.
    ext_admin_seed_email: str = ""
    ext_admin_seed_password: str = ""
    guest_ai_limit: int = 99_999_999
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
    gemini_model_fast: str = "gemini-flash-lite-latest"
    gemini_model_coding: str = "gemini-2.5-flash"
    gemini_model_complex: str = "gemini-2.5-pro"
    openai_api_key: str = ""
    openai_model_default: str = "gpt-4o-mini"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_coding: str = "gpt-4o-mini"
    openai_model_complex: str = "gpt-4o-mini"
    openai_paid_model_default: str = "gpt-4o"
    openai_paid_model_fast: str = "gpt-4o-mini"
    openai_paid_model_coding: str = "o4-mini"
    openai_paid_model_complex: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_model_fast: str = "claude-haiku-4-5"
    anthropic_model_coding: str = "claude-haiku-4-5"
    anthropic_model_complex: str = "claude-haiku-4-5"
    anthropic_paid_model: str = "claude-sonnet-4-5"
    anthropic_paid_model_fast: str = "claude-haiku-4-5"
    anthropic_paid_model_coding: str = "claude-sonnet-4-5"
    anthropic_paid_model_complex: str = "claude-sonnet-4-5"
    groq_api_key: str = ""
    groq_model_default: str = "llama-3.1-8b-instant"
    groq_model_fast: str = "llama-3.1-8b-instant"
    groq_model_coding: str = "qwen/qwen3-32b"
    groq_model_complex: str = "llama-3.3-70b-versatile"
    mistral_api_key: str = ""
    mistral_model_default: str = "mistral-small-latest"
    mistral_model_coding: str = "codestral-latest"
    mistral_model_complex: str = "mistral-large-latest"
    mistral_model_fast: str = "ministral-3b-latest"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_model_fast: str = "openrouter/free"
    openrouter_model_coding: str = "qwen/qwen3-coder:free"
    openrouter_model_complex: str = "openrouter/free"
    openrouter_paid_model: str = "anthropic/claude-sonnet-4-5"
    openrouter_paid_model_fast: str = "anthropic/claude-haiku-4-5"
    openrouter_paid_model_coding: str = "anthropic/claude-sonnet-4-5"
    openrouter_paid_model_complex: str = "anthropic/claude-sonnet-4-5"
    deepseek_api_key: str = ""
    packs_dir: Path = _AILT_ROOT / "packs"
    public_base_url: str = "https://cheradip.com/ailt/api"
    # Google Play Billing (AI Language Tutor Android app). Server-side purchase
    # verification via the Play Developer API (androidpublisher). Provide a
    # service-account key with "View financial data" access to the app.
    # google_play_service_account_json: either inline JSON or a path to the .json.
    # When blank, /billing/verify falls back to DEV mode (trusts the client) —
    # never leave blank in production.
    google_play_package_name: str = "com.cheradip.ailanguagetutor"
    google_play_service_account_json: str = ""
    # Optional shared secret to authenticate Play Real-Time Developer
    # Notifications (RTDN) push calls (?token=... on the webhook URL).
    google_play_rtdn_token: str = ""
    # Cheradip extension (Cursor-style) billing.
    # Provider: "paddle" (Merchant of Record — works from Bangladesh, pays out by
    # wire/Payoneer) or "stripe". Bangladesh cannot use Stripe/PayPal, so Paddle
    # is the default.
    billing_provider: str = "paddle"
    billing_success_url: str = "https://cheradip.com/ailt/billing/success"
    billing_cancel_url: str = "https://cheradip.com/ailt/billing/cancel"
    billing_pricing_url: str = "https://cheradip.com/ailt/pricing"
    # Paddle Billing (Merchant of Record) — Cheradip coding extension
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""
    paddle_environment: str = "sandbox"  # "sandbox" or "production"
    # Publishable client-side token (safe to expose to the pricing page).
    paddle_client_token: str = ""
    paddle_price_pro: str = ""
    paddle_price_plus: str = ""
    paddle_price_business: str = ""
    # Stripe (optional fallback; not usable from Bangladesh)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""
    stripe_price_plus: str = ""
    stripe_price_business: str = ""
    translate_api_responses: bool = True
    translate_api_timeout_seconds: float = 4.0
    home_ai_translate_url: str = "http://127.0.0.1:8787/translate-strings"

    def uses_local_postfix_direct(self) -> bool:
        """Misconfigured production: 127.0.0.1:25 does not reach real inboxes — use Brevo."""
        return self.smtp_host.strip().lower() in {"127.0.0.1", "localhost"} and self.smtp_port == 25

    def smtp_config_summary(self) -> str:
        tls = "tls" if self.smtp_use_tls else ("ssl" if self.smtp_use_ssl else "plain")
        return f"{self.smtp_host}:{self.smtp_port} ({tls}) from={self.smtp_from}"

    @model_validator(mode="after")
    def _submission_port_needs_tls(self) -> "Settings":
        """Port 587 (Brevo) requires STARTTLS when not using SSL."""
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

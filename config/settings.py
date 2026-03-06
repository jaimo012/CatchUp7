import os
import sys

from dotenv import load_dotenv


def _load_env_file() -> None:
    """
    Load values from a local .env file when present.
    In cloud environments, .env may not exist and that is fine.
    """
    load_dotenv(override=False)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _validate_required_env_vars() -> None:
    required_env_vars = [
        "GEMINI_API_KEY",
        "NAVER_CLIENT_ID",
        "NAVER_CLIENT_SECRET",
        "ELEVENLABS_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
        "GOOGLE_CREDENTIALS_JSON",
        "SPREADSHEET_ID",
    ]

    missing = [name for name in required_env_vars if not os.getenv(name)]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            "Required environment variables are missing: "
            f"{missing_text}. "
            "Please set them in OS environment variables or in a local .env file."
        )


_load_env_file()

try:
    _validate_required_env_vars()
except ValueError as exc:
    print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


class Settings:
    GEMINI_API_KEY: str = _require_env("GEMINI_API_KEY")
    NAVER_CLIENT_ID: str = _require_env("NAVER_CLIENT_ID")
    NAVER_CLIENT_SECRET: str = _require_env("NAVER_CLIENT_SECRET")
    ELEVENLABS_API_KEY: str = _require_env("ELEVENLABS_API_KEY")
    SLACK_BOT_TOKEN: str = _require_env("SLACK_BOT_TOKEN")
    SLACK_CHANNEL_ID: str = _require_env("SLACK_CHANNEL_ID")
    GOOGLE_CREDENTIALS_JSON: str = _require_env("GOOGLE_CREDENTIALS_JSON")
    SPREADSHEET_ID: str = _require_env("SPREADSHEET_ID")


settings = Settings()

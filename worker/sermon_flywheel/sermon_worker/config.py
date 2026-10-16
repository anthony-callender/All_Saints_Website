"""Configuration from environment variables (optionally loaded from .env files).

Load order (first value wins, real environment always wins):
  1. process environment
  2. <project root>/.env
  3. <project root>/tmp/local-credentials.env   (written by scripts/bootstrap.sh; local DDEV only)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_AGENT_DIR = PROJECT_ROOT / "AllSaints_Agent"
WORK_DIR = PROJECT_ROOT / "tmp" / "sermon-worker"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_dotenv() -> None:
    load_env_file(PROJECT_ROOT / ".env")
    load_env_file(PROJECT_ROOT / "tmp" / "local-credentials.env")


@dataclass
class Settings:
    openai_api_key: str = ""
    sermon_model: str = "gpt-5-mini"
    youtube_api_key: str = ""
    youtube_channel_id: str = "UCOouhW9_VVwiVODtl0gDvVA"  # All Saints' public channel
    wp_base_url: str = ""
    wp_username: str = ""
    wp_application_password: str = field(default="", repr=False)
    post_status: str = "draft"
    esv_api_key: str = field(default="", repr=False)
    include_notes: bool = False
    work_dir: Path = WORK_DIR

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        env = os.environ.get
        status = env("SERMON_POST_STATUS", "draft").strip().lower()
        if status not in ("draft", "pending", "publish"):
            raise ValueError(f"SERMON_POST_STATUS must be draft, pending or publish (got {status!r})")
        return cls(
            openai_api_key=env("OPENAI_API_KEY", ""),
            sermon_model=env("OPENAI_SERMON_MODEL", "gpt-5-mini"),
            youtube_api_key=env("YOUTUBE_API_KEY", ""),
            youtube_channel_id=env("YOUTUBE_CHANNEL_ID", "") or cls.youtube_channel_id,
            wp_base_url=env("WP_BASE_URL", "").rstrip("/"),
            wp_username=env("WP_USERNAME", ""),
            wp_application_password=env("WP_APPLICATION_PASSWORD", ""),
            post_status=status,
            esv_api_key=env("ESV_API_KEY", ""),
            include_notes=env("SERMON_INCLUDE_NOTES", "0").strip().lower() in ("1", "true", "yes"),
            work_dir=Path(env("SERMON_WORK_DIR", str(WORK_DIR))),
        )

    def describe(self) -> dict[str, str]:
        """Safe summary for logs: never includes secret values."""
        yes = lambda v: "set" if v else "missing"  # noqa: E731
        return {
            "OPENAI_API_KEY": yes(self.openai_api_key),
            "OPENAI_SERMON_MODEL": self.sermon_model,
            "YOUTUBE_API_KEY": yes(self.youtube_api_key),
            "YOUTUBE_CHANNEL_ID": self.youtube_channel_id,
            "WP_BASE_URL": self.wp_base_url or "missing",
            "WP_USERNAME": self.wp_username or "missing",
            "WP_APPLICATION_PASSWORD": yes(self.wp_application_password),
            "SERMON_POST_STATUS": self.post_status,
            "ESV_API_KEY": yes(self.esv_api_key),
            "SERMON_INCLUDE_NOTES": "on" if self.include_notes else "off",
        }

"""
Centralized configuration for the Cyber project.
All paths and environment variables should be accessed through this module.
"""

import os
from pathlib import Path

# PROJECT_ROOT: resolved once, relative to this file's location
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Standard paths
SHARED_DIR = PROJECT_ROOT / "shared"
DATABASE_DIR = PROJECT_ROOT / "database"
LOGS_DIR = PROJECT_ROOT / "logs"
CREDENTIALS_FILE = SHARED_DIR / "credentials" / "google.json"


def load_env() -> None:
    """
    Load .env file from project root into os.environ.
    Safe to call multiple times - only loads once.
    """
    if getattr(load_env, "_loaded", False):
        return

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        load_env._loaded = True
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Only set if not already in environment (allows overrides)
        if key not in os.environ:
            os.environ[key] = value

    load_env._loaded = True


def get_env(key: str, default: str = "") -> str:
    """Get environment variable, loading .env first if needed."""
    load_env()
    return os.getenv(key, default).strip()


def discord_token() -> str:
    """Get Discord bot token (supports both DISCORD_TOKEN and legacy KEY)."""
    return get_env("DISCORD_TOKEN") or get_env("KEY")


def members_sheet_id() -> str:
    """Get Google Sheet ID for members registry."""
    return get_env("MEMBERS_SHEET_ID")


def tasks_sheet_id() -> str:
    """Get Google Sheet ID for tasks."""
    return get_env("TASKS_SHEET_ID")


def activity_sheet_id() -> str:
    """Get Google Sheet ID for activity (supports legacy SPREADSHEET_ID)."""
    return get_env("ACTIVITY_SHEET_ID") or get_env("SPREADSHEET_ID")


def flask_secret_key() -> str:
    """Get Flask secret key with dev fallback."""
    key = get_env("SECRET_KEY")
    if not key:
        import warnings
        warnings.warn("SECRET_KEY not set - using insecure default for dev only!")
        return "dev-secret-change-in-production-" + str(hash(PROJECT_ROOT))
    return key


def discord_client_id() -> str:
    """Get Discord OAuth2 client ID (same as bot application ID)."""
    return get_env("DISCORD_CLIENT_ID", "1449101385760243752")


def discord_client_secret() -> str:
    """Get Discord OAuth2 client secret."""
    return get_env("DISCORD_CLIENT_SECRET")


def discord_redirect_uri() -> str:
    """Get Discord OAuth2 redirect URI."""
    return get_env("DISCORD_REDIRECT_URI", "http://localhost:5002/callback")


def reddit_client_id() -> str:
    """Get Reddit API client ID (from reddit.com/prefs/apps)."""
    return get_env("REDDIT_CLIENT_ID")


def reddit_client_secret() -> str:
    """Get Reddit API client secret."""
    return get_env("REDDIT_CLIENT_SECRET")

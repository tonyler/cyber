"""
Discord OAuth2 authentication helpers for the Cyber dashboard.

Sessions are persisted in dashboard3/data/sessions.json so they survive restarts
and are shared across the hederadashboard app.
"""

import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

def _get_log():
    """Return a logger wired to cyber.log (lazy so we don't import at module load)."""
    logger = logging.getLogger("discord_auth")
    if not logger.handlers:
        try:
            from pathlib import Path as _P
            _logs = _P(__file__).resolve().parent.parent / "logs"
            _logs.mkdir(parents=True, exist_ok=True)
            from logging.handlers import RotatingFileHandler
            h = RotatingFileHandler(_logs / "cyber.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            logger.addHandler(h)
            logger.setLevel(logging.DEBUG)
        except Exception:
            pass
    return logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_SESSIONS_FILE = _THIS_DIR / "data" / "sessions.json"
_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config helpers (lazy-imported to avoid circular import)
# ---------------------------------------------------------------------------

def _cfg():
    import sys
    sys.path.insert(0, str(_THIS_DIR.parent / "shared"))
    from config import (
        discord_client_id, discord_client_secret, discord_redirect_uri, get_env
    )
    return discord_client_id(), discord_client_secret(), discord_redirect_uri(), get_env


# Discord API base
_API = "https://discord.com/api/v10"
_UA = "DiscordBot (https://github.com/cyber, 1.0)"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_oauth_url(state: str) -> str:
    """Return the Discord OAuth2 authorization URL."""
    client_id, _, redirect_uri, _ = _cfg()
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    })
    return f"https://discord.com/api/oauth2/authorize?{params}"


def exchange_code_for_token(code: str) -> dict | None:
    """Exchange an authorization code for an access token. Returns token data or None."""
    client_id, client_secret, redirect_uri, _ = _cfg()
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(
        f"{_API}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": _UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        _get_log().error("exchange_code_for_token HTTP %s: %s", exc.code, body)
        return None
    except Exception as exc:
        _get_log().error("exchange_code_for_token error: %s", exc)
        return None


def get_user_info(access_token: str) -> dict | None:
    """Fetch basic user info from Discord using an OAuth access token."""
    req = urllib.request.Request(
        f"{_API}/users/@me",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        _get_log().error("get_user_info HTTP %s: %s", exc.code, body)
        return None
    except Exception as exc:
        _get_log().error("get_user_info error: %s", exc)
        return None


def check_user_has_role(user_id: str, bot_token: str) -> bool:
    """
    Return True if *user_id* has the "Loop 🎩" role in the configured guild.

    Requires DISCORD_GUILD_ID env var.  If the var is not set, access is
    granted to all authenticated Discord users (open mode).
    """
    _, _, _, get_env = _cfg()
    guild_id = get_env("DISCORD_GUILD_ID")
    if not guild_id:
        # No guild configured → allow all authenticated users
        return True

    req = urllib.request.Request(
        f"{_API}/guilds/{guild_id}/members/{user_id}",
        headers={"Authorization": f"Bot {bot_token}", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            member = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return False
        return False
    except Exception:
        return False

    # Fetch role list to find "Loop 🎩" by name
    roles_req = urllib.request.Request(
        f"{_API}/guilds/{guild_id}/roles",
        headers={"Authorization": f"Bot {bot_token}", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(roles_req, timeout=10) as resp:
            all_roles = json.loads(resp.read())
    except Exception:
        return False

    loop_role_ids = {r["id"] for r in all_roles if r.get("name") == "Loop 🎩"}
    if not loop_role_ids:
        # Role doesn't exist in guild → fall back to allowing any member
        return True

    member_role_ids = set(member.get("roles", []))
    return bool(loop_role_ids & member_role_ids)


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------

def _load_sessions() -> dict:
    if _SESSIONS_FILE.exists():
        try:
            return json.loads(_SESSIONS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_sessions(sessions: dict) -> None:
    _SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def create_session(user_id: str, username: str, avatar: str | None) -> str:
    """Persist a new session and return the session ID."""
    session_id = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    sessions[session_id] = {
        "user_id": user_id,
        "username": username,
        "avatar": avatar or "",
        "created_at": int(time.time()),
    }
    _save_sessions(sessions)
    return session_id


def delete_session(session_id: str) -> None:
    """Remove a session (logout)."""
    sessions = _load_sessions()
    sessions.pop(session_id, None)
    _save_sessions(sessions)


def _get_session_data(session_id: str) -> dict | None:
    """Return session dict or None if missing / expired (30-day TTL)."""
    sessions = _load_sessions()
    entry = sessions.get(session_id)
    if not entry:
        return None
    ttl = 30 * 24 * 60 * 60  # 30 days
    if time.time() - entry.get("created_at", 0) > ttl:
        delete_session(session_id)
        return None
    return entry


# ---------------------------------------------------------------------------
# Request-level helpers (require Flask request context)
# ---------------------------------------------------------------------------

def get_current_user() -> dict | None:
    """Return user dict for the current request, or None if not logged in."""
    from flask import request as _req
    session_id = _req.cookies.get("cyber_session")
    if not session_id:
        return None
    return _get_session_data(session_id)


def is_authenticated() -> bool:
    """True if the current request carries a valid session cookie."""
    return get_current_user() is not None


def get_avatar_url(user_id: str | None, avatar: str | None) -> str | None:
    """Build the CDN URL for a Discord avatar, or None if not available."""
    if not user_id or not avatar:
        return None
    ext = "gif" if avatar.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{ext}?size=64"

"""Authentication helpers: token file storage, token exchange, browser extraction."""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Optional

import httpx

TP_BASE = "https://tpapi.trainingpeaks.com"
TOKENS_FILE = pathlib.Path.home() / ".config" / "trainingpeaks-cli" / "tokens.json"


# ---------------------------------------------------------------------------
# Token file I/O
# ---------------------------------------------------------------------------

def _load_tokens() -> dict:
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_tokens(tokens: dict) -> None:
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    TOKENS_FILE.chmod(0o600)


# ---------------------------------------------------------------------------
# Cookie → token exchange
# ---------------------------------------------------------------------------

def _exchange_cookie(cookie: str) -> dict:
    """Exchange Production_tpAuth cookie for OAuth tokens."""
    resp = httpx.get(
        f"{TP_BASE}/users/v3/token",
        headers={
            "Cookie": f"Production_tpAuth={cookie}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    if resp.status_code == 401:
        raise AuthError("Cookie is invalid or expired.")
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success") and not data.get("token"):
        raise AuthError(f"Token exchange failed: {data}")

    token = data.get("token", {})
    access_token = token.get("access_token", "")
    refresh_token = token.get("refresh_token", "")
    expires_in = int(token.get("expires_in", 3600))

    if not access_token:
        raise AuthError(f"No access_token in response: {data}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in - 60,
        "session_cookie": cookie,
        # Preserve athlete_id if we have it
        "athlete_id": data.get("athleteId"),
    }


# ---------------------------------------------------------------------------
# Bearer token retrieval (with auto-refresh)
# ---------------------------------------------------------------------------

_cached_access_token: Optional[str] = None


def get_bearer_token(force_refresh: bool = False) -> str:
    """Return a valid Bearer token, re-exchanging cookie when expired."""
    global _cached_access_token

    if not force_refresh and _cached_access_token:
        return _cached_access_token

    tokens = _load_tokens()
    access_token = tokens.get("access_token", "")
    expires_at = float(tokens.get("expires_at", 0))

    if not force_refresh and access_token and time.time() < expires_at - 5:
        _cached_access_token = access_token
        return access_token

    # Need to refresh — use stored session cookie
    cookie = tokens.get("session_cookie") or os.environ.get("TP_AUTH_COOKIE", "").strip()
    if not cookie:
        raise AuthError("Not authenticated. Run `tp auth setup` to log in.")

    new_tokens = _exchange_cookie(cookie)
    # Preserve athlete_id from previous tokens if new exchange didn't return it
    if not new_tokens.get("athlete_id") and tokens.get("athlete_id"):
        new_tokens["athlete_id"] = tokens["athlete_id"]
    _save_tokens(new_tokens)
    _cached_access_token = new_tokens["access_token"]
    return _cached_access_token


def invalidate_cache() -> None:
    global _cached_access_token
    _cached_access_token = None


# ---------------------------------------------------------------------------
# Save / load cookie
# ---------------------------------------------------------------------------

def save_session(cookie: str) -> dict:
    """Exchange cookie, save tokens, return identity info."""
    tokens = _exchange_cookie(cookie)
    _save_tokens(tokens)
    invalidate_cache()
    return tokens


def load_session_cookie() -> Optional[str]:
    return _load_tokens().get("session_cookie")


def delete_session() -> None:
    if TOKENS_FILE.exists():
        TOKENS_FILE.unlink()
    invalidate_cache()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_cookie(cookie: str) -> dict:
    """Validate cookie and return identity info."""
    tokens = _exchange_cookie(cookie)
    # Try to get athlete_id from the token response or user profile
    identity = {
        "athlete_id": tokens.get("athlete_id"),
        "username": None,
    }
    # If no athlete_id from token exchange, fetch from profile
    if not identity["athlete_id"]:
        try:
            resp = httpx.get(
                f"{TP_BASE}/users/v3/user",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("user", data)
                athletes = user.get("athletes", [])
                athlete = athletes[0] if athletes else user
                identity["athlete_id"] = athlete.get("athleteId") or user.get("personId")
                identity["username"] = user.get("email") or user.get("userName")
        except Exception:
            pass
    return identity


def check_status() -> dict:
    """Check current auth status. Returns dict with valid/invalid info."""
    tokens = _load_tokens()
    if not tokens.get("session_cookie"):
        return {"authenticated": False, "reason": "No credentials stored"}

    expires_at = float(tokens.get("expires_at", 0))
    cookie = tokens.get("session_cookie", "")

    try:
        identity = validate_cookie(cookie)
        return {
            "authenticated": True,
            "athlete_id": identity.get("athlete_id") or tokens.get("athlete_id"),
            "username": identity.get("username"),
            "token_expires_in_s": max(0, int(expires_at - time.time())),
        }
    except AuthError as e:
        return {"authenticated": False, "reason": str(e)}


# ---------------------------------------------------------------------------
# Browser extraction (macOS: Chrome, Safari, Firefox, etc.)
# ---------------------------------------------------------------------------

def extract_from_browser(browser: str = "chrome") -> str:
    try:
        import browser_cookie3
    except ImportError:
        raise RuntimeError(
            "browser-cookie3 not installed. Run: pip install browser-cookie3"
        )

    extractors = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "safari": browser_cookie3.safari,
        "edge": browser_cookie3.edge,
        "chromium": browser_cookie3.chromium,
        "brave": browser_cookie3.brave,
    }

    key = browser.lower()
    if key not in extractors:
        raise ValueError(
            f"Unsupported browser '{browser}'. "
            f"Choose from: {', '.join(extractors)}"
        )

    jar = extractors[key](domain_name=".trainingpeaks.com")
    for cookie in jar:
        if cookie.name == "Production_tpAuth":
            return cookie.value

    raise AuthError(
        f"Production_tpAuth cookie not found in {browser}. "
        "Make sure you are logged into TrainingPeaks in that browser first."
    )


# ---------------------------------------------------------------------------
# Import from existing tpapi.py tokens file
# ---------------------------------------------------------------------------

def import_tokens_file(path: str) -> dict:
    """Import tokens from an existing tpapi.py / trainingpeaks-mcp tokens file."""
    src = pathlib.Path(path).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"File not found: {path}")

    data = json.loads(src.read_text())
    required = {"access_token", "session_cookie"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Invalid tokens file — missing keys: {missing}")

    _save_tokens(data)
    invalidate_cache()
    return data


class AuthError(Exception):
    pass

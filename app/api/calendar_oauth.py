from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from app.core.fp_core import Ok, Err, Result

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def make_oauth_state(user_id: str, secret: str, now_ts: int | None = None) -> str:
    """
    Create signed OAuth2 state: base64url("user_id:iat:nonce.sig")
    """
    iat = now_ts if now_ts is not None else int(time.time())
    nonce = secrets.token_urlsafe(16)
    payload = f"{user_id}:{iat}:{nonce}"
    signature = _sign(payload, secret)
    return _b64url_encode(f"{payload}.{signature}".encode("utf-8"))


def validate_oauth_state(
    state: str,
    secret: str,
    max_age_seconds: int = 900,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """
    Returns parsed state payload if valid:
    {
      "ok": bool,
      "user_id": str | None,
      "issued_at": int | None,
      "reason": str | None
    }
    """
    now_value = now_ts if now_ts is not None else int(time.time())

    try:
        decoded = _b64url_decode(state).decode("utf-8")
        payload, given_sig = decoded.rsplit(".", 1)
        expected_sig = _sign(payload, secret)

        if not hmac.compare_digest(given_sig, expected_sig):
            return {"ok": False, "user_id": None, "issued_at": None, "reason": "bad_signature"}

        user_id, issued_at_raw, _nonce = payload.split(":", 2)
        issued_at = int(issued_at_raw)

        if (now_value - issued_at) > max_age_seconds:
            return {"ok": False, "user_id": user_id, "issued_at": issued_at, "reason": "expired"}

        return {"ok": True, "user_id": user_id, "issued_at": issued_at, "reason": None}
    except Exception:
        return {"ok": False, "user_id": None, "issued_at": None, "reason": "invalid_format"}


def build_google_oauth_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    access_type: str = "offline",
    prompt: str = "consent",
    include_granted_scopes: bool = True,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": access_type,
        "prompt": prompt,
        "include_granted_scopes": "true" if include_granted_scopes else "false",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    http_post_form,  # callable(url: str, data: dict[str, str]) -> Result
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_url: str = GOOGLE_TOKEN_URL,
) -> Result:
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    # flat_map: post → normalize; Err short-circuits both steps
    return http_post_form(token_url, payload).flat_map(normalize_token_response)


def refresh_access_token(
    http_post_form,  # callable(url: str, data: dict[str, str]) -> Result
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_url: str = GOOGLE_TOKEN_URL,
) -> Result:
    payload = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }
    # Google sometimes omits refresh_token; preserve caller's original via map
    return (
        http_post_form(token_url, payload)
        .flat_map(normalize_token_response)
        .map(lambda n: {**n, "refresh_token": n.get("refresh_token") or refresh_token})
    )


def normalize_token_response(token_data: dict[str, object], now_ts: int | None = None) -> Result:
    """pure: validate and normalize OAuth token response dict into Result"""
    if "error" in token_data:
        return Err(f"OAuth token error: {token_data.get('error')}")

    now_value = now_ts if now_ts is not None else int(time.time())
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")

    if not access_token or not expires_in:
        return Err("Invalid token response: missing access_token or expires_in")

    return Ok({
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "scope": token_data.get("scope", ""),
        "expires_in": int(expires_in),
        "obtained_at": now_value,
    })


def is_access_token_expired(token: dict[str, Any], skew_seconds: int = 30, now_ts: int | None = None) -> bool:
    now_value = now_ts if now_ts is not None else int(time.time())
    obtained_at = int(token.get("obtained_at", 0))
    expires_in = int(token.get("expires_in", 0))
    return now_value >= (obtained_at + expires_in - skew_seconds)



import httpx


def post_form_httpx(url: str, data: dict[str, str]) -> Result:
    """io boundary: POST form data, returns Result to avoid raising on http errors"""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except Exception as exc:
        return Err(str(exc))
    if not resp.is_success:
        return Err(f"HTTP {resp.status_code}")
    return Ok(resp.json())
"""
Token repository — functional interface over in-memory storage.

Pure read/write functions over a module-level dict.
In production, swap the dict for Redis / DB — the signatures stay the same.
"""
from __future__ import annotations

from typing import Any

from app.services.fp_core import Result, Ok, Err

# ---------------------------------------------------------------------------
# Storage  (single mutable boundary — isolated here)
# ---------------------------------------------------------------------------
_token_store: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_user_tokens(user_id: str, tokens: dict[str, Any]) -> Result[dict[str, Any], str]:
    """Persist tokens for a user. Returns Ok(tokens) on success."""
    if not user_id:
        return Err("user_id must not be empty")
    _token_store[user_id] = {**tokens}          # shallow copy for safety
    return Ok(_token_store[user_id])


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_user_tokens(user_id: str) -> Result[dict[str, Any], str]:
    """Retrieve tokens for a user. Err if not found."""
    tokens = _token_store.get(user_id)
    if tokens is None:
        return Err(f"No tokens stored for user '{user_id}'")
    return Ok(tokens)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_user_tokens(user_id: str) -> Result[str, str]:
    """Remove tokens for a user."""
    if user_id in _token_store:
        del _token_store[user_id]
        return Ok(user_id)
    return Err(f"No tokens to delete for user '{user_id}'")


# ---------------------------------------------------------------------------
# Query (pure over snapshot)
# ---------------------------------------------------------------------------

def list_connected_users() -> list[str]:
    """Return all user_ids that have stored tokens."""
    return list(_token_store.keys())


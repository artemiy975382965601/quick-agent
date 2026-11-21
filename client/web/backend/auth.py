"""Авторизация веб-клиента: access-JWT + refresh-сессия в SQLite.

Схема:
  login    -> access (15 мин, подпись HS256, нигде не хранится) + refresh cookie (30 дней, в БД)
  refresh  -> новая пара, старый refresh отзывается (ротация)
  logout   -> refresh отзывается, access живёт до истечения (≤15 мин)

Refresh хранится только хешем: утечка базы не даёт войти.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

SECRET = os.environ.get("WEB_SECRET", "").encode() or os.urandom(32)
ACCESS_TTL = int(os.environ.get("WEB_ACCESS_TTL", "900"))          # 15 минут
REFRESH_TTL = int(os.environ.get("WEB_REFRESH_TTL", str(30 * 86400)))  # 30 дней
DB_PATH = Path(os.environ.get("WEB_SESSIONS_DB", str(Path(__file__).parent / "sessions.db")))

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("""
CREATE TABLE IF NOT EXISTS refresh_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  INTEGER NOT NULL,
    last_used   INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    user_agent  TEXT,
    ip          TEXT
)
""")
_conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON refresh_sessions(expires_at)")
_conn.commit()


# ------------------------------------------------------------------ JWT
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def make_access(sub: str = "owner") -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": sub, "iat": now, "exp": now + ACCESS_TTL,
                               "jti": secrets.token_hex(8)}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(SECRET, signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_access(token: str | None) -> dict | None:
    if not token or token.count(".") != 2:
        return None
    header, payload, sig = token.split(".")
    expected = _b64(hmac.new(SECRET, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except Exception:
        return None
    if claims.get("exp", 0) < time.time():
        return None
    return claims


# ------------------------------------------------------------------ refresh
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh(user_agent: str = "", ip: str = "") -> str:
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    _conn.execute(
        "INSERT INTO refresh_sessions (token_hash, created_at, last_used, expires_at, user_agent, ip)"
        " VALUES (?,?,?,?,?,?)",
        (_hash(token), now, now, now + REFRESH_TTL, user_agent[:200], ip[:64]),
    )
    _conn.commit()
    return token


def rotate_refresh(token: str, user_agent: str = "", ip: str = "") -> str | None:
    now = int(time.time())
    row = _conn.execute(
        "SELECT id, expires_at, revoked FROM refresh_sessions WHERE token_hash = ?", (_hash(token),)
    ).fetchone()
    if not row or row[2] or row[1] < now:
        return None
    _conn.execute("UPDATE refresh_sessions SET revoked = 1 WHERE id = ?", (row[0],))
    _conn.commit()
    return issue_refresh(user_agent, ip)


def revoke_refresh(token: str) -> None:
    _conn.execute("UPDATE refresh_sessions SET revoked = 1 WHERE token_hash = ?", (_hash(token),))
    _conn.commit()


def cleanup() -> None:
    now = int(time.time())
    _conn.execute("DELETE FROM refresh_sessions WHERE expires_at < ? OR revoked = 1", (now - 86400,))
    _conn.commit()


def active_sessions() -> list[dict]:
    rows = _conn.execute(
        "SELECT created_at, last_used, expires_at, user_agent, ip FROM refresh_sessions"
        " WHERE revoked = 0 AND expires_at > ? ORDER BY last_used DESC", (int(time.time()),)
    ).fetchall()
    return [{"created": r[0], "last_used": r[1], "expires": r[2], "ua": r[3], "ip": r[4]} for r in rows]

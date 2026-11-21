"""TOTP (RFC 6238) без внешних зависимостей: секрет, код, проверка, otpauth-ссылка."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from pathlib import Path

STATE = Path(os.environ.get("WEB_TOTP_FILE", str(Path(__file__).parent / "totp.json")))
PERIOD = 30
DIGITS = 6
ISSUER = "quick-agent"
LABEL = "owner"


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    STATE.write_text(json.dumps(data))
    STATE.chmod(0o600)


def _new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def status() -> dict:
    d = _load()
    return {"enabled": bool(d.get("enabled")), "has_secret": bool(d.get("secret"))}


def ensure_secret() -> str:
    d = _load()
    if not d.get("secret"):
        d["secret"] = _new_secret()
        d.setdefault("enabled", False)
        _save(d)
    return d["secret"]


def secret() -> str | None:
    return _load().get("secret")


def enabled() -> bool:
    return bool(_load().get("enabled"))


def set_enabled(value: bool) -> None:
    d = _load()
    d["enabled"] = value
    _save(d)


def _code(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    part = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(part % (10 ** DIGITS)).zfill(DIGITS)


def now(secret_b32: str) -> str:
    return _code(secret_b32, int(time.time()) // PERIOD)


def verify(secret_b32: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return False
    current = int(time.time()) // PERIOD
    return any(hmac.compare_digest(_code(secret_b32, current + d), code)
               for d in range(-window, window + 1))


def uri(secret_b32: str | None = None) -> str:
    s = secret_b32 or ensure_secret()
    return (f"otpauth://totp/{ISSUER}:{LABEL}?secret={s}"
            f"&issuer={ISSUER}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")

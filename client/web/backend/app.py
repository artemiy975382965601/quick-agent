"""Веб-клиент quick-agent: backend с авторизацией и long-polling.

Агент живёт на 127.0.0.1:7777 и наружу не смотрит. Сюда ходят только через
туннель, и только с валидной cookie-сессией.
"""
from __future__ import annotations

import asyncio
import re
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

AGENT = os.environ.get("AGENT_URL", "http://127.0.0.1:7777").rstrip("/")
PASSWORD = os.environ.get("WEB_PASSWORD", "")
SECRET = os.environ.get("WEB_SECRET", "").encode() or os.urandom(32)
COOKIE = "wq_session"
SECURE = os.environ.get("WEB_INSECURE") != "1"
TTL = 12 * 3600
from client.config import Config

_cfg = Config.load()
PROMPTS = {
    "md": _cfg.prompt_paths("web"),
    "html": _cfg.prompt_paths("web_html"),
}
FRONTEND = Path(__file__).parent.parent / "frontend"
SERVER_CONFIG = Path("/home/art-dev/dev/quick-agent/config.json")

if not PASSWORD:
    raise SystemExit("WEB_PASSWORD не задан")

app = FastAPI(title="quick-agent web")

# ------------------------------------------------------------------ авторизация
# access — JWT в памяти клиента (15 мин), refresh — HttpOnly cookie с ротацией.
import auth as webauth

REFRESH_COOKIE = "wq_refresh"
import totp as totp_lib

# Лимит общий, а не по IP: через туннель все запросы приходят с 127.0.0.1
_fails: dict[str, int] = {"count": 0, "until": 0}
MAX_FAILS = 5
LOCK_SECONDS = 900


def require_auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    if not webauth.verify_access(token):
        raise HTTPException(status_code=401, detail="auth required")


def _client_meta(request: Request) -> tuple[str, str]:
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    return ua, ip


def _set_refresh(resp: Response, token: str) -> None:
    resp.set_cookie(REFRESH_COOKIE, token, httponly=True, secure=SECURE,
                    samesite="strict", path="/", max_age=webauth.REFRESH_TTL)


class LoginBody(BaseModel):
    password: str
    totp: str | None = None


@app.post("/api/login")
async def login(request: Request, body: LoginBody):
    if _fails["until"] > time.time():
        raise HTTPException(429, "too many attempts, wait")

    if not hmac.compare_digest(body.password.encode(), PASSWORD.encode()):
        _fails["count"] += 1
        if _fails["count"] >= MAX_FAILS:
            _fails["until"] = time.time() + LOCK_SECONDS
            _fails["count"] = 0
        raise HTTPException(401, "wrong password")

    if totp_lib.enabled():
        if not body.totp:
            raise HTTPException(401, "totp_required")
        if not totp_lib.verify(totp_lib.secret() or "", body.totp or ""):
            _fails["count"] += 1
            if _fails["count"] >= MAX_FAILS:
                _fails["until"] = time.time() + LOCK_SECONDS
                _fails["count"] = 0
            raise HTTPException(401, "wrong code")

    _fails["count"] = 0
    ua, addr = _client_meta(request)
    webauth.cleanup()
    resp = JSONResponse({"access": webauth.make_access(), "expires_in": webauth.ACCESS_TTL})
    _set_refresh(resp, webauth.issue_refresh(ua, addr))
    return resp


@app.post("/api/auth/refresh")
async def refresh(request: Request):
    old = request.cookies.get(REFRESH_COOKIE)
    if not old:
        raise HTTPException(401, "нет refresh-токена")
    ua, addr = _client_meta(request)
    new = webauth.rotate_refresh(old, ua, addr)
    if not new:
        resp = JSONResponse({"detail": "сессия истекла"}, status_code=401)
        resp.delete_cookie(REFRESH_COOKIE, path="/")
        return resp
    resp = JSONResponse({"access": webauth.make_access(), "expires_in": webauth.ACCESS_TTL})
    _set_refresh(resp, new)
    return resp


@app.post("/api/logout")
async def logout(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        webauth.revoke_refresh(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(REFRESH_COOKIE, path="/")
    return resp


@app.get("/api/me")
async def me(request: Request):
    require_auth(request)
    return {"ok": True, "agent": AGENT}


@app.get("/api/auth/totp")
async def totp_status(request: Request):
    require_auth(request)
    return totp_lib.status()


@app.get("/api/auth/totp/setup")
async def totp_setup(request: Request):
    """Секрет и QR для подключения приложения-аутентификатора."""
    require_auth(request)
    import io
    import qrcode

    secret = totp_lib.ensure_secret()
    uri = totp_lib.uri(secret)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode()
    return {"secret": secret, "uri": uri, "qr": "data:image/png;base64," + data}


class TotpCode(BaseModel):
    code: str


@app.post("/api/auth/totp/enable")
async def totp_enable(request: Request, body: TotpCode):
    require_auth(request)
    secret = totp_lib.ensure_secret()
    if not totp_lib.verify(secret, body.code):
        raise HTTPException(400, "wrong code")
    totp_lib.set_enabled(True)
    return {"enabled": True}


@app.post("/api/auth/totp/disable")
async def totp_disable(request: Request, body: TotpCode):
    require_auth(request)
    if not totp_lib.verify(totp_lib.secret() or "", body.code):
        raise HTTPException(400, "wrong code")
    totp_lib.set_enabled(False)
    return {"enabled": False}


@app.get("/api/auth/sessions")
async def auth_sessions(request: Request):
    require_auth(request)
    return webauth.active_sessions()

# ------------------------------------------------------------------ агент
def agent_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=AGENT, timeout=httpx.Timeout(60, connect=5))


@app.get("/api/sessions")
async def sessions(request: Request):
    require_auth(request)
    async with agent_client() as c:
        r = await c.get("/sessions/list/")
    return r.json()


class NewSession(BaseModel):
    title: str | None = None
    model_alias: str | None = None
    clone_from: str | None = None


@app.get("/api/models")
async def models(request: Request):
    """Доступные провайдеры из серверного config.json (без ключей)."""
    require_auth(request)
    try:
        conf = json.loads(SERVER_CONFIG.read_text())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"конфиг недоступен: {exc}") from exc
    out = []
    for alias, cfg in (conf.get("models") or {}).items():
        out.append({"alias": alias, "model": cfg.get("model", "")})
    default = conf.get("default")
    return {"models": out, "default": default}


@app.post("/api/sessions")
async def new_session(request: Request, body: NewSession):
    require_auth(request)
    sid = "web_" + uuid.uuid4().hex[:10]
    payload = {"id": sid}
    if body.title:
        payload["title"] = body.title
    if body.model_alias:
        payload["model_alias"] = body.model_alias

    pinned: list[dict] = []
    if body.clone_from:
        async with agent_client() as c:
            src = await c.get(f"/sessions/{body.clone_from}/")
            if src.status_code >= 400:
                raise HTTPException(404, "исходный чат не найден")
            src_data = src.json()
            payload.setdefault("model_alias", src_data.get("model_alias"))
            if not payload.get("model_alias"):
                payload.pop("model_alias", None)
            pr = await c.get(f"/sessions/{body.clone_from}/pinned/")
            if pr.status_code < 400:
                pinned = pr.json() or []

    async with agent_client() as c:
        r = await c.post("/sessions/create/", json=payload)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        created = r.json()
        for item in pinned:
            await c.post(f"/sessions/{sid}/pinned/", json={
                "full_paths": [item.get("file")],
                "space_for_insert": item.get("type_of_inject") or "user",
            })
    created["pinned_copied"] = len(pinned)
    return created


@app.get("/api/sessions/{sid}/pinned")
async def list_pinned(request: Request, sid: str):
    require_auth(request)
    async with agent_client() as c:
        r = await c.get(f"/sessions/{sid}/pinned/")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()


class PinBody(BaseModel):
    full_paths: list[str]
    space_for_insert: str = "user"


@app.post("/api/sessions/{sid}/pinned")
async def pin_files(request: Request, sid: str, body: PinBody):
    require_auth(request)
    async with agent_client() as c:
        r = await c.post(f"/sessions/{sid}/pinned/", json=body.model_dump())
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()


class UnpinBody(BaseModel):
    full_paths: list[str]


@app.delete("/api/sessions/{sid}/pinned")
async def unpin_files(request: Request, sid: str, body: UnpinBody):
    require_auth(request)
    async with agent_client() as c:
        r = await c.request("DELETE", f"/sessions/{sid}/pinned/", json=body.model_dump())
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()


class SessionPatch(BaseModel):
    title: str | None = None
    model_alias: str | None = None


@app.patch("/api/sessions/{sid}")
async def patch_session(request: Request, sid: str, body: SessionPatch):
    require_auth(request)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(400, "нечего менять")
    async with agent_client() as c:
        r = await c.put(f"/sessions/{sid}/", json=payload)
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()


@app.delete("/api/sessions/{sid}")
async def delete_session(request: Request, sid: str):
    require_auth(request)
    streams.pop(sid, None)
    async with agent_client() as c:
        r = await c.delete(f"/sessions/{sid}/")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return {"ok": True}


@app.delete("/api/chat/{sid}/history")
async def clear_history(request: Request, sid: str):
    require_auth(request)
    async with agent_client() as c:
        r = await c.delete(f"/chat/{sid}/")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return {"ok": True}


def normalize(items: list) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "function_call":
            out.append({"kind": "tool", "name": item.get("name", "tool"), "text": ""})
        elif t == "function_call_output":
            continue
        elif item.get("role") in ("user", "assistant"):
            content = item.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
            else:
                text = ""
            out.append({"kind": item["role"], "text": text, "name": ""})
    return out


@app.get("/api/chat/{sid}")
async def history(request: Request, sid: str, limit: int = 30):
    require_auth(request)
    async with agent_client() as c:
        r = await c.get(f"/chat/{sid}/", params={"limit": limit})
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    data = r.json()
    items = normalize(data.get("messages", []))
    items.reverse()
    return {"messages": items, "has_more": data.get("has_more", False)}

# ------------------------------------------------------------------ стрим
@dataclass
class Stream:
    events: list[dict] = field(default_factory=list)
    done: bool = False
    waiter: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def push(self, kind: str, data: str = "") -> None:
        self.events.append({"k": kind, "d": data})
        self.waiter.set()

    def finish(self) -> None:
        self.done = True
        self.waiter.set()


streams: dict[str, Stream] = {}


async def pump(sid: str, query: str, prompts: list[str], path: str = "start") -> None:
    st = streams[sid]
    try:
        async with httpx.AsyncClient(base_url=AGENT, timeout=httpx.Timeout(900, connect=10)) as c:
            async with c.stream("POST", f"/chat/{sid}/{path}",
                                json={"query": query, "client_prompt_paths": prompts},
                                headers={"Accept": "text/event-stream"}) as r:
                if r.status_code >= 400:
                    st.push("error", f"{r.status_code}: {(await r.aread()).decode()[:300]}")
                    st.finish()
                    return
                event, data = "message", []
                async for raw in r.aiter_lines():
                    line = raw.rstrip("\r")
                    if not line:
                        if data:
                            st.push(event, "\n".join(data))
                        event, data = "message", []
                        continue
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        chunk = line[5:]
                        data.append(chunk[1:] if chunk.startswith(" ") else chunk)
                if data:
                    st.push(event, "\n".join(data))
    except Exception as exc:  # noqa: BLE001
        st.push("error", f"{type(exc).__name__}: {exc}")
    finally:
        st.finish()


class StartBody(BaseModel):
    query: str
    mode: str = "md"


@app.post("/api/chat/{sid}/start")
async def start(request: Request, sid: str, body: StartBody):
    require_auth(request)
    old = streams.get(sid)
    if old and not old.done:
        raise HTTPException(409, "генерация уже идёт")
    st = Stream()
    streams[sid] = st
    st.task = asyncio.create_task(pump(sid, body.query, PROMPTS.get(body.mode, PROMPTS["md"])))
    return {"stream": sid}


@app.get("/api/stream/{sid}")
async def stream(request: Request, sid: str, after: int = 0, wait: float = 20.0):
    require_auth(request)
    st = streams.get(sid)
    if st is None:
        return {"events": [], "seq": 0, "done": True}
    deadline = time.monotonic() + min(wait, 25.0)
    while len(st.events) <= after and not st.done:
        st.waiter.clear()
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            await asyncio.wait_for(st.waiter.wait(), timeout=left)
        except asyncio.TimeoutError:
            break
    chunk = st.events[after:]
    return {"events": chunk, "seq": after + len(chunk), "done": st.done}


@app.post("/api/chat/{sid}/cancel")
async def cancel_turn(request: Request, sid: str):
    """Отмена: останавливаем генерацию и удаляем последний ход целиком."""
    require_auth(request)
    st = streams.get(sid)
    if st and st.task:
        st.task.cancel()
        st.finish()
    streams.pop(sid, None)
    async with agent_client() as c:
        try:
            await c.post(f"/chat/{sid}/stop")
        except Exception:
            pass
        r = await c.post(f"/chat/{sid}/cancel")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return {"ok": True}


@app.post("/api/chat/{sid}/stop")
async def stop(request: Request, sid: str):
    require_auth(request)
    st = streams.get(sid)
    if st and st.task:
        st.task.cancel()
        st.finish()
    async with agent_client() as c:
        await c.post(f"/chat/{sid}/stop")
    return {"ok": True}


@app.post("/api/chat/{sid}/retry")
async def retry(request: Request, sid: str, body: StartBody | None = None):
    """Повтор той же генерации: сообщение пользователя остаётся в истории."""
    require_auth(request)
    old = streams.get(sid)
    if old and not old.done:
        old.task.cancel() if old.task else None
        old.finish()
    st = Stream()
    streams[sid] = st
    mode = (body.mode if body else None) or "md"
    st.task = asyncio.create_task(
        pump(sid, "", PROMPTS.get(mode, PROMPTS["md"]), path="retry")
    )
    return {"stream": sid}


# ------------------------------------------------------------------ статика
@app.get("/")
async def index():
    # без кеша + версия из времени правки файла: телефон не сможет взять старый скрипт
    html = (FRONTEND / "index.html").read_text()
    stamps = {}
    for name in ["app.js", "style.css", "template.css", "hljs.css"]:
        path = FRONTEND / name
        stamp = int(path.stat().st_mtime) if path.exists() else 0
        stamps[name] = stamp
        html = re.sub(rf"{re.escape(name)}\?v=[^\"&]*", f"{name}?v={stamp}", html)
    asset_meta = f'<meta name="assets" content="{stamps["template.css"]}|{stamps["hljs.css"]}"></head>'
    html = html.replace("</head>", asset_meta)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, must-revalidate"})


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

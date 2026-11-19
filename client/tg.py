#!/usr/bin/env python3
"""Telegram-клиент quick-agent.

Без стриминга и без редактирования сообщений: ответ приходит отдельными
сообщениями — текстовый блок, затем строка вызванного инструмента, затем
следующий текстовый блок. Разметка ответов — HTML, при ошибке разбора
Telegram сообщение уходит обычным текстом.

Запуск из корня проекта:
    set -a; . ~/dev/quick-agent-tg/.env; set +a
    ./venv/bin/python -m client.tg
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import socket
import time
import traceback
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BotCommand, ErrorEvent, Message
from aiohttp import ClientSession, TCPConnector

from client.aio import AsyncClient
from client.config import Config
from client.errors import ApiError, ClientError, ConnectionFailed
from client.events import Event
from client.history import TOOL_CALL, TOOL_RESULT, Item, chronological

MODE = 'tg'
BOT_TOKEN = os.environ['BOT_TOKEN']
ALLOWED_USER_ID = int(os.environ.get('ALLOWED_USER_ID', '5131050858'))
PROXY = os.environ.get('BOT_PROXY') or None
LIMIT = 3900

cfg = Config.load()
api = AsyncClient(cfg)
router = Router()
running: dict[int, asyncio.Task] = {}
use_map: dict[int, list[str]] = {}
_bot: Bot | None = None


def allowed(user_id: int | None) -> bool:
    return user_id == ALLOWED_USER_ID


# ------------------------------------------------------------------ отправка
_TAG = re.compile(r'</?[a-zA-Z][^>]*>')


def to_plain(text: str) -> str:
    return html.unescape(_TAG.sub('', text))


def split_text(text: str, limit: int = LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text] if text else []
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind('\n', 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip('\n')
    if rest:
        parts.append(rest)
    return parts


async def send_html(message: Message, text: str) -> None:
    """HTML, а при отказе Telegram — тот же текст обычным."""
    for chunk in split_text(text):
        if not chunk.strip():
            continue
        try:
            await message.answer(chunk)
        except TelegramBadRequest:
            await message.answer(to_plain(chunk), parse_mode=None)


async def send_plain(message: Message, text: str) -> None:
    for chunk in split_text(text):
        if chunk.strip():
            await message.answer(chunk, parse_mode=None)


async def report(message: Message, title: str, exc: BaseException | None = None,
                 code: int | None = None, body: object | None = None) -> None:
    parts = [f'⚠️ {html.escape(title)}']
    if code is not None:
        parts.append(f'код: {code}')
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        parts.append(f'ответ API: {text[:1500]}')
    if exc is not None:
        parts.append(f'{type(exc).__name__}: {exc}')
        tail = '\n'.join(traceback.format_exc().strip().splitlines()[-5:])
        parts.append(tail)
    await send_plain(message, '\n'.join(parts))


async def bot_send(text: str) -> None:
    if _bot is None:
        return
    try:
        await _bot.send_message(ALLOWED_USER_ID, text, parse_mode=None)
    except Exception:  # noqa: BLE001
        pass


def describe(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return f'error {exc.human()}'
    if isinstance(exc, (ConnectionFailed, ClientError)):
        return f'error: {exc}'
    return f'error: {type(exc).__name__}: {exc}'


# ------------------------------------------------------------------ история
def format_items(items: list[Item], has_more: bool, limit: int = 600) -> str:
    items = chronological(items)
    lines: list[str] = []
    if has_more:
        lines.append('… есть более ранние сообщения')
    for item in items:
        if item.kind == TOOL_RESULT:
            continue
        if item.kind == TOOL_CALL:
            lines.append(f'⚙ {item.name}')
            continue
        text = item.text.strip()
        if len(text) > limit:
            text = text[:limit] + '…'
        lines.append(f'[{item.kind}] {html.escape(text)}')
    return '\n\n'.join(lines) if lines else '(пусто)'


async def show_history(message: Message, sid: str, limit: int = 10) -> None:
    items, has_more = await api.history(sid, limit)
    await send_html(message, format_items(items, has_more))


# ------------------------------------------------------------------ сессии
async def ensure_session() -> str:
    sid = cfg.current(MODE)
    if sid:
        try:
            await api.get_session(sid)
            return sid
        except ApiError as exc:
            if not exc.not_found:
                raise
    sid = await api.create_session()
    cfg.set_current(MODE, sid)
    return sid


async def session_list_text(current: str | None) -> tuple[str, list[str]]:
    rows = await api.list_sessions()
    if not rows:
        return 'сессий нет — /new', []
    lines = []
    ids = []
    for idx, item in enumerate(rows, 1):
        sid = item.get('id', '?')
        ids.append(sid)
        mark = '→' if sid == current else ' '
        title = html.escape(item.get('title') or '(без названия)')
        model = html.escape(item.get('model_alias') or '')
        lines.append(f'{idx:>2}. {mark} {title}  {model}  ({sid})')
    return '\n'.join(lines), ids


# ------------------------------------------------------------------ рендер стрима
class Streamer:
    """Текст копится и уходит сообщением на границе блока: перед вызовом
    инструмента и в конце прогона. Никакого редактирования и черновиков."""

    def __init__(self, message: Message) -> None:
        self.message = message
        self.buf: list[str] = []

    def delta(self, text: str) -> None:
        if text in ('None', 'null'):
            return
        self.buf.append(text)

    async def flush(self) -> None:
        if not self.buf:
            return
        text = ''.join(self.buf).strip()
        self.buf.clear()
        if text:
            await send_html(self.message, text)

    async def tool(self, name: str) -> None:
        await self.flush()
        safe = html.escape(name)
        try:
            await self.message.answer(f'⚙ <code>{safe}</code>')
        except TelegramBadRequest:
            await self.message.answer(f'⚙ {name}', parse_mode=None)


async def consume(message: Message, events) -> None:
    streamer = Streamer(message)
    got = False
    async for event in events:
        got = True
        if event.kind == 'delta':
            streamer.delta(event.data)
        elif event.kind == 'tool_called':
            await streamer.tool(event.data)
        elif event.kind == 'error':
            await streamer.flush()
            info = event.error_info()
            hint = 'можно повторить' if info.get('retryable') else 'повтор не поможет'
            text = f"⚠️ {info.get('code')}: {info.get('message')} ({hint})"
            if info.get('detail'):
                text += f'\n\n{str(info["detail"])[:600]}'
            await send_plain(message, text)
        elif event.kind == 'done':
            await streamer.flush()
            return
    await streamer.flush()
    if not got:
        await send_plain(message, '(API ответил, но не прислал ни одного события)')


async def stream_task(message: Message, events) -> None:
    try:
        await consume(message, events)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        await report(message, 'ошибка стрима', exc)


# ------------------------------------------------------------------ команды
@router.message(Command('start', 'help'))
async def cmd_start(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    await send_plain(
        message,
        'quick-agent\n\n'
        '/new [заголовок] — новая сессия\n'
        '/sessions — список сессий\n'
        '/use <номер|id> — выбрать сессию (последние 10 сообщений)\n'
        '/show — текущая сессия\n'
        '/rename <заголовок>\n'
        '/model <alias>\n'
        '/del — удалить текущую\n'
        '/history [N] — последние N сообщений\n'
        '/clear — очистить историю\n'
        '/retry — откатить последний ход и повторить запрос\n'
        '/cancel — откатить последнее сообщение\n'
        '/pin <путь> [system|user], /unpin <путь>, /pinned\n'
        '/stop — прервать ответ\n'
        '/health — проверить API\n'
        '/url <url> — адрес API\n\n'
        'Любой текст — запрос к агенту.',
    )


@router.message(Command('health'))
async def cmd_health(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    await send_plain(message, 'ok' if await api.health() else 'API не отвечает')


@router.message(Command('url'))
async def cmd_url(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    arg = (message.text.partition(' ')[2] or '').strip()
    if not arg:
        await send_plain(message, cfg.base_url)
        return
    cfg.set_base_url(arg)
    api.config = cfg
    await send_plain(message, f'API: {cfg.base_url}')


@router.message(Command('new'))
async def cmd_new(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    title = (message.text.partition(' ')[2] or '').strip() or None
    try:
        sid = await api.create_session(title)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    cfg.set_current(MODE, sid)
    await send_plain(message, f'новая сессия {sid}')


@router.message(Command('sessions'))
async def cmd_sessions(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    try:
        text, ids = await session_list_text(cfg.current(MODE))
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    use_map[message.chat.id] = ids
    await send_plain(message, text)


@router.message(Command('use'))
async def cmd_use(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    arg = (message.text.partition(' ')[2] or '').strip()
    await select_session(message, arg)


async def select_session(message: Message, arg: str) -> None:
    try:
        if not arg:
            text, ids = await session_list_text(cfg.current(MODE))
            use_map[message.chat.id] = ids
            await send_html(message, text + '\n\nномер сессии?')
            return
        sid = arg
        if arg.isdigit():
            ids = use_map.get(message.chat.id)
            if not ids:
                text, ids = await session_list_text(cfg.current(MODE))
                use_map[message.chat.id] = ids
                await send_plain(message, 'сначала /sessions, потом номер')
                return
            idx = int(arg)
            if not 1 <= idx <= len(ids):
                await send_plain(message, f'номер вне списка (1..{len(ids)})')
                return
            sid = ids[idx - 1]
        session = await api.get_session(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    cfg.set_current(MODE, sid)
    use_map.pop(message.chat.id, None)
    title = html.escape(session.get('title') or 'без названия')
    await send_html(message, f'текущая: <b>{title}</b> (<code>{sid}</code>)')
    await show_history(message, sid, 10)


@router.message(Command('show'))
async def cmd_show(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии, /new')
        return
    try:
        session = await api.get_session(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, json.dumps(session, ensure_ascii=False, indent=2))


@router.message(Command('rename'))
async def cmd_rename(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    title = (message.text.partition(' ')[2] or '').strip()
    sid = cfg.current(MODE)
    if not sid or not title:
        await send_plain(message, 'нужно: /rename <заголовок> и текущая сессия')
        return
    try:
        await api.update_session(sid, title=title)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, 'ok')


@router.message(Command('model'))
async def cmd_model(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    alias = (message.text.partition(' ')[2] or '').strip()
    sid = cfg.current(MODE)
    if not sid or not alias:
        await send_plain(message, 'нужно: /model <alias> и текущая сессия')
        return
    try:
        await api.update_session(sid, model_alias=alias)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, 'ok')


@router.message(Command('del'))
async def cmd_del(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    try:
        await api.delete_session(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    cfg.set_current(MODE, None)
    await send_plain(message, 'ok')


@router.message(Command('history'))
async def cmd_history(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    arg = (message.text.partition(' ')[2] or '').strip()
    limit = int(arg) if arg.isdigit() else 10
    try:
        await show_history(message, sid, max(1, min(50, limit)))
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))


@router.message(Command('clear'))
async def cmd_clear(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    if message.chat.id in running and not running[message.chat.id].done():
        await send_plain(message, '⏳ идёт генерация — сначала /stop')
        return
    try:
        await api.clear(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, 'история очищена')


@router.message(Command('stop'))
async def cmd_stop(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    task = running.pop(message.chat.id, None)
    if task is not None and not task.done():
        task.cancel()
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нечего останавливать')
        return
    try:
        await api.stop(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, '⏹ остановлено')


@router.message(Command('retry'))
async def cmd_retry(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    active = running.get(message.chat.id)
    if active is not None and not active.done():
        await send_plain(message, '⏳ идёт генерация — /stop, потом /retry')
        return
    task = asyncio.create_task(stream_task(message, api.retry(sid, MODE)))
    running[message.chat.id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        running.pop(message.chat.id, None)


@router.message(Command('cancel'))
async def cmd_cancel(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    if message.chat.id in running and not running[message.chat.id].done():
        await send_plain(message, '⏳ идёт генерация — сначала /stop')
        return
    try:
        await api.cancel(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, 'откат выполнен')


@router.message(Command('pin'))
async def cmd_pin(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    arg = (message.text.partition(' ')[2] or '').strip()
    if not sid or not arg:
        await send_plain(message, 'нужно: /pin <путь> [system|user] и текущая сессия')
        return
    path, _, space = arg.partition(' ')
    space = space.strip() or 'user'
    if space not in ('system', 'user'):
        await send_plain(message, 'space: system или user')
        return
    try:
        results = await api.pin(sid, [path], space)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, '\n'.join(results) or 'ok')


@router.message(Command('unpin'))
async def cmd_unpin(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    arg = (message.text.partition(' ')[2] or '').strip()
    if not sid or not arg:
        await send_plain(message, 'нужно: /unpin <путь> и текущая сессия')
        return
    try:
        results = await api.unpin(sid, [arg])
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    await send_plain(message, '\n'.join(results) or 'ok')


@router.message(Command('pinned'))
async def cmd_pinned(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'нет текущей сессии')
        return
    try:
        rows = await api.pinned(sid)
    except (ApiError, ConnectionFailed) as exc:
        await send_plain(message, describe(exc))
        return
    if not rows:
        await send_plain(message, '(пусто)')
        return
    lines = [f"{r.get('type_of_inject')} {r.get('type_of_content')} {r.get('file')}" for r in rows]
    await send_plain(message, '\n'.join(lines))


# ------------------------------------------------------------------ чат
@router.message(F.text)
async def on_text(message: Message) -> None:
    if not allowed(message.from_user.id):
        return
    text = message.text
    if text.startswith('/'):
        return

    state_ids = use_map.get(message.chat.id)
    if text.strip().isdigit() and state_ids:
        await select_session(message, text.strip())
        return

    sid = cfg.current(MODE)
    if not sid:
        await send_plain(message, 'сначала /new')
        return

    active = running.get(message.chat.id)
    if active is not None and not active.done():
        await send_plain(message, '⏳ идёт генерация — /stop, потом отправляй')
        return

    task = asyncio.create_task(stream_task(message, api.start(sid, text, MODE)))
    running[message.chat.id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        running.pop(message.chat.id, None)


# ------------------------------------------------------------------ транспорт
class IPv4Session(AiohttpSession):
    """Telegram только по IPv4: IPv6 до api.telegram.org висит десятками секунд."""

    async def create_session(self):
        if self._should_reset_connector:
            await self.close()
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=TCPConnector(family=socket.AF_INET, limit=60, ttl_dns_cache=300),
            )
            self._should_reset_connector = False
        return self._session


COMMANDS = [
    ('new', 'новая сессия'),
    ('sessions', 'список сессий'),
    ('use', 'выбрать сессию'),
    ('show', 'текущая сессия'),
    ('history', 'последние сообщения'),
    ('retry', 'откатить ход и повторить запрос'),
    ('cancel', 'откатить последнее сообщение'),
    ('stop', 'прервать ответ'),
    ('clear', 'очистить историю'),
    ('rename', 'переименовать сессию'),
    ('model', 'сменить модель'),
    ('del', 'удалить текущую сессию'),
    ('pin', 'прикрепить файл'),
    ('unpin', 'открепить файл'),
    ('pinned', 'список прикреплённых'),
    ('health', 'проверить API'),
    ('url', 'адрес API'),
    ('help', 'справка'),
]


async def setup_commands(bot: Bot) -> None:
    """Кнопка Menu в Telegram: список команд."""
    await bot.set_my_commands([BotCommand(command=name, description=text) for name, text in COMMANDS])
    await bot.set_my_short_description(short_description='quick-agent: агент в терминале и Telegram')
    await bot.set_my_description(
        description='Клиент к quick-agent. Любой текст — запрос к агенту, '
                    'каждый вызов инструмента приходит отдельным сообщением.'
    )


async def main() -> None:
    global _bot
    session = IPv4Session(proxy=PROXY)
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _bot = bot

    dp = Dispatcher()
    dp.include_router(router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        where = getattr(event.update, 'event_type', 'update')
        await bot_send(f'⚠️ ошибка в обработчике ({where}): {event.exception!r}')
        return True

    me = await bot.get_me()
    try:
        await setup_commands(bot)
    except Exception as exc:  # noqa: BLE001
        print(f'warning: не удалось выставить меню команд: {exc}', flush=True)
    for missing in cfg.missing_prompts(MODE):
        print(f'warning: нет клиентского промпта {missing}', flush=True)

    try:
        sid = await ensure_session()
        session_info = await api.get_session(sid)
        title = session_info.get('title') or 'без названия'
    except (ApiError, ConnectionFailed) as exc:
        sid, title = None, describe(exc)

    line = f'@{me.username} (id {me.id}), api={cfg.base_url}, allowed={ALLOWED_USER_ID}'
    print(f'started {line}', flush=True)
    await bot_send(f'✅ запущен {line}\nсессия: {title} ({sid})')

    while True:
        try:
            await dp.start_polling(bot, handle_signals=False, polling_timeout=15, request_timeout=25)
            await bot_send('polling завершился без ошибки — перезапуск')
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await bot_send(f'⚠️ polling упал: {exc!r}')
        await asyncio.sleep(5)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

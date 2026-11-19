#!/usr/bin/env python3
"""qa — терминальный клиент quick-agent.

Запуск из корня проекта:
    ./venv/bin/python -m client.cli
    ./venv/bin/python -m client.cli chat <id> "текст"

Без аргументов — интерактивный режим.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading

from client.config import Config
from client.errors import ApiError, ClientError, ConnectionFailed
from client.history import ASSISTANT, TOOL_CALL, TOOL_RESULT, USER, Item, chronological
from client.sync import SyncClient

MODE = 'cli'

C_RESET = '\033[0m'
C_PROMPT = '\033[32m'
C_TOOL = '\033[2;32m'
C_ERR = '\033[91m'
C_DIM = '\033[2m'
USE_COLOR = sys.stdout.isatty() and os.environ.get('NO_COLOR') is None


def col(text: str, color: str) -> str:
    return f'{color}{text}{C_RESET}' if USE_COLOR else text


def dim(text: str) -> str:
    return col(text, C_DIM)


def err(text: str) -> None:
    print(col(text, C_ERR), file=sys.stderr)


def error_text(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return f'error {exc.human()}'
    if isinstance(exc, (ConnectionFailed, ClientError)):
        return f'error: {exc}'
    return f'error: {type(exc).__name__}: {exc}'


# ------------------------------------------------------------------ история
def show_items(items: list[Item], has_more: bool = False, limit: int = 600) -> None:
    items = chronological(items)
    if has_more:
        print(dim('… есть более ранние сообщения'))
    if not items:
        print(dim('(пусто)'))
        return
    for item in items:
        if item.kind == TOOL_RESULT:
            continue
        if item.kind == TOOL_CALL:
            print(col(f'⚙ {item.name}', C_TOOL))
            continue
        text = item.text.strip()
        if len(text) > limit:
            text = text[:limit] + '…'
        print(col(f'[{item.kind}]', C_TOOL), text)


# ------------------------------------------------------------------ стрим
class StreamThread(threading.Thread):
    """Стрим в фоне, чтобы приглашение и Ctrl+C оставались живыми."""

    def __init__(self, events, stop_evt: threading.Event) -> None:
        super().__init__(daemon=True)
        self.events = events
        self.stop_evt = stop_evt

    def run(self) -> None:
        try:
            for event in self.events:
                if self.stop_evt.is_set():
                    return
                render(event)
        except (ApiError, ConnectionFailed) as exc:
            print()
            err(error_text(exc))
        except Exception as exc:  # noqa: BLE001
            print()
            err(f'error: {type(exc).__name__}: {exc}')
        print()


def render(event) -> None:
    if event.kind == 'delta':
        if event.data in ('None', 'null'):
            return
        print(event.data, end='', flush=True)
    elif event.kind == 'tool_called':
        print(col(f'\n⚙ {event.data}', C_TOOL), flush=True)
    elif event.kind == 'error':
        info = event.error_info()
        print()
        err(f"⚠️ {info.get('code')}: {info.get('message')}")
    elif event.kind == 'done':
        return


ACTIVE: StreamThread | None = None


def stop_active(client: SyncClient, sid: str, quiet: bool = False) -> None:
    global ACTIVE
    if ACTIVE is None or not ACTIVE.is_alive():
        ACTIVE = None
        if not quiet:
            print(dim('нечего останавливать'))
        return
    ACTIVE.stop_evt.set()
    ACTIVE.join(timeout=3)
    ACTIVE = None
    try:
        client.stop(sid)
    except (ApiError, ConnectionFailed):
        pass
    if not quiet:
        print(col('⏹ остановлено', C_TOOL))


def run_stream(start, client: SyncClient, sid: str, quiet: bool = False) -> None:
    global ACTIVE
    if ACTIVE is not None and ACTIVE.is_alive():
        if not quiet:
            print(dim('⏳ идёт генерация — /stop, потом отправляй'))
        return
    ACTIVE = StreamThread(start(), threading.Event())
    ACTIVE.start()


# ------------------------------------------------------------------ сессии
def print_sessions(rows: list[dict], current: str | None) -> list[str]:
    if not rows:
        print(dim('(сессий нет)'))
        return []
    ids = []
    for idx, item in enumerate(rows, 1):
        sid = item.get('id', '?')
        ids.append(sid)
        mark = '→' if sid == current else ' '
        title = item.get('title') or '(без названия)'
        model = item.get('model_alias', '')
        print(f"{col(f'{idx:>2}.', C_PROMPT)} {mark} {title}  {dim(model)} {dim(sid)}")
    return ids


def ensure_session(cfg: Config, client: SyncClient, sid: str | None) -> str:
    if sid:
        try:
            client.get_session(sid)
            return sid
        except ApiError as exc:
            if not exc.not_found:
                raise
    sid = client.create_session()
    cfg.set_current(MODE, sid)
    return sid


def open_session(cfg: Config, client: SyncClient, sid: str) -> None:
    client.get_session(sid)
    cfg.set_current(MODE, sid)
    items, has_more = client.history(sid, 10)
    show_items(items, has_more)


# ------------------------------------------------------------------ REPL
HELP = """команды:
  /new [заголовок]        новая сессия (сразу текущая)
  /ls                     список сессий
  /use N|id               выбрать сессию, показать последние сообщения
  /show                   текущая сессия
  /hist                   история (последние 50)
  /retry                  откатить последний ход и повторить запрос
  /cancel                 откатить последнее сообщение на сервере
  /clear                  очистить историю
  /rename <заголовок>
  /model <alias>
  /rm                     удалить текущую сессию
  /stop                   остановить генерацию
  /pin <путь> [system|user]  прикрепить файл или папку
  /unpin <путь>
  /pinned                 список прикреплённых
  /health                 проверить API
  /url [url]              адрес API
  /help                   эта справка
  /q                      выход
всё остальное — сообщение агенту."""


def repl() -> None:
    cfg = Config.load()
    client = SyncClient(cfg)

    for missing in cfg.missing_prompts(MODE):
        err(f'warning: нет клиентского промпта {missing}')

    if not client.health():
        err(f'API не отвечает: {cfg.base_url}')
    else:
        try:
            sid = ensure_session(cfg, client, cfg.current(MODE))
        except (ApiError, ConnectionFailed) as exc:
            err(error_text(exc))
            return
        print(col('❯', C_PROMPT), dim(f'quick-agent · {cfg.base_url}'))
        print(dim(f'сессия {sid}. /help — команды, /q — выход.'))
        repl_loop(cfg, client, sid)


def repl_loop(cfg: Config, client: SyncClient, sid: str) -> None:
    while True:
        try:
            line = input(col('❯ ', C_PROMPT))
        except EOFError:
            print()
            stop_active(client, sid, quiet=True)
            return
        except KeyboardInterrupt:
            if ACTIVE is not None and ACTIVE.is_alive():
                stop_active(client, sid)
                continue
            print()
            return
        text = line.strip()
        if not text:
            continue

        try:
            if text in ('/q', '/quit', '/exit'):
                stop_active(client, sid, quiet=True)
                return
            if text == '/help':
                print(HELP)
                continue
            if text.startswith('/new'):
                title = text.partition(' ')[2].strip() or None
                sid = client.create_session(title)
                cfg.set_current(MODE, sid)
                print(dim(f'новая сессия {sid}'))
                continue
            if text == '/ls':
                print_sessions(client.list_sessions(), sid)
                continue
            if text.startswith('/use'):
                arg = text.partition(' ')[2].strip()
                rows = client.list_sessions()
                if arg.isdigit():
                    if not 1 <= int(arg) <= len(rows):
                        print(col(f'номер вне списка (1..{len(rows)})', C_ERR))
                        continue
                    picked = rows[int(arg) - 1].get('id')
                    if not picked:
                        print(col('у сессии нет id', C_ERR))
                        continue
                    sid = picked
                elif arg:
                    sid = arg
                else:
                    print(dim('укажи номер или id: /use 2'))
                    continue
                open_session(cfg, client, sid)
                print(dim(f'текущая: {sid}'))
                continue
            if text == '/show':
                print(json.dumps(client.get_session(sid), ensure_ascii=False, indent=2))
                continue
            if text == '/hist':
                show_items(*client.history(sid, 50))
                continue
            if text.startswith('/retry'):
                run_stream(lambda: client.retry(sid, MODE), client, sid)
                continue
            if text == '/cancel':
                if ACTIVE is not None and ACTIVE.is_alive():
                    print(dim('⏳ идёт генерация — сначала /stop'))
                    continue
                client.cancel(sid)
                print(col('откат выполнен', C_TOOL))
                continue
            if text == '/clear':
                if ACTIVE is not None and ACTIVE.is_alive():
                    print(dim('⏳ идёт генерация — сначала /stop'))
                    continue
                client.clear(sid)
                print(col('история очищена', C_TOOL))
                continue
            if text.startswith('/rename'):
                title = text.partition(' ')[2].strip()
                if not title:
                    print(dim('нужно: /rename <заголовок>'))
                    continue
                client.update_session(sid, title=title)
                print(col('ok', C_TOOL))
                continue
            if text.startswith('/model'):
                alias = text.partition(' ')[2].strip()
                if not alias:
                    print(dim('нужно: /model <alias>'))
                    continue
                client.update_session(sid, model_alias=alias)
                print(col('ok', C_TOOL))
                continue
            if text == '/rm':
                client.delete_session(sid)
                sid = client.create_session()
                cfg.set_current(MODE, sid)
                print(dim(f'удалена, новая сессия {sid}'))
                continue
            if text == '/stop':
                stop_active(client, sid)
                continue
            if text.startswith('/pin'):
                arg = text.partition(' ')[2].strip()
                if not arg:
                    print(dim('нужно: /pin <путь> [system|user]'))
                    continue
                path, _, space = arg.partition(' ')
                space = space.strip() or 'user'
                for line in client.pin(sid, [path], space):
                    print(line)
                continue
            if text.startswith('/unpin'):
                arg = text.partition(' ')[2].strip()
                if not arg:
                    print(dim('нужно: /unpin <путь>'))
                    continue
                for line in client.unpin(sid, [arg]):
                    print(line)
                continue
            if text == '/pinned':
                rows = client.pinned(sid)
                if not rows:
                    print(dim('(пусто)'))
                for row in rows:
                    print(f"{row.get('type_of_inject')} {row.get('type_of_content')} {row.get('file')}")
                continue
            if text == '/health':
                print('ok' if client.health() else col('API не отвечает', C_ERR))
                continue
            if text.startswith('/url'):
                arg = text.partition(' ')[2].strip()
                if arg:
                    cfg.set_base_url(arg)
                    client.config = cfg
                print(dim(cfg.base_url))
                continue
            if text.startswith('/'):
                print(dim('неизвестная команда, /help'))
                continue

            run_stream(lambda: client.start(sid, text, MODE), client, sid)
        except (ApiError, ConnectionFailed) as exc:
            err(error_text(exc))
        except KeyboardInterrupt:
            print()


# ------------------------------------------------------------------ подкоманды
def cmd_url(client: SyncClient, cfg: Config, args) -> None:
    if args.set:
        cfg.set_base_url(args.set)
        client.config = cfg
    print(cfg.base_url)


def cmd_new(client: SyncClient, cfg: Config, args) -> None:
    sid = client.create_session(args.title, args.model, args.id)
    cfg.set_current(MODE, sid)
    print(sid)


def cmd_sessions(client: SyncClient, cfg: Config, args) -> None:
    print_sessions(client.list_sessions(), cfg.current(MODE))


def cmd_show(client: SyncClient, cfg: Config, args) -> None:
    print(json.dumps(client.get_session(args.session_id), ensure_ascii=False, indent=2))


def cmd_rename(client: SyncClient, cfg: Config, args) -> None:
    client.update_session(args.session_id, args.title, args.model)
    print('ok')


def cmd_rm(client: SyncClient, cfg: Config, args) -> None:
    client.delete_session(args.session_id)
    if cfg.current(MODE) == args.session_id:
        cfg.set_current(MODE, None)
    print('ok')


def cmd_history(client: SyncClient, cfg: Config, args) -> None:
    items, has_more = client.history(args.session_id, args.limit)
    if args.json:
        print(json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2))
        return
    show_items(items, has_more)


def cmd_chat(client: SyncClient, cfg: Config, args) -> None:
    query = ' '.join(args.text) if args.text else sys.stdin.read().strip()
    if not query:
        err('пустой запрос')
        raise SystemExit(2)
    for event in client.start(args.session_id, query, MODE):
        render(event)
    print()


def cmd_retry(client: SyncClient, cfg: Config, args) -> None:
    for event in client.retry(args.session_id, MODE):
        render(event)
    print()


def cmd_stop(client: SyncClient, cfg: Config, args) -> None:
    client.stop(args.session_id)
    print('ok')


def cmd_cancel(client: SyncClient, cfg: Config, args) -> None:
    client.cancel(args.session_id)
    print('ok')


def cmd_clear(client: SyncClient, cfg: Config, args) -> None:
    client.clear(args.session_id)
    print('ok')


def cmd_pin(client: SyncClient, cfg: Config, args) -> None:
    for line in client.pin(args.session_id, args.paths, args.space):
        print(line)


def cmd_unpin(client: SyncClient, cfg: Config, args) -> None:
    for line in client.unpin(args.session_id, args.paths):
        print(line)


def cmd_pinned(client: SyncClient, cfg: Config, args) -> None:
    for row in client.pinned(args.session_id):
        print(f"{row.get('type_of_inject')} {row.get('type_of_content')} {row.get('file')}")


def cmd_health(client: SyncClient, cfg: Config, args) -> None:
    print('ok' if client.health() else 'down')
    raise SystemExit(0 if client.health() else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='qa', description='терминальный клиент quick-agent')
    parser.add_argument('--url', help='базовый URL API (сохраняется в конфиг)')
    sub = parser.add_subparsers(dest='command')

    s = sub.add_parser('repl', help='интерактивный режим (по умолчанию)')
    s.set_defaults(func=lambda c, g, a: repl())

    s = sub.add_parser('url', help='показать/задать адрес API')
    s.add_argument('--set')
    s.set_defaults(func=cmd_url)

    s = sub.add_parser('new', help='создать сессию')
    s.add_argument('--id')
    s.add_argument('--title')
    s.add_argument('--model', dest='model')
    s.set_defaults(func=cmd_new)

    s = sub.add_parser('sessions', help='список сессий')
    s.set_defaults(func=cmd_sessions)

    s = sub.add_parser('show', help='сессия по id')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_show)

    s = sub.add_parser('rename', help='изменить title/model_alias')
    s.add_argument('session_id')
    s.add_argument('--title')
    s.add_argument('--model', dest='model')
    s.set_defaults(func=cmd_rename)

    s = sub.add_parser('rm', help='удалить сессию')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_rm)

    s = sub.add_parser('history', help='история сообщений')
    s.add_argument('session_id')
    s.add_argument('--limit', type=int, default=10)
    s.add_argument('--json', action='store_true')
    s.set_defaults(func=cmd_history)

    s = sub.add_parser('chat', help='отправить запрос и стримить ответ')
    s.add_argument('session_id')
    s.add_argument('text', nargs='*')
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser('retry', help='откатить последний ход и повторить запрос')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_retry)

    s = sub.add_parser('stop', help='остановить ответ')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser('cancel', help='откатить последнее сообщение')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_cancel)

    s = sub.add_parser('clear', help='очистить историю')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_clear)

    s = sub.add_parser('pin', help='прикрепить файлы/папки к сессии')
    s.add_argument('session_id')
    s.add_argument('paths', nargs='+')
    s.add_argument('--space', choices=('system', 'user'), default='user')
    s.set_defaults(func=cmd_pin)

    s = sub.add_parser('unpin', help='открепить файлы/папки')
    s.add_argument('session_id')
    s.add_argument('paths', nargs='+')
    s.set_defaults(func=cmd_unpin)

    s = sub.add_parser('pinned', help='список прикреплённого')
    s.add_argument('session_id')
    s.set_defaults(func=cmd_pinned)

    s = sub.add_parser('health', help='проверить API')
    s.set_defaults(func=cmd_health)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = Config.load()
    if getattr(args, 'url', None):
        cfg.set_base_url(args.url)
    client = SyncClient(cfg)
    if not getattr(args, 'func', None):
        repl()
        return
    try:
        args.func(client, cfg, args)
    except (ApiError, ConnectionFailed) as exc:
        err(error_text(exc))
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()

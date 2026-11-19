"""Общий клиент к API quick-agent.

Ядро: один транспортный слой и одна нормализация — для CLI и для Telegram.
Фронтенды (cli.py, tg.py) только рисуют события.
"""

from client.config import Config
from client.errors import ApiError, ConnectionFailed
from client.events import Event, SSEParser
from client.history import Item, normalize, normalize_all

__all__ = [
    'Config',
    'ApiError',
    'ConnectionFailed',
    'Event',
    'SSEParser',
    'Item',
    'normalize',
    'normalize_all',
]

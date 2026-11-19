from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from core.config import get_config

engine = create_async_engine(
    get_config().database_url,
    echo=False,
    connect_args={'timeout': 30},
)


@event.listens_for(engine.sync_engine, 'connect')
def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA busy_timeout=30000')
    cursor.close()


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from repositories.pinned_file_repository import PinnedFileRepository
from repositories.session_repository import SessionRepository


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._db: AsyncSession | None = None
        self.sessions: SessionRepository
        self.chat: ChatRepository
        self.messages: MessageRepository
        self.pinned_files: PinnedFileRepository

    async def __aenter__(self) -> 'UnitOfWork':
        self._db = self._session_factory()
        self.sessions = SessionRepository(self._db)
        self.chat = ChatRepository(self._db)
        self.messages = MessageRepository(self._db)
        self.pinned_files = PinnedFileRepository(self._db)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._db is not None
        try:
            if exc_type is None:
                await self._db.commit()
            else:
                await self._db.rollback()
        finally:
            await self._db.close()
            self._db = None

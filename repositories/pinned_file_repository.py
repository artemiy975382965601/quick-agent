from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tables import PinnedFile


class PinnedFileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_paths(self, session_id: str, inject: str, content: str) -> list[str]:
        stmt = (
            select(PinnedFile.file)
            .where(PinnedFile.session_id == session_id)
            .where(PinnedFile.type_of_inject == inject)
            .where(PinnedFile.type_of_content == content)
        )
        return list((await self._db.scalars(stmt)).all())

    async def list_all(self, session_id: str) -> list[PinnedFile]:
        stmt = (
            select(PinnedFile)
            .where(PinnedFile.session_id == session_id)
            .order_by(PinnedFile.id)
        )
        return list((await self._db.scalars(stmt)).all())

    async def add(self, session_id: str, path: str, inject: str, content: str) -> PinnedFile:
        row = PinnedFile(
            session_id=session_id,
            file=path,
            type_of_inject=inject,
            type_of_content=content,
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def delete_by_path(self, session_id: str, path: str) -> bool:
        stmt = (
            select(PinnedFile)
            .where(PinnedFile.session_id == session_id)
            .where(PinnedFile.file == path)
        )
        row = await self._db.scalar(stmt)
        if row is None:
            return False
        await self._db.delete(row)
        await self._db.flush()
        return True

import os

from core.exceptions import NotFoundError
from core.uow import UnitOfWork
from schemas import PinnedFileCreate, PinnedFileGet, PinResult, UnpinResult


class PinnedFileService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def _ensure_session(self, session_id: str) -> None:
        if not await self.uow.sessions.exists(session_id):
            raise NotFoundError('session not found')

    async def list(self, session_id: str) -> list[PinnedFileGet]:
        await self._ensure_session(session_id)
        rows = await self.uow.pinned_files.list_all(session_id)
        return [PinnedFileGet.model_validate(r) for r in rows]

    async def pin(self, session_id: str, payload: PinnedFileCreate) -> PinResult:
        await self._ensure_session(session_id)
        results = []
        for path in payload.full_paths:
            if os.path.isfile(path):
                content_type = 'file'
            elif os.path.isdir(path):
                content_type = 'folder'
            else:
                results.append(f'{path}: path is not founded')
                continue
            await self.uow.pinned_files.add(
                session_id,
                path,
                payload.space_for_insert,
                content_type,
            )
            results.append(f'{path}: was pinned')
        return PinResult(results=results)

    async def unpin(self, session_id: str, full_paths: list[str]) -> UnpinResult:
        await self._ensure_session(session_id)
        results = []
        for path in full_paths:
            if await self.uow.pinned_files.delete_by_path(session_id, path):
                results.append(f'{path}: was unpinned')
            else:
                results.append(f'{path}: path is not founded')
        return UnpinResult(results=results)

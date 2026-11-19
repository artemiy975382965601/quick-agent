from fastapi import APIRouter

from api.deps import PinnedFileServiceDep
from schemas import PinnedFileCreate, PinnedFileGet, PinResult, UnpinRequest, UnpinResult

router = APIRouter(prefix='/sessions/{session_id}/pinned')


@router.get('/', response_model=list[PinnedFileGet])
async def list_pinned(session_id: str, service: PinnedFileServiceDep):
    return await service.list(session_id)


@router.post('/', response_model=PinResult)
async def pin(session_id: str, payload: PinnedFileCreate, service: PinnedFileServiceDep):
    return await service.pin(session_id, payload)


@router.delete('/', response_model=UnpinResult)
async def unpin(session_id: str, payload: UnpinRequest, service: PinnedFileServiceDep):
    return await service.unpin(session_id, payload.full_paths)

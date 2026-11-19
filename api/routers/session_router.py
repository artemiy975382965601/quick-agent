from fastapi import APIRouter

from api.deps import AgentDep, SessionServiceDep
from schemas import SessionCreate, SessionOut, SessionPut

router = APIRouter(prefix='/sessions')


@router.get('/list/', response_model=list[SessionOut])
async def list_session(service: SessionServiceDep):
    return await service.list()


@router.get('/{session_id}/', response_model=SessionOut)
async def get_session(session_id: str, service: SessionServiceDep):
    return await service.get(session_id)


@router.post('/create/', status_code=201, response_model=SessionOut)
async def create_session(payload: SessionCreate, service: SessionServiceDep):
    return await service.create(payload)


@router.put('/{session_id}/', response_model=SessionOut)
async def put_session(session_id: str, payload: SessionPut, service: SessionServiceDep):
    return await service.update(session_id, payload)


@router.delete('/{session_id}/', status_code=204)
async def delete_session(session_id: str, service: SessionServiceDep, agent: AgentDep):
    await agent.stop(session_id)
    try:
        await service.delete(session_id)
    finally:
        await agent.delete(session_id)

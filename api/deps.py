from typing import Annotated, AsyncGenerator

from fastapi import Depends, Request

from agent.registry import AgentsRegistry
from core.config import ConfigDep
from core.database import async_session_factory
from core.uow import UnitOfWork
from services.chat_service import ChatService
from services.pinned_file_service import PinnedFileService
from services.session_service import SessionService


async def get_uow() -> AsyncGenerator[UnitOfWork, None]:
    async with UnitOfWork(async_session_factory) as uow:
        yield uow


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_agent(request: Request) -> AgentsRegistry:
    return request.app.state.agent


AgentDep = Annotated[AgentsRegistry, Depends(get_agent)]


def get_session_service(uow: UowDep, config: ConfigDep) -> SessionService:
    return SessionService(uow, config)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def get_chat_service(uow: UowDep, config: ConfigDep, agent: AgentDep) -> ChatService:
    return ChatService(uow, config, agent)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_pinned_file_service(uow: UowDep) -> PinnedFileService:
    return PinnedFileService(uow)


PinnedFileServiceDep = Annotated[PinnedFileService, Depends(get_pinned_file_service)]

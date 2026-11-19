from sqlalchemy.ext.asyncio import async_sessionmaker

from agent.context import AgentContext
from agent.session import AgentSession
from core.config import AppConfig
from core.uow import UnitOfWork


class AgentContextFactory:
    def __init__(self, session_factory: async_sessionmaker, config: AppConfig) -> None:
        self._session_factory = session_factory
        self._config = config

    def build(self, session_id: str, client_prompt_paths: tuple[str, ...] = ()) -> AgentContext:
        return AgentContext(
            session_id=session_id,
            config=self._config,
            uow=lambda: UnitOfWork(self._session_factory),
            client_prompt_paths=client_prompt_paths,
        )

    def session(self, session_id: str) -> AgentSession:
        return AgentSession(self._session_factory, session_id)

from dataclasses import dataclass
from typing import Callable

from core.config import AppConfig
from core.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class AgentContext:
    session_id: str
    config: AppConfig
    uow: Callable[[], UnitOfWork]
    client_prompt_paths: tuple[str, ...] = ()

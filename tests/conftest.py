from collections.abc import AsyncGenerator

import pytest
import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from agents.testing import ScriptedModel, function_call, assistant_message
from agent.registry import AgentsRegistry
from agent.context_factory import AgentContextFactory
from agents import RunConfig

from api.deps import get_uow, get_agent
from core.uow import UnitOfWork
from tables.base import Base
from tests.e2e.mock_tool import echo
from core.config import get_config



async def _create(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def db_engine():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    asyncio.run(_create(engine))
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture
def sessionmaker(db_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def uow(sessionmaker) -> AsyncGenerator[UnitOfWork, None]:
    async with UnitOfWork(sessionmaker) as unit:
        yield unit


@pytest.fixture
def app(sessionmaker) -> FastAPI:
    from main import app as fastapi_app

    async def override_get_uow() -> AsyncGenerator[UnitOfWork, None]:
        async with UnitOfWork(sessionmaker) as unit:
            yield unit

    fastapi_app.dependency_overrides[get_uow] = override_get_uow
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()

@pytest.fixture
def scripted_model():
    return ScriptedModel([
        [function_call("echo", {"text": "one"}, call_id="c1")],
        [assistant_message("done")],
    ])

@pytest.fixture
def client(sessionmaker, app, scripted_model):
    conf = get_config()
    run_config = RunConfig()

    registry = AgentsRegistry(
        config=conf,
        context_factory=AgentContextFactory(sessionmaker, conf),
        tools=[echo],
        mcp_servers=[],
        instructions='test',
        run_config=run_config,
        model=scripted_model
    )

    app.dependency_overrides[get_agent] = lambda: registry
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
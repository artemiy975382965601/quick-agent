from api.handlers import register_exception_handlers
from api.routers.session_router import router as session_router
from api.routers.chat_router import router as chat_router
from api.routers.pinned_router import router as pinned_router
from api.routers.health_router import router as health_router
from fastapi import FastAPI
import logging
from contextlib import asynccontextmanager
from agent.context_factory import AgentContextFactory
from core.database import engine, async_session_factory
from agent.registry import AgentsRegistry
from core.config import get_config
from tools import local_tools_list
from agent.mcp_loader import load_mcp_list
from agents.mcp import MCPServerManager
from agent.prompts.filters import UserPinnedFilesFilter, make_system
from agents import RunConfig

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conf = get_config()
    run_config = RunConfig(call_model_input_filter=UserPinnedFilesFilter())

    async with MCPServerManager(load_mcp_list(conf), strict=True) as manager:
        app.state.agent = AgentsRegistry(
            config=conf,
            context_factory=AgentContextFactory(async_session_factory, conf),
            tools=local_tools_list,
            mcp_servers=manager.active_servers,
            instructions=make_system,
            run_config=run_config
        )

        yield

        await app.state.agent.close()

    await engine.dispose()

app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)

app.include_router(session_router)
app.include_router(chat_router)
app.include_router(pinned_router)
app.include_router(health_router)

from crud import router as crud_router
from chat import router as chat_router
from fastapi import FastAPI
import httpx
from contextlib import asynccontextmanager
from database import engine, async_session_factory, SessionDep
from tables import Base
from agents_registry import AgentsRegistry
from config import get_config
from local_tools import local_tools_list
from mcp_load import load_mcp_list
from agents.mcp import MCPServerManager
from system_load import make_system
from user_loader import UserPinnedFilesFilter
from agents import RunConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    conf = get_config()
    run_config = RunConfig(call_model_input_filter=UserPinnedFilesFilter())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with MCPServerManager(load_mcp_list(conf), strict=True) as manager:
        app.state.agent = AgentsRegistry(
            config=conf,
            async_session_factory=async_session_factory, 
            tools=local_tools_list,
            mcp_servers=manager.active_servers,
            instructions=make_system,
            run_config=run_config
        )

        yield

    
    await engine.dispose()

app = FastAPI(lifespan=lifespan)


app.include_router(crud_router)
app.include_router(chat_router)

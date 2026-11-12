from crud import router as crud_router
from chat import router as chat_router
from fastapi import FastAPI
import httpx
from contextlib import asynccontextmanager
from database import engine, async_session_factory, SessionDep
from tables import Base
from agents_registry import AgentsRegistry
from config import get_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.agent = AgentsRegistry(config=get_config(), async_session_factory=async_session_factory)

    yield

    
    await engine.dispose()

app = FastAPI(lifespan=lifespan)


app.include_router(crud_router)
app.include_router(chat_router)

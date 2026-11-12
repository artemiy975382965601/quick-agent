from crud import router as crud_router
from fastapi import FastAPI
import httpx
from contextlib import asynccontextmanager
from core.database import engine, get_db, SessionDep
from tables import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await app.state.http_client.aclose()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)


app.include_router(crud_router)

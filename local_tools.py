from sqlalchemy import select, delete
from agents import function_tool, RunContextWrapper
from tables import PinnedFile
import os


@function_tool
async def pin_files(ctx: RunContextWrapper[dict], full_paths: list[str]) -> str:
    """
    Прикрепляет файлы. Возвращает отчет, удалось ли прикрепление или нет.
    """
    parts = []
    async with ctx.context['async_session_factory']() as session:
        for path in full_paths:
            if os.path.isfile(path):
                session.add(PinnedFile(
                    session_id=ctx.context['session_id'],
                    file=path,
                ))
                parts.append(f"{path}: was pinned")
            else:
                parts.append(f"{path}: path is not founded")
        await session.commit()
    return "\n".join(parts)


@function_tool
async def unpin_files(ctx: RunContextWrapper[dict], full_paths: list[str]) -> str:
    """
    Открепляет файлы. Возвращает отчет, удалось ли открепление или нет.
    """
    parts = []
    async with ctx.context['async_session_factory']() as session:
        for path in full_paths:
            stmt = (
                select(PinnedFile)
                .where(PinnedFile.session_id == ctx.context['session_id'])
                .where(PinnedFile.file == path)
            )
            res = await session.scalar(stmt)
            if res is not None:
                await session.delete(res)
                parts.append(f"{path}: was unpinned")
            else:
                parts.append(f"{path}: path is not founded")
        await session.commit()
    return "\n".join(parts)


local_tools_list = [unpin_files, pin_files]
import aiofiles
from sqlalchemy import select
from tables import PinnedFile

async def make_system(ctx, agent):
    async with ctx.context['async_session_factory']() as session:
        stmt = (
            select(PinnedFile.file)
            .where(PinnedFile.session_id == ctx.context['session_id'])
        )
        pinned_files = await session.scalars(stmt)
    res = 'Ты ии агент, у тебя есть инструмент, который имеет возможность прикреплять и откреплять файлы. Эти файлы прикрепляются у тебя в системном промпте списком из их пути их содержания, и при изменении файла ты увидишь изменения в системном промпте сразу. В них могут лежать либо твои инструкции, либо файлы, над которыми ты работаешь.'
    for i in pinned_files:
        res += i
        res += '\n'
        try:
            async with aiofiles.open(i, mode='r', encoding='utf8') as f:
                res += await f.read()
        except FileNotFoundError as e:
            res += 'FileNotFoundError'
        res += '\n\n'
    print(res)
    return res
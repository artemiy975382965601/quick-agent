import aiofiles
from sqlalchemy import select
from tables import PinnedFile
from files_loader import get_files

async def make_system(ctx, agent):
    async with ctx.context['async_session_factory']() as session:
        stmt = (
            select(PinnedFile.file)
            .where(PinnedFile.session_id == ctx.context['session_id'])
            .where(PinnedFile.type_of_inject == 'system')
        )
        pinned_files = await session.scalars(stmt)
    res = 'Ты ии агент, у тебя есть инструмент, который имеет возможность прикреплять и откреплять файлы. Эти файлы прикрепляются у тебя в системном промпте или к последнему user сообщению списком из их пути их содержания, и при изменении файла ты увидишь изменения в промпте сразу. В них могут лежать либо твои инструкции(system), либо файлы, над которыми ты работаешь(user).'
    res += await get_files(pinned_files)
    print(res)
    return res
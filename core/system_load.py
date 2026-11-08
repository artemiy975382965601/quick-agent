import aiofiles

async def make_system(ctx, agent):
    res = ''
    for i in ctx.context.pinned_files:
        res += i
        res += '\n'
        try:
            async with aiofiles.open(i, mode='r', encoding='utf8') as f:
                i += f
        except FileNotFoundError as e:
            res += 'FileNotFoundError'
        res += '\n\n'

    return res
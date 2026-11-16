import aiofiles

async def get_files(pinned_files):
    res = ''
    for i in pinned_files:
        res += i
        res += '\n'
        try:
            async with aiofiles.open(i, mode='r', encoding='utf8') as f:
                res += await f.read()
        except FileNotFoundError as e:
            res += 'FileNotFoundError'
        res += '\n\n'
    return res
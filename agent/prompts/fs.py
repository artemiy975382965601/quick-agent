import asyncio
import os

import aiofiles
import pathspec

from agent.prompts.content import FileContent, FolderContent

DEFAULT_MAX_FILE_SIZE = 256 * 1024
DEFAULT_MAX_WORKERS = 32


def _load_spec(dirpath: str, ignore_name: str) -> pathspec.PathSpec | None:
    p = os.path.join(dirpath, ignore_name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8-sig', errors='replace') as f:
        return pathspec.PathSpec.from_lines('gitignore', f)


def _is_ignored(rel: str, is_dir: bool, stack: list[tuple[str, pathspec.PathSpec]]) -> bool:
    ignored = False
    for prefix, spec in stack:
        if prefix:
            if not rel.startswith(prefix + '/'):
                continue
            sub = rel[len(prefix) + 1:]
        else:
            sub = rel
        if spec.match_file(sub) or (is_dir and spec.match_file(sub + '/')):
            ignored = True
    return ignored


async def _is_binary(path: str) -> bool:
    try:
        async with aiofiles.open(path, 'rb') as f:
            chunk = await f.read(8192)
    except OSError:
        return True
    return b'\x00' in chunk


async def _collect_path(
    path: str,
    paths: list[str],
    skip_binary: bool,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if skip_binary and await _is_binary(path):
            return
        paths.append(path)


async def _walk(
    dirpath: str,
    root: str,
    stack: list[tuple[str, pathspec.PathSpec]],
    paths: list[str],
    ignore_name: str,
    max_file_size: int | None,
    skip_binary: bool,
    semaphore: asyncio.Semaphore,
) -> None:
    spec = _load_spec(dirpath, ignore_name)
    if spec is not None:
        prefix = os.path.relpath(dirpath, root).replace(os.sep, '/')
        if prefix == '.':
            prefix = ''
        stack = stack + [(prefix, spec)]

    try:
        entries = list(os.scandir(dirpath))
    except OSError:
        return

    tasks = []
    for e in entries:
        if e.name == ignore_name:
            continue
        rel = os.path.relpath(e.path, root).replace(os.sep, '/')
        try:
            is_dir = e.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if _is_ignored(rel, is_dir, stack):
            continue
        if is_dir:
            tasks.append(_walk(e.path, root, stack, paths, ignore_name, max_file_size, skip_binary, semaphore))
        elif e.is_file(follow_symlinks=False):
            try:
                if max_file_size is not None and e.stat(follow_symlinks=False).st_size > max_file_size:
                    continue
            except OSError:
                continue
            tasks.append(_collect_path(e.path, paths, skip_binary, semaphore))

    if tasks:
        await asyncio.gather(*tasks)


async def collect_paths(
    root: str,
    ignore_name: str = '.qaignore',
    max_file_size: int | None = DEFAULT_MAX_FILE_SIZE,
    skip_binary: bool = True,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[str]:
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise NotADirectoryError(root)

    paths: list[str] = []
    semaphore = asyncio.Semaphore(max_workers)
    await _walk(root, root, [], paths, ignore_name, max_file_size, skip_binary, semaphore)
    return sorted(paths)


async def read_file(path: str) -> FileContent:
    try:
        async with aiofiles.open(path, mode='r', encoding='utf8') as f:
            return FileContent(path=path, content=await f.read())
    except FileNotFoundError:
        return FileContent(path=path, content='', error='FileNotFoundError')
    except (UnicodeDecodeError, OSError):
        return FileContent(path=path, content='', error='UnreadableFile')


async def read_files(paths: list[str]) -> list[FileContent]:
    return [await read_file(p) for p in paths]


async def read_folder(path: str) -> FolderContent:
    paths = await collect_paths(path)
    return FolderContent(path=path, files=await read_files(paths))

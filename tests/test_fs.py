import os

import pytest

from agent.prompts.fs import collect_paths, read_file, read_folder


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text('a', encoding='utf8')
    (tmp_path / 'b.txt').write_text('b', encoding='utf8')
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'c.py').write_text('c', encoding='utf8')
    return tmp_path


@pytest.mark.asyncio
async def test_collect_paths(tree):
    paths = await collect_paths(str(tree))
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ['a.py', 'b.txt', 'c.py']


@pytest.mark.asyncio
async def test_collect_paths_ignore(tree):
    (tree / '.qaignore').write_text('*.txt\n', encoding='utf8')
    paths = await collect_paths(str(tree))
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ['a.py', 'c.py']


@pytest.mark.asyncio
async def test_collect_paths_ignore_dir(tree):
    (tree / '.qaignore').write_text('sub/\n', encoding='utf8')
    paths = await collect_paths(str(tree))
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ['a.py', 'b.txt']


@pytest.mark.asyncio
async def test_collect_paths_max_size(tree):
    paths = await collect_paths(str(tree), max_file_size=0)
    assert paths == []


@pytest.mark.asyncio
async def test_collect_paths_not_a_dir(tmp_path):
    f = tmp_path / 'file.txt'
    f.write_text('x', encoding='utf8')
    with pytest.raises(NotADirectoryError):
        await collect_paths(str(f))


@pytest.mark.asyncio
async def test_read_file(tree):
    res = await read_file(str(tree / 'a.py'))
    assert res.content == 'a'
    assert res.error is None


@pytest.mark.asyncio
async def test_read_file_missing(tmp_path):
    res = await read_file(str(tmp_path / 'nope.py'))
    assert res.error == 'FileNotFoundError'


@pytest.mark.asyncio
async def test_read_folder(tree):
    res = await read_folder(str(tree))
    assert res.path == str(tree)
    assert len(res.files) == 3

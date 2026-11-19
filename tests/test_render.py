from agent.prompts.content import FileContent, FolderContent, PinnedContent, PromptParts
from agent.prompts.render import render_files, render_folders, render_pinned, render_system


def test_fields_collected_by_metaclass():
    assert FileContent.__fields__ == ('path', 'content', 'error')
    assert FolderContent.__fields__ == ('path', 'files')
    assert PinnedContent.__fields__ == ('files', 'folders')
    assert PromptParts.__fields__ == ('base', 'client', 'pinned')


def test_render_files():
    files = [FileContent(path='/a.py', content='x = 1')]
    assert render_files(files) == '=== /a.py ===\nx = 1\n=== end ==='


def test_render_files_with_error():
    files = [FileContent(path='/a.py', content='', error='FileNotFoundError')]
    assert render_files(files) == '=== /a.py ===\nFileNotFoundError\n=== end ==='


def test_render_folders():
    folder = FolderContent(
        path='/dir',
        files=[FileContent(path='/dir/a.py', content='x = 1')],
    )
    expected = (
        '=== folder: /dir ===\n'
        '--- /dir/a.py ---\nx = 1\n--- end ---\n'
        '=== end folder ==='
    )
    assert render_folders([folder]) == expected


def test_render_pinned_empty():
    assert render_pinned(PinnedContent()) == ''


def test_render_pinned_files_only():
    pinned = PinnedContent(files=[FileContent(path='/a.py', content='x')])
    assert render_pinned(pinned) == '[PINNED FILES]\n=== /a.py ===\nx\n=== end ==='


def test_render_pinned_both():
    pinned = PinnedContent(
        files=[FileContent(path='/a.py', content='x')],
        folders=[FolderContent(path='/dir', files=[FileContent(path='/dir/b.py', content='y')])],
    )
    out = render_pinned(pinned)
    assert out.startswith('[PINNED FILES]')
    assert '[PINNED FOLDERS]' in out
    assert out.index('[PINNED FILES]') < out.index('[PINNED FOLDERS]')


def test_render_system():
    parts = PromptParts(base='BASE', client='', pinned=PinnedContent())
    assert render_system(parts) == '[BASE SYSTEM]\nBASE'


def test_render_system_with_client():
    parts = PromptParts(base='BASE', client='CLIENT RULES', pinned=PinnedContent())
    out = render_system(parts)
    assert out == '[BASE SYSTEM]\nBASE\n\n[CLIENT]\nCLIENT RULES'


def test_render_system_client_before_pinned():
    parts = PromptParts(
        base='BASE',
        client='CLIENT RULES',
        pinned=PinnedContent(files=[FileContent(path='/a.py', content='x')]),
    )
    out = render_system(parts)
    assert out.index('[BASE SYSTEM]') < out.index('[CLIENT]') < out.index('[PINNED FILES]')


def test_render_system_empty_client_skipped():
    parts = PromptParts(base='BASE', client='', pinned=PinnedContent())
    assert '[CLIENT]' not in render_system(parts)


def test_render_system_with_pinned():
    parts = PromptParts(
        base='BASE',
        client='',
        pinned=PinnedContent(files=[FileContent(path='/a.py', content='x')]),
    )
    out = render_system(parts)
    assert out.startswith('[BASE SYSTEM]\nBASE')
    assert '[PINNED FILES]' in out


def test_is_empty():
    assert PinnedContent().is_empty()
    assert not PinnedContent(files=[FileContent(path='/a', content='')]).is_empty()

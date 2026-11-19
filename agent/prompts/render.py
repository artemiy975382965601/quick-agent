from agent.prompts.content import FileContent, FolderContent, PinnedContent, PromptParts

FILE_OPEN = '=== {path} ==='
FILE_CLOSE = '=== end ==='
NESTED_OPEN = '--- {path} ---'
NESTED_CLOSE = '--- end ---'
FOLDER_OPEN = '=== folder: {path} ==='
FOLDER_CLOSE = '=== end folder ==='


def _render_file(f: FileContent, open_tpl: str, close: str) -> str:
    body = f.content if f.error is None else f.error
    return f'{open_tpl.format(path=f.path)}\n{body}\n{close}'


def render_files(files: list[FileContent]) -> str:
    return '\n\n'.join(_render_file(f, FILE_OPEN, FILE_CLOSE) for f in files)


def render_folders(folders: list[FolderContent]) -> str:
    parts = []
    for folder in folders:
        inner = '\n\n'.join(_render_file(f, NESTED_OPEN, NESTED_CLOSE) for f in folder.files)
        parts.append(f'{FOLDER_OPEN.format(path=folder.path)}\n{inner}\n{FOLDER_CLOSE}')
    return '\n\n'.join(parts)


def render_pinned(pinned: PinnedContent) -> str:
    sections = []
    for name in pinned.__fields__:
        value = getattr(pinned, name)
        if not value:
            continue
        if name == 'files':
            sections.append('[PINNED FILES]\n' + render_files(value))
        elif name == 'folders':
            sections.append('[PINNED FOLDERS]\n' + render_folders(value))
    return '\n\n'.join(sections)


def render_system(parts: PromptParts) -> str:
    sections = []
    for name in parts.__fields__:
        value = getattr(parts, name)
        if name == 'base':
            sections.append('[BASE SYSTEM]\n' + value)
        elif name == 'client':
            if value:
                sections.append('[CLIENT]\n' + value)
        elif name == 'pinned':
            rendered = render_pinned(value)
            if rendered:
                sections.append(rendered)
    return '\n\n'.join(sections)

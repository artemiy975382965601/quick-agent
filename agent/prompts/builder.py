from core.config import AppConfig
from core.uow import UnitOfWork
from agent.prompts.content import PinnedContent, PromptParts
from agent.prompts.fs import read_file, read_files, read_folder
from agent.prompts.render import render_system, render_files

async def load_pinned(uow: UnitOfWork, session_id: str, inject: str) -> PinnedContent:
    file_paths = await uow.pinned_files.list_paths(session_id, inject, 'file')
    folder_paths = await uow.pinned_files.list_paths(session_id, inject, 'folder')
    return PinnedContent(
        files=await read_files(file_paths),
        folders=[await read_folder(p) for p in folder_paths],
    )


async def build_system(
    uow: UnitOfWork,
    session_id: str,
    config: AppConfig,
    client_prompt_paths: tuple[str, ...] = (),
) -> str:
    base = await read_file(config.base_prompt_path)
    client = await read_files(list(client_prompt_paths))
    pinned = await load_pinned(uow, session_id, 'system')
    return render_system(
        PromptParts(
            base=base.content if base.error is None else base.error,
            client=render_files(client) if client else '',
            pinned=pinned,
        )
    )


async def build_user(uow: UnitOfWork, session_id: str) -> PinnedContent:
    return await load_pinned(uow, session_id, 'user')

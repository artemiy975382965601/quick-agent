import os
from typing import Literal

from agents import RunContextWrapper, function_tool

from agent.context import AgentContext


@function_tool
async def pin_files(
    ctx: RunContextWrapper[AgentContext],
    full_paths: list[str],
    space_for_insert: Literal['system', 'user'],
) -> str:
    """
    Прикрепляет файлы и папки к контексту текущей сессии.

    Что прикрепляется:
    - файл — целиком, как есть;
    - папка — рекурсивно, все файлы внутри.

    Игнор: в корне папки можно положить .qaignore (синтаксис gitignore: venv/, __pycache__/, *.log, .env, *.db, отрицание через !). Игнорируемые файлы и папки не прикрепляются, игнорируемые папки не обходятся. Вложенные .qaignore действуют только на свою подпапку. Симлинки на папки не разворачиваются. Бинарные файлы и файлы больше 256 КБ пропускаются.

    Куда попадает (space_for_insert):
    - system — в системный промпт, после базового промпта. Сюда кладут инструкции, правила, шаблоны, описание проекта.
    - user — в конец последнего сообщения пользователя, под заголовком [PINNED FILES]. Сюда кладут файлы, над которыми идёт работа.

    Формат вставки: путь, затем содержимое файла. Содержимое перечитывается на каждом шаге модели, поэтому правки в файлах видны сразу, без повторного прикрепления.

    Тип (файл или папка) определяется по фактическому типу пути.

    Возвращает отчёт по каждому пути: was pinned или path is not founded.

    Не прикрепляй без необходимости, не прикрепляй секреты (.env, ключи, токены), не прикрепляй бинарники и большие файлы. Открепляй то, что больше не нужно.
    """
    parts = []
    async with ctx.context.uow() as uow:
        for path in full_paths:
            if os.path.isfile(path):
                await uow.pinned_files.add(ctx.context.session_id, path, space_for_insert, 'file')
                parts.append(f'{path}: was pinned')
            elif os.path.isdir(path):
                await uow.pinned_files.add(ctx.context.session_id, path, space_for_insert, 'folder')
                parts.append(f'{path}: was pinned')
            else:
                parts.append(f'{path}: path is not founded')
    return '\n'.join(parts)


@function_tool
async def unpin_files(ctx: RunContextWrapper[AgentContext], full_paths: list[str]) -> str:
    """
    Открепляет ранее прикреплённые файлы и папки по их путям.

    Путь должен совпадать с тем, что был передан в pin_files. Открепление папки убирает её целиком, отдельные файлы внутри откреплять не нужно.

    Возвращает отчёт по каждому пути: was unpinned или path is not founded.
    """
    parts = []
    async with ctx.context.uow() as uow:
        for path in full_paths:
            if await uow.pinned_files.delete_by_path(ctx.context.session_id, path):
                parts.append(f'{path}: was unpinned')
            else:
                parts.append(f'{path}: path is not founded')
    return '\n'.join(parts)

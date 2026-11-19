from __future__ import annotations

from dataclasses import dataclass

USER = 'user'
ASSISTANT = 'assistant'
TOOL_CALL = 'tool_call'
TOOL_RESULT = 'tool_result'


@dataclass(frozen=True, slots=True)
class Item:
    kind: str
    text: str = ''
    name: str = ''


def _content_text(content: object) -> str:
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get('text')
                if isinstance(text, str):
                    parts.append(text)
        return '\n'.join(parts)
    return str(content)


def normalize(item: object) -> Item | None:
    """Приводит сырой item из таблицы messages к одному из четырёх видов.

    В базе лежат не сообщения, а items OpenAI Responses: у них разный набор
    полей, у tool-вызовов вообще нет role. Всё, что не распознано, отбрасывается.
    """
    if not isinstance(item, dict):
        return None

    item_type = item.get('type')
    if item_type == 'function_call':
        return Item(TOOL_CALL, name=str(item.get('name') or 'tool'))
    if item_type == 'function_call_output':
        return Item(TOOL_RESULT, text=_content_text(item.get('output')))

    role = item.get('role')
    if role == USER:
        return Item(USER, text=_content_text(item.get('content')))
    if role == ASSISTANT:
        return Item(ASSISTANT, text=_content_text(item.get('content')))
    return None


def normalize_all(messages: object) -> list[Item]:
    if not isinstance(messages, list):
        return []
    items = (normalize(m) for m in messages)
    return [item for item in items if item is not None]


def chronological(items: list[Item]) -> list[Item]:
    """API отдаёт сообщения от новых к старым (курсор before_id идёт назад по id).
    Для показа нужен прямой порядок."""
    return list(reversed(items))

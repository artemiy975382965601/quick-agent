# client — общий клиент к API quick-agent

Одно ядро, два фронтенда. Ядро не зависит от UI: транспорт, разбор SSE,
нормализация истории, сессии, pin-файлы. Фронтенды только рисуют.

    client/
      config.py    адрес API, таймауты, текущие сессии, пути клиентских промптов
      api.py       эндпоинты: метод, путь, тело
      events.py    SSE-парсер и тип события
      history.py   нормализация items из таблицы messages
      sync.py      синхронный транспорт (stdlib) — для CLI
      aio.py       асинхронный транспорт (httpx) — для бота
      cli.py       REPL и подкоманды
      tg.py        Telegram-бот

Конфиг: `~/.config/quick-agent-client/config.json`.

## CLI

Из корня проекта (`~/dev/quick-agent`):

    ./venv/bin/python -m client.cli            # интерактивный режим
    ./venv/bin/python -m client.cli health
    ./venv/bin/python -m client.cli sessions
    ./venv/bin/python -m client.cli chat <id> "текст"

Подкоманды: `url`, `new`, `sessions`, `show`, `rename`, `rm`, `history`,
`chat`, `retry`, `stop`, `cancel`, `clear`, `pin`, `unpin`, `pinned`, `health`.

В REPL дополнительно: `/ls`, `/use N|id`, `/hist`, `/retry`, `/cancel`,
`/clear`, `/model`, `/pinned`, `/q`.

Вывод инструментов не печатается: видна только строка `⚙ имя_инструмента`.

## Telegram

    set -a; . ~/dev/quick-agent-tg/.env; set +a
    PYTHONPATH=~/dev/quick-agent ~/dev/quick-agent-tg/venv/bin/python -m client.tg

Нужны `BOT_TOKEN`, опционально `ALLOWED_USER_ID`, `BOT_PROXY`, `QUICK_AGENT_URL`.

Особенности:

- Никакого стриминга и редактирования сообщений. Ответ приходит отдельными
  сообщениями: текстовый блок → `⚙ имя_инструмента` → следующий текстовый блок.
  Граница блока — вызов инструмента или конец прогона. Вывод инструментов не
  показывается.
- Ответы уходят с `parse_mode=HTML`. Если Telegram отвечает ошибкой разбора,
  тот же текст уходит обычным (теги снимаются, сущности раскрываются).
- Длинный текст режется по строкам до 3900 символов на сообщение.
- `/use` показывает последние 10 сообщений выбранной сессии.

## Клиентские промпты

Клиент передаёт в `POST /chat/{id}/start` поле `client_prompt_paths`:

- терминал: `client_base`, `client_mode_terminal`
- Telegram: `client_base`, `client_mode_tg`

Файлы лежат в `/home/art-dev/prompts` (переопределяется `QUICK_AGENT_PROMPTS_DIR`
или ключом `prompt_paths` в конфиге). Порядок важен: `client_base` ссылается
на «следующий файл». Отсутствующие файлы клиент показывает предупреждением при
старте — сервер в этом случае кладёт в промпт строку `FileNotFoundError`.

## Повтор запроса

`/retry` (и `client.cli retry`) собирается на клиенте из двух вызовов:

1. `GET /chat/{id}/?limit=50` — берётся последний `user`-item, его текст и есть
   повторяемый запрос;
2. `POST /chat/{id}/cancel` — сервер удаляет последний ход целиком
   (`rollback_turn`: от последнего `user`-сообщения до конца);
3. `POST /chat/{id}/start` — тот же текст уходит заново с текущими клиентскими
   промптами.

Эндпоинта `/chat/{id}/retry` нет и не требуется. Если последнего user-сообщения
нет в истории, клиент пишет «в истории нет сообщения пользователя»; если прогон
ещё идёт, cancel вернёт 409.

## История

`GET /chat/{id}/` отдаёт items от новых к старым (курсор `before_id` идёт назад
по id). В базе лежат не сообщения, а items OpenAI Responses — четыре формы:

    {role: user|assistant, content: str | [{type: output_text, text}]}
    {type: function_call, name, arguments, call_id}
    {type: function_call_output, call_id, output: [{type: input_text, text}]}

`history.normalize` приводит их к `user | assistant | tool_call | tool_result`,
`history.chronological` разворачивает в прямой порядок для показа.

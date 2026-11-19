from dataclasses import dataclass
from typing import Any

from agents import Agent, Model, ModelSettings, OpenAIChatCompletionsModel, RunConfig, Runner
from agents.result import RunResultStreaming
from openai import AsyncOpenAI
import httpx

from agent.context_factory import AgentContextFactory
from agent.session import AgentSession
from core.config import AppConfig
from core.exceptions import ConflictError, ValidationError


@dataclass(slots=True)
class AgentEntry:
    agent: Agent
    session: AgentSession
    client: AsyncOpenAI
    alias: str
    stream: RunResultStreaming | None = None


class AgentsRegistry:
    def __init__(
        self,
        config: AppConfig,
        context_factory: AgentContextFactory,
        tools: list[Any],
        mcp_servers: list[Any],
        instructions: Any,
        run_config: RunConfig,
        model: Model | None = None,
    ) -> None:
        self.config = config
        self.context_factory = context_factory
        self.tools = tools
        self.mcp_servers = mcp_servers
        self.instructions = instructions
        self.run_config = run_config
        self.model = model
        self.entries: dict[str, AgentEntry] = {}

    def _make_client(self, alias: str) -> AsyncOpenAI:
        cfg = self.config.models[alias]
        return AsyncOpenAI(
            api_key=cfg.api_key.get_secret_value(),
            base_url=cfg.base_url,
            timeout=httpx.Timeout(300.0, connect=15.0),
            max_retries=2,
        )

    async def _resolve_alias(self, session: str) -> str:
        async with self.context_factory.build(session).uow() as uow:
            model_alias = await uow.sessions.get_model_alias(session)
        if model_alias is None:
            model_alias = self.config.default.model_alias
        if model_alias not in self.config.models:
            raise ValidationError(f'unknown model alias: {model_alias}')
        return model_alias

    async def _build_entry(self, session: str, alias: str) -> AgentEntry:
        cfg = self.config.models[alias]
        client = self._make_client(alias)
        agent = Agent(
            name=session,
            model=self.model if self.model is not None else OpenAIChatCompletionsModel(model=cfg.model, openai_client=client),
            model_settings=ModelSettings(**cfg.model_settings),
            instructions=self.instructions,
            tools=self.tools,
            mcp_servers=self.mcp_servers,
        )
        return AgentEntry(
            agent=agent,
            session=self.context_factory.session(session),
            client=client,
            alias=alias,
        )

    async def _get_entry(self, session: str) -> AgentEntry:
        alias = await self._resolve_alias(session)
        entry = self.entries.get(session)
        if entry is not None and entry.alias == alias:
            return entry
        if entry is not None:
            await self._close_entry(entry)
        entry = await self._build_entry(session, alias)
        self.entries[session] = entry
        return entry

    async def _close_entry(self, entry: AgentEntry) -> None:
        if entry.stream is not None:
            entry.stream.cancel()
            try:
                await entry.stream.wait_until_done()
            except Exception:
                pass
            entry.stream = None
        await entry.client.close()

    async def start(
        self,
        session: str,
        query: list[dict[str, Any]],
        client_prompt_paths: tuple[str, ...] = (),
    ) -> RunResultStreaming:
        entry = await self._get_entry(session)
        if entry.stream is not None:
            if not entry.stream.is_complete:
                raise ConflictError('stream is already running for this session')
            entry.stream = None

        entry.stream = Runner.run_streamed(
            entry.agent,
            query,
            context=self.context_factory.build(session, client_prompt_paths),
            session=entry.session,
            run_config=self.run_config,
            max_turns=self.config.run.max_turns,
        )
        return entry.stream

    async def stop(self, session: str) -> None:
        entry = self.entries.get(session)
        if entry is None or entry.stream is None:
            return
        stream = entry.stream
        entry.stream = None
        stream.cancel()
        try:
            await stream.wait_until_done()
        except Exception:
            pass

    def is_running(self, session: str) -> bool:
        entry = self.entries.get(session)
        return entry is not None and entry.stream is not None and not entry.stream.is_complete

    async def delete(self, session: str) -> None:
        entry = self.entries.pop(session, None)
        if entry is not None:
            await self._close_entry(entry)

    async def close(self) -> None:
        for session in list(self.entries):
            await self.delete(session)

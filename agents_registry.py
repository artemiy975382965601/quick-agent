from system_load import make_system
from agents import Agent, ModelSettings, Runner
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from db_session import DBSession


class AgentsRegistry:
    def __init__(self, config: dict, async_session_factory, tools: list, mcp_servers: list):
        self.async_session_factory = async_session_factory
        self.config = config
        self.agents_pool = {}
        self.session_pool = {}
        self.stream_pool = {}
        self.tools = tools
        self.mcp_servers = mcp_servers

    def start(self, session, query):
        a = self.agents_pool.get(session)
        if a is None:
            a = self.build(session)
            self.session_pool[session] = DBSession(session_id=session, async_session_factory=self.async_session_factory)

        s = Runner.run_streamed(a, query, context={'session_id': session, 'async_session_factory': self.async_session_factory}, session=self.session_pool[session])
        self.stream_pool[session] = s
        return s
        
    async def stop(self, session):
        await self.stream_pool[session].cancel()
    

    def build(self, session):
        cfg = self.config["models"]["deepseek"]
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        return Agent(
            name=session,
            model=OpenAIChatCompletionsModel(
                model=cfg["model"],
                openai_client=client,
            ),
            model_settings=cfg["model_settings"],
            instructions=make_system,
            tools=self.tools,
            mcp_servers=self.mcp_servers
        )

    def delete(self, session):
        self.session_pool.pop(session, None)
        self.agents_pool.pop(session, None)
        self.stream_pool.pop(session, None)

    async def mcp_health(self):
        async with MCPServerManager(self.servers, connect_in_parallel=True) as manager:
            return {
                'active_servers': [s.name for s in manager.active_servers],
                'failed_servers': [s.name for s in manager.failed_servers]
            }
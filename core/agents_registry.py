from core.system_load import make_system
from agents import Agent, ModelSettings, Runner
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

class AgentsRegistry:
    def __init__(self, config: dict):
        self.config = config
        self.agents_pool = {}
        self.stream_pool = {}

    def start(self, session, query):
        a = self.agents_pool.get(session)
        if a is None:
            a = self.build(session)

        s = Runner.run_streamed(a, query)
        self.stream_pool[session] = s
        return s
        
    async def stop(self, session):
        await self.agents_pool[session].cancel()
    

   

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
            instructions='Ты бесполезный агент.',
        )
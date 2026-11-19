from typing import Any

from agents import Agent, RunContextWrapper
from agents.run import CallModelData, ModelInputData

from agent.context import AgentContext
from agent.prompts.builder import build_system, build_user
from agent.prompts.render import render_pinned


async def make_system(ctx: RunContextWrapper[AgentContext], agent: Agent) -> str:
    async with ctx.context.uow() as uow:
        return await build_system(
            uow,
            ctx.context.session_id,
            ctx.context.config,
            ctx.context.client_prompt_paths,
        )


class UserPinnedFilesFilter:
    async def __call__(self, data: CallModelData[Any]) -> ModelInputData:
        ctx: AgentContext = data.context
        original_input = data.model_data.input
        original_instructions = data.model_data.instructions

        async with ctx.uow() as uow:
            pinned = await build_user(uow, ctx.session_id)

        if pinned.is_empty():
            return ModelInputData(input=original_input, instructions=original_instructions)

        rendered = render_pinned(pinned)
        new_input = list(original_input)
        for i in range(len(new_input) - 1, -1, -1):
            item = new_input[i]
            if isinstance(item, dict) and item.get('role') == 'user':
                text = item.get('content', '')
                if isinstance(text, str):
                    new_input[i] = {**item, 'content': text + '\n\n' + rendered}
                break

        return ModelInputData(input=new_input, instructions=original_instructions)

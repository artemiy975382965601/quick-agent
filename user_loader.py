from typing import Any
from agents import RunConfig, Runner
from agents.run import CallModelData, ModelInputData
from agents.items import TResponseInputItem
from files_loader import get_files
from sqlalchemy import select
from tables import PinnedFile

class UserPinnedFilesFilter:

    async def __call__(self, data: CallModelData[Any]) -> ModelInputData:
        ctx = data.context 

        original_input = data.model_data.input
        original_instructions = data.model_data.instructions
        async with ctx['async_session_factory']() as session:
            stmt = (
                select(PinnedFile.file)
                .where(PinnedFile.session_id == ctx['session_id'])
                .where(PinnedFile.type_of_inject == 'user')
            )
            pinned_files = await session.scalars(stmt)
        files_content = await get_files(pinned_files)  
        if not files_content:
            return ModelInputData(input=original_input, instructions=original_instructions)

        new_input = list(original_input)
        for i in range(len(new_input) - 1, -1, -1):
            item = new_input[i]
            if isinstance(item, dict) and item.get("role") == "user":
                original_text = item.get("content", "")
                if isinstance(original_text, str):
                    new_input[i] = {
                        **item,
                        "content": original_text + "\n\n--- PINNED FILES ---\n" + files_content,
                    }
                break

        return ModelInputData(input=new_input, instructions=original_instructions)
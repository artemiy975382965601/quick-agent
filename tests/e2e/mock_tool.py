from agents import function_tool


@function_tool
async def echo(
    text: str,
) -> str:
    return text


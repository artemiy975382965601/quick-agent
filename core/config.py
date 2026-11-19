import json
import os
from functools import lru_cache
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import Depends
from pydantic import BaseModel, Field, SecretStr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
ENV_PATH = os.path.join(BASE_DIR, '.env')

PLACEHOLDER_PREFIX = '${'
PLACEHOLDER_SUFFIX = '}'


class ModelConfig(BaseModel):
    api_key: SecretStr
    base_url: str
    model: str
    model_settings: dict = Field(default_factory=dict)


class DefaultConfig(BaseModel):
    model_alias: str
    title: str


class RunSettings(BaseModel):
    max_turns: int = 30


class McpServerConfig(BaseModel):
    transport: Literal['stdio', 'streamable_http', 'sse']
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None
    headers: dict[str, str] | None = None
    cache_tools_list: bool = True
    tool_filter: list[str] | None = None
    require_approval: str = 'never'


class AppConfig(BaseModel):
    models: dict[str, ModelConfig]
    default: DefaultConfig
    run: RunSettings = Field(default_factory=RunSettings)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    base_prompt_path: str
    database_url: str
    database_sync_url: str


def _substitute(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v) for v in value]
    if (
        isinstance(value, str)
        and value.startswith(PLACEHOLDER_PREFIX)
        and value.endswith(PLACEHOLDER_SUFFIX)
    ):
        name = value[len(PLACEHOLDER_PREFIX):-len(PLACEHOLDER_SUFFIX)]
        resolved = os.environ.get(name)
        if resolved is None:
            raise RuntimeError(f'config placeholder {value} is not set in environment')
        return resolved
    return value


@lru_cache
def get_config() -> AppConfig:
    load_dotenv(ENV_PATH)
    with open(CONFIG_PATH, encoding='utf8') as f:
        raw = json.load(f)
    return AppConfig.model_validate(_substitute(raw))


ConfigDep = Annotated[AppConfig, Depends(get_config)]

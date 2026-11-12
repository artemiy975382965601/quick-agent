import json
from functools import lru_cache
from typing import Annotated
from fastapi import Depends


@lru_cache
def get_config():
    return json.load(open('config.json'))


ConfigDep = Annotated[dict, Depends(get_config)]
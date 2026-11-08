from core.agents_registry import AgentsRegistry
import json
import asyncio

a = AgentsRegistry(json.load(open('config.json')))
async def main():
    while True:
        res = a.start('1', input('query: '))
        async for i in res.stream_events():
            print(i)

asyncio.run(main())
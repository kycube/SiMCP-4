"""Live test 2: the server over MCP stdio, as an agent uses it (needs SimCity 4; starts it or attaches).

    python live/t2_stdio.py

Runs: guide, game_launch, game_status, list_regions, load_region("Timbuktu"), load_city of a founded tutorial
city, city_status, leave_city, load_region("MCP Test"), load_city of an unfounded small tile, city_status,
leave_city. Prints every result.
"""
import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CALLS = [
    ("guide", {"topic": "start"}),
    ("game_launch", {}),
    ("game_status", {}),
    ("list_regions", {}),
    ("load_region", {"name": "Timbuktu"}),
    ("load_city", {"name": "Making Money Tutorial"}),
    ("city_status", {}),
    ("leave_city", {}),
    ("load_region", {"name": "MCP Test"}),
    ("load_city", {"size": "small"}),
    ("city_status", {}),
    ("leave_city", {}),
]


async def run():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONIOENCODING="utf-8")
    params = StdioServerParameters(command=sys.executable, args=["-m", "sc4_mcp"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for name, args in CALLS:
                t0 = time.time()
                res = await s.call_tool(name, args)
                text = res.content[0].text if res.content else ""
                if name == "list_regions":
                    d = json.loads(text)
                    text = json.dumps([(x["folder"], len(x["tiles"]),
                                        [c["name"] for c in x["cities"] if c.get("established")])
                                       for x in d["regions"]])
                print("%-12s %5.1fs %s %s" % (name, time.time() - t0, "ERROR" if res.isError else "ok",
                                               text[:400].replace("\n", " ")))


if __name__ == "__main__":
    asyncio.run(run())

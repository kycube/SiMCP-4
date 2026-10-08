"""The MCP server: every tool is registered with a full JSON schema and annotations, the generated tool reference is
current, and the server answers over the MCP stdio protocol (no game needed for these calls)."""
import asyncio
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tool_docs_current():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "gen_tool_docs.py"), "--check"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


def test_stdio_handshake():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        env = dict(os.environ, PYTHONPATH=ROOT, PYTHONIOENCODING="utf-8")
        params = StdioServerParameters(command=sys.executable, args=["-m", "sc4_mcp"], env=env)
        async with stdio_client(params, errlog=open(os.devnull, "w")) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = (await s.list_tools()).tools
                guide = await s.call_tool("guide", {"topic": "all"})
                return init, tools, guide

    init, tools, guide = asyncio.run(run())
    assert init.serverInfo.name == "simcity4"
    assert {"guide", "game_launch", "game_status", "list_regions", "quit_game"} <= {t.name for t in tools}
    for t in tools:
        assert t.description and t.inputSchema.get("type") == "object", t.name
        assert "$ref" not in json.dumps(t.inputSchema), t.name
        assert t.annotations is not None, t.name
    assert not guide.isError and "game_launch" in guide.content[0].text

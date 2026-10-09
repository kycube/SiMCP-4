# Using SiMCP 4 from an MCP client

SiMCP 4 is a stdio MCP server: the client starts `simcp4` (or `python -m sc4_mcp`) and talks to it over
stdin / stdout. Many tools wait for the game (starting it, loading a region, running the simulation), so give the
client a tool timeout of a few minutes.

- **Claude Code**: `claude mcp add simcp4 -- simcp4`
- **Claude Desktop**: add the entry in `claude_desktop_config.json` (this folder) to the `mcpServers` of your own
  config (Settings, Developer, Edit Config) and restart the app.
- **Any other client**: command `simcp4`, no arguments; or `python -m sc4_mcp --transport streamable-http --port 8766`
  for HTTP at `http://localhost:8766/mcp`.

Then ask the agent to call `setup_check`, then `guide`, then `game_launch`.

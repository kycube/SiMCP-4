# Contributing to SiMCP 4

Thanks for helping. A few rules keep the servers useful to any agent and honest about the game.

## Ground rules

- **The game's own code, the game's own rules.** Tools act through the game's own commands and functions and read
  state from memory; they never write memory values to gain an advantage. If the game doesn't offer something,
  there is no tool for it. Cheats exist only as an explicit, tracked tool.
- **Any client, any model.** Every tool is fully described in its JSON schema (every parameter documented), carries
  the standard MCP annotations and reports failures as tool errors with a JSON `{error, hint}`. No vendor-specific
  wording in tool text.
- **No game files in the repository.** No binaries, dumps, textures, models, saved cities or config logs (saved
  cities and the game's config log carry the Windows user name). Reverse-engineering findings go in
  `re/agents/*/REPORT.md` and `notes/`, with addresses and how they were verified.
- **Respect the community's licences.** Interface layouts, ids and addresses are facts and may be restated; code
  from LGPL/GPL projects is not copied into this MIT repository. MIT/Apache-2.0 code may be included with its notice.
- **Verify live.** A tool or recipe is done when it has worked against the running game; note what was checked in
  `notes/LIVE_FACTS.md`.

## Before a pull request

```bash
python -m pip install -e ".[test]"
python -m pytest
```

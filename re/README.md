# Reverse-engineering notes

How SimCity 4 1.1.641 is understood well enough to drive it through its own code.

- `agents/<topic>/REPORT.md`: static-analysis reports, one per subsystem (so far `framework`, `app-city`,
  `commands`, `time`), written from the GOG binary following `notes/RE_BRIEF.md`, with addresses as VAs of `SimCity 4.exe` (base 0x400000, never relocated)
  and a confidence (CONFIRMED / LIKELY / GUESS). The plan is `notes/STATIC_PLAN.md`. Findings are then tested in
  the running game; `notes/LIVE_FACTS.md` records what was verified and how, and wins where they disagree.
- `pe.py`: a small PE/x86 helper (load the exe, disassemble with capstone, cross-references, an indexed call
  graph, strings, vtables, function starts).
- `dbpf_inventory.py`: an inventory of every DBPF file of the game (and optionally a Plugins folder): record
  types, exemplars, texts, Lua scripts, UI layouts, INI files. Output goes to a folder you name (keep it out of
  the repository: it is game content).

Nothing here contains game code or data; you need your own copy of SimCity 4 Deluxe to reproduce it.

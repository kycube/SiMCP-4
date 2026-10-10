# Static analysis of SimCity 4: rules and references (SiMCP 4)

I reverse engineered **SimCity 4 Deluxe 1.1.641** (GOG digital release, `Apps\SimCity 4.exe`) so an MCP server can
drive the game through its own code. The static part went one subsystem at a time (the topics in
`STATIC_PLAN.md`), each ending in a short report in `re/reports/<topic>/REPORT.md`. These are the rules I kept to
and the references I worked from.

## Rules

1. **Static only.** No launching the game, attaching to, reading or writing a running `SimCity 4.exe`, running
   anything in `live\`, importing `sc4_mcp` modules that talk to the game, or using Cheat Engine. Everything
   static was checked in the running game afterwards (`LIVE_FACTS.md`).
2. Everything in the game folder (`C:\Program Files\GOG Galaxy\Games\SimCity 4 Deluxe Edition`), my
   `Documents\SimCity 4` (Plugins, Regions) and `%APPDATA%\io.github.memo33` stays **read-only**.
   `sc4pac-profiles.json` is never opened (it holds a sign-in token).
3. Scratch files go in the workbench (`<workbench>\re\<topic>\`), never in the repository; a topic's finished
   report is saved as `re/reports/<topic>/REPORT.md`.
4. Python 3.13 with pefile, capstone and numpy (not `-I`; `PYTHONIOENCODING=utf-8`; no script named `dis.py`). No
   Ghidra or IDA.
5. Copyright: the community sources below are references. The reports quote names, ids, vtable slot orders and
   addresses, never their code.

## Tools and references

- `<repo>\re\pe.py`: `Image()` loads the exe (or `Image(path)` a plugin DLL). `dis(va, n, stop_at_ret)`,
  `around(va)`, `func_start(va)` (nearest call target / vtable slot at or before va), `xrefs(va)` (code whose
  imm/disp32 == va), `data_refs(va)` (dwords in data == va, e.g. vtable slots), `calls_to(fn)` (fast, indexed),
  `find_str(s, wide)`, `strings()`, `vtable(va)` -> [(slot, fn, nargs)], `vtable_starts()` ->
  {vtable: [ctor sites]}, `stack_args(fn)`, `follow_jmp`, `cstr`, `wstr`, `u32`, `imports`, `exports`.
- `<workbench>\sources\` (shallow clones):
  - `gzcom-dll\gzcom-dll\include\`: 202 interface headers (`cIGZ*` framework, `cISC4*` game: app, city, every
    simulator and manager, lots, occupants, networks, view, region, advisors, disasters, Lua...). Their method
    order comes from the Mac build's vtables - **check every slot against 1.1.641** before relying on it.
  - `sc4-gzids\allGZIDs.h`: class ids, interface ids, message ids, type ids.
  - `sc4-game-command-documentation\`: the game's command system (192 commands with parameters).
  - DLL sources that patch or call 1.1.641 at fixed addresses: `sc4fix`, `nam-dll`, `sc4-dbpf-loading`,
    `sc4-query-ui-hooks`, `sc4-resource-loading-hooks`, `sc4-lua-extensions`, `sc4-custom-budget-departments`,
    `sc4-custom-ordinance-host`, `sc4-advanced-water-management`, `sc4-legalize-gambling-ordinance-upgrade`,
    `transparent-texture-fix-dll`, `sc4-lua-sandbox-dll`, `sc4-dll-utilities`, `sc4-gzcom-dll-template`. Grep them
    for `0x00` addresses: each one is a 1.1.641 function or patch site somebody verified.
- `<workbench>\ghidra\` - Maxis' own names, decoded from the Mac build's Ghidra archive (`sc4-ghidra-symbols`,
  Apache-2.0): `vftables.txt` (357 vtables, one line per slot with the method name and, where known, its
  signature; mangled names demangled), `classes.txt` (449 class/struct layouts), `types.json` (everything),
  `validation.txt` (comparison with gzcom-dll: 84 interfaces identical, 62 cosmetic differences, 35 structural).
  Caveats: GCC puts two destructor slots where MSVC has one; MSVC groups overloaded virtuals in **reverse**
  declaration order (GCC keeps declaration order), so overloads (`X1`/`X2` in the archive) may be swapped on
  Windows; Mac struct offsets differ (PowerPC Darwin `bool` is 4 bytes, other alignment) - use them for names
  and field order, then find the Windows offsets in the code.
- `<workbench>\inventory\game\`: `exemplars.jsonl` (every exemplar: TGI, parent, type 0x10, name 0x20, all
  properties), `ltext.jsonl` (every game string with its TGI), `lua\` (every Lua script), `type0\` (UI layouts with
  window/button ids - group 0x96A006B0 - and the INI files - group 0x8A5971C5), `types.json`, `summary.txt`.
- `<repo>\notes\PHASE0.md`, `DATA_INVENTORY.md`, `LIVE_FACTS.md` (facts measured in the running game - **the most
  important input**; where static analysis disagrees with it, it wins).

## Binary facts

- One executable, preferred base **0x400000, never relocated**; all game code is in it (no game DLLs; the DLLs in
  Plugins are third-party). Addresses are plain VAs (`0x5C45A0`), "SC4" where ambiguous; plugin DLL addresses as
  `NAM.dll 0x1000xxxx` (preferred base).
- MSVC 7.x, STLport containers (`_STL::`), `thiscall` (this in ecx, callee pops), bool in AL, `__stdcall` COM
  style for some interfaces. **No RTTI** for game classes (only ~60 exception/STL type descriptors). Many functions
  have no `push ebp` frame: use `func_start()` and `calls_to()`. SEH frames: `push -1; push handler; mov eax,
  fs:[0]`.
- GZCOM: every interface derives from `cIGZUnknown` (slot 0 QueryInterface(iid, void**), 1 AddRef, 2 Release).
  `QueryInterface` implementations compare the iid argument against constants - that tells which interfaces a
  class implements; match the constants with `sc4-gzids`. Components are created by class id through the COM
  object (`RZGetFramework()` / `GZCOM()->GetClassObject(clsid, iid, void**)`), and plugin DLLs export
  `GZDllGetGZCOMDirector` (the loader references that string at 0x87BA7E's function).
- Messages: `cIGZMessageServer2` broadcasts typed messages (ids in `sc4-gzids`, e.g. city init/shutdown, new day /
  month). A director subscribes with `AddNotification(target, msgType)`.
- Command server: command names (`PlaceLot` string at 0xAA17E0 is used in 0x5C45A0's function) map to command ids;
  each command class parses a parameter string.

## How the findings are used

A GZCOM plugin DLL (the bridge) runs inside the game: it gets the framework and `cISC4App` at start-up, can
subscribe to messages, run game commands, call any interface method or function on the main thread under SEH,
and read memory. The Python server outside reads memory directly and asks the bridge to act. The best recipes are
interface-based: "get `cISC4App` (GZIID 0x26CE01C0) -> `GetCity()` (slot N) -> `GetBudgetSimulator()` (slot M) ->
method slot K (args) returns ...; it charges funds / opens a dialog / needs Z first". Raw addresses are the
fallback, always with the function's purpose and calling convention.

Honest play: every action recipe notes whether it goes through the same checks and costs as the player's own tool
or menu (and if not, it becomes a cheat-class tool).

## Report format

At most **150 lines** per topic:
1. Answers to the topic's numbered questions (`STATIC_PLAN.md`), each with exact addresses / interface slots and
   the evidence (string xref, call pattern, QueryInterface constant, data table, a community DLL that uses it) and
   a confidence (CONFIRMED by code / LIKELY / GUESS).
2. Object layouts established (offset, type, meaning).
3. Concrete recipes for the bridge (interface or function, convention, this, args, return, side effects, thread).
4. Open questions that need a live test, phrased as a test ("read X before/after placing a road").

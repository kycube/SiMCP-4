# Facts measured in the running game

Heap addresses change per run; code addresses do not (the exe is never relocated). Each entry says how it was
verified. Where a static report disagrees with this file, this file wins.

## Session 2026-10-08 (Phase 0: one windowed run, no bridge)

- **Unelevated launch through a junction** works: `%LOCALAPPDATA%\SiMCP-4\game` -> the GOG folder, game started
  as `<junction>\Apps\SimCity 4.exe -CPUCount:1 -w -intro:off -CustomResolution:enabled -r1024x768x32`, cwd
  `<junction>\Apps`, `__COMPAT_LAYER=HIGHDPIAWARE`. Verified: no error 740, the process opened for reading by a
  normal-user process, region view shown. (Through the real path every launch fails with error 740 because of
  GOG's WINXPSP3 layer; see PHASE0.md.)
- Main window: class `GDriverClass--DirectX`, title `SC4Fix r7`, client 1024x768 (Win32 client rect). Other windows
  of the process: `Win32ClipboardSupportClass` (hidden), IME windows.
- Start-up to the region view (Timbuktu, from the .cfg) in under 20 s with `-intro:off`.
- Plugin DLLs are loaded from the user Plugins root (all 12 seen as modules); `NAM.log` reports the 4GB patch.
- Quitting from the game's own menu leaves no stack dump.

# RE report: framework (plugin loading, main loop, threads, cheats). SC4 1.1.641, static analysis only

All addresses are SC4 VAs. Scratch: `<workbench>\re\framework\` (a39.txt holds the cheat list).

## 1. Answers

**Q1 Plugin DLL scan (CONFIRMED by code)**
- Runs inside `cSC4App::PreFrameWorkInit` (cIGZApp slot 6, 0x452360; `this` = the cIGZApp sub-object at
  cSC4App+0x2C), in this order: the single-instance check (Q7); 0x450350 (creates the system services, reads
  `[Directories] Data=/PlugIn=` from the app INI via 0x44FE70); at 0x452CFC **0x451260** =
  `int cSC4App::LoadPluginDLLs(const cRZString& dir)` (thiscall, ret 4, returns the number of DLLs added).
- An empty `dir` makes it call itself for `GetPluginDirectory` (cISC4App slot 55, string at cISC4App+0xC0 =
  `<install>\Plugins`) then `GetUserPluginDirectory` (slot 59, +0x124 = `<UserDir>\Plugins`): install Plugins
  always load first. `-UserDir` is parsed in ReadCommandLine 0x44F571 (string 0xA86E20, used at 0x44FB07).
- Per directory: exists check (0x91B6CA); already-loaded paths from GZCOM()->EnumerateLibraries (cIGZCOM slot 13);
  file finder (0x91BD31 / 0x91BCD7 / 0x91B9C7) with pattern `"*.dll"` (global 0xB07EDC), files only -
  **root only, no recursion**.
- Per DLL: skipped if the exact path is loaded, or if `<name>.ini` beside it has `[Admin] Enabled` = false / 0;
  otherwise `cIGZCOM::AddLibrary(path)` (slot 5, 0x87C081). FindFirstFile / FindNextFile order (by name on NTFS;
  no re-sort seen, LIKELY).
- AddLibrary 0x87C081: under a lock (+0x24) skips paths in the set at +0x40; 0x87BDDF calls 0x87BA7E
  `cGZCOMLibrary::Load` (LoadLibraryW on NT, then GetProcAddress `GZDllGetGZCOMDirector`; missing export = silent
  unload); calls the export, then `director->InitializeCOM(GZCOM(), path)` (slot 3; false logs "GZCOM Director
  failed initialization" and unloads); `EnumClassObjects(0x87BD51, COM)`; then **`director->OnStart(COM)` (slot 4)
  immediately**. A LoadLibrary failure formats a message into a local (no dialog found, LIKELY log-only).
- Hot-load (LIKELY): cSC4App has two directory watchers (cSC4App+0x5D4, +0x600; built by 0x5C0EB0; thread 0x5C0F90
  uses FindFirstChangeNotificationA). `cSC4App::DoMessage` (main vtable 0xA86C2C slot 3, 0x451C30) handles
  kMessageTypeFileChangeNotification 0x87163754 by re-running 0x451260 on that directory, then posts 0xA42396C6: a DLL
  dropped into Plugins at runtime is loaded late, after the framework hooks have fired.

**Q2 Director lifecycle and framework (CONFIRMED; all on the main / WinMain thread)**
- Framework pointer **[0xB540AC]**, vtable 0xA8C970 (SC4 subclass of cGZFramework; base vtable 0xAC3090, ctor
  0x87A69E; cIGZFrameworkW32 sub-vtable 0xA8C954). App pointer [0xB540B4] (cIGZApp*). Exit code at 0xB540A8.
  Windows cIGZFramework slot order = vftables.txt; extra Windows-only slots: 40 dtor, 41 PreAppInit, 42 AppInit,
  43 PostAppInit, 44 PreAppShutdown, 45 AppShutdown, 46 PostAppShutdown, 47 OnInstall, 48 **Run 0x8795BD**.
- Init 0x87AF13: state(+0xCC)=0; COM RealInit, AddSystemService(COM); app AddApplicationServicesHere /
  AddCOMDirectorsHere / AddDynamicLibrariesHere (empty in SC4); state=1; **app->PreFrameWorkInit** (mutex check,
  services, **DLL load with InitializeCOM and OnStart**); hooks `PreFrameWorkInit` (0x87A286); state=3; fw PreAppInit
  (services with priority > -2000000); hooks `PreAppInit` (0x87A2D6); state=4; fw AppInit (priority -2999999 ..
  -2000000; failure = exit -1); **ToggleTick(true)**; state=5; fw PostAppInit (priority < -2999999); state=6; app
  PostFrameWorkInit (0x453240); hooks `PostAppInit` (0x87A326); Run.
- Shutdown 0x87AB07: hooks PreAppShutdown (0x87A376), PostAppShutdown (0x87A3C6), PostSystemServiceShutdown
  (0x87A416). AbortiveQuit 0x87A610 calls hooks AbortiveQuit (0x87A466). OnInstall hook: no caller (LIKELY never).
- Framework methods: AddHook 0x87A1F4 (slot 7), RemoveHook 0x8798AA (8), **AddToTick 0x879BB9 (9)**, RemoveFromTick
  0x879C6C (10), **AddToOnIdle 0x879D21 (11)**, RemoveFromOnIdle 0x879DB3 (12), Get/SetOnIdleInterval
  0x87946C/0x87944F (13/14), OnTick 0x473440 (15; base 0x87A74B), OnIdle 0x4735F0 (16; base 0x87A812),
  IsTickEnabled/ToggleTick 0x472E30/0x472E40 (17/18), Quit 0x87963D (19), GetState 0x472E50 (24), Application
  0x879473 (37).

**Q3 Main loop (CONFIRMED)**
- Run 0x8795BD: WaitMessage if tick is disabled; `while PeekMessageA(PM_REMOVE)`: WM_QUIT returns wParam, else
  TranslateMessage + DispatchMessageA; if tick is enabled, `this->OnIdle()`; exits when +0x124 and +0x140 are set
  (code at +0x144). No sleep or frame cap (busy loop).
- OnIdle 0x4735F0 per loop: ++counter (+0xC0); `OnTick(n)` = every tick service's OnTick(n) (cIGZSystemService slot
  10; list snapshotted under the lock; an exception is caught and posts 0x49A780B2); every `idleInterval` (+0xBC)
  loops, every idle service's OnIdle(n) (slot 11).
- Message servers deliver queued posts inside their own tick (cGZMessageServer, vtable 0xA8CA7C, calls AddToTick in
  Init; the SC4 message-server-2 subclass (ctor 0x472EB0) LIKELY the same). Explicit pumps:
  `cISC4App::RunMessageServerPump` / `RunMessageServer2Pump` (slots 4/5) pump [0xB43CC8] / [0xB43CCC] ([0xB43CCC] =
  the global cIGZMessageServer2*). App OnIdle (0x449C70) only posts 0xBA44EB51 about once a second. Other
  PeekMessage loops: 0x9DA84F (modal "wait for message X" pump, Sleep(0) every 4th pass), 0x98CDB0.

**Q4 Threads.** CreateThread directly at 0x869B2B; the rest through CRT _beginthreadex 0x9F5306 in cRZThread
(vtable 0xACFB90, ctor 0x9207A4; Start(fn,arg) slot 2 0x9208CB, Start(runnable) slot 1 0x92093B).
- 0x86ABC0: TIME_CRITICAL polling loop with callbacks [0xB50B38]/[0xB50B3C], 0x86AC10, Sleep([0xB50944]&0xFF), uses
  GetForegroundWindow (GUESS: input / timer).
- Background loader 0x48E2B0 (option "backgroundLoader"; thread 0x48E8F0 -> 0x48E460), CONFIRMED by string.
- Directory watchers 0x5C0F90 (x2 in cSC4App, plus one from 0x5207A0) and 0x9852AF, CONFIRMED.
- FTP / exception-report uploader workers (0x816990: PORT/STOR/RETR; 0x817560, 0x81C9B0, 0x81E0E0, 0x818210), on
  demand only. File-system service thread 0x9335F4 (from 0x9304A6, kGZFileSystemServiceID 0x2073215D), LIKELY async
  I/O. Object clsid 0x8A433690 created in PostFrameWorkInit (0x4DFA40, a cRZThread and an event): GUESS audio.
- **Simulation:** no thread start points at simulator code - the simulation runs on the main thread (LIKELY).
- **`-CPUCount:N`** (0x44FC3A -> 0x5F8CD0): `SetProcessAffinityMask(GetCurrentProcess, (1<<N)-1)` (N<1 -> 1); pins every
  thread to CPUs 0..N-1, creates no threads (CONFIRMED).

**Q5 Main-thread execution from another thread**
- `cIGZMessageServer2::MessagePost` (slot 4, 0x92D0BB) takes a scoped lock (+0x28, 0x48C9F0) and enqueues into +0x38
  (high priority = queue slot 4, normal = slot 3) - thread-safe (CONFIRMED); delivery on the main thread in the
  server's OnTick. Windows slot order of cIGZMessageServer2 = gzcom-dll (3 Send, 4 Post, 5 AddNotification ... 13
  CreateMessage).
- AddToTick / AddToOnIdle: the object must be a cIGZSystemService (13 slots), it is AddRef'd and ordered by
  GetServiceTickPriority (slot 12); tick runs every Run iteration, idle every idleInterval iterations, neither until
  ToggleTick(1) after AppInit. Both take the framework lock (+0xE0) and return false while that list is being
  snapshotted (flags +0xD3 tick, +0xD2 idle, +0xD4 hooks); calling them from inside a callback is fine.

**Q6 Cheat code manager (CONFIRMED)**
- cGZCheatCodeManager, vtable 0xACFCD0, QI 0x920C0A (IID 0xA1085722), at cISC4App+0x30C. Windows slot order =
  gzcom-dll: Register 3 (0x921B38), Unregister 4, AddNotification 5, AddNotification2 7, GetCheatsWithEnabledStates
  16, SetCheatState 17, SendCheatNotifications 20 (0x920ECE), DoesCheatCodeMatch 21 (0x92184B),
  DoDefaultCheatCodeProcessing 22 (0x921621), EnableCheatCodes 23, GetCheatCodesEnabled 24.
- Owners call `RegisterCheatCode(id, cRZString(name))` then `AddNotification2(this, id)`. SendCheatNotifications
  builds **kMessageCheatIssued 0x230E27AC** (data1 = id, data2 = the cIGZString with the full typed line) and
  **MessageSends** it synchronously.
- Static list (44 names; "D" = registered only if `GetDebugFunctionalityEnabled`, cISC4App slot 21, byte +0x644):
  Money (0x692FF0): RiskyMoney 0xCBF31943, WeaknessPays 0x4AB87766, Moolah 0x493F4FE6 D. Utilities (0x69D240):
  HowDryIAm 0x491865E1, FightThePower 0x08DAD89A, Barstuck 0x6AB6A2D7. Time (0x445B70): WhatTimeIzIt 0x281F7858,
  Stopwatch 0xC9B73FBB; ShowTime 0xEA5EDB88 (0x4E10BE); SimDate 0x8A78BEFF D (0x703250). Names (0x45BD20):
  WhereRUFrom 0xEA73FCC2, HelloMyNameIs 0xEA73FCD8. Misc: DollyLlama 0xAAB7F42A and Adv 0xA919D25E D (0x41B570);
  Tutorial 0x6A382BAF D (0x43F7A0); Flora 0x095BDC9C (0x6B2960). Paths / automata (0x513910): DrawPaths 0xE97FCBC8 D,
  HidePaths 0xE97FCBC9 D, udriveit 0x0B70C96D, NoCSI 0x6BB354C7, Casper 0xCC478B79; Controllers 0xABA2B5BB D
  (0x51C140), csitrigger 0x8C4136DB D (0x52DC40). Effects (0x594A30): Effect 0x4921FF8E, Snow 0x4921FF8D D, HeapCheck
  0x4921FF8F D. Plop (0x734030): PlopAllLots 0x8929E68E D, PlopAllBuildings 0x4AB569C9 D. View / debug (0x7E9900): GOL
  0x8973A69C, SizeOf 0xCA7BC5B5, TastyZots 0xAA7A2746, Zoneria 0x6A7A276E, TerrainQuery 0x8AB730AE, RenderProp
  0x88F3D4BB / RP 0x88F3D4BC, Recorder 0x6976AFA0, WatchMeMove 0x4A972F37, LotPlop 0x4AC096C6 D, BuildingPlop
  0x4AC096CA D, toll 0x0BFD8064. App (0x44C320, handled in 0x451C30): GP 0x2AB5C431 (pause on focus loss on/off),
  CreateException 0x2B60E45B, ForceIdle 0x8B6D4F8D. "nerdz rool", "garbage in garbage out" and "CallCousinVinnie"
  do **not** exist in the exe.
- **Refuse:** CreateException (raises an exception / exception report via 0x5FA520), HeapCheck and every D-gated
  debug cheat, Recorder (LIKELY writes files); GOL / TerrainQuery / RenderProp / RP / SizeOf / WatchMeMove /
  Controllers / csitrigger are debug UI (effects GUESS). Funds / utilities / plop cheats (WeaknessPays, Moolah,
  RiskyMoney, HowDryIAm, FightThePower, Plop*) are cheat-class (effects community knowledge, GUESS).

**Q7 Single instance (CONFIRMED)**
- The cSC4App ctor (0x44ACD0, at 0x44B2F6) calls wrapper 0x920AA2 -> `CreateMutexA(NULL, FALSE, "SimCity 4 Mutex")`
  (name at 0xB07EC8; object at cSC4App+0x648, vtable 0xACFBE4). PreFrameWorkInit at 0x45266B calls TryLock (slot 3,
  0x920A49: `WaitForSingleObject(h, 0)`; WAIT_ABANDONED counts as acquired).
- On failure: `-AllowMultipleInstances` continues start-up; `-Restart` retries every 200 ms for up to 30 s;
  otherwise PreFrameWorkInit returns false and the process exits before any DLL loads. No FindWindow, no file lock.

**Q8 cISC4App on Windows (CONFIRMED)**: vtable **0xA86AF0** on the cSC4App+0xC sub-object (main vtable 0xA86C2C;
cIGZApp 0xA86A68 at +0x2C; cIGZSystemService 0xA86ABC at +0x10): **71 slots, matches gzcom-dll** (slots 45 and 48 both
0x44B4F0, folded); the Mac 69-slot layout does not apply. GetAppState **25**, GetCheatCodeManager **33**, GetRegion
**35**, GetRegionalCity **36**, GetCity **37**, GetLuaInterpreter **47**, GetUserDataDirectory **58**,
GetRegionsDirectory **60**.

## 2. Layouts
- **cISC4App\*** (QI 0x26CE01C0 result): +0x38 AppState, +0x40 main window, +0x48 nation, +0x50 city, +0x308 feature
  manager, +0x30C cheat manager, +0x3A4 preferences, +0x624 render properties, +0x654 glyph texture manager, +0x658
  Lua interpreter; +0x644 debug-enabled byte, +0x645 popups-enabled byte, +0x65C run-first-time; directory strings
  +0x70 app dir, +0xC0 plugin dir, +0x110 user data dir, +0x124 user plugin dir, +0x138 regions dir.
- **cGZFramework**: +0x84 hooks, +0xA8 idle services, +0xB0 tick services, +0xB8 tickEnabled byte, +0xBC idle
  interval, +0xC0 loop counter, +0xCC state (0-6), +0xD2/+0xD3/+0xD4 iteration flags, +0xE0 lock (slot 1 Lock, 2
  Unlock).

## 3. Recipes for the bridge
- Main-thread work from a worker: `PostMessage` to the bridge's message-only window (Run's PeekMessage /
  DispatchMessage handles it every loop; WaitMessage wakes even while tick is off).
- Per-frame hook: implement cIGZSystemService and `framework->AddToTick(svc)` (slot 9); OnTick(n) then runs on the
  main thread every loop. AddToOnIdle (slot 11) every idleInterval loops.
- Posting a game message from a worker: MessagePost is lock-protected but message AddRef/Release are not interlocked:
  create and post on the main thread.
- Cheat as the player would: `app->GetCheatCodeManager()` (slot 33), `DoesCheatCodeMatch(str, &id)` (slot 21),
  `SendCheatNotifications(str, id)` (slot 20); main thread only; cheat-class; allow-list excluding the refusals.

## 4. Open questions for live tests
- GetCurrentThreadId in a NewDay / NewMonth notification vs the bridge window thread (simulation on the main thread).
- OnTick calls per second on a registered tick service; [[0xB540AC]+0xBC] (idle interval).
- Copy a test DLL into `<UserDir>\Plugins` while the game runs: is OnStart called (watcher hot-load)?
- `[[0xB540AC]+0xCC]` from inside the plugin's PostAppInit: should be 6.

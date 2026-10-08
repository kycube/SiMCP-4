# RE report: time (clock, speed, simulation steps, randomness). SC4 1.1.641, static analysis only

All addresses are SC4 VAs. S = the cSC4Simulator object. Scratch scripts and dumps: `<workbench>\re\time\`.

## 1. Simulation date and the 24-hour clock
- **The date is stored in cSC4Simulator** (CLSID 0x2990C1E5; IID cISC4Simulator 0x8695664E, compared in QI 0x702040;
  GetGZCLSID 0x702030). Global `*(cISC4Simulator**)0xB43D5C` = city->GetSimulator(), written at 0x601E11 right
  after city slot 50 (+0xC8), cleared at 0x60202E on city close. CONFIRMED.
- **Storage:** cGZDate embedded at S+0xE8 {+0 vtbl 0xACEAF0, +4 uint32 day number, +8 cIGZDate vtbl 0xACEA38, +0xC
  refcount}: **day number at S+0xEC**, cIGZDate* = S+0xF0. It is a **Julian Day Number** (0x912B5F is the standard
  JDN formula: 146097/1461/153/1721119), so 2000-01-01 = 2451545; the ctor at 0x7041D2 starts at 1/1/2000. CONFIRMED.
- **Getters** (cISC4Simulator vtable 0xAB2FB8, 34 slots, header order with MSVC overloads): 5 GetSimStartDate
  0x7024A0; 6 GetSimDate(y*, m*, d*, dayOfYear*, weekDay*) 0x702150; 7 GetSimDate() -> S+0xF0 (0x703D20);
  8 GetSimDateNumber 0x703D40. cIGZDate (vtbl 0xACEA38): 12 WeekDay, 13 Year, 14 DayOfYear, 15 DayOfMonth, 23 Month,
  26 DayNumber, 37 operator++ ([+4]++), 44 Jday(m,d,y). CONFIRMED.
- Within a day the simulator keeps its own counters: S+0xB8 minute (0..60), S+0xBC hour (0..24+).
- **cSC424HourClock** is the visual day/night clock only: CLSID 0xA7E7F929, service id 0xA7E7F92A (priority
  -2000000), ctor 0x445940, city slot 86, vtable 0xA86588 (30 slots, header order). Fields: +0x30 pause count, +0x34
  hidden-pause count, +0x38 float magnification (default 100.0, clamped [0.05, 2000]), +0x44 time of day in seconds
  (starts 43200 = noon; GetHour = sec/3600, 0x444EC0), +0x48 visual seconds, +0x50 cRZTimer. Advances in its OnIdle
  (0x445820): wall-clock ms x magnification, applied once more than 60 s has built up, capped at 1200 s, wrapping at
  86400; posts 0x44778231 every 10 game minutes plus an hour-change notification (0x445750). Pause(bool) slot 24 /
  HiddenPause(bool) slot 26 count up and post 0x44778235 / 0x44778236. It never touches the simulator date. CONFIRMED.

## 2. Speed and pause
- **Speed** = S+0x3C: 0 slow (turtle), 1 medium (llama), 2 fast (cheetah); GetSimSpeed slot 27. **SetSimSpeed** slot
  28 (0x7026D0) fails while S+0x44 == 0 (emergency), no-op if unchanged; the internal setter 0x702430 accepts 0..2,
  sets target fps S+0x84 = 30/20/15, ms-per-day S+0x80 = S+0xFC[speed], restarts the throttle timer S+0x48, posts
  SimSpeedChange 0x4A7FB7E9 (data1 = speed). CONFIRMED.
- **ms-per-day table** S+0xFC[3]: ctor defaults 5000/1000/100; 0x7025B0 reloads it from exemplar
  6534284A-E7E2C2DB-E9590E52 "Main Simulator", property 0x89590E6D = [2000, 1000, 50] (a plugin could override it).
  Property 0x89590E6E = animation dilation [1, 1, 1.5, 3, 1] (S+0x108).
- **Pausing is reference-counted, three counters** (CONFIRMED): user S+0x30 (Pause slot 9 0x7021E0 +1; Resume slot
  12 0x702220 -1 only if S+0x44 != 0); hidden S+0x34 (HiddenPause slot 10 0x702200, HiddenResume slot 13 0x702240);
  emergency S+0x38 (EmergencyPause slot 11 0x702540 = Pause + clear S+0x44 + count; EmergencyResume slot 14 0x702580).
  Slots 15-17 return counter > 0; slot 18 IsAnyPaused. Messages on 0->1 and 1->0 (data1 = new count):
  SimPauseChange 0xAA7FB7E0, SimHiddenPauseChange 0x4A7FB7E2, SimEmergencyPauseChange 0x4A7FB807.
- **Speed commands** (city-view handler 0x7F1C10; simulator pointer at handler+0x154): SimSpeedPause 0x6A935CAD
  toggles Pause/Resume; SimSpeedSlow 0x6A935CB0 / Medium 0x6A935CB2 / Fast 0x6A935CB5 call SetSimSpeed(0/1/2), then
  Resume() if paused, then refresh the UI (0x7E59B0). CONFIRMED.
- **GamePause command** (parser 0x5C9E02) calls cdecl 0x5F91C0(pause, draw, anim, simClock, clock24): Draw = service
  0xC416025C slot 18/19; Anim = service 0x86AD10EC slot 12(bool); SimulationClock = GetSystemService(0x46956659,
  0x8695664E) then HiddenPause/HiddenResume; 24HourClock = city slot 86 -> HiddenPause(bool). Same helper used by a
  scoped pause object (ctor 0x5F9320 / dtor 0x5F9360) in the app's save/load/dialog paths (0x4543B0..0x454C22) and by
  0x449380 (app sub-vtable 0xA86C2C slot 11, flag app+0x5D1), LIKELY the focus-loss pause. Dialog and game pauses
  nest on the hidden counter; the user pause is separate.

## 3. The simulation loop
- **No simulator thread.** cSC4Simulator is a cIGZSystemService (S+8, vtbl 0xAB2F6C); its OnTick (slot 10 =
  0x703E70, this = S+8, SEH-framed) holds the whole loop; OnIdle is a stub. It runs in the framework tick (main
  thread; LIKELY, see the framework report).
- **OnTick:** budget S+0x78 = max(15, 1000/fps - ms since the previous tick (timer S+0x60)), fps = 30 when paused else
  S+0x84. Runs only if S+0x2C (initialised, set in Init 0x703250) and not S+0x2D (re-entry guard). Restarts timer
  S+0x198, then loops `{ if hidden>0 break; if user<=0 { AdvanceTime 0x702A80; RunAgents 0x7038B0 } if hidden<=0
  RunIdle 0x702DF0 } while (S+0x198 elapsed < budget)`. Other AdvanceTime caller: the set-date cheat 0x703420 (id
  0x8A78BEFF); cheat id 0xAC07E24 sets the fps field S+0x84.
- **AdvanceTime 0x702A80** (thiscall S): clears the event flags S+0xDC..0xE6; returns at once while any OneShot (count
  S+0x118) or EmergencyTime (count S+0x124) agent is registered; minute = 60 if no minute agents (S+0x130 == 0) else
  +1; hour likewise (S+0x13C); the **day** advances when hour >= 24, the day list (and week/month/year lists when
  tomorrow starts one) is finished, and the wall-clock throttle passes (granularity S+0x7C = 4 = day, set only in the
  ctor; timer S+0x48 >= S+0x80 ms). Then hour = 0, restart S+0x48, date++ (flag S+0xE0), post the messages below.
- **One step = one whole day** (no Maxis code registers minute or hour agents). Wall-clock ceiling at 2000/1000/50 ms
  per day: 0.5 / 1 / 20 days per second. CONFIRMED.
- **Agents** (AddAgent slot 19 (agent, type, name, flags)): list t header at S+0x114+12t, count S+0x118+12t, iterator
  S+0x1B0+4t; t = 0 OneShot ... 10 Idle. RunAgents restarts the iterator (0x702F10) of each event type 2..7 that fired
  this step, then dispatches in type order calling **agent->DoMessage synchronously** (msg = 0x66956810+t, data1 =
  DayNumber, data3 = S+0xB0+4t: day -> DayOfYear S+0xC0, week -> S+0xC4, month -> S+0xC8, year -> S+0xCC). An agent
  returning false is called again later (time-sliced); OneShot agents are removed on success; repeats until all lists
  are finished or S+0x198 >= budget. CONFIRMED.
- **Registered agents** (AddAgent call sites; OneShot LIKELY): Day - Aura, Budget, BuildingDevelopment, Commercial,
  Crime, Demand, Flora, GrowthDeveloper, LandValue, LotDeveloper, Neighbors, Plumbing, Pollution, Power,
  PropDeveloper, Protection, Residential, Traffic, Weather. Month - the Day list minus GrowthDeveloper,
  PropDeveloper, Weather, plus TractDeveloper. Week - Weather. Year - HistoryWarehouse, TractDeveloper. Idle - Aura,
  BuildingDevelopment, Commercial, Crime, Demand, GrowthDeveloper, LandValue, Neighbors, Plumbing, Power,
  PropDeveloper, Residential. OneShot - Aura, Budget, BuildingDevelopment, Commercial, Demand, LandValue,
  LotDeveloper, Residential, Traffic.
- **Idle dispatch 0x702DF0** runs only when hidden == 0 (so idle agents run while user-paused): round-robin, msg
  0x6695681A, data1 = DayNumber, data2 = user-paused flag, data3 = ms budget (wall clock, <= budget/3).
- **Messages** sent in 0x702A80 after date++ with **MessagePost(msg, false)** (message server S+0xF8, slot 4): queued,
  not synchronous. NewDay 0x66956814 (data1 = DayNumber, data3 = DayOfYear); NewWeek 0x66956815 (WeekDay == 1,
  data3 = week); NewMonth 0x66956816 (DayOfMonth == 1, data3 = month); NewYear 0x66956817 (DayOfYear == 1, data3 =
  year). NewMinute, NewHour, Idle, Begin go only to agents. CONFIRMED.
- **Saved state** (Write 0x702290, this = S+4): version 4, bytes S+0x2D/0x2E, user-pause count S+0x30, speed S+0x3C,
  simTime S+0x40, S+0x78, the S+0xB0.. per-type values (date follows, LIKELY).

## 4. Recipe: advance exactly N days (bridge, main thread, outside OnTick, under SEH)
0. S = `*(void**)0xB43D5C` (or app slot 37 -> city slot 50). Require S != 0, byte S+0x2C set, byte S+0x2D clear.
1. **Freeze once** with S->HiddenPause() (slot 10): stops time, agents and idle in OnTick (a user Pause still lets idle
   agents run). Release later with exactly one HiddenResume (slot 13); the counter is shared with GamePause and dialogs.
2. **Per day:** save k = [S+0x7C], write [S+0x7C] = 0 (turns off the wall-clock day throttle; [S+0x80] = 0 also works
   but SetSimSpeed rewrites it); d0 = [S+0xEC]; loop (with a cap): call 0x702A80 (ecx = S) then 0x7038B0 (ecx = S);
   stop when [S+0xEC] != d0 **and** [S+0x1B0+4t] == [S+0x114+12t] for every t in 0..9; restore [S+0x7C] = k.
   **Always call the two as a pair** (AdvanceTime clears the event flags RunAgents uses to restart iterators).
3. "Finished" = every day/week/month/year agent returned true for the new day (the state OnTick reaches before it
   advances again). NewDay/NewMonth/NewYear messages are still queued: let one frame pass (still hidden-paused) or
   call the message server's OnTick before the next day if listeners must see each day.
4. **Idle agents never run in this recipe** (live test whether that changes growth). If they must: set [S+0x34] = 0
   temporarily, call 0x702DF0 a fixed number of times, restore (they are wall-clock budgeted).
- Honest play: the game's own day code with the same checks; only the wall-time spacing between days is removed.
- Cheaper, not exact: S+0xFC..0x104 = 0 or [S+0x7C] = 0, then Resume: unthrottled in OnTick; stopping from a NewDay
  listener lands mid-day.
- **Wall-clock dependencies:** (a) day throttle S+0x48 vs S+0x80 (cRZTimer elapsed 0x890198, restart 0x89058F; RDTSC or
  QueryPerformanceCounter); (b) tick budget S+0x78 / S+0x198 (slicing only); (c) self-slicing agents (e.g.
  GrowthDeveloper NewDay 0x6B7030 -> worker 0x6B5F20, 5 ms budget); (d) **idle agents** (their budget and the number
  of idle passes per day: the main nondeterminism in normal play); (e) the 24-hour clock; (f) one GetTickCount import
  xref (not traced); timeGetTime is not imported.

## 5. Randomness
- **cRZRandom (LCG)**: +0 int state, +4 float-stream state (= seed), +8 cached-gaussian flag, +0x10 cached double;
  size >= 0x18. Ctor 0x913A5C(seed); Seed 0x913667(seed) (-1 = time() ^ (clock()<<16 | clock()), CRT time 0x9EFB59,
  clock 0x9F361F); Next 0x913696 (state*0x41C64E6D + 12345, returns bits 16..47); UInt(n) 0x9136B1; Range 0x9136CA;
  mean of 4 draws 0x9136DF; float stream 0x91372E ([+4] *= 0x278DDE6D; **if [+4] == 0 it seeds itself from
  clock()**); Uniform 0x913761; Gaussian 0x913777. CONFIRMED.
- **cRZRandomSuper (MT19937)**: 624 dwords at +0, +0x9C0 cached flag, +0x9C4 index; size 0x9C8. Ctor 0x913B74(seed);
  Seed 0x913A72 (-1 = time-based via 0x913977; 69069 initialisation); Refill 0x9138A9, Next 0x9139B9, UInt 0x913A06,
  Range 0x913A14, Float 0x913A29, Uniform 0x913A46. CONFIRMED.
- **Seed source 0x470B50** = current local date-time (1-second resolution), 43 callers.
- **Global generators** (static initialisers, seed = 0x470B50() ^ constant; verified for 0xB228A0 (^0x6C09BFC3) and
  0xB21D78 (^0x4C09C170), LIKELY for the rest): cRZRandom at 0xB21648, 0xB217C0, 0xB228A0, 0xB22AE8, 0xB22B60,
  0xB22B80, 0xB22BE8, 0xB22C10, 0xB22C38, 0xB22DF8, 0xB22E28, 0xB22E58, 0xB22FB0, 0xB23078, 0xB230C8, 0xB485F0,
  0xB49080, 0xB49AF0, 0xB4AFD8, 0xB4B398, 0xB4B3D0, 0xB4BC78, 0xB4C7C8, 0xB4D530, 0xB4D5D0, 0xB4E240; seeded -1:
  0xB43DE8 (static initialiser), 0xB49B18 (in 0x6D0520). cRZRandomSuper at 0xB21D78, 0xB231B0, 0xB43E88, 0xB44870,
  0xB47B78, 0xB48630, 0xB49120, 0xB49BD0, 0xB4A5C0.
- **Per-object**: traffic simulator MT pointer at **Traffic+0x6FC** (allocated in Init 0x71E7E0, ctor 0x71F1A0, seeded
  with the local date-time; Mac +0x700) CONFIRMED; MT at obj+0x38 (0x6F3410, power-simulator region, seed =
  datetime*0x1C) LIKELY; MT at obj+0x50 seeded -1 (0x5125E0). Not checked on Windows: zone manager cRZRandom (Mac
  +0x30), effects manager MT (Mac +0x1C0), cISC4AdvisorSystem GetRandom (slot 9), GZCOM's cRZRandom (ctor 0x87BA04).
- **Stack-local generators seeded -1** (fresh time seed per call): ctor sites 0x4BBE9D, 0x5157AF, 0x516C4C, 0x51984E,
  0x51C45C, 0x53DAAF, 0x53E097, 0x558E3F, 0x55C902, 0x57F5AD, 0x69E029, 0x777B3C; also 0x6DF116 (Plumbing init) and
  0x948ABF.
- **CRT rand / srand**: rand 0x9EFB9F, srand 0x9EFB92 (cdecl), per-thread state (_getptd()+0x14), starting at 1.
  srand's only caller is Lua math.randomseed (0x8C0B20). rand callers: Lua math.random (0x8C0450); simulation code
  0x6C68C0 (from 0x6CD940, lot-developer area), 0x6BCFC0 (from the monthly handler 0x6B9EA0), 0x6DB010/0x5CF610 (from
  0x5D0890); demolish effects 0x49CBE0/0x49D1C0; 0x4EE6F1 (roles LIKELY).
- **Reproducible trial** (after LoadCity and HiddenPause, main thread): srand(K); Seed(Ki) on every global and
  per-object generator (0x913667 / 0x913A72), clear cached-gaussian flags, reseed [Traffic+0x6FC]; make the
  time-seed paths deterministic (calls at 0x913676/0x91367E, 0x91373B, 0x913A81/0x913A89, and 0x470B50 return a
  bridge counter); step with section 4 without idle.

## Object layout: cSC4Simulator (Windows offsets)
- Vtables: +0x00 cISC4Simulator 0xAB2FB8; +0x04 cIGZSerializable 0xAB2FA0; +0x08 cIGZSystemService 0xAB2F6C; +0x0C
  0xAB2F54; +0x24 cIGZMessageTarget2 0xAB2F44 (DoMessage 0x703540).
- +0x2C initialised · +0x2D OnTick re-entry guard · +0x2E established (LIKELY) · +0x30/+0x34/+0x38 user / hidden /
  emergency pause counts · +0x3C speed · +0x40 simTime · +0x44 resume and speed change allowed · +0x48 day-throttle
  cRZTimer · +0x60 frame timer · +0x78 tick budget ms · +0x7C throttle granularity (4 = day) · +0x80 ms per day ·
  +0x84 target fps · +0x88 cSC4LimitTimerCalibrator · +0xB0+4t per-type values (+0xB8 minute, +0xBC hour, +0xC0
  DayOfYear, +0xC4 week, +0xC8 month, +0xCC year) · +0xDC+t event-fired bytes · +0xE8 cGZDate (**+0xEC day number**,
  +0xF0 cIGZDate*) · +0xF8 message server · +0xFC ms-per-day[3] · +0x108 dilation table · +0x114+12t agent lists
  (count +0x118+12t) · +0x198 agent/idle budget timer · +0x1B0+4t agent iterators.

## Open questions (live tests)
1. New city: [[0xB43D5C]+0xEC] = 2451545 on 1 Jan 2000, +1 per day; compare with slot 6.
2. HiddenPause, step 30 days with the recipe: [S+0xEC] +30 exactly; S+0xB8 = 60 and S+0xBC = 0 after each day; wall
   time per day in a small city.
3. Dump S+0x118+12t (t = 0..10): expect 0 for t = 2 and 3 (a plugin DLL registering hour agents would make a day
   take 24+ steps).
4. Same save twice + seeding recipe + 60 days: compare population, funds, demand; then against normal cheetah play.
5. Subscribe to 0x66956814: arrives after the step returns (queued), once per day, data1 = DayNumber.
6. S+0x30 after the UI pause; S+0x34 during save and dialogs; app+0x5D1 when unfocused.
7. HiddenPause(true) the 24-hour clock and run a 30-day trial: does the simulation read the hour / IsNight?
8. S+0xFC..0x104 live: expect 2000/1000/50 unless a plugin overrides the Main Simulator exemplar.

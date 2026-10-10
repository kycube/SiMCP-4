# app-city: from the app object to every simulator and manager (SimCity 4 1.1.641, static analysis only)

Scratch: `<workbench>\re\app-city\`. Main outputs are `city_subsystems.tsv` (the full table from Q4), `city_vt.txt`
(all 110 cISC4City slots), `sim_iface.txt` and `qi.py` (a symbolic QueryInterface evaluator).

## 1. Answers

**Q1. cSC4App** (CONFIRMED)
- Constructor 0x44ACD0, destructor 0x44B690. Allocated with `new(0x670)` at 0x44C1D4. QueryInterface 0x449250.
- Sub-objects, each with its own vtable:

| Offset | vtable | Answers iid |
|---|---|---|
| +0x00 | 0xA86C2C | cIGZMessageTarget 0xE98B2F57, also kSC4CLSID_cSC4App 0xCA263481 |
| +0x04 | 0xA86C1C | cIGZMessageTarget2 0x452294AA |
| +0x08 | 0xA86C0C | cIGZWinMessageTarget 0xC6AE7085 |
| **+0x0C** | **0xA86AF0** | **cISC4App 0x26CE01C0** (the QI returns `this+0xC`) |
| +0x10 | 0xA86ABC | base; any other iid goes to its QI at 0x87B0DC |
| +0x14 | 0xA86AA4 | - |
| +0x2C | 0xA86A68 | - (this is the cIGZApp* the framework holds) |

- **The cISC4App vtable 0xA86AF0 has 71 slots**, laid out exactly as the gzcom-dll header (header slots 45 and 48
  both point to 0x44B4F0, `lea eax,[ecx+0x1DC]`).
- One exception: slots 15 and 16 are swapped. Slot 15 is `SaveCity(cIGZString const&, bool)` and slot 16 is
  `SaveCity(bool)` - MSVC's reverse overload order. A plugin compiled with MSVC from the header gets it right
  automatically; raw slot calls must use the physical slot.
- Methods reached through this vtable take `ecx = cISC4App*` (= app+0xC), so field offsets are given relative to
  A (= app+0xC) and to the app object.

| Slot | Method | Function | Body |
|---|---|---|---|
| 25 (+0x64) | GetAppState | 0x80BC00 | `mov eax,[ecx+0x38]` -> app+0x44 |
| 26 | GetMainWindow | 0x68D1B0 | [A+0x40] = app+0x4C |
| 34 | GetNation | 0x698CF0 | [A+0x48] = app+0x54 |
| 35 (+0x8C) | GetRegion | 0x44B4A0 | nation (app+0x54) -> its vtable slot 8 (tail jump) |
| 36 (+0x90) | GetRegionalCity | 0x44B620 | [A+0x4C] = app+0x58, or 0 |
| 37 (+0x94) | GetCity | 0x81F910 | `mov eax,[ecx+0x50]` -> app+0x5C |
| 38 | GetPreferences | - | [A+0x3A4] |
| 33 | GetCheatCodeManager | - | [A+0x30C] |
| 47 | GetLuaInterpreter | - | [A+0x658] |

- Argument counts were checked for every slot 0..70.
- **GetAppState values** (CONFIRMED). The app's message handler is cIGZMessageTarget2::DoMessage at 0x451ED0
  (slot 3 of 0xA86C1C, `this` = app+4); it writes `[esi+0x40]` = app+0x44:
  - **0** on kSC4MessagePreRegionShutdown 0x8BB5BB46 and kSC4MessagePreCityShutdown 0x26D31EC2 (and the ctor).
  - **1** (region view) on kSC4MessagePostRegionInit 0xCBB5BB45.
  - **2** (city) on kSC4MessagePostCityInitComplete 0xEA8AE29A.
  - No separate "loading" value: loading or tearing down shows as 0, or the previous value until the Post message.
- The city object is created by `new(0x20C)` + constructor 0x459F30 inside 0x4548B0 (slot 13 of 0xA86C2C), which
  stores it at app+0x5C.

**Q2. Global pointers** (CONFIRMED)
- **`[0xB43C94]` = cISC4App\*** (= app+0xC), written once at the end of the app constructor (0x44B46F calls
  0x601C00), read 287 times. App state `[[0xB43C94]+0x38]`; city `[[0xB43C94]+0x50]`; cSC4App* = `[0xB43C94]-0xC`.
- **`[0xB43CEC]` = current cISC4City\*** (the cSC4City object; interface at +0). Set at the end of the city
  constructor (0x45A34A calls 0x601C10), cleared by 0x602100 when the city is torn down; read 1030 times. It exists
  before Init and during shutdown, so **gate reads on app state == 2**.
- **Subsystem cache 0xB43CF0..0xB43DC0**, filled by 0x601C20 (from cSC4City::Init at 0x45BEC4); mapping in Q4.
- Framework route: RZGetFramework() 0x8793EC returns `[0xB540AC]` (909 callers); framework vtable 0xA8C970
  (cSC4Framework, ctor 0x472E10); its slot 37 (Application) 0x879473 returns `[0xB540B4]` = cSC4App+0x2C, so
  cSC4App = `[0xB540B4]-0x2C` and cISC4App\* = `[0xB540B4]-0x20`.
- Other service globals (init code 0x602290..0x6024F0): 0xB43CCC cIGZMessageServer2\* (496 reads),
  0xB43CC8 cIGZMessageServer\*, 0xB43CB0 command server, 0xB43CA8 cIGZPersistResourceManager\*, 0xB43C9C graphics
  system.

**Q3. cSC4City** (CONFIRMED)
- Constructor 0x459F30, size 0x20C. QI 0x459300 answers 0x66BA4DB5, 1 and CLSID 0x8990C372 -> `this`;
  cIGZMessageTarget2 -> +4; cIGZSerializable -> +8; anything else -> property holder at +0xC (0x5FD200).
- vtables: **+0 = 0xA87620 (cISC4City, 110 slots)**; +4 = 0xA8760C (DoMessage 0x45C1A0); +8 = 0xA875F4 (Write
  0x45C5B0, Read 0x45CB10, GetGZCLSID 0x45A360); +0xC = 0xA87590 (cSCPropertyHolder).
- **All 110 slots follow the Mac / gzcom-dll order**; every getter's offset matches the Mac field name.

| Slot | Method | Function | Reads |
|---|---|---|---|
| 5 | GetCitySerialNumber | 0x6AAC50 | [+0x30] |
| 12 (+0x30) | GetCityName(cIGZString&) | 0x459DC0 | string at +0x74 |
| 13 | SetCityName | 0x45A5A0 | - |
| 14 | GetCityNameChanged | - | byte +0x2D |
| 16 (+0x40) | GetMayorName | 0x459DE0 | string at +0x9C |
| 18 | GetCityDescription | - | string at +0xC4 |
| 20 (+0x50) | GetBirthDate | 0x698CF0 | dword +0x48 |
| 22 (+0x58) | GetEstablished | 0x4596B0 | byte +0x25 |
| 24 (+0x60) | GetDifficultyLevel | 0x60FB80 | +0x28 (0 easy, 1 medium, 2 hard) |
| 26 | GetWorldPosition | - | floats +0xEC (x), +0xF0 (z) |
| 28 | GetWorldBaseElevation | - | float +0xF4 |
| 30 | GetWorldHemisphere | - | 1 if +0xF0 > constant, else 2 |
| 87 (+0x15C) | GetCitySizeType | 0x459390 | from +0x118: 64 -> 0, 128 -> 1, else 2 |
| 89/90 | SizeX/SizeZ | - | floats +0x100/+0x104 (metres) |
| 91/92 | CellWidthX/Z | - | +0x108/+0x10C (16.0) |
| 93/94 | **CellCountX/Z** | - | **+0x118/+0x11C** |
| 101 | ToggleSimulationMode | 0x4598C0 | - |
| 102 | IsInCityTimeSimulationMode | 0x4598A0 | true when sim+0x40 is 0 |
| 103-105 | Enable/Disable/IsSaveDisabled | - | +0xF8 |
| 106-108 | UI lock count | - | +0xFC |

- SetEstablished (slot 23, 0x459A80) broadcasts kSC4MessageCityEstablished 0x26D31EC4 or kSC4MessageCityObliterated
  0x26D31EC5.
- **Date getters live on cISC4Simulator** (city slot 50 -> [city+0x158], vtable 0xAB2FB8, 34 slots): slot 6 (+0x18)
  0x702150 = `GetSimDate(&year,&month,&day,&dayOfYear,&weekDay)` (ret 0x14); slot 7 (+0x1C) 0x703D20 returns
  cIGZDate\* = sim+0xF0 (slots 6 and 7 swapped against the header); slot 8 = GetSimDateNumber. **Day number** =
  dword `[sim+0xEC]` (cIGZDate slot 26 is `mov eax,[ecx-4]`); cRZDate at sim+0xE8 (vtable 0xACEAF0; cIGZDate vtable
  0xACEA38 at +0xF0). **Pause counters** (slots 15-17): +0x30 pause, +0x34 hidden pause, +0x38 emergency pause.
  **Speed** (slot 27): +0x3C, initial 3. **Mode** (slots 29/30): +0x40, 0 = city-time (mayor) mode (LIKELY).
  RemoveAgent (20/21) and RemoveAllAgents (22/23) overload pairs are also swapped against the header.

**Q4. Subsystems.** All created in 0x45AA10 through `GZCOM()->CreateInstance(clsid, iid, &field)`; vtable checked
by symbolically evaluating each class's QI (CONFIRMED). Interface at object+0 except the lot manager.

| City field | Getter slot | Cached global | Class | vtable at *ptr |
|---|---|---|---|---|
| 0x120 | 31 | 0xB43D00 | Demolition (CLSID 0x0990C38A) | 0xA88004 |
| 0x124 | 39 | 0xB43D04 | Dispatch manager (0x4990BD93) | 0xA88108 |
| 0x128 | 32 | 0xB43DC0 | History warehouse (0x89EFA536) | 0xA8CCB4 |
| 0x12C | 34 | 0xB43D0C | Occupant manager (0x098F964D) | 0xA8F7F0 |
| 0x130 | 35 | 0xB43D10 | Prop manager (0xA990BD10) | 0xA8F928 |
| 0x134 | 36 | 0xB43D14 | Zone manager (0x298F9B2D) | 0xA92E00 |
| 0x138 | 75 | 0xB43DB0 | Zone developer (0x498F9B01) | 0xAB3830 |
| 0x13C | 79 | 0xB43D20 | Lot developer | 0xAB1B98 |
| 0x140 | 80 | 0xB43D24 | Tract developer | 0xAB3118 |
| **0x144** | 33 | 0xB43D08 | **Lot manager** (see note) | **0xAB37C0** |
| 0x148 | 37 | 0xB43D18 | Lot configuration manager | 0xA8EC58 |
| 0x14C | 41 | 0xB43DB8 | Prop developer | 0xAB29F8 |
| 0x150 | 42 | 0xB43D58 | Network lot manager | 0xAA7958 |
| 0x154 | - | - | City detail manager | 0xA87888 |
| 0x158 | 50 | 0xB43D5C | Simulator | 0xAB2FB8 |
| 0x15C | 51 | 0xB43D60 | Aura | 0xAB07C8 |
| **0x160** | 52 | 0xB43D64 | **Budget** | **0xAB0908** |
| 0x164 | 53 | 0xB43D68 | Building development | 0xAB0AF8 |
| 0x168 | 54 | 0xB43D6C | Commercial | 0xAB0CCC |
| 0x16C | 55 | 0xB43D70 | Crime | 0xAB0DC8 |
| 0x170 | 56 | 0xB43D74 | Demand | 0xAB0E48 |
| 0x174 | 57 | 0xB43D78 | Fire protection | 0xAB1160 |
| 0x178 | 58 | 0xB43D7C | Flammability | 0xAB128C |
| 0x17C | 59 | 0xB43D80 | Flora | 0xAB13C0 |
| 0x180 | 60 | 0xB43D84 | Industrial | 0xAB1530 |
| 0x184 | 61 | 0xB43D88 | Land value | 0xAB1670 |
| 0x188 | 62 | 0xB43D8C | Neighbors | 0xAB1EE0 |
| 0x18C | 63 | 0xB43D90 | Ordinance | 0xABEAC0 |
| 0x190 | 64 | 0xB43D94 | Plumbing | 0xAB2228 |
| 0x194 | 65 | 0xB43D98 | Police | 0xAB2490 |
| 0x198 | 66 | 0xB43D9C | Pollution | 0xAB2630 |
| 0x19C | 67 | 0xB43DA0 | Power | 0xAB28B8 |
| 0x1A0 | 68 | 0xB43DA4 | Residential | 0xAB2C10 |
| 0x1A4 | 69 | 0xB43DA8 | Traffic | 0xAB33D0 |
| 0x1A8 | 70 | 0xB43DAC | Weather | 0xAB3610 |
| 0x1AC | 71 | - | MySim agent | 0xA85544 |
| 0x1B0 | 73 | 0xB43DB4 | Civic building (health/education) | 0xAB0C7C |
| 0x1B4 | 78 | 0xB43D28 | Landfill developer | 0xAB157C |
| 0x1B8 | 77 | 0xB43D2C | Airport developer | 0xAB0714 |
| 0x1BC | 76 | 0xB43D30 | Seaport developer | 0xAB2E10 |
| 0x1C0 | 74 | 0xB43D40 | Park manager | 0xAB20AC |
| 0x1C4 | 72 | 0xB43D3C | Disaster layer | 0xA9E3DC |
| 0x1C8 | 81 | 0xB43D34 | Advisor system | 0xA82AC8 |
| 0x1CC | 82 | 0xB43D38 | Tutorial system | 0xA861B8 |
| 0x1D0 | 43 | 0xB43D44 | Vehicle manager | 0xA9D1E0 |
| 0x1D4 | 44 | 0xB43D48 | Pedestrian manager | 0xA9A470 |
| 0x1D8 | 45 | 0xB43D4C | Aircraft manager | 0xA94850 |
| 0x1DC | 46 | 0xB43D50 | Watercraft manager | 0xA9DF38 |
| 0x1E0 | 47 | - | Automata controller manager | 0xA96058 |
| 0x1E4 | 48 | - | Automata script system | 0xA96BA8 |
| 0x1E8 | 40 | 0xB43D54 | TrafficNetworkMap | 0xA8FED8 |
| 0x1EC | 49 | - | City situation manager | 0xA97E58 |
| 0x1F0 | 83 | 0xB43CF0 | Surface water | 0xAB3B00 |
| 0x1F4 | 84 | 0xB43CF4 (also 0xB43CF8) | Terrain | 0xAB3D18 |
| 0x1F8 | 86 | 0xB43DBC | 24-hour clock | 0xA86588 |
| 0x1FC | 85 | 0xB43D1C | Effects manager | 0xA9F264 |
| 0x200 | 38 | - | Network manager | 0xAA7AD0 |

- Lot manager: not created on its own; it is `[city+0x138]->QueryInterface(0x681905BD)`, i.e. the zone developer
  object at +4 (vtables +0 0xAB3830 cISC4ZoneDeveloper 0xE818ED2B, +4 0xAB37C0 cISC4LotManager, +8 0xAB37AC,
  +0xC 0xAB3794).

**Q5.** The Windows cSC4City field offsets **equal the Mac classes.txt offsets** for every named field (0x28, 0x2D,
0x30, 0x38, 0x48, 0x4C, 0xF8, 0xFC, 0x120..0x200; CONFIRMED by the getters). Mac field_0x154 is the city detail
manager; field_0x1B8 the airport developer.

## 2. Layouts
- **cSC4App**: 0x44 appState; 0x4C main window; 0x54 nation; 0x58 cISC4RegionalCity\*; 0x5C cISC4City\*;
  0x3B0 preferences (A+0x3A4); 0x650/0x651 debug / popup bools (A+0x644/0x645); 0x664 Lua (A+0x658).
- **cSC4City**: 0x20 refcount; 0x24 initialised (byte); 0x25 established (byte); 0x28 difficulty; 0x2D name
  changed; 0x30 serial; 0x34 occupant serial counter; 0x38/0x3C original language/country; 0x40/0x44 last
  language/country; 0x48 birth date; 0x4C save path (cRZString); 0x74 **name**; 0x88 previous name; 0x9C
  **mayor**; 0xC4 description; strings also at 0x60, 0xB0, 0xD8 (unidentified); 0xEC/0xF0/0xF4 world x / z /
  elevation; 0x100..0x11C sizes; 0x120..0x200 subsystem pointers.
- cRZString is 0x14 bytes: {vtable 0xA80810, begin, end, end-of-storage, refcount}; STLport NUL-terminated char
  data. Name = `cstr([city+0x78])`, length `[city+0x7C]-[city+0x78]`; mayor `[city+0xA0]`; description `[city+0xC8]`.
- **Simulator**: 0x28 refcount, 0x30/0x34/0x38 pause counters, 0x3C speed, 0x40 mode, 0x44 bool, 0xE8 cRZDate
  (day number at **0xEC**).

## 3. Bridge recipes (read-only, main thread)
- `app = QI(0x26CE01C0)` or `[0xB43C94]`; `state = app->vtbl[25]()` before touching the city;
  `city = app->vtbl[37]()` (== `[0xB43CEC]`); each subsystem `city->vtbl[N]()` or the global cache.
- Name: `city->vtbl[12](cIGZString&)`; mayor slot 16. Date: `sim = city->vtbl[50]()`, `sim->vtbl[6](&y,&m,&d,&doy,&wd)`.
- State-changing: speed `SetSimSpeed(n)` (sim slot 28; refuses when byte [sim+0x44] is 0) = the speed buttons;
  pause / resume sim slots 9 and 12 (counters); rename `SetCityName` (13) / `SetMayorName` (17) broadcast a message
  (LIKELY what the rename dialog does). Cheat-class: `SetDifficultyLevel` (25), `SetEstablished` (23),
  `ToggleSimulationMode` (101), `SetSize` (88; only before Init). App `RequestSaveCity(showNotif, fast)` slot 9 and
  `RequestGoToRegionView(bool)` slot 12 go through the menus' request path (LIKELY).

## 4. Live tests
1. `[0xB43C94]` equals the plugin's QI result; `[[0xB43C94]]` == 0xA86AF0; `[0xB540B4]-0x20` equals it too.
2. `[[0xB43C94]+0x38]`: 1 in region view, 2 in a city, 0 during load/exit (log values entering/leaving a city).
3. In a city: `[0xB43CEC] == [[0xB43C94]+0x50]`, `[[0xB43CEC]] == 0xA87620`; after returning to the region both 0.
4. `[[city+0x160]] == 0xAB0908`, `[0xB43D64] == [city+0x160]`, `[city+0x144] == [city+0x138]+4`.
5. City name via `[city+0x78]` vs the UI; `[city+0x118]` = 64/128/256 on small/medium/large.
6. `[sim+0xEC]` on two consecutive days (+1); epoch from the UI date; `[sim+0x3C]` at each speed.
7. `[sim+0x40]` and city slot 102 in mayor mode and in god mode.

# SiMCP 4 static RE: cheats (SC4 1.1.641)

Static analysis only. Scratch files are in `<workbench>\re\cheats\` (d.py, ids.py, scan.py, h1-h3.txt, app84.txt).

## 1. Answers

**Q3 (the matching path is covered first, because every other answer depends on it)**
- **Where cheats are typed:** the cheat dialog handler is 0x79BFC0 (CONFIRMED by code).
  - On message 0x9B1552D5 (Enter in the edit box) it reads the text from the edit control `[this+0x110]` (slot 45). An empty line closes the box.
  - It then calls `DoDefaultCheatCodeProcessing(line, &id)` on `[0xB43CAC]`, which is the cheat manager (set at 0x6022A4 from app slot 33).
  - **If id == 0 (no cheat matched), the line goes to the command server `[0xB43CB0]` slot 19 (+0x4C) `(text, len, 0)` and runs as a game command line.** Commands such as CreateGZLog (creates a file) and ExecuteScript become reachable this way. The community command docs say the same.
  - The line is appended to an in-memory typed-line history at 0xB4DFDC (20-byte cRZString entries). Holding Ctrl or Shift (VK 0x11/0x10) while pressing Enter keeps the box open.
  - The command OpenCheatCodeDialog exists. That Ctrl+X opens the box is community knowledge; I did not find the accelerator.
- **DoesCheatCodeMatch (slot 21, 0x92184B)** (CONFIRMED by code):
  - It returns 0 at once if cheats are disabled (byte `+0x54`) or the line is empty.
  - It copies and lowercases the line (0x90EAC5, ASCII only). It then walks the registered list `+0x28` in list order and lowercases each name.
  - **A name matches iff `line.find(name) == 0`.** So matching is case-insensitive, prefix-only, with no word boundary: "GOLD" matches GOL, "rpx" matches RP, "flora2" matches Flora.
  - It returns 2 for an exact length match, 1 when the line is longer, and 0 otherwise. The first match wins, and `*id` = node+0x1C.
- **Handlers get the original line, not the lowercased copy.** data2 is the cIGZString. They split it with the whitespace tokenizer 0x914E14; token 0 is the cheat word.
  - Some lowercase their argument before comparing: Stopwatch, GP, Flora, TerrainQuery.
  - Casper's "off" and udriveit's "reset" are compared raw, so they are case-sensitive.
  - Names cannot contain spaces: only token[1] is used.
- **SendCheatNotifications (slot 20, 0x920ECE)** (CONFIRMED by code):
  - It returns at once if `+0x54` is 0.
  - For the AddNotification list (`+0x2C`; node +8 target, +0xC id filter, 0 = all) it builds a stack cGZMessage {0x230E27AC, id, line} and calls the target's slot 3 synchronously.
  - For the AddNotification2 list (`+0x30`) it builds a heap cGZMessage2 the same way and calls DoMessage.
  - It always returns false, so handler results are lost.
- **DoDefaultCheatCodeProcessing (slot 22, 0x921621)** (CONFIRMED by code):
  - Path: DoesCheatCodeMatch (slot 21), then SendCheatNotifications (slot 20), then it records history through 0x9215A3.
  - If nothing matched, it only checks the enable/disable password strings (`+0x58`/`+0x6C`, then slot 23 EnableCheatCodes).
  - It has **no** command-server fallback; that fallback lives only in the dialog.
- **ExecuteCheat command (0x5C9A8D)** (CONFIRMED by code): it reads string parameter 0xABAC26B5 and calls `[0xB43CAC]` slot 22. That is the same match, notification and history path as typing the cheat, without the command fallback. The result is 2 at start and 0 when it matched with id != 0.
- **Correction to the framework report:** `cISC4App+0x30C` (slot 33) is the cheat manager. The object built by 0x7E9300 (vtable 0xABCB60, owner of the view cheats) is at `+0x310`. `cSC4App+0x10+0x308` is the same field as `cISC4App+0x30C`.

**Q1/Q2 (one entry per cheat: id, handler, effect, needs a city or not, rating)**

Owner DoMessage functions:

| Group | Handler | Owner |
|---|---|---|
| Budget | 0x693450 | budget sim, this = sim+4 |
| Utilities | 0x69CCE0 | building development sim (BDS), this = iface+8 |
| Time of day | 0x445CC0 | cSC424HourClock |
| App | 0x451C30 | app |
| Names | 0x45C1A0 | cSC4City |
| Paths / automata | 0x50DD30 | automata |
| Effects | 0x594263 | effects manager |
| Flora | 0x6B2F70 | flora sim |
| Time sim | 0x703420 | time sim |
| View | 0x7F3510 | 3D view; thiscall(id, line), ret 8 |

Player cheats:
- **RiskyMoney 0xCBF31943** (CONFIRMED by code). Needs a city, mayor mode only (city slot 22 GetEstablished, byte city+0x25, must be true).
  - Calls budget slot 7 DepositFunds(10000).
  - Increments a counter at budget+0x50 and rolls rand < 1 - 1/(1+0.2n).
  - On success it gets disaster 0x42963812 (riot) from `[0xB43D3C]` slot 7 and starts it with slot 6 at x = SizeX·(0.375+0.25·rand), z likewise. It resets the counter if the riot started.
  - No mayor-rating change seen. **SAFE but has a side effect (riot).**
- **WeaknessPays 0x4AB87766**: SetTotalFunds(GetTotalFunds()+1000) (slots 5/6), always, no other effect. SAFE (CONFIRMED).
- **HowDryIAm 0x491865E1**: sets BDS byte +0xDD = 1, which is CheatIgnorePlumbing, readable at BDS slot 54. Set only, no way to turn it off. SAFE (CONFIRMED; the names come from the Mac vtable).
- **FightThePower 0x08DAD89A**: sets BDS +0xDE = 1 (CheatIgnorePower, slot 55; the growth code reads it at 0x695495). Set only. SAFE.
- **Barstuck 0x6AB6A2D7**: **toggles** BDS +0xE1 (CheatCoffeeBar, slot 58). SAFE.
  - BDS is `[0xB43D68]` (city slot 53, vtable 0xAB0AF8). All of these flags are zeroed in 0x69A000 at 0x69A1DB-F3 (LIKELY on city init) and are not saved.
- **WhatTimeIzIt `<hour>`**: cISC424HourClock SetHour(atoi) (slot 11). This is the visual day/night clock, not the sim date. SAFE (CONFIRMED).
- **Stopwatch `pause|resume|magnify <n>`**: Pause(1/0) (slot 24); SetTimeMagnification((float)atoi n) (slot 21). The 3-token form is required for magnify. SAFE; clamp n.
- **ShowTime**: 0x78C590 toggles flag 0x800 (visible) on window 0xCA5E6261, the small "<ShowTime>" clock panel (layout 96A006B0/AA5E60D1). SAFE UI (CONFIRMED).
- **WhereRUFrom `<name>`**: city slot 13 SetCityName(token1). **HelloMyNameIs `<name>`**: city slot 17 SetMayorName(token1). One word only. Needs a city. SAFE (CONFIRMED).
- **DollyLlama**: toggles global byte 0xB20D50. 0x4205D0 (vtables 0xA83AEC/0xA9B794) then loads S3D type 0x5AD0E817 group 0xBADB57F1 with instance+0x100, i.e. alternate models. Cosmetic (LIKELY). SAFE.
- **Casper `[off]`**: global byte 0xB09968 = 1, or 0 only for the exact word "off". It is read by the automata code at 0x50AFD0, 0x54C2E0 and 0x54C5B0. Probably ghosted automata (GUESS). SAFE.
- **toll**: pushes view input control 0x4D9E80 (view slot 25), LIKELY the hidden toll-booth tool. Needs a city. SAFE-ish UI tool.
- **Flora `on|off|preserve [off]|propogation [off]…`**:
  - on: flora+0x28 = 1. off: 0x6B19E0(0).
  - preserve: +0x2B = 1, or 0 with "off".
  - propogation: +0x2A = +0x29 = 1.
  - Flora growth tuning (GUESS on meaning). DEBUG.
- **Effect `kill | <name> …`**: "kill" removes cheat effects (0x58DCE0); otherwise 0x592A10 spawns a named effect. Arguments not decoded. DEBUG (cosmetic).

Developer / debug cheats:
- **udriveit `[reset]`**: no argument calls 0x506850, which creates the U-Drive-It controller (0xC0 bytes, ctor 0x565480, global 0xB21D74) and enters drive mode. "reset" calls city slot 49 (situation manager) slot 33. DEBUG-UI (needs keyboard control).
- **NoCSI**: dispatch manager `[0xB43D04]` slot 22, then 0x46D3A0(4, 0). Meaning unknown (GUESS). DEBUG.
- **GP `[on|off]`**: app byte this+0x5D0 (toggled when no argument). If it changes, calls `[this+0xC]` slot 18 (pause when the window loses focus). SAFE app setting.
- **ForceIdle**: posts kMessageGameInIdleState 0xBA44EB51 (data 60) through `[0xB43CCC]` slot 4. DEBUG.
- **WatchMeMove**: view+0x124 = 1 (one-way). **TerrainQuery `[off]`**: view+0x126 = 1/0. **GOL**: pushes control 0x4BC310 (debug toy). **Zoneria / TastyZots**: toggle a debug view control (type 0x8A7A1C2C, vtable 0xA88084). **SizeOf `<f>`**: f clamped to [0.9, 64], passed to 0x7CD6E0 on `[view+0xF0]` (some view scale, GUESS). All DEBUG-UI, effects GUESS, but no files and no exceptions seen.
- **RenderProp / RP `<prop> [value]`**: 0x7ECDA0 sets a render property; with no arguments it shows a usage string through view slot 45. DEBUG: can break rendering.

Refuse:
- **Recorder**: REFUSE. 0x7F0840(1) uses "RecordedAnimations" (LIKELY writes files).
- **CreateException `<kind>`**: REFUSE (crash). 0x5FA520 → 0x5FA340 deliberately triggers access violation, illegal instruction, division by zero, stack overflow or stack trash (CONFIRMED by the strings).
- **FPS `<n>` 0x0AC07E24**: missing from a39 because it is registered with another string constructor at 0x703385 (name at `[0xB0D458]`), and **not debug-gated**. It sets time sim S+0x84. OnTick computes `idiv 1000/fps` at 0x703EED when not paused, so "FPS 0" or "FPS abc" divides by zero and crashes. REFUSE, or allow only a validated 1..1000.
- **Debug-gated** (registered only if app slot 21, byte +0x644): REFUSE all.
  - Moolah `<n>`: SetTotalFunds(atoi64 n), CONFIRMED.
  - SimDate `<m> <d> [y]`: date slot 6 Set, then AdvanceTime.
  - Snow: 0x58F160. HeapCheck: toggles effects+0xDD4.
  - Adv (parses "guids"), Tutorial, DrawPaths `<n>` / HidePaths, Controllers, csitrigger.
  - PlopAllLots, PlopAllBuildings, LotPlop / BuildingPlop (0x4C0430 controls).
- **Unlisted id 0x4A82253E**: handled in the view (sets view+0x446 = 1); the registration site was not found.

**Q4 Record of use** (CONFIRMED by code)
- The manager keeps a history vector at `+0x40` of 16-byte records {id, time (0x91307C), kind, 0}. kind is 0 = issued, 1/2 = state on/off (SetCheatState slot 17). History is on by default (`+0x24` = 1 in the ctor 0x921970).
- DoDefault/ExecuteCheat add a record. A direct SendCheatNotifications (slot 20) does not.
- HasUserUsedCheat(id) (slot 14, 0x920E7E) counts the kind-0 records for that id.
- City Write 0x45C5B0 (cSC4City cIGZSerializable vtable 0xA875F4, slot 3) **first calls ClearCheatCodeHistory (slot 10, 0x921310)**. It then writes GetCheatCodeSaveData (slot 11) into chunk 0x89D9B9EE/0x69D9B9F1 v1. Read 0x45CB10 calls SetCheatCodeSaveData (slot 12).
- So use records do not survive a save. Only the enabled-state set (`+0x34`) and an opaque blob persist; none of the cheats above use states.
- No statistic, flag or mayor-rating change was found. The typed-line list at 0xB4DFDC is memory only.

## 2. Layouts
- **cGZCheatCodeManager** (`[0xB43CAC]`): vtables 0xACFCD0 (+0), 0xACFC98 (+4), 0xACFC80 (+8).
  - +0x24 u8 history enabled.
  - +0x28 registered-list sentinel. Node: +0 next, +8 cRZString name, +0x1C id.
  - +0x2C / +0x30 notification lists.
  - +0x34 state set (count +0x38).
  - +0x40 / 44 / 48 history vector.
  - +0x4C / +0x50 save blob pointer / length.
  - +0x54 u8 cheats enabled.
- **Windows slot order** = the Mac names: 9 EnableHistory, 10 ClearHistory, 11 Get/12 SetSaveData, 14 HasUserUsedCheat, 15 GetCheatState, 16 GetCheatsWithEnabledStates, 17 SetCheatState, 20 / 21 / 22 as above.
- **Readable state:**
  - BDS `[0xB43D68]`: +0xDD water, +0xDE power, +0xE1 coffee bar.
  - Budget+0x50: RiskyMoney counter.
  - Bytes 0xB20D50 (DollyLlama) and 0xB09968 (Casper).
  - Time sim S+0x84: fps.

## 3. Recipes for the bridge (main thread only)
- `mgr = app->vtbl[33]()` (or `[0xB43CAC]`).
- `id = 0; r = mgr->vtbl[21](cIGZString* line, uint32* &id)` (thiscall, ret 8; 0 = no match).
- Refuse unless `id` is on the allow-list **and** the arguments are validated, and log it.
- Then `mgr->vtbl[22](line, &id)`. This is the same path as the player's cheat box minus the command fallback, and it records history.
- Never send free text through the dialog path or the command server.
- Proposed allow-list: WeaknessPays, RiskyMoney (warn about the riot), HowDryIAm, FightThePower, Barstuck, WhatTimeIzIt 0-23, Stopwatch with a clamped magnify, ShowTime, WhereRUFrom / HelloMyNameIs (single word), DollyLlama, Casper, GP.
- Everything here is cheat-class, not honest play.

## 4. Open questions (live tests)
- Type "gold": does GOL fire? (Expect yes, prefix match.)
- RiskyMoney ×5 in mayor mode: watch funds +10000 each and a riot disaster; read budget+0x50 before and after.
- Read BDS +0xDD/+0xDE/+0xE1 before and after HowDryIAm / FightThePower / Barstuck; then save, reload and read again (expect 0).
- After DoDefault "weaknesspays": does HasUserUsedCheat(0x4AB87766) return 1? Save, reload: expect 0.
- Stopwatch "magnify 0": stable? Effect `<name>`: arguments and placement. NoCSI, SizeOf, Zoneria, TastyZots: what visibly changes?
- Is Ctrl+X the accelerator for OpenCheatCodeDialog?

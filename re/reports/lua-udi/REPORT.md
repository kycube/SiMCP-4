# RE report: lua-udi (Lua, U-Drive-It missions, driving, My Sim), SC4 1.1.641, static only

Scratch folder: `<workbench>\re\lua-udi\`. It holds `collector.txt` (all 47 game.* C functions), `sc4game_reg.txt` (sc4game.* registrations), `drive_panels.txt` (the 42 "Drive X Panel" exemplars), disassembly dumps `d_*.txt` and scripts s1..s47.

## 1. Answers

**Q1. Lua.** There are three entry points.

- **(a) The app's Lua state.** This one runs the advisors, automata and city situations. CONFIRMED.
  - Access: cISC4App slot 47 GetLuaInterpreter returns `[A+0x658]` (cISCLua*).
  - Object: cSCLua, ctor 0x8809E0, base cGZLua5Thread. Vtables: +0 0xAC4444, +8 0xAC42C0 (thread), +0x40 **cISCLua 0xAC4148**.
  - QI 0x8806C0: iid 0xEA10C4A2 returns this+0x40; any other iid goes to cGZLua5's QI (iid 0x6B2811A6).
  - The vtable has 78 slots, exactly the gzcom-dll order. Thunks checked: slot 6 GetTop, 24 ToString, 37 GetGlobal, 51 CallProtected 0x880490 -> 0x8B8F30, 53 DoFile, **54 DoString -> 0x8B7FE0**, 55 DoBuffer.
  - DoString takes the global Lua lock (0x892A0A / 0x8929E0) and calls lua_dostring 0x8BE620(L=[thread+8], text). It returns **an int status in EAX (0 = OK)**, although the header declares void.
  - The results stay on the stack (Lua 5.0 load + pcall with MULTRET). LIKELY.
  - SC4LuaExtensions' source says the advisor and automata scripting use this same object. Advisor system slot 10 GetScriptingContext (`[sys+0x58]`) should be the same object. LIKELY.
- **(b) cGZLuaScriptServer** (service 0x4BD10133). CONFIRMED.
  - Fetched by the wrapper 0x4496F0. Ctor 0x8B07C0, size 0x4C, vtables 0xAC8710 / 0xAC86DC / 0xAC86C4, cIGZLua5 at +0x34.
  - Its 25 slots match cIGZLuaScriptServer.h exactly:
    - 5 GetLua
    - **6 RunScriptString(script, fileName, args) 0x8B32B0**
    - 7 RunScriptFile(fileName, args) 0x8B1A80
    - 8 KillScript
    - 9 / 10 Pause / Resume
    - 19 EnumerateScriptIDs
    - 20 GetScriptInfo
    - 21 GetCurrentRunningScriptID 0x8AECF0
    - 22 / 23 Get / SetScriptAutoYield
    - 24 GetLastCreatedScriptID
  - It is a separate Lua state where scripts run as coroutines. They see `sc4app.*` (game commands, WaitForMessage2), not `game.*`.
  - It returns a script id, not values. Output only goes through `print`, which SC4LuaExtensions writes to its log.
- **(c) The ExecuteScript command** (id 0xABAC067C; app handler DoMessage 0x5C8B30, case at 0x5C9758). CONFIRMED.
  - `ExecuteScript <full path> [args]` checks that the file exists (0x919E96) and calls server slot 7.
  - `ExecuteScript <t> <g> <i>` loads the resource and runs it.
  - Status is 0 when the script id != -1, else 2. No result value comes back. A plain `DoString` / `RunString` command does not exist.
- **game.\* C functions.** CONFIRMED by data.
  - They live in a static vector at **0xB207CC (begin) / 0xB207D0 (end)**, filled by the static initializer 0x40B8D0. Entries are 12 bytes: {char* name, lua_CFunction, bool isGlobal}.
  - **Read-only:** trend_value 0x4097E0, trend_slope 0x409690, trend_count 0x409900, ordinance_is_on 0x409A50, ordinance_is_available / name / description / enact_fee / repeal_fee / monthly_cost, difficulty_level 0x40A120, building_is_group, event_building_distance, event_disaster_distance, mysim_distance_to_closest_building / _landmark_or_reward, mysim_local_school_grade / hospital_grade, reward_instance_count 0x40A8E0, get_reward_building_state 0x40AA60, is_tutorial, advice_subject, advice_info.
  - random_chance 0x40A810 has a side effect: it consumes the RNG.
  - **State-changing:** ordinance_set_on 0x409B80 / set_off 0x409B00, unlock_reward_building 0x40B760, trigger_event 0x40B5B0, expire_advice 0x409F80, retire_advice 0x409FD0, nd_cancel 0x40AC10, event_feedback 0x409E40, mysim_dispatch_tool 0x40A790.
  - **UI:** camera_jump 0x40AF90, camera_zoom 0x40B1F0, tool_plop_network / zone / building / flora 0x40C720 / 0x40C740 / 0x40C760 / 0x40C780 (these select tools), tool_button 0x40C8B0, window_budget / map / graph / query.
  - **Globals:** print 0x5FB850, _dofile_from_resource 0x5FC020, _combine_guids 0x40AD10.
  - City data is in the Lua variables `game.g_*` (about 300 names in adv_game_data.lua, e.g. g_city_r_population). The advisor system pushes them (SetGlobalValue, slots 12 / 13).
- **sc4game.\* functions.** CONFIRMED.
  - Registered through the game data registry (GetSystemService 0xEBE0E860, iid 0xE898ED03; helpers 0x68C180 add-table, 0x58DE80 add-function).
  - sitmgr: get_success_count 0x524760, activate_situation 0x525550, get_current_target 0x5247E0, get_active_auto 0x524830, get_target_name 0x52DB50, show_CSI 0x524880, num_targets_remaining 0x524910, plus num_targets / cur_target_index.
  - automata: create_automaton 0x51D220, create_controller 0x51D3C0, attach / detach_controller(_group) 0x51D510 / 0x51D640 / 0x51D750 / 0x51D860, get_source_building_count 0x51C7D0.
  - mysims: get_sim 0x42EBA0, get_count 0x42E460.
  - mysims_ui: pop_select_car / pedestrian_dialog.
  - **budget: total_funds, deposit_funds 0x690030 (adds money).**
  - effects.create_effect 0x58F720; aura.add_transient_effect 0x68BCA0, aura.end_strike 0x68BD50; civic.get_landmark_count 0x69D740.
  - SC4LuaExtensions (installed) adds dbpf.* and sc4game.camera / city / language.
- **Sandbox.** memo.lua-sandbox.dll is **installed**.
  - It overwrites the library tables (base 0xACB374..0xACB39C, io 0xACAF0C..0xACAF94, os 0xACAFF4..0xACB03C, 0xACABEC, 0xACACB4) so these raise "`x` not supported in sandbox": loadfile, loadstring, require, dofile, collectgarbage, string.dump, math.randomseed, os.date / execute / exit / getenv / remove / rename / tmpname / setlocale (with arguments), every io.* function and file:* method except io.write / io.flush.
  - It also hooks f_parser at 0x8BC1E5 so binary chunks are refused.
  - The bridge's C-level DoString is **not** affected, but a chunk cannot use loadstring or dofile inside.
- **Is Lua a safe read-only channel?** Only with an allow-list.
  - Reading `game.g_*`, the read-only getters above and the sitmgr / mysims getters has no side effects.
  - The same state runs the advisor triggers, so: never assign globals, avoid random_chance, and refuse the state-changing, UI and sc4game.budget / automata / aura / effects calls.
  - Main thread only.

**Q2. Missions.**
- **Manager.** City slot 49 returns `[city+0x1EC]`, cSC4CitySituationManager (CLSID 0x0BB14381). CONFIRMED.
  - vtable **0xA97E58**, IID **0x6BB1437A**, QI 0x5246B0.
  - Other sub-objects: +4 cIGZMessageTarget2, +0xC serializable, +0x10 window target (vtable 0xA97E08).
  - **All 34 cISC4CitySituationManager.h slots match** (the getter bodies give the fields in section 2).
- **How offers are created.**
  - About 40 situations are defined in Lua: `create_advice_citysituation(guid)` creates a cSC4CitySituationAdvice (clsid 0x8BE3753B, iid 0x6BEB1E8A). Its slot order matches the header at the slots checked: 11, 15, 18, 46, 48, 49, 51.
  - Advisor 29 (City Situations) activates them like any advice when the trigger is true. Examples: "Road Vehicle Training Mission" 0x8C151EFD (civilian car, reach a residential target, trigger `get_success_count == 0 and g_city_r_population > 0`, training mission); Tank training 0x0C151F05; Freight-train training 0x2C1725C1.
  - AdviceAdded 0x8A09FA64 reaches sitmgr DoMessage 0x52EB80, which calls 0x52A380 to register the situation. The player then sees mission indicators (CSI) over matching vehicles: visibility byte +0x9F0, slots 26-30.
- **How the player starts a mission.**
  - Clicking a mission indicator calls InitiateSituationForOccupant (slot 22).
  - Clicking a vehicle in the "Earned Vehicles" catalog (My Sim mode) calls InitiateSituationByAutomataGroup (slot 23, 0x52AB00). LIKELY for the UI callers. It calls slot 21 when a situation is active for that group, else StartJoyride (slot 24).
  - InitiateSituationByGuid (slot 21, 0x52A8B0; Lua `activate_situation`): GetAdvisor(0x1D), finds the advice by guid, picks a relevant automaton, then calls **slot 36 ShowSituation 0x52E750(advice, automaton, 0)**.
  - Slot 36 sets the active situation (+0x9F4) and status 4, then posts **kSC4MessageShowSituationPopup 0xEBB67EF7**.
  - The DoMessage handler calls 0x52E910. It pauses the simulation (scope 0x5F9320), shows the mission status panel (View3D slot 56; panel id = drive-panel exemplar property 0xEC1B2361) and opens the modal **offer dialog 0x2BB16D50**.
- **Dialog buttons** (handler 0x52CAB0; window message type 3, `[msg+4]==0x287259F6`, button id at `[msg+8]`). CONFIRMED.
  - **Accept 6:** sitmgr slot 37 0x5276A0 = Begin. Status 3, timer +0xA88 = 0, posts **ActivationChange 0xABBBCA64**, starts driving the active automaton.
  - **Free Ride 7:** 0x52BFB0 drops the situation (0x52BF00), then **StartJoyride(auto, 1, 0)**.
  - **Cancel 1:** if 0x524580 holds (LIKELY: an evil-twin alternative exists) posts 0x6BB350E4; else drops the situation. 0x525330 closes the dialog.
- **Mission state** (offsets in section 2).
  - Status `+0xA48`: 4 offered, 3 running, **1 success**, **2 failure**, 5 cancelled / no situation. The 3 and 4 values come from code; the meanings of 1 / 2 / 5 come from the result layouts (LIKELY).
  - The time limit comes from the Lua `get_time_limit(dist, maxSpeed)`.
  - Target reached: ProgressChange 0xAC083D7D (posted at 0x52BBC0).
- **How it ends.**
  - SetStatus 0x524C40(1 or 2) sets a delay from the advice's GetDelayAfterDisabled.
  - The success handler 0x52C190 applies advice slot 46 SuccessAura to the aura simulator `[0xB43D60]` slot 7 and slot 48 **SuccessMoney to the budget `[0xB43D64]` slot 7**. The failure handler 0x526720 does the same with slots 49 / 51.
  - Result dialog: 0x0BBC06B6 for status 1 / 5, 0x4BBC080F for status 2 (root 0xEBBC081E, Close id 1).
  - The success count (map at +0xA3C) increments. Training missions are never offered again. reward_guid moves a reward toward unlocking.

**Q3. Driving.**
- **The PlayerDrive control** (kViewInputControlPlayerDrive **0x2B709676**). CONFIRMED.
  - Single global instance **`[0xB21D74]`**. Ctor 0x565480, size 0xC0, vtable 0xA9D9B0.
  - **The driven vehicle is the cISC4Automaton\* at `[ctrl+0x30]`.**
- **Starting to drive: 0x506850(cdecl: automaton, cIGZMessageTarget2\* callback).**
  - Creates the control and calls View3D (`[0xB43DC4]`, cISC4View3DWin) slot 25 SetCurrentViewInputControl(ctrl, 2).
  - Calls automaton slot 64 SetPriority(0xFF) and vehicle manager `[0xB43D44]` slot 23 (camera follow, LIKELY).
  - Calls 0x565160 SetAutomaton. It uses automaton slot 50 FindDrivingAutomaton and the exemplar property 0x2BE8FBF3 (drive-panel instance) to show the panel.
  - Callers: StartJoyride 0x524E20, sitmgr slot 35 SetDriving(bool) 0x5252D0 (false removes the control with View3D slot 26), My Sim code 0x437411, the "udriveit" cheat 0x50DF04.
  - IsPlayerDriving 0x506940 = View3D slot 24 GetCurrentViewInputControl()->GetID() == 0x2B709676.
- **Input (keyboard).**
  - Key down = control slot 14 OnKeyDown 0x566C60(vk, modifiers):
    - auto-repeat (modifiers & 0x40000000) is ignored;
    - **ESC (0x1B) exits** through control slot 27;
    - keys are ignored while sitmgr CountdownIsInProgress (slot 32);
    - otherwise the key map `[ctrl+0xB0]` slot 14(vk) gives a drive command (13 = none), then key effects run (0x566A70(cmd, down)), else **0x563D40(cmd)**.
  - Key up = slot 15 0x566CF0, which ends in **0x564060(cmd)**.
  - Both end in **automaton slot 60 HandlePlayerDriveCommand(cmd, bool down)** (+0xF0), plus panel button highlights (left / right buttons 0x8BCB93FC / 0x6BCB93F5) and sounds.
  - Drive commands (_keycodes.lua): 0 ACCELERATE, 1 BRAKE, 2 TURN_LEFT, 3 TURN_RIGHT, 4 OFF_ROAD, 5 CLIMB, 6 DIVE, 7 SPECIAL (horn, siren, hose), 8 AIM (mouse), 9 ALTERNATE, 10 LAND, 11 POWERUP, 12 POWERDOWN.
  - Default keys: arrows / WASD / numpad, Shift, Home / E, End / C, Space, Enter, period, comma.
- **Input (mouse):** AIM / shoot is OnMouseDownL 0x5655D0.
- **The bridge can steer without real key presses** through these same functions (recipes R4).
- **The panel commands** Min / Max / ToggleDrivingPanel (0xAC1F0449 / 0xCC1F0457 / 0xAC1F045D, table 0xB0A110, registered in 0x563970) only resize the panel. LIKELY.
- **Automaton (iid 0xA9B40F05) slots** — the vtable follows cISC4Automaton.h.
  - Checked by call patterns: 31 CheckAutomataFlag, 44 / 45 / 47 effects, 50, 57 FindState, 60, 64, 67 GetAutomataGroup.
  - Taken from the header order (LIKELY): **7 GetPosition(cS3DVector3&), 15 GetOrientation, 34 GetCurrentSpeed, 37 GetMaxSpeed, 38 GetActualSpeed**.

**Q4. Free ride and vehicles.**
- **StartJoyride, slot 24 0x524E20(automaton, bool, msgTarget).** CONFIRMED.
  - Sets byte +0xA98, broadcasts ActivationChange 0xABBBCA64 (data 1), then calls 0x506850. There is no situation and no reward.
- **Vehicles:** 42 type-0x23 exemplars (group 0x690F693F, "Drive X Panel").
  - Car, Taxi, PoliceCar, PoliceVan, Ambulance, Fire Truck, Hearse, School Bus, CityBus, MayorLimo, IceCreamTruck, News Van, garbage_truck, Toxic Waste Truck x2, army_truck, TankCamo / TankDesert;
  - Freight / Passenger / SteamEngine train, MonoRail;
  - Police / Medical / News / attack helicopters, Cropduster, Fireplane, Skywriterplane, JetFighter, SkyDiver, UFO;
  - FerryBoat, Passenger FerryBoat, Off Shore, Yacht, TugBoat, MotorBoat, Speed Boat, Fishing Boat, Generic Boats, Metal Whale.
  - Properties: 0x2BE8E61B panel layout, 0x2BE8E6CB / 0x2BE8E834 control images / labels, 0xABE8E6CC, 0xEC1B2361 mission status panel.
- **Choosing and placing:** the Earned Vehicles catalog calls slot 23 with the vehicle's automata group. It uses an existing automaton of that group or one created at a source building. The vehicle is greyed out until such a building exists (get_source_building_count). LIKELY.

**Q5. My Sim.**
- **Agent simulator:** city slot 71 returns `[city+0x1AC]`, vtable **0xA85544** (CLSID 0x29E37DEC; its QI first tests 0xA9E37EBB, LIKELY the IID). All 13 slots = the header.
  - 5 GetActiveMySims 0x42F4A0
  - **6 MoveIn 0x42E990** (7 arguments)
  - 9 MySimLivesHere
  - 10 CancelMoveIn
  - 11 / 12 Set / GetActiveUIPanelSim (`[agent+0x38]`)
  - **The five sims are at `[agent+0x14]`[0..4]** (cISC4MySim\*).
- **cSC4MySim** (clsid 0x4A1DBBBF): cISC4MySim is at obj+0xB8, vtable **0xA85080**. **All 69 header slots match** (the getter bodies give the fields in section 2).
- **Move-in flow.** The My Sim panel (ToggleMySimPanel 0x6A935CA8): pick a face, name, sign. Agent MoveIn hands it to the first inactive sim's slot 4 MoveIn 0x42D880. That installs a move-in view input control (0x4C bytes, ctor 0x439FC0). The player clicks a house, which runs ChangeResidence / SetResidence and then AnnounceMoveIn. Messages: MySimMovedIn 0xEA3ADA33, MySimsChanged 0xAA25827C.
- **Status:** GetResidence / GetJob / GetHomeName / GetJobName / GetJobTitle, GetAge, GetWealth, EQ / HQ text, LeaveForWork / ReturnHome (commute).
  - Mood = the moods of that Sim's advisor balloons (advisor ids 1-5; GetCurrentBalloonAdvice 62/63). LIKELY.
  - Driving the Sim's own car: CanUDriveIt 64 / **EnterUDriveIt 65** / ExitUDriveIt 66 (they go through `[I+0x154]`).
  - DoScriptCommand(40) with the header's ids: MoveOut, Die, Retire...

## 2. Object layouts
- **Situation manager (S):**
  - +0x9F0 CSI visible
  - +0x9F4 active cISC4CitySituationAdvice\*
  - +0xA18 tracked automata count
  - +0xA28 dialog window
  - +0xA3C success-count map
  - +0xA48 status
  - +0xA4C active automaton
  - +0xA50 target occupant
  - +0xA5C number of targets
  - +0xA60 current target index
  - +0xA64 bool
  - +0xA88 post-end delay
  - +0xA8C elapsed seconds
  - +0xA90 countdown
  - +0xA94 time limit
  - +0xA98 driving flag
  - Max CSI is the global byte 0xB21D34.
- **PlayerDrive control:** +0xC id; +0x1C View3D; +0x30 automaton; +0xA4 panel window; +0xB0 key map. Global `[0xB21D74]`.
- **cISC4MySim I** (= obj+0xB8):
  - +4 slot
  - +8 state (0 = not moved in)
  - +0xC residence occupant
  - +0x28 job occupant
  - +0x48 vehicle key
  - +0x54 wealth
  - +0x5A sign
  - +0x5B male
  - +0x5C bio
  - +0x70 age
  - +0x74 / +0x78 bitmap id / file
  - +0xB0 home-name pointer
  - +0xC4 HQ (float)
  - +0x154 automaton / dispatch object
- **cSCLua:** thread at +8 (lua_State\* at `[+8+8]`); cISCLua at +0x40.
- **Script server:** +0x24 initialised; +0x34 cIGZLua5; +0x48 running-script data.
- **Global:** `[0xB43DC4]` = cISC4View3DWin\*. Slots CONFIRMED: 24, 25, 26, 56 ShowMissionStatusPanel, 57 Hide.

## 3. Bridge recipes (main thread, under SEH)
- **R1 lua_eval(chunk), read-only.**
  - `L = app->vtbl[47]()`, then `top = L->vtbl[6]()`, then `st = L->vtbl[54]("return <expr>")`.
  - Read `GetTop()-top` values with 15 IsString / 23 ToNumber / 24 ToString / 29 ToBoolean, then `SetTop(top)` (slot 7).
  - Reject a chunk if `st != 0`.
  - Enforce an allow-list: `game.g_*`, the read-only getters, sitmgr / mysims getters. No assignments; run only in the city view.
- **R2 mission_status():** `S = city->vtbl[49]()`.
  - Slot 7 status, 6 situation (QI 0x6BEB1E8A).
  - On the situation: AsAdvice (slot 3), then advice slot 18 / 20 for title / message text.
  - Slots 13 / 14 / 15 time limit / elapsed / remaining (float in ST0); 11 / 12 targets; 16 target name (cIGZString&); 18 money (int64&).
  - Offered missions = the active advices of advisor 29.
- **R3 accept / free ride / decline (honest):**
  - When the offer dialog is modal (root 0xEBB16D71), click 6 / 7 / 1 with GZWinClickButton.
  - To open an offer: the player's route is the mission indicator or catalog click; Lua `activate_situation(guid)` or S slot 21(guid, 0, 0) is an equivalent, LIKELY honest.
  - Calling slot 37, or StartJoyride on an arbitrary automaton, bypasses the dialog: **cheat-class**.
- **R4 steer:**
  - `ctrl=[0xB21D74]`; require ctrl != 0 and `[ctrl+0x30]` != 0.
  - Press: thiscall ctrl->vtbl[14](vk, 0); release: ctrl->vtbl[15](vk, 0). This is the player's own keyboard path, including the key map and effects.
  - Or command level: 0x563D40(ecx=ctrl, cmd) for down / 0x564060(ecx=ctrl, cmd) for up.
  - Hold = down, wait N frames, up. ESC (vk 0x1B) exits.
  - Telemetry: auto = `[ctrl+0x30]`; slot 7 GetPosition(&v3), 15 GetOrientation(&v3), 34 / 38 speeds, 67 group.
- **R5 My Sims:**
  - Read: walk `[agent+0x14]`[0..4]; for each with IsActive (I slot 20) read the getters or fields above; the name comes from AsAdvisor (I slot 3).
  - Move-in: agent slot 6 MoveIn, then a house click with the tool, the same as the player (honest). Slot 13 SetResidence directly would be cheat-class.
- **Never through Lua:** deposit_funds, unlock_reward_building, ordinance_set_*, create_automaton, trigger_event (cheat-class or unsafe).

## 4. Live tests
1. Check `[[A+0x658]+0]`; also `[[A+0x658]] == 0xAC4148`? — no: the QI returns +0x40. Correct test: the QI-0xEA10C4A2 pointer's vtable == 0xAC4148, and it equals the advisor system's `[sys+0x58]`.
2. DoString("return 1+2"): EAX 0, GetTop grows by 1, ToNumber == 3. A syntax error gives EAX != 0 and leaves the stack top unchanged.
3. DoString("return game.g_city_r_population") vs residents `[[0xB43DA4]+0xA4]`.
4. ExecuteScript with a test file that prints: the output appears in SC4LuaExtensions.log, the command returns status 0.
5. City with residents: advisor 29 lists "Road Vehicle Training Mission". Click its indicator: status `[S+0xA48]` 0 -> 4; offer root 0xEBB16D71 modal.
6. Click Accept: status 3, `[0xB21D74]` != 0, `[ctrl+0x30] == [S+0xA4C]`, `[S+0xA94]` > 0. Then hold vk 0x26 through ctrl slot 14 / 15 and watch GetPosition change and GetCurrentSpeed rise.
7. Reach the target: status 1, funds change by success_money, result root 0xEBBC081E. Time out: status 2.
8. Click Free Ride: no situation (`[S+0x9F4]` == 0), driving active. ESC: `[0xB21D74]` returns to 0.
9. Does the simulation keep running while driving (`[sim+0xEC]` across 10 s)?
10. Move a My Sim in: `[agent+0x14]` slot I+8 goes 0 -> nonzero, I+0xC = the house occupant, age I+0x70 matches the panel.
11. After a load, is `[[0xB207CC]]` entry 0 name "advice_info"? Verifies the collector.

Open: the UI callers of slots 22 / 23 (mission indicator click, catalog click); the meanings of status 5 and the result layouts; MySim state values other than 0.

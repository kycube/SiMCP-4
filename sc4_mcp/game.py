"""The running game: launch, attach, status, quit."""

from __future__ import annotations

import os
import re
import struct
import time

from . import bridge, identity, launch, memory, regions, win32

# cISC4App vtable slots (gzcom-dll numbering, cIGZUnknown = 0..2; verified live where LIVE_FACTS says so)
APP_REQUEST_QUIT = 10        # RequestQuit(bool showDialog, bool saveFirst)
APP_GET_APP_STATE = 25
APP_GET_POPUPS = 23         # Get/SetPopupDialogsEnabled
APP_SET_POPUPS = 24
APP_GET_REGION = 35
APP_GET_CITY = 37
APP_GO_TO_REGION_VIEW = 12   # RequestGoToRegionView(bool askFirst)
A_NATION = 0x48
NATION_SET_ACTIVE, NATION_GET_REGION, NATION_ADD_REGION = 9, 11, 13
REGION_INIT, REGION_SHUTDOWN, REGION_SET_TERRAIN = 8, 9, 19
REGION_VIEW_VTABLE = 0xAB9260
RV_TILES, RV_TILE_SIZE = 0x118, 0x80
FN_RV_TILE_CITY = 0x7AEA00      # region view: (tile record, create) -> cISC4RegionalCity*
FN_RV_PLAY = 0x7ADC20           # region view: Play (LoadCity from the file, or a new city)
FN_RZSTRING_CTOR = 0x578390
SIM_MS_PER_DAY = 0x80     # simulator: wall-clock ms per day (the speed's throttle)
SIM_HIDDEN_PAUSE = 10       # cISC4Simulator::HiddenPause / HiddenResume (counted)
SIM_HIDDEN_RESUME = 13
BTN_MAYOR_MODE = 0xC988BC79  # city control panel (layout 0xC973B411): Mayor Mode
DLG_ESTABLISH = 0x6A414973   # Establish City dialog (layout 0x2A41436B)
FLD_CITY_NAME, FLD_MAYOR_NAME = 0xAA4149BF, 0xAA4149D2
DLG_CITY_SAVED = 0xAA8DEF97  # the "City Saved. (file)" notice, button OK (id 0)
REGION_GET_NAME = 3          # cISC4Region::GetName -> SC4String* (a cRZString)


CRASH_LOG = os.path.join(launch.ROOT, "crash.log")


def crash_log(pid: int | None = None, kinds: tuple[str, ...] | None = None) -> list[str]:
    """Faults noted in crash.log by the bridge (time, pid, kind, exception, address, registers, return addresses
    into the game) for one game process or all. Kinds: "first-chance" (a fault in the game's own code, outside
    SiMCP's calls - it may still be handled), "caught-in-call" / "caught-in-deferred" (inside a SiMCP call, caught
    by the bridge); older entries have no kind."""
    try:
        with open(CRASH_LOG, encoding="latin-1") as f:
            text = f.read().splitlines()
    except OSError:
        return []
    out = []
    for i, line in enumerate(text):
        m = re.search(r" pid (\d+) (?:(\S+) )?exception", line)
        if not m or (pid is not None and int(m.group(1)) != pid):
            continue
        kind = m.group(2) or "first-chance"
        if kinds and kind not in kinds:
            continue
        out.append(line + (" |" + text[i + 1].strip() if i + 1 < len(text) and text[i + 1].startswith("  ") else ""))
    return out


class GameError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


class Game:
    """One attached game process (SiMCP's own instance, with the plugin)."""

    def __init__(self):
        self.proc: win32.Process | None = None
        self.bridge: bridge.Bridge | None = None
        self.popen = None

    # ---- discovery
    @staticmethod
    def foreign_instances() -> list[int]:
        """Running SimCity 4 processes this server cannot open (e.g. started elevated by GOG Galaxy)."""
        out = []
        for pid in win32.find_pids(identity.EXE_NAME):
            try:
                win32.Process(pid).close()
            except win32.WinError:
                out.append(pid)
        return out

    def attach(self, timeout: float = 120.0) -> bridge.Bridge:
        if self.bridge and self.proc and self.proc.alive():
            return self.bridge
        proc = bridge.find_game()
        if not proc:
            foreign = self.foreign_instances()
            if foreign:
                raise GameError("a SimCity 4 started elsewhere is running (pid %s) and cannot be controlled"
                                % foreign[0], "it was started with administrator rights (GOG Galaxy does this); "
                                "close it, then call game_launch")
            raise GameError("SimCity 4 is not running", "call game_launch")
        end = time.time() + timeout
        while True:
            try:
                b = bridge.Bridge(proc)
                break
            except bridge.BridgeError as e:
                if "not loaded" in str(e) and time.time() < end and proc.alive():
                    time.sleep(0.5)
                    continue
                raise GameError(str(e), "start the game with game_launch (it installs the SiMCP plugin)")
        b.wait_ready(max(1.0, end - time.time()))
        b.attach()
        self.proc, self.bridge = proc, b
        return b

    # ---- lifecycle
    def launch(self, windowed: bool = True, width: int = 1024, height: int = 768, intro: bool = False,
               timeout: float = 120.0) -> dict:
        others = win32.find_pids(identity.EXE_NAME)
        if others and bridge.find_game() is not None and "simcp4.dll" in bridge.find_game().modules32():
            self.attach(timeout)
            return {"launched": False, "already_running": True, **self.status()}
        if not os.path.exists(bridge.PLUGIN_DLL) or not os.path.exists(bridge.BRIDGE_DLL):
            raise GameError("the SiMCP DLLs are not built", "run bridge\\build.bat (Visual Studio C++ x86 tools)")
        bridge.install_plugin(launch.USER_DIR)
        t0 = time.time()
        # Another SimCity 4 (the player's own, possibly elevated) may be open: run beside it.
        self.popen = launch.launch(windowed=windowed, resolution=(width, height), intro=intro,
                                   beside_other=bool(others))
        time.sleep(2)
        if self.popen.poll() is not None:
            raise GameError("the game exited right after starting (exit code %s)" % self.popen.returncode,
                            "another instance may be running, or the install is damaged")
        self.attach(timeout)
        # The region view registers its commands (LoadRegion, LoadCity...) when it is up: wait for it.
        self._wait_state(1, max(5.0, timeout - (time.time() - t0)))
        return {"launched": True, "seconds": round(time.time() - t0, 1), **self.status()}

    def status(self) -> dict:
        pids = win32.find_pids(identity.EXE_NAME)
        if not pids:
            out = {"running": False}
            last = crash_log()
            if last:
                out["last_crashes"] = last[-3:]
            return out
        try:
            self.attach(5.0)
        except GameError as e:
            return {"running": True, "controllable": False, "error": str(e), "hint": e.hint}
        state = memory.app_state(self.proc)
        out = {"running": True, "controllable": True, "pid": self.proc.pid,
               "view": memory.APP_STATES.get(state, state), "region": self.region_name(),
               "user_dir": launch.USER_DIR}
        city = memory.city_basics(self.proc)
        if city:
            out["city"] = city
        crashes = crash_log(self.proc.pid, ("first-chance",))
        if crashes:
            out["faults_in_game_code"] = crashes[-3:]
        faults = self.bridge.faults() if self.bridge and self.bridge.block else 0
        if faults:
            out["faults_caught"] = faults
            out["warning"] = ("the bridge caught %d fault(s) inside the game's code since it loaded; a simulator may "
                              "be stuck mid-update - save if needed, then quit_game and game_launch" % faults)
        return out

    # ---- regions and cities
    def region_name(self) -> str | None:
        """The loaded region's name (cISC4App::GetRegion -> cISC4Region::GetName, slot 3)."""
        b = self.attach(5.0)
        reg = b.vcall(b.plugin_state()["app"], APP_GET_REGION).ret[0] & 0xFFFFFFFF
        if not reg:
            return None
        s = b.vcall(reg, REGION_GET_NAME).ret[0] & 0xFFFFFFFF
        return memory.rz_string(self.proc, s) if s else None

    def _wait_state(self, want: int, timeout: float) -> int:
        end = time.time() + timeout
        s = memory.app_state(self.proc)
        while s != want and time.time() < end:
            time.sleep(0.25)
            s = memory.app_state(self.proc)
        return s

    def load_region(self, name: str, timeout: float = 120.0) -> dict:
        b = self.attach(10.0)
        if memory.app_state(self.proc) == 2:
            raise GameError("a city is open", "leave it first with leave_city (the game loads regions only from "
                                              "the region view)")
        # LoadRegion takes the region's display name (region.ini Name, e.g. "Timbuktu"), not its folder name
        # ("timbuktu" when the game made the folder itself) - verified live.
        rs = regions.list_regions(launch.USER_DIR)
        hit = next((r for r in rs if name.lower() in (r["folder"].lower(), (r.get("name") or "").lower())), None)
        if not hit:
            raise GameError("no region %r in SiMCP's user folder" % name,
                            "list_regions shows the regions: %s" % ", ".join(sorted(r["folder"] for r in rs)))
        display = hit.get("name") or hit["folder"]
        t0 = time.time()
        r = b.command('LoadRegion "%s"' % display, defer=True, timeout_s=timeout)
        if r.get("pending") or r.get("status") != 0:
            raise GameError("the game did not load the region (%r)" % r,
                            "regions copied in while the game runs are known only after a restart (quit_game, "
                            "game_launch)")
        state = self._wait_state(1, timeout)
        got = self.region_name()
        if state != 1 or (got or "").lower() != display.lower():
            raise GameError("region still loading or not loaded (view %s, region %r)" % (state, got),
                            "call game_status")
        return {"region": got, "seconds": round(time.time() - t0, 1)}

    def _region_view(self) -> int:
        """The region view window (cSC4WinRegionView, vtable 0xAB9260) in the window tree."""
        from . import dialogs
        p = self.proc
        wm = dialogs.win_mgr(self)
        main = self.bridge.call_function(p.u32(p.u32(wm) + 4 * dialogs.WM_GET_MAIN), [], this=wm).ret[0] & 0xFFFFFFFF
        stack = [main]
        while stack:
            w = stack.pop()
            for c in dialogs._children(p, w):
                if p.u32(c) == REGION_VIEW_VTABLE:
                    return c
                stack.append(c)
        return 0

    def tiles(self) -> list[dict]:
        """The region view's city tiles: grid position, size (from the view's own tile records)."""
        self.attach(10.0)
        if memory.app_state(self.proc) != 1:
            raise GameError("the region view is not open", "leave_city goes back to it")
        p, v = self.proc, self._region_view()
        if not v:
            raise GameError("the region view window was not found", "game_status")
        b0, b1 = p.u32(v + RV_TILES), p.u32(v + RV_TILES + 4)
        out = []
        for i in range(min((b1 - b0) // RV_TILE_SIZE, 1024)):
            t = b0 + RV_TILE_SIZE * i
            out.append({"x": p.i32(t + 8), "z": p.i32(t + 0xC), "size": {0: "small", 1: "medium", 2: "large"}.get(
                p.u32(t + 0x18) & 0xFF, p.u32(t + 0x18) & 0xFF), "_rec": t})
        return out

    def open_tile(self, x: int, z: int, timeout: float = 180.0) -> dict:
        """Open the city tile whose grid square (x, z) is its north-west corner, as the region view's Play button
        does (0x7AEA00 makes the tile's regional city; 0x7ADC20 loads its file, or starts a new city in god mode)."""
        b = self.attach(10.0)
        end = time.time() + 5.0
        while True:                    # right after a region loads, its view is still being built: retry briefly
            try:
                tiles, v = self.tiles(), self._region_view()
                break
            except (win32.WinError, GameError):
                if time.time() > end:
                    raise
                time.sleep(0.5)
        hit = [t for t in tiles if (t["x"], t["z"]) == (x, z)]
        if not hit:
            raise GameError("no city tile starts at grid square (%d, %d)" % (x, z), "list_regions shows the tiles")
        r = b.call_function(FN_RV_TILE_CITY, [hit[0]["_rec"], 1], this=v)
        ref = r.ret[0] & 0xFFFFFFFF
        if not r.ok or not ref:
            raise GameError("the region view could not prepare that tile")
        t0 = time.time()
        b.defer_call(FN_RV_PLAY, [ref], this=v)
        self._wait_deferred(timeout)
        if self._wait_state(2, max(1.0, timeout - (time.time() - t0))) != 2:
            raise GameError("the tile did not open", "a dialog may be waiting: dialog_status")
        return {"city": memory.city_basics(self.proc), "seconds": round(time.time() - t0, 1)}

    def _wait_deferred(self, timeout: float) -> None:
        end = time.time() + timeout
        while time.time() < end and self.bridge.deferred_state()["busy"]:
            time.sleep(0.2)

    def new_region(self, name: str, water: bool = False) -> dict:
        """Create a region as the Create New Region dialog does (nation AddNewRegion, Init, base terrain, Shutdown
        writes region.ini) and open it. The game picks a random layout of city tiles."""
        if not re.fullmatch(r"[A-Za-z0-9 _'-]{1,32}", name):
            raise GameError("region names: letters, digits, spaces, - ' _ (up to 32)")
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 1:
            raise GameError("the region view is not open", "leave_city goes back to it")
        from . import regions as regionsmod
        if any(r.get("name", "").lower() == name.lower() for r in regionsmod.list_regions(launch.USER_DIR)):
            raise GameError("a region named %r exists" % name)
        p = self.proc
        app = p.u32(memory.G_APP)
        nation = p.u32(app + A_NATION)
        s = b.scratch(0x780)
        p.write(s, name.encode("latin-1") + bytes(1))
        p.write(s + 0x40, bytes(0x20))
        if not b.call_function(FN_RZSTRING_CTOR, [], this=s + 0x40).ok:
            raise GameError("could not make the region name")
        try:
            b.vcall(s + 0x40, 3, s, len(name))                       # FromChar(text, length)
            idx = b.vcall(nation, NATION_ADD_REGION, s + 0x40).ret[0]
        finally:
            b.vcall(s + 0x40, 28, 0)
        if idx < 0:
            raise GameError("the game refused the region name")
        reg = b.vcall(nation, NATION_GET_REGION, idx).ret[0] & 0xFFFFFFFF
        b.vcall(reg, REGION_INIT)
        b.vcall(reg, REGION_SET_TERRAIN, 1 if water else 0)
        b.vcall(reg, REGION_SHUTDOWN)
        b.vcall(nation, NATION_SET_ACTIVE, idx)
        b.defer_call(p.u32(p.u32(app) + 4 * APP_GO_TO_REGION_VIEW), [0], this=app)
        self._wait_deferred(120)
        time.sleep(1)
        self._wait_state(1, 120)
        return {"region": self.region_name(), "index": idx}

    def load_city(self, name: str = "", size: str = "any", timeout: float = 180.0) -> dict:
        """The region view's own LoadCity command (handler 0x7AF4B0): with a name, the founded city of that name;
        without one, the first unfounded tile of the size (founded cities are skipped when the name is empty)."""
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 1:
            raise GameError("not in the region view", "load_city works from the region view (leave_city first)")
        if size not in ("small", "medium", "large", "any"):
            raise GameError("size must be small, medium, large or any")
        if '"' in name:
            raise GameError("city names cannot contain double quotes")
        t0 = time.time()
        line = 'LoadCity "%s" %s %s' % (name, size, "full" if name else "empty")
        r = b.command(line, defer=True, timeout_s=timeout)
        if r.get("pending"):
            return {"pending": True, "hint": "the game is waiting on a window; call game_status"}
        if r.get("status") != 0:
            what = ("no founded city named %r" % name) if name else ("no unfounded %s tile" % size)
            raise GameError("%s in this region" % what, "list_regions shows the region's tiles and cities")
        if self._wait_state(2, timeout) != 2:
            raise GameError("the city did not finish loading", "call game_status")
        return {"city": memory.city_basics(self.proc), "seconds": round(time.time() - t0, 1)}

    def leave_city(self, timeout: float = 120.0) -> dict:
        """Back to the region view without the confirmation dialog (QuitCity 1); unsaved changes are lost."""
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 2:
            raise GameError("no city is open")
        r = b.command("QuitCity 1", defer=True, timeout_s=timeout)
        if r.get("pending"):
            return {"pending": True, "hint": "the game is waiting on a window; call game_status"}
        state = self._wait_state(1, timeout)
        return {"view": memory.APP_STATES.get(state, state), "region": self.region_name()}

    def advance_days(self, days: int, max_seconds: float = 60.0) -> dict:
        """Advance the open city by exactly `days` game days with the game's own day code (re/agents/time): the
        simulator is hidden-paused for the duration, each day runs all of its day / week / month / year agents, and
        the wall-clock spacing between days is removed. Stops early at max_seconds (remaining_days says how many are
        left). The simulator's previous pause state is restored."""
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 2:
            raise GameError("no city is open", "load_city opens one")
        sim = self.proc.u32(memory.G_SIMULATOR)
        if not sim:
            raise GameError("the city has no simulator yet", "wait a moment and retry")
        start = self.proc.u32(sim + memory.SIM_DAY)
        t0 = time.time()
        done = steps = idles = 0
        b.vcall(sim, SIM_HIDDEN_PAUSE)
        try:
            while done < days and time.time() - t0 < max_seconds:
                r = b.step_days(days - done, 250)
                done += r["days"]
                steps += r["steps"]
                idles += r["idle_passes"]
                if r["message"]:
                    raise GameError("the simulation stopped advancing: %s" % r["message"],
                                    "a game window may be waiting for an answer; see game_status")
                if r["in_progress"] or r["days"] == 0:
                    time.sleep(0.01)    # let the game's main loop (and its loader threads) run
        finally:
            b.vcall(sim, SIM_HIDDEN_RESUME)
        end = self.proc.u32(sim + memory.SIM_DAY)
        y, m, d = memory.jdn_to_date(end)
        dt = time.time() - t0
        return {"days": done, "remaining_days": days - done, "date": "%04d-%02d-%02d" % (y, m, d),
                "day_number": end, "elapsed_days": end - start, "seconds": round(dt, 2),
                "days_per_second": round(done / dt, 1) if dt > 0 else None, "steps": steps, "idle_passes": idles}

    def run_days(self, days: int, max_seconds: float = 120.0, unthrottled: bool = False) -> dict:
        """Advance the open city `days` game days by letting the game's own loop run at its fast speed, so
        everything the game does while it plays happens (construction finishing, automata, idle work), then pause
        on the target day: the last two days run at 400 ms each so the pause lands exactly. unthrottled lifts the
        game's wall-clock day spacing (ms-per-day S+0x80 = 0): days pass as fast as the machine allows, but
        buildings finish on wall-clock time in this game, so fewer of them complete per day. The player's speed and
        pause state are restored afterwards."""
        b = self.attach(10.0)
        p = self.proc
        if memory.app_state(p) != 2:
            raise GameError("no city is open", "load_city opens one")
        sim = p.u32(memory.G_SIMULATOR)
        if not sim:
            raise GameError("the city has no simulator yet", "wait a moment and retry")
        c0 = memory.city_basics(p)
        speed0, paused0 = c0["speed"], c0["paused"]
        start = p.u32(sim + memory.SIM_DAY)
        target = start + days
        t0 = time.time()
        stalled_since, reason = None, None
        throttle = sim + SIM_MS_PER_DAY
        fast_ms = None
        try:
            b.command("SimSpeedFast")              # the speed button also un-pauses
            if memory.city_basics(p)["paused"]:
                b.command("SimSpeedPause")
            fast_ms = p.u32(throttle)
            while time.time() - t0 < max_seconds:
                day = p.u32(sim + memory.SIM_DAY)
                if day >= target:
                    break
                p.write(throttle, struct.pack("<I", 400 if target - day <= 2 else (0 if unthrottled else fast_ms)))
                time.sleep(0.005)
                if p.u32(sim + memory.SIM_DAY) == day:
                    stalled_since = stalled_since or time.time()
                    if time.time() - stalled_since > 3.0:
                        from . import dialogs
                        if dialogs.is_modal(self):
                            reason = "a dialog is open and holds the clock (dialog_status, close_dialog)"
                            break
                        stalled_since = time.time()
                else:
                    stalled_since = None
        finally:
            if not memory.city_basics(p)["paused"]:
                b.command("SimSpeedPause")         # stop on the target day first
            b.command({"slow": "SimSpeedSlow", "medium": "SimSpeedMedium", "fast": "SimSpeedFast"}.get(speed0,
                                                                                              "SimSpeedSlow"))
            if memory.city_basics(p)["paused"] != paused0:
                b.command("SimSpeedPause")
        end = p.u32(sim + memory.SIM_DAY)
        y, m, d = memory.jdn_to_date(end)
        dt = time.time() - t0
        out = {"days": end - start, "remaining_days": max(0, target - end), "date": "%04d-%02d-%02d" % (y, m, d),
               "day_number": end, "seconds": round(dt, 2),
               "days_per_second": round((end - start) / dt, 1) if dt > 0 else None,
               "mode": "unthrottled" if unthrottled else "natural"}
        if reason:
            out["stopped"] = reason
        return out

    # ---- founding, speed, saving
    def found_city(self, name: str, mayor: str, difficulty: str = "easy", timeout: float = 30.0) -> dict:
        """The player's flow: Mayor Mode button (0xC988BC79, city control panel) -> the Establish City dialog: city and
        mayor name fields, difficulty, Establish City (re/agents/advisors-ui; verified in LIVE_FACTS)."""
        from . import dialogs
        b = self.attach(10.0)
        c = memory.city_basics(self.proc)
        if not c:
            raise GameError("no city is open", "load_city(size=...) opens an unfounded tile")
        if c["established"]:
            raise GameError("%s is already founded" % c["name"])
        if difficulty not in ("easy", "medium", "hard"):
            raise GameError("difficulty must be easy, medium or hard")
        for s in (name, mayor):
            if not s or '"' in s or len(s) > 31:
                raise GameError("names must be 1-31 characters without double quotes")
        b.command("GZWinClickButton %d 0" % BTN_MAYOR_MODE)
        end = time.time() + timeout
        while time.time() < end:
            st = dialogs.status(self)
            if st["open"] and any(d["id"] == "0x%08X" % DLG_ESTABLISH for d in st["dialogs"]):
                break
            time.sleep(0.2)
        else:
            raise GameError("the Establish City dialog did not open", "see dialog_status")
        b.command('GZWinSetWindowText %d %d "%s"' % (FLD_CITY_NAME, DLG_ESTABLISH, name))
        b.command('GZWinSetWindowText %d %d "%s"' % (FLD_MAYOR_NAME, DLG_ESTABLISH, mayor))
        dialogs.click(self, difficulty)
        time.sleep(0.3)
        dialogs.click(self, "Establish City")
        while time.time() < end:
            c = memory.city_basics(self.proc)
            if c and c["established"]:
                return {"city": c}
            time.sleep(0.25)
        raise GameError("the city was not founded", "see dialog_status")

    def set_speed(self, speed: str) -> dict:
        """The speed buttons (commands SimSpeedSlow / Medium / Fast); they also un-pause, as the buttons do."""
        b = self.attach(10.0)
        cmd = {"slow": "SimSpeedSlow", "medium": "SimSpeedMedium", "fast": "SimSpeedFast"}.get(speed)
        if not cmd:
            raise GameError("speed must be slow, medium or fast")
        if memory.app_state(self.proc) != 2:
            raise GameError("no city is open")
        b.command(cmd)
        return {"speed": memory.city_basics(self.proc)["speed"], "paused": memory.city_basics(self.proc)["paused"]}

    def set_paused(self, paused: bool) -> dict:
        """The pause button (command SimSpeedPause toggles the player's pause)."""
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 2:
            raise GameError("no city is open")
        for _ in range(4):
            if memory.city_basics(self.proc)["paused"] == bool(paused):
                break
            b.command("SimSpeedPause")
        c = memory.city_basics(self.proc)
        return {"paused": c["paused"], "speed": c["speed"]}

    def set_popups(self, enabled: bool) -> dict:
        """cISC4App slot 24 SetPopupDialogsEnabled (the switch behind the SetPopupModalDialogsEnabled command)."""
        b = self.attach(10.0)
        app = b.plugin_state()["app"]
        b.call_sequence([(APP_SET_POPUPS, app, [1 if enabled else 0], 1 << 15)])
        return {"popups": bool(b.vcall(app, APP_GET_POPUPS).ret[0] & 0xFF)}

    def city_file(self) -> str:
        c = memory.city_pointer(self.proc)
        return memory.rz_string(self.proc, c + memory.C_SAVE_PATH, 1024) if c else ""

    def save_city(self, allow_shipped: bool = False, timeout: float = 120.0) -> dict:
        """The game's own save (command SaveCity) into the city's file in SiMCP's user folder. Copies of the game's
        shipped cities are kept as shipped unless allow_shipped."""
        b = self.attach(10.0)
        if memory.app_state(self.proc) != 2:
            raise GameError("no city is open")
        path = self.city_file()
        rel = os.path.relpath(path, os.path.join(launch.USER_DIR, "Regions")) if path else ""
        shipped = os.path.join(identity.game_dir(), "Regions", rel)
        if rel and os.path.exists(shipped) and not allow_shipped:
            raise GameError("this city is SiMCP's copy of a city shipped with the game (%s)" % rel,
                            "found a new city (MCP Test region) to save, or pass allow_shipped=true")
        # The game names the file after the city at save time ("City - <name>.sc4") and also rewrites its
        # neighbours' files (regional data), so watch for the open city's own file name.
        folder = os.path.dirname(path)
        start = time.time() - 1
        own = ("city - %s.sc4" % memory.city_basics(self.proc)["name"]).lower()
        target = os.path.join(folder, own)
        if os.path.exists(target) and os.path.normcase(os.path.abspath(target)) != \
                os.path.normcase(os.path.abspath(path)):
            raise GameError("saving would overwrite another city's file (%s)" % os.path.basename(target),
                            "rename_city to a name no other city of the region has")
        trel = os.path.relpath(target, os.path.join(launch.USER_DIR, "Regions"))
        if os.path.exists(os.path.join(identity.game_dir(), "Regions", trel)) and not allow_shipped:
            raise GameError("saving would replace SiMCP's copy of a shipped city (%s)" % trel,
                            "rename_city first, or pass allow_shipped=true")

        def newest():
            best = None
            for f in os.listdir(folder):
                q = os.path.join(folder, f)
                if f.lower().endswith(".sc4") and os.path.getmtime(q) > start:
                    if f.lower() == own:
                        return q
                    if best is None or os.path.getmtime(q) > os.path.getmtime(best):
                        best = q
            return best if best and os.path.basename(best).lower() == own else None

        from . import dialogs
        r = b.command("SaveCity", defer=True, timeout_s=3)
        end = time.time() + timeout
        while time.time() < end:
            q = newest()
            if q:
                # the game confirms with a "City Saved" notice (root 0xAA8DEF97): press its OK as the player would
                st = dialogs.status(self)
                if st["open"] and st["dialogs"][0]["id"] == "0x%08X" % DLG_CITY_SAVED:
                    dialogs.click(self, "OK")
                if not b.deferred_state()["busy"]:
                    time.sleep(0.3)
                    return {"saved": q, "bytes": os.path.getsize(q)}
            time.sleep(0.25)
        raise GameError("the save did not complete", "a dialog may be waiting: see dialog_status")

    def city_status(self) -> dict:
        self.attach(5.0)
        city = memory.city_basics(self.proc)
        if not city:
            raise GameError("no city is open", "load_city opens one from the region view")
        city["region"] = self.region_name()
        return city

    def quit(self, force: bool = False, timeout: float = 30.0) -> dict:
        """Quit through the game's own RequestQuit (no dialog, no save); force=True ends the process instead."""
        b = self.attach(10.0)
        pid = self.proc.pid
        if force:
            import subprocess
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            app = b.plugin_state()["app"]
            b.call_sequence([(APP_REQUEST_QUIT, app, [0, 0], 1 << 15)])
        end = time.time() + timeout
        while time.time() < end and self.proc.alive():
            time.sleep(0.25)
        alive = self.proc.alive()
        if not alive:
            self.proc, self.bridge = None, None
        return {"quit": not alive, "pid": pid, "forced": force}

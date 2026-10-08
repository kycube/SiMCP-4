"""The running game: launch, attach, status, quit."""

from __future__ import annotations

import os
import time

from . import bridge, identity, launch, memory, regions, win32

# cISC4App vtable slots (gzcom-dll numbering, cIGZUnknown = 0..2; verified live where LIVE_FACTS says so)
APP_REQUEST_QUIT = 10        # RequestQuit(bool showDialog, bool saveFirst)
APP_GET_APP_STATE = 25
APP_GET_POPUPS = 23         # Get/SetPopupDialogsEnabled
APP_SET_POPUPS = 24
APP_GET_REGION = 35
APP_GET_CITY = 37
SIM_HIDDEN_PAUSE = 10       # cISC4Simulator::HiddenPause / HiddenResume (counted)
SIM_HIDDEN_RESUME = 13
BTN_MAYOR_MODE = 0xC988BC79  # city control panel (layout 0xC973B411): Mayor Mode
DLG_ESTABLISH = 0x6A414973   # Establish City dialog (layout 0x2A41436B)
FLD_CITY_NAME, FLD_MAYOR_NAME = 0xAA4149BF, 0xAA4149D2
DLG_CITY_SAVED = 0xAA8DEF97  # the "City Saved. (file)" notice, button OK (id 0)
REGION_GET_NAME = 3          # cISC4Region::GetName -> SC4String* (a cRZString)


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
            return {"running": False}
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
        # The game names the file after the city at save time ("City - <name>.sc4"), so watch the region folder.
        folder = os.path.dirname(path)
        start = time.time() - 1

        def newest():
            best = None
            for f in os.listdir(folder):
                q = os.path.join(folder, f)
                if f.lower().endswith(".sc4") and os.path.getmtime(q) > start:
                    if best is None or os.path.getmtime(q) > os.path.getmtime(best):
                        best = q
            return best

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

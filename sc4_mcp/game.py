"""The running game: launch, attach, status, quit."""

from __future__ import annotations

import os
import time

from . import bridge, identity, launch, memory, regions, win32

# cISC4App vtable slots (gzcom-dll numbering, cIGZUnknown = 0..2; verified live where LIVE_FACTS says so)
APP_REQUEST_QUIT = 10        # RequestQuit(bool showDialog, bool saveFirst)
APP_GET_APP_STATE = 25
APP_GET_REGION = 35
APP_GET_CITY = 37
SIM_HIDDEN_PAUSE = 10       # cISC4Simulator::HiddenPause / HiddenResume (counted)
SIM_HIDDEN_RESUME = 13
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
        names = {r["folder"].lower(): r["folder"] for r in regions.list_regions(launch.USER_DIR)}
        folder = names.get(name.lower())
        if not folder:
            raise GameError("no region %r in SiMCP's user folder" % name,
                            "list_regions shows the regions: %s" % ", ".join(sorted(names.values())))
        t0 = time.time()
        r = b.command('LoadRegion "%s"' % folder, defer=True, timeout_s=timeout)
        if r.get("pending") or r.get("status") != 0:
            raise GameError("the game did not load the region (%r)" % r, "see game_status")
        state = self._wait_state(1, timeout)
        got = self.region_name()
        if state != 1 or (got or "").lower() != folder.lower():
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

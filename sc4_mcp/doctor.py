"""Setup check: what SiMCP needs on this machine, without starting the game (python -m sc4_mcp --check)."""

from __future__ import annotations

import os
import platform
import struct
import sys


def _item(name: str, ok: bool, detail: str, hint: str = "") -> dict:
    d = {"check": name, "ok": bool(ok), "detail": detail}
    if hint and not ok:
        d["hint"] = hint
    return d


def check() -> dict:
    from . import bridge, identity, launch
    items = []
    items.append(_item("windows", sys.platform == "win32", platform.platform(),
                       "SiMCP drives the Windows release of SimCity 4"))
    items.append(_item("python", sys.version_info >= (3, 10), "%s (%d-bit)" % (platform.python_version(),
                                                                            struct.calcsize("P") * 8),
                       "Python 3.10 or later"))
    try:
        from importlib.metadata import version
        v = version("mcp")
        from mcp.server.fastmcp import FastMCP  # noqa: F401 - SiMCP is written for the 1.x API
        items.append(_item("mcp package", True, v))
    except Exception as e:  # noqa: BLE001
        items.append(_item("mcp package", False, str(e)[:200], 'SiMCP needs the 1.x MCP package: python -m pip '
                           'install "mcp>=1.29,<2"'))
    exe = identity.check_exe()
    items.append(_item("game", exe.get("ok", False), exe.get("path", "") + (
        " - " + exe.get("variant", "") if exe.get("ok") else " - " + exe.get("reason", "")),
        "SimCity 4 Deluxe 1.1.641 (GOG or the digital release); set SC4_GAME_DIR to its folder if it is elsewhere"))
    for label, path in (("plugin DLL", bridge.PLUGIN_DLL), ("bridge DLL", bridge.BRIDGE_DLL)):
        ok = os.path.isfile(path)
        items.append(_item(label, ok, path + (" (%d bytes)" % os.path.getsize(path) if ok else " - missing"),
                           "build them with bridge\\build.bat (Visual Studio C++ x86 tools) or use a release, "
                           "which bundles them"))
    home = launch.ROOT
    try:
        os.makedirs(home, exist_ok=True)
        probe = os.path.join(home, ".simcp4-write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        items.append(_item("SiMCP home", True, home))
    except OSError as e:
        items.append(_item("SiMCP home", False, "%s - %s" % (home, e), "set SIMCP4_HOME to a writable folder "
                           "outside OneDrive and AppData"))
    if "onedrive" in home.lower() or "\\appdata\\" in home.lower():
        items.append(_item("SiMCP home location", False, home, "keep it outside OneDrive and AppData (the game "
                           "folder junction and MSIX virtualisation break there)"))
    try:
        src = launch.player_user_dir()
        plugins = os.path.join(src, "Plugins")
        items.append(_item("your plugins (mirrored, read only)", os.path.isdir(plugins), plugins,
                           "optional: without them the game runs with SiMCP's plugin only"))
        nam = os.path.isdir(plugins) and any("network-addon-mod" in d.lower() or d.lower().startswith("nam")
                                              for d in os.listdir(plugins))
        items.append(_item("NAM", nam, "found" if nam else "not found",
                           "optional: puzzle pieces and bridges beyond the game's own come from NAM"))
    except Exception as e:  # noqa: BLE001
        items.append(_item("your plugins", False, str(e)))
    needed = {"windows", "python", "mcp package", "game", "plugin DLL", "bridge DLL", "SiMCP home"}
    ok = all(i["ok"] for i in items if i["check"] in needed)
    return {"ok": ok, "checks": items}


def main() -> int:
    import json
    out = check()
    print(json.dumps(out, indent=1))
    return 0 if out["ok"] else 1

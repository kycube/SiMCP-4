"""Starting SimCity 4 for SiMCP: unelevated, windowed, with SiMCP's own user folder.

Why a junction: GOG registers the WINXPSP3 compatibility layer for `...\\Apps\\SimCity 4.exe`, and on current
Windows that layer makes CreateProcess fail with ERROR_ELEVATION_REQUIRED (740). An elevated game cannot be read or
messaged by a normal-user server. The layer is keyed by the exe's path, so the game is started through a directory
junction (`%USERPROFILE%\\SiMCP-4\\game` -> the game folder): same files, no registry or game-folder change, no
elevation. The junction lives outside OneDrive on purpose (a sync client would follow it into the game folder).

Why a separate user folder: the game is started with `-UserDir:` pointing at `%USERPROFILE%\\SiMCP-4\\UserDir\\`.
Its Plugins folder mirrors the player's own Plugins root (junctions to the category folders, the same DLL links,
copies of the DLLs' INI files) plus the SiMCP bridge plugin, and it has its own Regions and SimCity 4.cfg. Nothing
in the player's Documents\\SimCity 4 is written by SiMCP.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from . import identity

# SiMCP's home: the profile root, not AppData - a packaged client (e.g. a desktop app) sees AppData through its own
# private, virtualized copy, which the player's shortcuts and other clients cannot see (verified 2026-10-08).
ROOT = os.environ.get("SIMCP4_HOME") or os.path.join(os.path.expanduser("~"), "SiMCP-4")
JUNCTION = os.path.join(ROOT, "game")
USER_DIR = os.environ.get("SC4_USER_DIR") or os.path.join(ROOT, "UserDir")
DEFAULT_RESOLUTION = (1024, 768)

ERROR_ELEVATION_REQUIRED = 740


def player_user_dir() -> str:
    """The player's own SimCity 4 folder (Documents\\SimCity 4; the GOG registry key names it)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games\1207664593") as k:
            p = winreg.QueryValueEx(k, "savegamefolder")[0]
            if p and os.path.isdir(p):
                return p
    except OSError:
        pass
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL (Documents)
    return os.path.join(buf.value, "SimCity 4")


def is_junction(path: str) -> bool:
    try:
        return os.path.isjunction(path)
    except AttributeError:  # Python < 3.12
        import stat
        st = os.lstat(path)
        return bool(getattr(st, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT)


def ensure_junction(link: str, target: str) -> None:
    """Create (or repoint) a directory junction. Only ever removes a junction, never a real folder."""
    import _winapi
    if os.path.lexists(link):
        if is_junction(link) and os.path.normcase(os.path.realpath(link)) == os.path.normcase(os.path.realpath(target)):
            return
        if not is_junction(link):
            raise RuntimeError("%s exists and is not a junction; refusing to replace it" % link)
        os.rmdir(link)  # removes the junction itself, not its target
    os.makedirs(os.path.dirname(link), exist_ok=True)
    _winapi.CreateJunction(target, link)


def ensure_game_junction() -> str:
    ensure_junction(JUNCTION, identity.game_dir())
    return JUNCTION


SPLIT_FOLDERS = {"140-ordinances"}     # mirrored as a real folder holding a junction, so SiMCP can add files
PLAYER_SUBFOLDER = "000-player"


def mirror_plugins(user_dir: str = USER_DIR, source: str | None = None) -> dict:
    """Make <user_dir>\\Plugins mirror the player's Plugins root: a junction per folder, a link to the same file per
    DLL link, a copy of each INI. Entries SiMCP created earlier that no longer exist in the source are removed (links
    only); files SiMCP did not create (the bridge, logs) are left alone."""
    source = source or os.path.join(player_user_dir(), "Plugins")
    dst = os.path.join(user_dir, "Plugins")
    os.makedirs(dst, exist_ok=True)
    os.makedirs(os.path.join(user_dir, "Regions"), exist_ok=True)
    done = {"junctions": [], "links": [], "copies": [], "removed": []}
    wanted = set()
    for name in sorted(os.listdir(source)):
        s = os.path.join(source, name)
        d = os.path.join(dst, name)
        low = name.lower()
        if os.path.islink(s):
            if not low.endswith(".dll"):
                continue
            # Absolute target: Windows does not resolve a relative symlink whose path crosses one of our junctions
            # (verified 2026-10-08: the mirrored links were dangling and no DLL loaded).
            target = os.path.realpath(s)
            wanted.add(low)
            if os.path.islink(d) and os.readlink(d) == target:
                continue
            if os.path.lexists(d):
                if not os.path.islink(d):
                    raise RuntimeError("%s exists and is not a link; refusing to replace it" % d)
                os.unlink(d)
            os.symlink(target, d)
            done["links"].append(name)
        elif os.path.isdir(s) and low in SPLIT_FOLDERS:
            # a real folder of SiMCP's own: the player's folder as a junction inside it, SiMCP's designs beside it
            # (the custom ordinance host reads ordinances only from Plugins\140-ordinances and its sub-folders)
            wanted.add(low)
            if os.path.lexists(d) and is_junction(d):
                os.rmdir(d)                        # removes the junction itself, never the player's folder
                done["removed"].append(name)
            os.makedirs(d, exist_ok=True)
            inner = os.path.join(d, PLAYER_SUBFOLDER)
            if not (os.path.lexists(inner) and is_junction(inner) and
                    os.path.normcase(os.path.realpath(inner)) == os.path.normcase(os.path.realpath(s))):
                ensure_junction(inner, s)
                done["junctions"].append(name + "\\" + PLAYER_SUBFOLDER)
        elif os.path.isdir(s):
            wanted.add(low)
            if not (os.path.lexists(d) and is_junction(d) and
                    os.path.normcase(os.path.realpath(d)) == os.path.normcase(os.path.realpath(s))):
                ensure_junction(d, s)
                done["junctions"].append(name)
        elif low.endswith(".ini"):
            wanted.add(low)
            if not (os.path.exists(d) and os.path.getmtime(d) >= os.path.getmtime(s)):
                shutil.copy2(s, d)
                done["copies"].append(name)
    for name in os.listdir(dst):
        d = os.path.join(dst, name)
        if name.lower() in wanted:
            continue
        if os.path.islink(d) and name.lower().endswith(".dll") and not name.lower().startswith("simcp"):
            os.unlink(d); done["removed"].append(name)
        elif os.path.isdir(d) and is_junction(d):
            os.rmdir(d); done["removed"].append(name)
    return done


def ensure_regions(user_dir: str = USER_DIR) -> list[str]:
    """Copy the game's shipped regions into <user_dir>\\Regions where missing (the game itself does this only when
    the folder is empty on its first start). Never overwrites anything. Returns the regions copied."""
    src = os.path.join(identity.game_dir(), "Regions")
    dst = os.path.join(user_dir, "Regions")
    os.makedirs(dst, exist_ok=True)
    copied = []
    if os.path.isdir(src):
        for name in sorted(os.listdir(src)):
            s, d = os.path.join(src, name), os.path.join(dst, name)
            if os.path.isdir(s) and not os.path.exists(d):
                shutil.copytree(s, d)
                copied.append(name)
    return copied


def command_line(user_dir: str | None = USER_DIR, windowed: bool = True,
                 resolution: tuple[int, int] | None = DEFAULT_RESOLUTION, intro: bool = False,
                 extra: list[str] | None = None) -> list[str]:
    args = ["-CPUCount:1", "-w" if windowed else "-f"]
    if not intro:
        args.append("-intro:off")
    if resolution:
        args += ["-CustomResolution:enabled", "-r%dx%dx32" % resolution]
    if user_dir:
        p = os.path.join(os.path.abspath(user_dir), "")
        if " " in p:
            raise ValueError("the user folder path must not contain spaces: %s" % p)
        args.append("-UserDir:" + p)
    return args + list(extra or [])


def launch(user_dir: str | None = USER_DIR, mirror: bool = True, beside_other: bool = False,
           **kw) -> subprocess.Popen:
    """Start the game unelevated (see the module docstring). Returns the Popen of the game process.
    beside_other=True adds Maxis' -AllowMultipleInstances switch (the game otherwise exits when another instance
    holds its "SimCity 4 Mutex"), so SiMCP's game can run while the player's own is open."""
    check = identity.check_exe()
    if not check["ok"]:
        raise RuntimeError(check["reason"])
    root = ensure_game_junction()
    if user_dir and mirror:
        mirror_plugins(user_dir)
        ensure_regions(user_dir)
    exe = os.path.join(root, "Apps", identity.EXE_NAME)
    env = dict(os.environ)
    # Our own environment may carry __COMPAT_LAYER (e.g. DetectorsAppHealth); give the game GOG's DPI flag only.
    env["__COMPAT_LAYER"] = "HIGHDPIAWARE"
    env["SIMCP4_HOME"] = ROOT                 # the bridge writes its crash log there
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    cmd = [exe] + command_line(user_dir, **kw)
    if beside_other:
        cmd.append("-AllowMultipleInstances")
    try:
        return subprocess.Popen(cmd, cwd=os.path.dirname(exe), env=env, close_fds=True,
                                creationflags=flags | 0x01000000)  # + CREATE_BREAKAWAY_FROM_JOB
    except OSError as e:
        if getattr(e, "winerror", None) == ERROR_ELEVATION_REQUIRED:
            raise RuntimeError("Windows asks for elevation for %s - the junction did not avoid GOG's "
                               "compatibility layer" % exe) from e
        return subprocess.Popen(cmd, cwd=os.path.dirname(exe), env=env, close_fds=True, creationflags=flags)

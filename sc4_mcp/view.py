"""The city view: camera and snapshots (re/agents/view-disasters Q3/Q4, LIVE_FACTS Phase 3).

The camera is the city view's camera control: view [0xB43DC4] (cISC4View3DWin) +0xF0 -> target in metres at
+0x44/+0x48/+0x4C (x, altitude, z; a cell is 16 m), zoom +0x108 (0..5, the UI's 1..6), rotation +0x10C (0..3).
It is moved with the game's own commands (SetViewTarget cell x z, Zoom0..Zoom5, RotateCW), as the player's
keys and buttons do. A snapshot is the game's TakeSnapshot command: it writes the last frame the game drew (the
colour buffer, with the game's UI) to a PNG - so the game window must be drawing (not minimised).
"""

from __future__ import annotations

import io
import os
import struct
import time

from . import launch, memory

G_VIEW = 0xB43DC4
G_RENDERER = 0xB43DD0
CC_TARGET, CC_ZOOM, CC_ROTATION = 0x44, 0x108, 0x10C
V_CAMERA, V_LEVEL = 0xF0, 0x324
R_WIDTH, R_HEIGHT = 0x68, 0x6C


class ViewError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _cc(p) -> int:
    if not memory.city_pointer(p):
        raise ViewError("no city is open", "load_city opens one")
    v = p.u32(G_VIEW)
    cc = p.u32(v + V_CAMERA) if v else 0
    if not cc:
        raise ViewError("the city view is not ready")
    return cc


def camera(p) -> dict:
    cc = _cc(p)
    x, y, z = struct.unpack("<3f", p.read(cc + CC_TARGET, 12))
    r = p.u32(G_RENDERER)
    return {"x": round(x / 16 - 0.5, 2), "z": round(z / 16 - 0.5, 2), "altitude": round(y, 1),
            "zoom": p.i32(cc + CC_ZOOM) + 1, "rotation": p.i32(cc + CC_ROTATION),
            "viewport": [p.i32(r + R_WIDTH), p.i32(r + R_HEIGHT)] if r else None}


def set_camera(g, x: int | None = None, z: int | None = None, zoom: int | None = None,
               rotation: int | None = None) -> dict:
    """Centre the view on cell (x, z), set the zoom (1 far .. 6 close) and the rotation (0..3)."""
    p, b = g.proc, g.bridge
    cc = _cc(p)
    if (x is None) != (z is None):
        raise ViewError("give both x and z (or neither)")
    if x is not None:
        nx, nz = p.u32(memory.city_pointer(p) + memory.C_CELLS_X), p.u32(memory.city_pointer(p) + memory.C_CELLS_Z)
        if not (0 <= x < nx and 0 <= z < nz):
            raise ViewError("cell (%d, %d) is outside the city" % (x, z), "the city is %d x %d cells" % (nx, nz))
        b.command("SetViewTarget cell %d %d" % (x, z))
    if zoom is not None:
        if not 1 <= zoom <= 6:
            raise ViewError("zoom is 1 (far) to 6 (close)")
        b.command("Zoom%d" % (zoom - 1))
    if rotation is not None:
        if not 0 <= rotation <= 3:
            raise ViewError("rotation is 0..3")
        for _ in range(4):
            if p.i32(cc + CC_ROTATION) == rotation:
                break
            b.command("RotateCW")
    return camera(p)


def snapshot_dir() -> str:
    d = os.path.join(launch.ROOT, "snapshots")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(g, width: int = 1024, settle_s: float = 0.4) -> tuple[dict, bytes]:
    """The game's own snapshot of the view, as a JPEG (scaled to `width` pixels wide), and where the full PNG is."""
    from PIL import Image
    p = g.proc
    cam = camera(p)
    vw, vh = cam["viewport"] or (1024, 768)
    path = os.path.join(snapshot_dir(), time.strftime("city-%Y%m%d-%H%M%S.png"))
    time.sleep(settle_s)             # let the game draw a frame after a camera move
    r = g.bridge.command('TakeSnapshot "%s" 0 0 %d %d' % (path, vw, vh))
    for _ in range(50):
        if os.path.exists(path) and os.path.getsize(path):
            break
        time.sleep(0.1)
    if r.get("status") != 0 or not os.path.exists(path):
        raise ViewError("the game did not write a snapshot (status %s)" % r.get("status"),
                        "the game window must be drawing (not minimised)")
    im = Image.open(path).convert("RGB")
    if 0 < width < im.width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return dict(cam, file=path, size=list(im.size)), buf.getvalue()

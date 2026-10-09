"""Game options: the Play Options dialog and the preferences the game keeps (re/agents/networks-deals Q3).

SC4Preferences `[0xB43CD8]` (= app slot 38 GetPreferences, 0x1734 bytes; sub-blocks as in gzcom-dll
SC4Preferences.h): +0 day / night, +0x4 audio, +0x4A4 app, +0xF08 game options, +0xF0C video. The Play Options
dialog (layout 0x0A7DF315, Accept 0x76B110) writes its checkbox bytes, sends kMessageTypePreferencesChanged
0x231BBF91 (a cGZMessage2Standard: new 0x2C bytes 0x9133DA, ctor 0x9134D6, slot 5 SetType) through the message
server `[0xB43CCC]` slot 4, then app slot 17 SavePreferences writes SimCity 4.cfg in the user folder (SiMCP's own).
SiMCP does the same.
"""

from __future__ import annotations

import struct

G_PREFS, G_MSG_SERVER = 0xB43CD8, 0xB43CCC
MSG_PREFERENCES_CHANGED = 0x231BBF91
FN_NEW, FN_MESSAGE_CTOR = 0x9133DA, 0x9134D6
MSG_SET_TYPE, MS_SEND, APP_SAVE_PREFERENCES = 5, 4, 17

PLAY_OPTIONS = {
    "auto_go_to_disaster": (0xF08, "the camera jumps to a disaster when it starts"),
    "edge_scrolling": (0xF09, "the view scrolls when the mouse touches the window's edge"),
    "expanded_tooltips": (0xF0A, "longer tooltips"),
    "urgent_advice_dialogs": (0xF0B, "urgent advisor messages open as popup dialogs"),
    "auto_edge_reconciliation": (0x4EC, "the terrain at the city's edges is matched to the neighbours"),
}
VIDEO = {"visual_effects": 0x1, "cars_and_sims": 0x2, "shadows": 0x3, "texture_quality": 0x4,
         "atmospheric_effects": 0x5, "water_effects": 0x6, "translucency": 0x9, "city_detail": 0xA,
         "full_screen": 0xB}


class OptionsError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _prefs(g) -> int:
    pr = g.proc.u32(G_PREFS)
    if not pr:
        raise OptionsError("the game's preferences are not loaded yet")
    return pr


def options(g) -> dict:
    p = g.proc
    pr = _prefs(g)
    v = pr + 0xF0C
    return {"play_options": {k: {"on": bool(p.u8(pr + off)), "what": what} for k, (off, what) in PLAY_OPTIONS.items()},
            "audio": {"music": bool(p.u32(pr + 0x4 + 0xC)), "sound": bool(p.u8(pr + 0x4 + 0x65))},
            "video": {**{k: p.u8(v + off) for k, off in VIDEO.items()},
                      "resolution": list(struct.unpack("<III", p.read(v + 0x10, 12)))},
            "pause_when_window_loses_focus": bool(p.u32(pr + 0x4A4)),
            "language": p.read(pr + 0x4A4 + 8, 64).split(b"\0", 1)[0].decode("latin-1"),
            "note": "set_play_option changes the play options; day / night is day_night(), popups set_popups()"}


def _send_preferences_changed(g) -> None:
    p, b = g.proc, g.bridge
    r = b.call_function(FN_NEW, [0x2C])
    msg = r.ret[0] & 0xFFFFFFFF
    if not r.ok or not msg:
        raise OptionsError("could not make the message: %s" % r.msg)
    b.call_function(FN_MESSAGE_CTOR, [], this=msg)
    b.vcall(msg, 1)                                   # AddRef, as the dialog's smart pointer does
    try:
        b.vcall(msg, MSG_SET_TYPE, MSG_PREFERENCES_CHANGED)
        ms = p.u32(G_MSG_SERVER)
        b.vcall(ms, MS_SEND, msg, 0)
    finally:
        b.vcall(msg, 2)                               # Release: frees it


def set_play_option(g, name: str, on: bool) -> dict:
    if name not in PLAY_OPTIONS:
        raise OptionsError("unknown option %r" % name, "options: " + ", ".join(PLAY_OPTIONS))
    p, b = g.proc, g.bridge
    pr = _prefs(g)
    off = PLAY_OPTIONS[name][0]
    before = bool(p.u8(pr + off))
    p.write(pr + off, bytes([1 if on else 0]))
    _send_preferences_changed(g)
    app = b.plugin_state()["app"]
    b.vcall(app, APP_SAVE_PREFERENCES)
    return {"option": name, "before": before, "now": bool(p.u8(pr + off)), "saved": True}

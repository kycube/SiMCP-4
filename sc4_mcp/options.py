"""Game options: the Play Options dialog and the preferences the game keeps (re/agents/networks-deals Q3).

SC4Preferences `[0xB43CD8]` (= app slot 38 GetPreferences, 0x1734 bytes; sub-blocks as in gzcom-dll
SC4Preferences.h): +0 day / night, +0x4 audio, +0x4A4 app, +0xF08 game options, +0xF0C video. The Play Options
dialog (layout 0x0A7DF315, Accept 0x76B110) writes its checkbox bytes, sends kMessageTypePreferencesChanged
0x231BBF91 (a cGZMessage2Standard: new 0x2C bytes 0x9133DA, ctor 0x9134D6, slot 5 SetType) through the message
server `[0xB43CCC]` slot 4, then app slot 17 SavePreferences writes SimCity 4.cfg in the user folder (SiMCP's own).
SiMCP does the same.

Graphics and sound go through the game's own Graphic Options and Audio Options dialogs (commands
OpenGraphicOptionsDialog / OpenAudioOptionsDialog, run from the game's loop because they are modal): SiMCP reads
their controls, clicks the radio buttons and checkboxes with GZWinClickButton, moves the volume sliders with the
slider's own SetValue (it notifies the dialog as a drag does) and presses Accept, so the game applies and saves
the settings itself. A button is on when bit 0 of [window+0xD8] is set; a slider's interface is window+0xD8
(slot 4 GetValue, 5 SetValue, range 0-1000).
"""

from __future__ import annotations

import struct
import time

from . import dialogs

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
            "note": "set_play_option changes the play options; graphics_options / audio_options the graphics and sound "
                    "(through their dialogs); day / night is day_night(), popups set_popups()"}


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


# ---- the Graphic Options and Audio Options dialogs

LEVELS = ("low", "medium", "high")
GRAPHICS = {"command": "OpenGraphicOptionsDialog", "root": 0x2A57CB82, "accept": 0xEA57DA59, "cancel": 0x6A57DA48}
GRAPHICS_LEVELS = {     # low, medium, high radio buttons
    "visual_effects": (0x6A57DA49, 0x6A57DA4A, 0x6A57DA4B),
    "cars_and_sims": (0x6A57DA4C, 0x6A57DA4D, 0x6A57DA4E),
    "shadows": (0x6A57DA4F, 0x6A57DA50, 0x6A57DA51),
    "building_draw_speed": (0xAB81DED5, 0xAB81DED6, 0xAB81DED7),
    "texture_quality": (0x0B85CF92, 0x2B85CF9F, 0x2B85CFAA),
    "city_detail": (0x2AB6C373, 0x2AB6C374, 0x2AB6C375)}
GRAPHICS_SWITCHES = {"clouds_and_fog": 0x6A57DA54, "waves": 0x6A57DA55, "ui_translucency": 0x6A57DA56,
                     "color_cursor": 0x6A57DA60, "variable_speed_automata": 0x0A8B7E00}
GRAPHICS_DISPLAY = {     # read only: SiMCP's launch sets the window (game_launch width / height)
    "resolution": {0x6A57DA5A: "800x600", 0x6A57DA5B: "1024x768", 0x6A57DA5C: "1280x1024", 0x6A57DA5D: "1600x1200"},
    "color_quality": {0x2AB6C376: "16-bit", 0x2AB6C377: "32-bit"},
    "renderer": {0x6A57DA57: "hardware", 0x6A57DA58: "software"}}
AUDIO = {"command": "OpenAudioOptionsDialog", "root": 0xEA53F5DB, "accept": 0xEA5509E4, "cancel": 0xEA5509E3}
AUDIO_SWITCHES = {"music": 0x8A550C50, "sound": 0x8A550C52, "custom_tunes": 0x8A550C5A}
AUDIO_SLIDERS = {"music_volume": 0x8A550C51, "sound_volume": 0x8A550C53}
BTN_STATE, SLIDER_IFACE, SLIDER_GET, SLIDER_SET, SLIDER_MAX = 0xD8, 0xD8, 4, 5, 1000


def _controls(g, root: int) -> dict:
    """Every window under the dialog root, by id (the dialog's own ids are unique)."""
    p = g.proc
    out, stack = {}, [root]
    while stack:
        w = stack.pop()
        for c in dialogs._children(p, w):
            out.setdefault(p.u32(c + dialogs.W_ID), c)
            stack.append(c)
    return out


def _open(g, dlg: dict) -> dict:
    if dialogs.is_modal(g):
        raise OptionsError("a dialog is open", "dialog_status shows it; close_dialog closes it")
    g.bridge.command(dlg["command"], defer=True, timeout_s=0.5)       # modal: runs from the game's loop
    end = time.time() + 5.0
    while time.time() < end:
        root = dialogs.find_window(g, dlg["root"])
        if root:
            return _controls(g, root)
        time.sleep(0.1)
    raise OptionsError("the game did not open the options dialog", "game_status: the game must be controllable")


def _close(g, dlg: dict, button: int) -> None:
    g.bridge.command("GZWinClickButton %d %d" % (button, dlg["root"]))
    end = time.time() + 5.0
    while time.time() < end and (g.bridge.deferred_state()["busy"] or dialogs.find_window(g, dlg["root"])):
        time.sleep(0.1)


def _on(g, w: int) -> bool:
    return bool(g.proc.u32(w + BTN_STATE) & 1)


def _enabled(g, w: int) -> bool:
    return bool(g.proc.u32(w + dialogs.W_FLAGS) & dialogs.F_ENABLED)


def _click(g, dlg: dict, ctl: dict, wid: int, want: bool) -> None:
    w = ctl[wid]
    for _ in range(3):
        if _on(g, w) == want:
            return
        g.bridge.command("GZWinClickButton %d %d" % (wid, dlg["root"]))
        time.sleep(0.15)
    if _on(g, w) != want:
        raise OptionsError("the dialog did not take the click on control 0x%08X" % wid)


def _graphics_state(g, ctl: dict) -> dict:
    out = {}
    for k, ids in GRAPHICS_LEVELS.items():
        on = [lvl for lvl, i in zip(LEVELS, ids) if i in ctl and _on(g, ctl[i])]
        out[k] = on[0] if on else None
    for k, i in GRAPHICS_SWITCHES.items():
        out[k] = _on(g, ctl[i]) if i in ctl else None
    for k, ids in GRAPHICS_DISPLAY.items():
        on = [name for i, name in ids.items() if i in ctl and _on(g, ctl[i])]
        out[k] = on[0] if on else None
    return out


def _audio_state(g, ctl: dict) -> dict:
    out = {k: _on(g, ctl[i]) for k, i in AUDIO_SWITCHES.items() if i in ctl}
    for k, i in AUDIO_SLIDERS.items():
        if i in ctl:
            v = g.bridge.vcall(ctl[i] + SLIDER_IFACE, SLIDER_GET).ret[0]
            out[k] = round(100 * v / SLIDER_MAX)
    if AUDIO_SWITCHES["custom_tunes"] in ctl and not _enabled(g, ctl[AUDIO_SWITCHES["custom_tunes"]]):
        out["custom_tunes_available"] = False
    return out


def _session(g, dlg: dict, state, apply) -> dict:
    """Open the dialog, read it, apply the changes (if any), Accept (or Cancel when nothing changes)."""
    ctl = _open(g, dlg)
    try:
        before = state(g, ctl)
        changed = apply(g, ctl, before)
        now = state(g, ctl)
    except Exception:
        _close(g, dlg, dlg["cancel"])                                    # never leave the modal dialog open
        raise
    _close(g, dlg, dlg["accept"] if changed else dlg["cancel"])
    out = {"settings": now}
    if changed:
        out["changed"] = {k: [before.get(k), now.get(k)] for k in changed}
        out["saved"] = True
    st = dialogs.status(g)
    if st.get("open"):
        out["dialog"] = st["dialogs"][0]                               # e.g. a notice that needs a restart
    return out


def graphics(g, **want) -> dict:
    """The Graphic Options dialog's settings; with arguments, set them as the player does (then Accept)."""
    for k, v in want.items():
        if k in GRAPHICS_LEVELS and v not in LEVELS:
            raise OptionsError("%s is low, medium or high" % k)
        if k not in GRAPHICS_LEVELS and k not in GRAPHICS_SWITCHES:
            raise OptionsError("unknown graphics setting %r" % k,
                               "settings: " + ", ".join(list(GRAPHICS_LEVELS) + list(GRAPHICS_SWITCHES)))

    def apply(g, ctl, before):
        changed = []
        for k, v in want.items():
            if before.get(k) == v:
                continue
            if k in GRAPHICS_LEVELS:
                _click(g, GRAPHICS, ctl, GRAPHICS_LEVELS[k][LEVELS.index(v)], True)
            else:
                _click(g, GRAPHICS, ctl, GRAPHICS_SWITCHES[k], bool(v))
            changed.append(k)
        return changed
    out = _session(g, GRAPHICS, _graphics_state, apply)
    out["note"] = "resolution, colour quality and renderer are set when SiMCP starts the game (game_launch)"
    return out


def audio(g, **want) -> dict:
    """The Audio Options dialog's settings (music, sound, volumes 0-100, custom tunes); with arguments, set them."""
    for k, v in want.items():
        if k in AUDIO_SLIDERS:
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
                raise OptionsError("%s is 0-100" % k)
        elif k not in AUDIO_SWITCHES:
            raise OptionsError("unknown audio setting %r" % k,
                               "settings: " + ", ".join(list(AUDIO_SWITCHES) + list(AUDIO_SLIDERS)))

    def apply(g, ctl, before):
        changed = []
        for k, v in want.items():
            if before.get(k) == v:
                continue
            if k in AUDIO_SLIDERS:
                g.bridge.vcall(ctl[AUDIO_SLIDERS[k]] + SLIDER_IFACE, SLIDER_SET, round(v * SLIDER_MAX / 100))
            else:
                w = ctl[AUDIO_SWITCHES[k]]
                if not _enabled(g, w):
                    raise OptionsError("%s cannot be switched here" % k,
                                       "custom tunes need music files in the game's custom music folder")
                _click(g, AUDIO, ctl, AUDIO_SWITCHES[k], bool(v))
            changed.append(k)
        return changed
    return _session(g, AUDIO, _audio_state, apply)

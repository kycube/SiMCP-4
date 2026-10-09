"""Authored facades: a wall's texture drawn element by element (windows, doors, cornice bands, friezes, railings,
ornaments, shingle fields) in clean flat colours, at positions measured from a reference photo - the photo is used
as a guide, not pasted. The renderer then lights the wall like the game's own buildings, so the result is crisp and
consistent instead of carrying the photo's blur, noise and sunlight.

    {"facade": {"size_m": [W, H], "px_per_m": 40,
                "palette": {"body": "#8a9c8c", "trim": "#5f7066", ...},
                "base": {"pattern": "clapboard", "color": "body", "size_m": [1, 1]},
                "elements": [{"type": "band", "v": 3.8, "h": 0.4, "color": "trim", "style": "dentil"},
                             {"type": "window", "u": 2.0, "v": 4.6, "w": 1.0, "h": 2.2, "transom": true, "hood": true},
                             {"type": "repeat", "n": 4, "du": 2.5, "element": {...}}, ...]}}

u = metres from the face's left edge (seen from outside), v = metres down from its top. Colours are "#rrggbb",
"r,g,b", a palette name or "clear" (see-through: the renderer cuts the face away there - open balustrades, iron
fences, porch arches; "base": {"color": "clear"} starts from an empty face). On a round tower u runs around it
(see partmodel: prism "angle").
Element types (defaults in brackets):
- window: u, v, w, h; frame [trim], glass [glass], sash [sash], curtain [none], transom [false] (stained top
  light), arch [false] (round top), hood [false] (cap above), pediment [false], sill [true], mullion [w > 1.4]
- door: u, v, w, h; color [door], frame [trim], leaves [2], transom [true]
- band: v, h, color [trim]; style plain | dentil | molding | frieze | brackets | corbel; color2 [dark]; u, w
  [the whole width]
- arch: u, v, w, h, rise [w / 2 = round], color [dark] (an opening or panel with a round or segmental top: porch
  arches, loggias; "clear" makes it open)
- rect: u, v, w, h, color (blank wall, dark recesses such as an open loggia, panels)
- field: u, v, w, h, pattern (clapboard | shingle | fishscale | brick | stone ...), color, color2, size_m
- railing: u, v, w, h, color [trim], spindle [0.18], style balustrade | iron (rails and spindles; iron = thin
  bars with spear tops), back [none] (the colour between the spindles: "clear" to see through)
- ornament: u, v, w, h, style sunburst | rosette | fan | diamond, color [trim], color2 [dark]
- repeat: n, du (and/or dv), element - the element n times, shifted by du / dv each time
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw



class GameError(Exception):
    """A facade spec the drawing cannot follow (the message says what to fix)."""

    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

DEFAULT_PALETTE = {
    "body": "#8a9c8c", "trim": "#5c6c62", "dark": "#3e4a44", "light": "#d8d4c2", "glass": "#2c3644",
    "sky": "#5f7891", "sash": "#3c4640", "door": "#4a3a30", "curtain": "#d6ccb4", "accent": "#a88a4c",
}


class Facade:
    def __init__(self, spec: dict):
        try:
            self.W, self.H = (float(v) for v in spec["size_m"])
        except (KeyError, TypeError, ValueError):
            raise GameError('facade: "size_m": [width, height] of the face in metres')
        self.k = float(spec.get("px_per_m", 40))
        self.pal = dict(DEFAULT_PALETTE)
        self.pal.update(spec.get("palette", {}))
        w, h = int(round(self.W * self.k)), int(round(self.H * self.k))
        if w * h > 4096 * 4096:
            raise GameError("facade too large: lower px_per_m")
        self.im = Image.new("RGBA", (max(4, w), max(4, h)), self.c("body"))
        self.d = ImageDraw.Draw(self.im)
        base = spec.get("base")
        if base:
            self.field({"u": 0, "v": 0, "w": self.W, "h": self.H, **base})
        for i, e in enumerate(spec.get("elements", [])):
            self.element(e, i)

    # ---------------------------------------------------------------- helpers
    def c(self, v, default=None):
        from .partmodel import parse_color
        if v is None:
            v = default
        if v is None:
            return None
        if isinstance(v, str) and v in self.pal:
            v = self.pal[v]
        if v == "clear":
            return (0, 0, 0, 0)
        return parse_color(v) + (255,)

    def px(self, u, v):
        return int(round(u * self.k)), int(round(v * self.k))

    def box(self, u, v, w, h, color):
        x0, y0 = self.px(u, v)
        x1, y1 = self.px(u + w, v + h)
        if x1 > x0 and y1 > y0:
            self.d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=color)

    @staticmethod
    def shade(c, k):
        if len(c) == 4 and c[3] == 0:
            return c
        return tuple(max(0, min(255, int(x * k))) for x in c[:3]) + (255,)

    # ---------------------------------------------------------------- elements
    def element(self, e: dict, i: int):
        t = e.get("type")
        fn = {"window": self.window, "door": self.door, "band": self.band, "rect": self.rect, "field": self.field,
              "railing": self.railing, "ornament": self.ornament, "repeat": self.repeat, "arch": self.arch}.get(t)
        if not fn:
            raise GameError(f"facade element {i}: type window, door, band, rect, arch, field, railing, ornament "
                            f"or repeat")
        try:
            fn(e)
        except KeyError as ex:
            raise GameError(f"facade element {i} ({t}): missing {ex.args[0]!r}")

    def repeat(self, e):
        el = e["element"]
        for k in range(int(e.get("n", 1))):
            x = dict(el)
            x["u"] = float(el.get("u", 0)) + k * float(e.get("du", 0))
            x["v"] = float(el.get("v", 0)) + k * float(e.get("dv", 0))
            self.element(x, k)

    def rect(self, e):
        self.box(float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"]), self.c(e.get("color"), "dark"))

    def arch(self, e):
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        rise = min(float(e.get("rise", w / 2)), h)
        col = self.c(e.get("color"), "dark")
        self.box(u, v + rise, w, h - rise, col)
        if rise > 0:
            x0, y0 = self.px(u, v)
            x1, y1 = self.px(u + w, v + 2 * rise)
            # a segmental top: the chord of an ellipse through both springing points and the crown
            self.d.chord([x0, y0, x1 - 1, y1], 180, 360, fill=col)

    def field(self, e):
        from .partmodel import pattern_image
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        if "pattern" not in e:
            self.box(u, v, w, h, self.c(e.get("color"), "body"))
            return
        col = self.c(e.get("color"), "body")[:3]
        col2 = self.c(e.get("color2"))[:3] if e.get("color2") else None
        sw, sh = (float(x) for x in e.get("size_m", (1.0, 1.0)))
        tile = pattern_image(e["pattern"], "#%02x%02x%02x" % col,
                             ("#%02x%02x%02x" % col2) if col2 else None)
        tw, th = max(2, int(round(sw * self.k))), max(2, int(round(sh * self.k)))
        tile = tile.resize((tw, th), Image.LANCZOS).convert("RGBA")
        x0, y0 = self.px(u, v)
        x1, y1 = self.px(u + w, v + h)
        region = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)))
        for yy in range(0, region.height, th):
            for xx in range(0, region.width, tw):
                region.paste(tile, (xx, yy))
        self.im.paste(region, (x0, y0))

    def band(self, e):
        v, h = float(e["v"]), float(e["h"])
        col = self.c(e.get("color"), "trim")
        dark = self.c(e.get("color2"), "dark")
        hi = self.shade(col, 1.18)
        style = e.get("style", "plain")
        U = float(e.get("u", 0))
        W = float(e.get("w", self.W - U))
        self.box(U, v, W, h, col)
        self.box(U, v, W, max(h * 0.12, 1 / self.k), hi)                      # lit top edge
        self.box(U, v + h - max(h * 0.12, 1 / self.k), W, max(h * 0.12, 1 / self.k), self.shade(col, 0.7))
        if style == "dentil":
            step = max(h * 0.7, 0.16)
            n = int(W / step)
            for j in range(n):
                self.box(U + j * step + step * 0.25, v + h * 0.3, step * 0.5, h * 0.5, dark)
        elif style == "molding":
            self.box(U, v + h * 0.4, W, h * 0.18, dark)
        elif style == "frieze":
            step = max(h * 1.1, 0.3)
            n = int(W / step) + 1
            for j in range(n):
                cx, cy = U + j * step + step / 2, v + h / 2
                if cx > U + W:
                    break
                r = h * 0.32
                x0, y0 = self.px(cx - r, cy - r)
                x1, y1 = self.px(cx + r, cy + r)
                self.d.ellipse([x0, y0, x1, y1], fill=dark)
                x0, y0 = self.px(cx - r * 0.45, cy - r * 0.45)
                x1, y1 = self.px(cx + r * 0.45, cy + r * 0.45)
                self.d.ellipse([x0, y0, x1, y1], fill=hi)
                lx0, ly = self.px(cx + r * 1.2, cy)
                lx1, _ = self.px(cx + step - r * 1.2, cy)
                self.d.line([(lx0, ly), (lx1, ly)], fill=dark, width=max(1, int(h * self.k * 0.12)))
        elif style in ("brackets", "corbel"):
            step = float(e.get("spacing", 1.0))
            n = int(W / step)
            for j in range(n):
                bx = U + j * step + step / 2
                self.box(bx - 0.07, v, 0.14, h, hi)
                self.box(bx + 0.03, v + h * 0.15, 0.05, h * 0.8, dark)

    def window(self, e):
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        frame = self.c(e.get("frame"), "trim")
        glass = self.c(e.get("glass"), "glass")
        sash = self.c(e.get("sash"), "sash")
        sky = self.c(e.get("sky"), "sky")
        fw = float(e.get("frame_w", 0.1))
        dark = self.shade(frame, 0.62)
        if e.get("hood") or e.get("pediment"):
            hh = 0.28
            self.box(u - fw - 0.12, v - fw - hh, w + 2 * fw + 0.24, hh, self.shade(frame, 1.12))
            self.box(u - fw - 0.12, v - fw - 0.06, w + 2 * fw + 0.24, 0.06, dark)
            if e.get("pediment"):
                x0, y0 = self.px(u - fw - 0.12, v - fw - hh)
                x1, _ = self.px(u + w + fw + 0.12, v - fw - hh)
                xm, ytop = self.px(u + w / 2, v - fw - hh - min(0.6, w * 0.35))
                self.d.polygon([(x0, y0), (x1, y0), (xm, ytop)], fill=self.shade(frame, 1.12), outline=dark)
        self.box(u - fw, v - fw, w + 2 * fw, h + 2 * fw, frame)               # frame
        self.box(u + w + fw * 0.4, v - fw, fw * 0.6, h + 2 * fw, dark)       # shadow on its right
        gv, gh = v, h
        if e.get("transom"):
            th = min(0.6, h * 0.22)
            self.box(u, v, w, th, self.c(e.get("transom_color"), "accent"))
            for j in range(4):
                self.box(u + w * (0.1 + 0.22 * j), v + th * 0.3, w * 0.1, th * 0.4, self.shade(glass, 1.4))
            self.box(u, v + th, w, fw * 0.8, frame)
            gv, gh = v + th + fw * 0.8, h - th - fw * 0.8
        self.box(u, gv, w, gh, glass)
        # sky reflection in the upper part of each pane
        self.box(u, gv, w, gh * 0.18, sky)
        if e.get("curtain"):
            cur = self.c(e.get("curtain"))
            self.box(u + w * 0.05, gv + gh * 0.22, w * 0.22, gh * 0.75, cur)
            self.box(u + w * 0.73, gv + gh * 0.22, w * 0.22, gh * 0.75, cur)
        # meeting rail and stiles
        self.box(u, gv + gh / 2 - fw * 0.35, w, fw * 0.7, sash)
        if e.get("mullion", w > 1.4):
            self.box(u + w / 2 - fw * 0.35, gv, fw * 0.7, gh, sash)
        if e.get("arch"):
            x0, y0 = self.px(u - fw, v - fw - w / 2)
            x1, y1 = self.px(u + w + fw, v - fw + w / 2)
            self.d.pieslice([x0, y0, x1, y1], 180, 360, fill=frame)
            x0, y0 = self.px(u, v - w / 2 + 0.02)
            x1, y1 = self.px(u + w, v + w / 2)
            self.d.pieslice([x0, y0, x1, y1], 180, 360, fill=glass)
        if e.get("sill", True):
            self.box(u - fw - 0.08, v + h + fw, w + 2 * fw + 0.16, 0.12, self.shade(frame, 1.15))
            self.box(u - fw - 0.08, v + h + fw + 0.12, w + 2 * fw + 0.16, 0.05, dark)

    def door(self, e):
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        frame = self.c(e.get("frame"), "trim")
        col = self.c(e.get("color"), "door")
        fw = 0.14
        self.box(u - fw, v - fw, w + 2 * fw, h + fw, frame)
        top = v
        if e.get("transom", True):
            th = min(0.6, h * 0.18)
            self.box(u, v, w, th, self.c("glass"))
            self.box(u, v, w, th * 0.3, self.c("sky"))
            top = v + th + 0.06
            self.box(u, v + th, w, 0.06, frame)
        n = int(e.get("leaves", 2))
        lw = w / n
        for j in range(n):
            lu = u + j * lw
            self.box(lu + 0.02, top, lw - 0.04, v + h - top, col)
            for k in range(2):                                              # two raised panels per leaf
                pv = top + 0.15 + k * (v + h - top - 0.3) / 2
                ph = (v + h - top - 0.45) / 2
                self.box(lu + lw * 0.2, pv, lw * 0.6, ph, self.shade(col, 1.25))
                self.box(lu + lw * 0.2, pv + ph - 0.04, lw * 0.6, 0.04, self.shade(col, 0.7))

    def railing(self, e):
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        col = self.c(e.get("color"), "trim")
        step = float(e.get("spindle", 0.18))
        if e.get("back"):
            self.box(u, v, w, h, self.c(e["back"]))
        if e.get("style") == "iron":            # thin bars with spear tops between two rails
            self.box(u, v + 0.12, w, 0.05, col)
            self.box(u, v + h - 0.1, w, 0.06, col)
            x = u + step / 2
            while x < u + w - 0.02:
                self.box(x - 0.02, v + 0.04, 0.04, h - 0.06, col)
                x0, y0 = self.px(x - 0.05, v + 0.08)
                x1, y1 = self.px(x + 0.05, v)
                self.d.polygon([(x0, y0), (x1, y0), ((x0 + x1) / 2, y1)], fill=col)
                x += step
            return
        self.box(u, v, w, 0.1, self.shade(col, 1.15))
        self.box(u, v + h - 0.08, w, 0.08, col)
        x = u + step / 2
        while x < u + w - 0.04:
            self.box(x - 0.03, v + 0.1, 0.06, h - 0.18, col)
            x += step

    def ornament(self, e):
        u, v, w, h = float(e["u"]), float(e["v"]), float(e["w"]), float(e["h"])
        col = self.c(e.get("color"), "trim")
        dark = self.c(e.get("color2"), "dark")
        style = e.get("style", "sunburst")
        x0, y0 = self.px(u, v)
        x1, y1 = self.px(u + w, v + h)
        if style in ("sunburst", "fan"):
            cx, cy = (x0 + x1) / 2, y1
            R = min((x1 - x0) / 2, (y1 - y0))
            rays = 9 if style == "sunburst" else 7
            for j in range(rays):
                a0 = math.pi + math.pi * j / rays
                a1 = math.pi + math.pi * (j + 0.55) / rays
                self.d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                                (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=col)
            r = R * 0.25
            self.d.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=dark)
        elif style == "rosette":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            R = min(x1 - x0, y1 - y0) / 2
            for j in range(8):
                a = 2 * math.pi * j / 8
                px_, py_ = cx + R * 0.55 * math.cos(a), cy + R * 0.55 * math.sin(a)
                self.d.ellipse([px_ - R * 0.38, py_ - R * 0.38, px_ + R * 0.38, py_ + R * 0.38], fill=col)
            self.d.ellipse([cx - R * 0.35, cy - R * 0.35, cx + R * 0.35, cy + R * 0.35], fill=dark)
        elif style == "diamond":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            self.d.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=col, outline=dark)
        else:
            raise GameError("ornament style: sunburst, fan, rosette or diamond")


def draw(spec: dict) -> Image.Image:
    return Facade(spec).im

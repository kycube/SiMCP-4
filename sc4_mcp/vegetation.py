"""Trees and shrubs as parts models (partmodel), rendered per view like the game's own flora (batrender): a trunk
and branches, and the crown built of leaf clumps - rounded masses ("blob" parts) dressed in a see-through leaf
texture, lit by the sun with their own shadows and the sky's occlusion, so the crown is bright on the sunny side,
dark inside and ragged at the edge as the game's pre-rendered trees are.

Every generator returns a parts model ({"materials", "parts"}) with the tree's foot at (width / 2, width / 2) (lobes
of the crown may reach a little past 0..width), z up; `seed` varies the shape. Sizes are life-size; the game's own trees are drawn about life-size too
(its large deciduous tree is 15 m).
"""

from __future__ import annotations

import math

import numpy as np

KINDS = ("broadleaf", "conifer", "palm", "shrub")


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in rgb)


def _shade(rgb, k):
    return tuple(v * k for v in rgb)


def broadleaf(height: float = 13.0, width: float = 8.5, leaf=(90, 114, 58), trunk=(78, 64, 52), seed: int = 1,
              clumps: int = 0) -> dict:
    """A deciduous tree (maple, oak, elm): a trunk to about 35 % of its height, branches, a rounded crown."""
    rnd = np.random.default_rng(seed)
    c = width / 2
    trunk_h = height * 0.3
    tr = 0.018 * height + 0.08
    crown_h = height - trunk_h * 0.85
    cz = height - crown_h / 2
    rx = ry = width / 2
    rz = crown_h / 2
    mats = {"bark": {"color": _hex(trunk), "grain": 0.15},
            "leaves": {"pattern": "leaves", "color": _hex(leaf), "color2": _hex(_shade(leaf, 0.62)),
                       "density": 0.62, "seed": seed, "size_m": [3.2, 3.2], "grain": 0.1, "wrap": 0.6},
            "core": {"pattern": "leaves", "color": _hex(_shade(leaf, 0.86)), "color2": _hex(_shade(leaf, 0.6)),
                     "density": 1.3, "seed": seed + 7, "size_m": [2.6, 2.6], "grain": 0.08, "wrap": 0.6}}
    parts = [{"type": "prism", "cx": c, "cy": c, "z": 0, "r": tr, "h": trunk_h + 0.6, "sides": 0, "mat": "bark"}]
    for k in range(5):                              # main branches into the crown
        a = 2 * math.pi * (k / 5 + rnd.uniform(-0.06, 0.06))
        L = width * rnd.uniform(0.22, 0.32)
        parts.append({"type": "beam", "from": [c, c, trunk_h], "to": [c + L * math.cos(a), c + L * math.sin(a),
                                                                       trunk_h + crown_h * rnd.uniform(0.3, 0.5)],
                      "w": tr * 0.75, "h": tr * 0.75, "offset": -tr * 0.37, "mat": "bark"})
    crown = {"c": [c, c, cz], "r": [rx, ry, rz], "mix": 0.65}
    parts.append({"type": "blob", "cx": c, "cy": c, "z": cz, "rx": rx * 0.6, "ry": ry * 0.6, "rz": rz * 0.62,
                  "jitter": 0.22, "seed": seed, "mat": "core", "crown": crown})
    n = clumps or int(30 + 2.6 * width * crown_h / 4)
    for k in range(n):
        while True:                                 # a point in the crown, mostly towards its shell
            v = rnd.normal(size=3)
            v /= np.linalg.norm(v)
            rr = rnd.uniform(0.6, 1.0) ** 0.35
            x, y, z = v * rr
            if z > -0.75:
                break
        s = rnd.uniform(0.12, 0.22) * width / 2 + 0.4
        out = rnd.uniform(0.85, 1.12)                # lobes past the crown's shell, hollows inside it
        parts.append({"type": "blob", "cx": c + x * (rx - s * 0.6) * out, "cy": c + y * (ry - s * 0.6) * out,
                      "z": cz + z * (rz - s * 0.5) * out, "rx": s, "ry": s, "rz": s * 0.85, "jitter": 0.4,
                      "seed": seed * 101 + k, "detail": 1, "mat": "leaves", "crown": crown})
    return {"materials": mats, "parts": parts}


def conifer(height: float = 14.0, width: float = 6.0, leaf=(62, 88, 62), trunk=(84, 66, 52), seed: int = 1) -> dict:
    """A spruce or fir: a straight trunk, tiers of needle clumps narrowing to a point."""
    rnd = np.random.default_rng(seed)
    c = width / 2
    mats = {"bark": {"color": _hex(trunk), "grain": 0.15},
            "needles": {"pattern": "needles", "color": _hex(leaf), "color2": _hex(_shade(leaf, 0.55)),
                        "density": 0.75, "seed": seed, "size_m": [2.4, 2.4], "grain": 0.1, "wrap": 0.3},
            "core": {"pattern": "needles", "color": _hex(_shade(leaf, 0.6)), "color2": _hex(_shade(leaf, 0.4)),
                     "density": 1.5, "seed": seed + 5, "size_m": [2.0, 2.0], "grain": 0.08, "wrap": 0.3}}
    base = height * 0.1
    parts = [{"type": "prism", "cx": c, "cy": c, "z": 0, "r": 0.012 * height + 0.08, "h": height * 0.9,
              "sides": 0, "mat": "bark"},
             {"type": "cone", "cx": c, "cy": c, "z": base, "r": width * 0.4, "h": height - base, "sides": 10,
              "mat": "core"}]
    tiers = max(5, int(height / 1.6))
    for t in range(tiers):
        f = t / tiers
        z = base + (height - base) * f * 0.92
        R = width / 2 * (1 - f) ** 0.95
        n = max(3, int(2 * math.pi * R / 1.3))
        for k in range(n):
            a = 2 * math.pi * (k + rnd.uniform(-0.3, 0.3)) / n + t * 0.5
            s = max(0.45, R * 0.42) * rnd.uniform(0.8, 1.1)
            parts.append({"type": "blob", "cx": c + (R - s * 0.5) * math.cos(a), "cy": c + (R - s * 0.5) * math.sin(a),
                          "z": z, "rx": s, "ry": s, "rz": s * 0.55, "jitter": 0.3, "seed": seed * 97 + t * 13 + k,
                          "detail": 1, "mat": "needles",
                          "crown": {"c": [c, c, base + (height - base) * 0.35], "r": [width / 2, width / 2,
                                                                                    (height - base) * 0.6],
                                    "mix": 0.5}})
    parts.append({"type": "cone", "cx": c, "cy": c, "z": height * 0.9, "r": 0.35, "h": height * 0.1, "sides": 6,
                  "mat": "needles"})
    return {"materials": mats, "parts": parts}


def palm(height: float = 10.0, width: float = 7.0, leaf=(92, 120, 56), trunk=(122, 104, 84), seed: int = 1) -> dict:
    """A palm: a slightly curved ringed trunk and a crown of drooping fronds."""
    rnd = np.random.default_rng(seed)
    c = width / 2
    mats = {"bark": {"pattern": "shingle", "color": _hex(trunk), "color2": _hex(_shade(trunk, 0.7)),
                     "size_m": [0.8, 0.8], "grain": 0.12},
            "frond": {"pattern": "fronds", "color": _hex(leaf), "color2": _hex(_shade(leaf, 0.6)), "seed": seed,
                      "size_m": [1.0, 1.0], "grain": 0.1, "wrap": 0.5},
            "heart": {"color": _hex(_shade(leaf, 0.55)), "grain": 0.1}}
    lean = rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6)
    parts, prev = [], (c, c, 0.0)
    segs = 5
    for k in range(1, segs + 1):                    # the trunk, leaning more towards the top
        f = k / segs
        pt = (c + lean[0] * f * f, c + lean[1] * f * f, height * f * 0.97)
        parts.append({"type": "beam", "from": list(prev), "to": list(pt), "w": 0.42 - 0.12 * f, "h": 0.42 - 0.12 * f,
                      "offset": -(0.21 - 0.06 * f), "mat": "bark"})
        prev = pt
    tx, ty, tz = prev
    parts.append({"type": "blob", "cx": tx, "cy": ty, "z": tz, "r": 0.45, "rz": 0.5, "jitter": 0.1, "mat": "heart"})
    n = 16
    for k in range(n):                              # fronds: two leaning sheets each, drooping
        a = 2 * math.pi * k / n + rnd.uniform(-0.15, 0.15)
        up = rnd.uniform(-0.1, 0.5)
        L = width / 2 * rnd.uniform(0.85, 1.0)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy * 0.55, dx * 0.55              # half the frond's width, across it
        mid = (tx + dx * L * 0.55, ty + dy * L * 0.55, tz + 0.4 + up)
        end = (tx + dx * L, ty + dy * L, tz - 1.1 + up * 0.5)
        for a0, a1, wid0, wid1 in (((tx, ty, tz + 0.2), mid, 0.4, 1.0), (mid, end, 1.0, 0.3)):
            parts.append({"type": "quad", "mat": "frond", "points": [
                [a0[0] - px * wid0, a0[1] - py * wid0, a0[2]], [a1[0] - px * wid1, a1[1] - py * wid1, a1[2]],
                [a1[0] + px * wid1, a1[1] + py * wid1, a1[2]], [a0[0] + px * wid0, a0[1] + py * wid0, a0[2]]]})
    return {"materials": mats, "parts": parts}


def shrub(height: float = 1.6, width: float = 2.4, leaf=(88, 116, 56), seed: int = 1) -> dict:
    """A shrub: a low mound of leaf clumps."""
    rnd = np.random.default_rng(seed)
    c = width / 2
    mats = {"leaves": {"pattern": "leaves", "color": _hex(leaf), "color2": _hex(_shade(leaf, 0.6)),
                       "density": 0.7, "seed": seed, "size_m": [2.2, 2.2], "grain": 0.1, "wrap": 0.4},
            "core": {"pattern": "leaves", "color": _hex(_shade(leaf, 0.6)), "color2": _hex(_shade(leaf, 0.42)),
                     "density": 1.5, "seed": seed + 3, "size_m": [1.8, 1.8], "grain": 0.08, "wrap": 0.4}}
    parts = [{"type": "blob", "cx": c, "cy": c, "z": height * 0.42, "rx": width * 0.4, "ry": width * 0.4,
              "rz": height * 0.45, "jitter": 0.2, "seed": seed, "mat": "core"}]
    for k in range(7):
        a = 2 * math.pi * k / 7 + rnd.uniform(-0.3, 0.3)
        rr = width * rnd.uniform(0.12, 0.25)
        s = width * rnd.uniform(0.2, 0.28)
        parts.append({"type": "blob", "cx": c + rr * math.cos(a), "cy": c + rr * math.sin(a),
                      "z": height * rnd.uniform(0.35, 0.6), "rx": s, "ry": s, "rz": s * 0.85, "jitter": 0.3,
                      "seed": seed * 31 + k, "mat": "leaves"})
    return {"materials": mats, "parts": parts}


def model(kind: str, height: float, width: float, leaf=None, trunk=None, seed: int = 1) -> dict:
    if kind not in KINDS:
        raise ValueError("kind: " + ", ".join(KINDS))
    kw = {}
    if leaf is not None:
        kw["leaf"] = tuple(leaf)
    if trunk is not None and kind != "shrub":
        kw["trunk"] = tuple(trunk)
    return {"broadleaf": broadleaf, "conifer": conifer, "palm": palm, "shrub": shrub}[kind](height, width,
                                                                                        seed=seed, **kw)

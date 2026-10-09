"""Build a SiMCP 4 release: the wheel (with the plugin and bridge DLLs inside) and a zip for GitHub releases.

    python scripts/package_release.py            # uses bridge\\build\\*.dll, building them first if missing

Output in dist\\: simcp_4-<version>-py3-none-any.whl and SiMCP-4-<version>.zip (the wheel, README, LICENSE,
CHANGELOG, the tool list and the client examples). The wheel is written directly (a zip with the package and its
.dist-info: METADATA, WHEEL, entry_points.txt, RECORD), so nothing needs to be installed or downloaded to build it.
"""

from __future__ import annotations

import base64
import glob
import hashlib
import os
import re
import shutil
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLLS = ("simcp4.dll", "simcp4bridge.dll")
PACKAGE = "sc4_mcp"
DATA = ("data/*.json", "guide.md", "bin/*.dll")


def _project() -> dict:
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()

    def one(key):
        m = re.search(r'^%s = "([^"]*)"' % key, text, re.M)
        return m.group(1) if m else ""

    deps = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
    scripts = dict(re.findall(r'^(\w[\w-]*) = "([\w.]+:\w+)"',
                              text.split("[project.scripts]", 1)[1].split("[", 1)[0], re.M)) \
        if "[project.scripts]" in text else {}
    classifiers = re.findall(r'"([^"]+ :: [^"]+)"', text.split("classifiers", 1)[1].split("]", 1)[0]) \
        if "classifiers" in text else []
    return {"name": one("name"), "version": one("version"), "summary": one("description"),
            "requires_python": one("requires-python"), "license": one("license"),
            "deps": re.findall(r'"([^"]+)"', deps.group(1)) if deps else [], "scripts": scripts,
            "classifiers": classifiers}


def _files() -> list[tuple[str, str]]:
    """(path on disk, path in the wheel) for the package's modules and data."""
    out = []
    pkg = os.path.join(ROOT, PACKAGE)
    for f in sorted(glob.glob(os.path.join(pkg, "*.py"))):
        out.append((f, "%s/%s" % (PACKAGE, os.path.basename(f))))
    for pattern in DATA:
        for f in sorted(glob.glob(os.path.join(pkg, pattern))):
            out.append((f, "%s/%s" % (PACKAGE, os.path.relpath(f, pkg).replace(os.sep, "/"))))
    return out


def _hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def build_wheel(dist: str) -> str:
    p = _project()
    name = p["name"].replace("-", "_")
    info = "%s-%s.dist-info" % (name, p["version"])
    meta = ["Metadata-Version: 2.4", "Name: %s" % p["name"], "Version: %s" % p["version"],
            "Summary: %s" % p["summary"], "License-Expression: %s" % p["license"], "License-File: LICENSE",
            "Requires-Python: %s" % p["requires_python"]]
    meta += ["Classifier: %s" % c for c in p["classifiers"]]
    meta += ["Requires-Dist: %s" % d for d in p["deps"]]
    meta += ["Description-Content-Type: text/markdown", "",
             open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()]
    extra = {
        "%s/METADATA" % info: "\n".join(meta).encode("utf-8"),
        "%s/WHEEL" % info: b"Wheel-Version: 1.0\nGenerator: simcp-package\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        "%s/entry_points.txt" % info: ("[console_scripts]\n" + "".join("%s = %s\n" % kv for kv in p["scripts"].items())
                                       ).encode("utf-8"),
        "%s/licenses/LICENSE" % info: open(os.path.join(ROOT, "LICENSE"), "rb").read(),
    }
    path = os.path.join(dist, "%s-%s-py3-none-any.whl" % (name, p["version"]))
    record = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in _files():
            data = open(src, "rb").read()
            z.writestr(arc, data)
            record.append("%s,%s,%d" % (arc, _hash(data), len(data)))
        for arc, data in extra.items():
            z.writestr(arc, data)
            record.append("%s,%s,%d" % (arc, _hash(data), len(data)))
        record.append("%s/RECORD,," % info)
        z.writestr("%s/RECORD" % info, "\n".join(record) + "\n")
    return path


def main() -> int:
    p = _project()
    build = os.path.join(ROOT, "bridge", "build")
    if not all(os.path.isfile(os.path.join(build, d)) for d in DLLS):
        print("building the DLLs (bridge\\build.bat)")
        subprocess.run(["cmd", "/c", os.path.join(ROOT, "bridge", "build.bat")], check=True)
    bundled = os.path.join(ROOT, PACKAGE, "bin")
    os.makedirs(bundled, exist_ok=True)
    for d in DLLS:
        shutil.copy2(os.path.join(build, d), os.path.join(bundled, d))
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    wheel = build_wheel(dist)
    with zipfile.ZipFile(wheel) as z:
        inside = set(z.namelist())
    missing = [d for d in DLLS if "%s/bin/%s" % (PACKAGE, d) not in inside]
    if missing:
        raise SystemExit("the wheel lacks %s" % ", ".join(missing))
    zpath = os.path.join(dist, "SiMCP-4-%s.zip" % p["version"])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(wheel, os.path.basename(wheel))
        for rel in ("README.md", "LICENSE", "CHANGELOG.md", os.path.join("docs", "TOOLS.md")):
            z.write(os.path.join(ROOT, rel), rel.replace(os.sep, "/"))
        for ex in sorted(glob.glob(os.path.join(ROOT, "examples", "*"))):
            z.write(ex, "examples/" + os.path.basename(ex))
    print("wheel:", wheel)
    print("zip:  ", zpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

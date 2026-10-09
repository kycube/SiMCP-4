"""The simcp4 command (and python -m sc4_mcp): the MCP server, or --check for the setup check. The check runs
before the server module is imported, so it can report a missing or wrong MCP package."""

from __future__ import annotations

import argparse


def main():
    ap = argparse.ArgumentParser(prog="simcp4")
    ap.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--check", action="store_true", help="check the setup and exit (no game needed)")
    a = ap.parse_args()
    if a.check:
        from . import doctor
        raise SystemExit(doctor.main())
    from . import server
    server.run(a.transport, a.port)

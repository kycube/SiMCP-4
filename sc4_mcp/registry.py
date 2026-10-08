"""Tool registration that makes every tool self-describing for any MCP client (Claude, OpenAI, Gemini, ...).

Clients show their models only what the protocol carries: the tool description, the JSON schema of the arguments
and the tool annotations. So each tool function documents itself in one place, its docstring:

    def advance_time(days: int = 0, ...) -> dict:
        '''What the tool does (becomes the MCP description).

        Args:
            days: what this parameter means (becomes the parameter's JSON-schema "description").
        '''

`tool(kind)` turns the "Args:" section into per-parameter schema descriptions, sets the MCP annotations
(readOnlyHint / destructiveHint / idempotentHint / openWorldHint) for the kind, and reports a result
{"error": ...} as a real MCP tool error (isError = true; the text is the same JSON). The decorated function itself is
returned unchanged, so Python callers (tests, other tools) still get plain dicts.
"""

from __future__ import annotations

import functools
import inspect
import json
import re
import typing
from typing import Annotated

from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

# kind -> annotations. All tools act on the local game only (openWorldHint False).
KINDS = {
    # reads game state, changes nothing, same answer when repeated
    "read": ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    # reads game state but has a cursor or side effect on what is shown (e.g. "since the last call")
    "observe": ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    # sets a value: repeating the call with the same arguments changes nothing more
    "set": ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    # acts in the game (builds, spends, advances time...): additive, not idempotent
    "act": ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    # discards or destroys something (unsaved city, buildings, a deal, a file, the game process)
    "destructive": ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False,
                                   openWorldHint=False),
}

REGISTERED: list[dict] = []          # [{"name", "kind", "fn"}] in registration order (docs generator)
_ARGS_RE = re.compile(r"^(\w+)\s*(?:\([^)]*\))?:\s*(.*)$")


def split_doc(doc: str | None) -> tuple[str, dict[str, str]]:
    """(description without the Args section, {parameter: description})."""
    lines = inspect.cleandoc(doc or "").splitlines()
    desc, params, i = [], {}, 0
    while i < len(lines):
        if lines[i].strip() == "Args:":
            i += 1
            cur = None
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                text = lines[i].strip()
                if not text:
                    i += 1
                    if i < len(lines) and not lines[i].startswith((" ", "\t")):
                        break
                    continue
                m = _ARGS_RE.match(text)
                indent = len(lines[i]) - len(lines[i].lstrip())
                if m and (cur is None or indent <= base):
                    cur, base = m.group(1), indent
                    params[cur] = m.group(2)
                elif cur:
                    params[cur] += " " + text
                i += 1
            continue
        desc.append(lines[i])
        i += 1
    # unwrap the source's hard line breaks (paragraphs stay separated by a blank line)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", "\n".join(desc).strip())
    return text, {k: " ".join(v.split()) for k, v in params.items()}


def _json(r) -> str:
    return json.dumps(r, separators=(",", ":"), ensure_ascii=False, default=str)


def title_of(name: str) -> str:
    return name.replace("_", " ").capitalize()


def tool(mcp, kind: str, title: str | None = None, structured_output: bool | None = None):
    """Register fn with `mcp` as a documented tool of this kind (see module docstring)."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)}")

    def deco(fn):
        description, docs = split_doc(fn.__doc__)
        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn, include_extras=True)
        missing = [p for p in sig.parameters if p not in docs]
        if missing:                       # caught by tools/gen_tool_docs.py --check (never crash a running server)
            fn.__undocumented__ = missing
        params = [p.replace(annotation=Annotated[hints.get(p.name, typing.Any),
                                                 Field(description=docs.get(p.name, ""))])
                  for p in sig.parameters.values()]

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            r = fn(*a, **kw)
            if isinstance(r, dict) and "error" in r:      # a tool error the model should see and act on
                return CallToolResult(content=[TextContent(type="text", text=_json(r))], isError=True)
            if isinstance(r, list) and any(not isinstance(x, (str, int, float, bool, dict, list, type(None)))
                                           for x in r):
                return r               # mixed content (text + images): FastMCP converts each item
            if isinstance(r, (dict, list)):
                return _json(r)        # compact JSON text: pretty-printing puts every number of a grid on a line
            return r

        wrapper.__signature__ = sig.replace(parameters=params,
                                            return_annotation=hints.get("return", inspect.Signature.empty))
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        if "return" in hints:
            wrapper.__annotations__["return"] = hints["return"]
        mcp.tool(name=fn.__name__, title=title or title_of(fn.__name__), description=description,
                 annotations=KINDS[kind], structured_output=structured_output)(wrapper)
        REGISTERED.append({"name": fn.__name__, "kind": kind, "fn": fn})
        return fn

    return deco

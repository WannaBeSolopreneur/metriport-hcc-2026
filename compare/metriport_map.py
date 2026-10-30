"""Parse Metriport's public hcc-map.ts (export const hccMap = { CODE: [display, [v24], [v28]] })."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

ENTRY_RE = re.compile(
    r'^\s*"?([A-Z][0-9A-Z]+)"?\s*:\s*\[\s*'  # key and opening bracket
    r'("(?:[^"\\]|\\.)*")\s*,\s*'  # display string
    r"\[([^\]]*)\]\s*,\s*"  # v24 list
    r"\[([^\]]*)\]\s*,?\s*\]\s*,?",  # v28 list, optional trailing comma
    re.M,
)


@dataclass(frozen=True)
class MapEntry:
    display: str
    v24: tuple[int, ...]
    v28: tuple[int, ...]


def _ints(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split(",") if x.strip())


def parse_hcc_map(source: str) -> dict[str, MapEntry]:
    body = source.split("export const hccMap", 1)[1]
    body = body[body.index("{") + 1 :]
    out: dict[str, MapEntry] = {}
    for code, display, v24, v28 in ENTRY_RE.findall(body):
        if code in out:
            raise ValueError(f"duplicate key {code} in hcc-map.ts")
        out[code] = MapEntry(json.loads(display), _ints(v24), _ints(v28))
    # Guard against silent regex misses: every top level key line must have parsed.
    keys = re.findall(r'^\s{2}"?([A-Z][0-9A-Z]+)"?\s*:', body, re.M)
    if len(keys) != len(out):
        raise ValueError(f"parsed {len(out)} entries but found {len(keys)} keys")
    return out

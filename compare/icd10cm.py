"""Read the official ICD-10-CM code files: valid codes for a year, and that year's addenda."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

ADDENDA_RE = re.compile(r"^(Add|Delete):\s+([A-Z][0-9A-Z]{2,6})\s")


@dataclass(frozen=True)
class CodeYear:
    year: int
    codes: frozenset[str]
    added: frozenset[str]
    deleted: frozenset[str]


def read_code_year(path: Path, year: int) -> CodeYear:
    with zipfile.ZipFile(path) as zf:
        codes_txt = zf.read(f"icd10cm_codes_{year}.txt").decode("latin-1")
        addenda_txt = zf.read(f"icd10cm_codes_addenda_{year}.txt").decode("latin-1")
    codes = frozenset(line.split(None, 1)[0] for line in codes_txt.splitlines() if line.strip())
    added, deleted = set(), set()
    for line in addenda_txt.splitlines():
        m = ADDENDA_RE.match(line)
        if m:
            (added if m.group(1) == "Add" else deleted).add(m.group(2))
    return CodeYear(year, codes, frozenset(added), frozenset(deleted))

"""Read the CMS ICD-10-CM to HCC mapping CSV straight out of the CMS zip."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

CODE_RE = re.compile(r"^[A-Z][0-9][0-9A-Z]{1,5}$")


def _norm(header: str) -> str:
    return " ".join(header.split())


def read_cms_csv(zip_path: Path, member: str) -> tuple[list[str], list[dict[str, str]]]:
    """Return (normalized header, data rows) from a CMS mapping CSV.

    The CMS file has title lines above the header and source notes below the data.
    Data rows are the ones whose first cell looks like an ICD-10-CM code.
    """
    with zipfile.ZipFile(zip_path) as zf:
        text = zf.read(member).decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    start = next(i for i, r in enumerate(rows) if r and r[0].startswith("Diagnosis"))
    header = [_norm(h) for h in rows[start]]
    out = []
    for r in rows[start + 1 :]:
        if r and CODE_RE.match(r[0].strip()):
            out.append({h: (v or "").strip() for h, v in zip(header, r, strict=False)})
    return header, out

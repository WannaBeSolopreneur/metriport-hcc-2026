"""Independent recount of the headline numbers.

This script does not import any code from this repo. It uses only the Python standard
library. It reads the pinned input files that `make crosswalk` and `make compare` downloaded
into .cache, checks their sha256, and recounts everything with its own parser. Then it checks
data/hcc_crosswalk_2026.csv row by row, and spot checks 25 codes.

Run it with `make verify`. It exits with an error if any number is different.
"""

from __future__ import annotations

import csv
import hashlib
import io
import random
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"

FILES = {
    "cms26": (
        "cms_2026_midyear_final_icd10_mappings.zip",
        "1143bc102311fa6f9da33ef7c72cb4a34849a4354feb0ef1c745d38c887f23a2",
    ),
    "cms25": (
        "cms_2025_midyear_final_icd10_mappings.zip",
        "3fd8a313d8476332243fd4ad139cb3c71bd3597e1e1164c6e9f844a66de0b8ac",
    ),
    "map": (
        "metriport_hcc-map_e1f26d5.ts",
        "8ddc36082f70ab3c2df9b80a5d8943e9da6e8116e433955a32ce0bb3f2a0f15c",
    ),
}
CODE = re.compile(r"[A-Z][0-9A-Z]{2,6}")
V28 = "CMS-HCC Model Category V28"
V24 = "CMS-HCC Model Category V24"
MODELS = {
    "CMS-HCC ESRD Model Category V21": "ESRD-V21",
    "CMS-HCC ESRD Model Category V24": "ESRD-V24",
    "CMS-HCC Model Category V22": "CMS-HCC-V22",
    "CMS-HCC Model Category V28": "CMS-HCC-V28",
    "RxHCC Model Category V08": "RxHCC-V08",
}
EXPECTED = {
    "crosswalk rows": 58084,
    "codes with a V28 HCC in CMS 2026": 8019,
    "codes in the map": 11184,
    "V28 codes missing from the map": 231,
    "missing codes not in CMS 2025 (new)": 134,
    "missing codes in CMS 2025 with a V28 HCC": 97,
    "map V28 differences vs CMS 2026": 0,
    "map V24 differences vs CMS 2025": 0,
    "HCC numbers in both V24 and V28": 26,
    "of those, sharing no codes": 23,
}


def path_of(key: str) -> Path:
    name, sha = FILES[key]
    p = CACHE / name
    if not p.exists():
        sys.exit(f"missing {p}. Run `make crosswalk compare` first.")
    if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
        sys.exit(f"sha256 mismatch for {p}")
    return p


def read_cms(key: str) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(path_of(key)) as z:
        member = next(n for n in z.namelist() if n.endswith("Mappings.csv"))
        rows = list(csv.reader(io.StringIO(z.read(member).decode("latin-1"))))
    header = [c.replace("\n", " ").strip() for c in rows[3]]
    return header, [r for r in rows[4:] if r and CODE.fullmatch(r[0].strip())]


def by_code(header, rows, column) -> dict[str, set[int]]:
    i = header.index(column)
    out: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        out[r[0].strip()]
        if r[i].strip():
            out[r[0].strip()].add(int(r[i]))
    return out


def read_map() -> dict[str, tuple[set[int], set[int]]]:
    text = path_of("map").read_text(encoding="utf-8")
    pattern = (
        r'^\s*"?([A-Z0-9]+)"?\s*:\s*\[\s*"(?:[^"\\]|\\.)*"\s*,\s*\[([^\]]*)\]\s*,\s*\[([^\]]*)\]'
    )
    out = {}
    for code, a, b in re.findall(pattern, text, re.M | re.S):
        out[code] = (
            {int(x) for x in a.split(",") if x.strip()},
            {int(x) for x in b.split(",") if x.strip()},
        )
    return out


def expected_crosswalk(header, rows) -> set[tuple]:
    """(code, model, hcc or '', paying) rows the crosswalk should have."""
    out = set()
    for r in rows:
        code = r[0].strip()
        for col, model in MODELS.items():
            hcc = r[header.index(col)].strip()
            flag = r[header.index(f"{col} for 2026 Payment Year")].strip()
            if hcc and flag == "Yes":
                out.add((code, model, hcc, "true"))
            elif not hcc and flag == "No":
                out.add((code, model, "", "false"))
    return out


def main() -> None:
    h26, r26 = read_cms("cms26")
    h25, r25 = read_cms("cms25")
    mp = read_map()
    v28_26 = by_code(h26, r26, V28)
    v28_25 = by_code(h25, r25, V28)
    v24_25 = by_code(h25, r25, V24)

    v28_codes = {c for c, h in v28_26.items() if h}
    missing = sorted(v28_codes - set(mp))
    new = [c for c in missing if c not in v28_25]
    old = [c for c in missing if c in v28_25 and v28_25[c]]

    v24n: dict[int, set[str]] = defaultdict(set)
    v28n: dict[int, set[str]] = defaultdict(set)
    for c, (a, b) in mp.items():
        for n in a:
            v24n[n].add(c)
        for n in b:
            v28n[n].add(c)
    both = set(v24n) & set(v28n)

    with open(ROOT / "data" / "hcc_crosswalk_2026.csv", newline="") as f:
        xw = list(csv.DictReader(f))
    ours = {(r["code"], r["hcc_model"], r["hcc_code"], r["payment_flag"]) for r in xw}

    got = {
        "crosswalk rows": len(xw),
        "codes with a V28 HCC in CMS 2026": len(v28_codes),
        "codes in the map": len(mp),
        "V28 codes missing from the map": len(missing),
        "missing codes not in CMS 2025 (new)": len(new),
        "missing codes in CMS 2025 with a V28 HCC": len(old),
        "map V28 differences vs CMS 2026": sum(
            1 for c, (_, b) in mp.items() if c in v28_26 and b != v28_26[c]
        ),
        "map V24 differences vs CMS 2025": sum(
            1 for c, (a, _) in mp.items() if c in v24_25 and a != v24_25[c]
        ),
        "HCC numbers in both V24 and V28": len(both),
        "of those, sharing no codes": sum(1 for n in both if not v24n[n] & v28n[n]),
    }
    ok = True
    for k, want in EXPECTED.items():
        mark = "OK" if got[k] == want else "DIFFERENT"
        ok &= got[k] == want
        print(f"verify: {k}: {got[k]:,} (expected {want:,}) {mark}")

    exp = expected_crosswalk(h26, r26)
    same = ours == exp and len(ours) == len(xw)
    ok &= same
    print(f"verify: every crosswalk row matches the CMS 2026 file: {'OK' if same else 'NO'}")

    # Spot checks: 20 random codes (fixed seed) plus 5 named ones.
    codes = sorted({r[0].strip() for r in r26})
    picks = random.Random(20261030).sample(codes, 20) + ["C50A0", "E66813", "C810A", "I10", "Z992"]
    bad = [c for c in picks if {x for x in ours if x[0] == c} != {x for x in exp if x[0] == c}]
    ok &= not bad
    print(f"verify: spot checked {len(picks)} codes: {', '.join(picks)}")
    print(f"verify: spot check result: {'OK' if not bad else 'DIFFERENT ' + ', '.join(bad)}")
    if not ok:
        sys.exit("verify: FAILED")
    print("verify: all checks passed")


if __name__ == "__main__":
    main()

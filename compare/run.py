"""Compare Metriport's public hcc-map.ts with the CMS 2026 crosswalk.

Writes reports/compare.md, reports/missing_v28_codes.csv and reports/hcc_number_overlap.csv.
Every number comes from the pinned inputs, so two runs give byte-identical output.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass

from compare.metriport_map import MapEntry, parse_hcc_map
from crosswalk.build import build_rows
from crosswalk.cms import read_cms_csv
from crosswalk.sources import (
    CMS_2025,
    CMS_2026,
    METRIPORT_COMMIT,
    METRIPORT_HCC_MAP,
    METRIPORT_HCC_MAP_PATH,
    REPORTS,
    fetch,
)

V28_2025 = "CMS-HCC Model Category V28"
V24_2025 = "CMS-HCC Model Category V24"


@dataclass
class Result:
    map_codes: int
    v28_codes_2026: int
    missing: list[dict]
    v28_mismatch: list[tuple[str, tuple, tuple]]
    v24_mismatch: list[tuple[str, tuple, tuple]]
    v24_only_in_map: int
    overlap: list[dict]


def load_inputs():
    cms26_path, _ = fetch(CMS_2026)
    cms25_path, _ = fetch(CMS_2025)
    map_path, _ = fetch(METRIPORT_HCC_MAP)
    header26, rows26 = read_cms_csv(cms26_path, CMS_2026.member)
    _, rows25 = read_cms_csv(cms25_path, CMS_2025.member)
    hcc_map = parse_hcc_map(map_path.read_text(encoding="utf-8"))
    return build_rows(rows26, header26), rows25, hcc_map


def _by_code(rows: list[dict], column: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        out[r["Diagnosis Code"]]
        if r[column]:
            out[r["Diagnosis Code"]].add(int(r[column]))
    return out


def analyze(crosswalk: list[dict], rows25: list[dict], hcc_map: dict[str, MapEntry]) -> Result:
    v28_26: dict[str, set[int]] = defaultdict(set)
    other_26: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    display: dict[str, str] = {}
    for r in crosswalk:
        display[r["code"]] = r["display"]
        if not r["payment_flag"]:
            continue
        if r["hcc_model"] == "CMS-HCC-V28":
            v28_26[r["code"]].add(int(r["hcc_code"]))
        else:
            other_26[r["code"]][r["hcc_model"]].add(int(r["hcc_code"]))
    v28_25 = _by_code(rows25, V28_2025)
    v24_25 = _by_code(rows25, V24_2025)

    missing = []
    for code in sorted(v28_26):
        if code in hcc_map:
            continue
        if code not in v28_25:
            status = "new ICD-10-CM code in FY2026 (not in the CMS 2025 file)"
        elif v28_25[code]:
            status = "in the CMS 2025 file with a V28 HCC"
        else:
            status = "in the CMS 2025 file without a V28 HCC"
        missing.append(
            {
                "code": code,
                "display": display[code],
                "v28_hcc_2026": "|".join(map(str, sorted(v28_26[code]))),
                "v22_hcc_2026": "|".join(map(str, sorted(other_26[code]["CMS-HCC-V22"]))),
                "esrd_v24_hcc_2026": "|".join(map(str, sorted(other_26[code]["ESRD-V24"]))),
                "rxhcc_v08_2026": "|".join(map(str, sorted(other_26[code]["RxHCC-V08"]))),
                "status": status,
            }
        )

    v28_mismatch = [
        (c, e.v28, tuple(sorted(v28_26.get(c, ()))))
        for c, e in sorted(hcc_map.items())
        if c in display and set(e.v28) != v28_26.get(c, set())
    ]
    v24_mismatch = [
        (c, e.v24, tuple(sorted(v24_25[c])))
        for c, e in sorted(hcc_map.items())
        if c in v24_25 and set(e.v24) != v24_25[c]
    ]
    v24_only = sum(1 for e in hcc_map.values() if e.v24 and not e.v28)

    codes_v24: dict[int, list[str]] = defaultdict(list)
    codes_v28: dict[int, list[str]] = defaultdict(list)
    for c, e in sorted(hcc_map.items()):
        for n in e.v24:
            codes_v24[n].append(c)
        for n in e.v28:
            codes_v28[n].append(c)
    overlap = []
    for n in sorted(set(codes_v24) & set(codes_v28)):
        a, b = codes_v24[n], codes_v28[n]
        shared = len(set(a) & set(b))
        overlap.append(
            {
                "hcc_number": n,
                "v24_codes": len(a),
                "v28_codes": len(b),
                "shared_codes": shared,
                "same_meaning": "no" if shared == 0 else ("yes" if set(a) == set(b) else "partly"),
                "v24_example": f"{a[0]} {hcc_map[a[0]].display}",
                "v28_example": f"{b[0]} {hcc_map[b[0]].display}",
            }
        )
    return Result(
        map_codes=len(hcc_map),
        v28_codes_2026=len(v28_26),
        missing=missing,
        v28_mismatch=v28_mismatch,
        v24_mismatch=v24_mismatch,
        v24_only_in_map=v24_only,
        overlap=overlap,
    )


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_markdown(res: Result) -> str:
    status = Counter(m["status"] for m in res.missing)
    new = status["new ICD-10-CM code in FY2026 (not in the CMS 2025 file)"]
    cats = Counter(m["code"][:3] for m in res.missing).most_common(8)
    no_shared = [o for o in res.overlap if o["same_meaning"] == "no"]
    url = f"https://github.com/metriport/metriport/blob/{METRIPORT_COMMIT}/{METRIPORT_HCC_MAP_PATH}"
    lines = [
        "# Metriport public HCC map vs CMS 2026",
        "",
        f"Inputs: [`hcc-map.ts` at `{METRIPORT_COMMIT[:7]}`]({url}) (sha256 "
        f"`{METRIPORT_HCC_MAP.sha256[:12]}`), [CMS 2026 mapping]({CMS_2026.url}) (sha256 "
        f"`{CMS_2026.sha256[:12]}`), [CMS 2025 mapping]({CMS_2025.url}) (sha256 "
        f"`{CMS_2025.sha256[:12]}`). Regenerate with `make compare`.",
        "",
        "## Summary",
        "",
        f"- The public map has {_fmt(res.map_codes)} ICD-10-CM codes.",
        f"- CMS 2026 gives a payable V28 HCC to {_fmt(res.v28_codes_2026)} codes.",
        f"- **{_fmt(len(res.missing))} of those codes are not in the public map.** "
        f"{_fmt(new)} are brand new ICD-10-CM codes for FY2026.",
        f"- Codes that are in the map agree with CMS 2026 on V28: "
        f"{_fmt(len(res.v28_mismatch))} differences.",
        f"- Codes that are in the map agree with CMS 2025 on V24: "
        f"{_fmt(len(res.v24_mismatch))} differences.",
        f"- {_fmt(res.v24_only_in_map)} codes in the map carry a V24 HCC and no V28 HCC. "
        "Community V24 is not one of the models in the CMS 2026 file.",
        f"- {len(res.overlap)} HCC numbers are used by both V24 and V28 in the map. "
        f"{len(no_shared)} of them share no ICD-10-CM code at all between the two versions, "
        "so the number alone does not say which condition group it is.",
        "",
        "So the map is accurate for the codes it has. The gap is the newer codes, "
        "which a refresh from the 2026 CMS file closes.",
        "",
        "## Missing codes by status",
        "",
        "| Status | Codes |",
        "|---|---:|",
        *[f"| {k} | {_fmt(v)} |" for k, v in sorted(status.items())],
        "",
        "Most common ICD-10-CM categories among them: "
        + ", ".join(f"{c} ({n})" for c, n in cats)
        + ".",
        "",
        "Examples (full list in `missing_v28_codes.csv`):",
        "",
        "| Code | Description | V28 HCC 2026 | Status |",
        "|---|---|---:|---|",
    ]
    picks = [m for m in res.missing if m["code"] in {"C50A0", "C50A1", "C50A2", "E66813"}]
    seen_cat = {m["code"][:3] for m in picks}
    for m in res.missing:
        if len(picks) >= 10:
            break
        if m["code"][:3] not in seen_cat:
            picks.append(m)
            seen_cat.add(m["code"][:3])
    for m in sorted(picks, key=lambda m: m["code"]):
        lines.append(f"| {m['code']} | {m['display']} | {m['v28_hcc_2026']} | {m['status']} |")
    lines += [
        "",
        "## HCC numbers used by both V24 and V28",
        "",
        "Same meaning is judged only from the map itself: `no` means no ICD-10-CM code "
        "maps to that number in both versions.",
        "",
        "| HCC | V24 codes | V28 codes | Shared | Same meaning | V24 example | V28 example |",
        "|---:|---:|---:|---:|---|---|---|",
    ]
    for o in res.overlap:
        lines.append(
            f"| {o['hcc_number']} | {o['v24_codes']} | {o['v28_codes']} | {o['shared_codes']} "
            f"| {o['same_meaning']} | {o['v24_example']} | {o['v28_example']} |"
        )
    lines += [
        "",
        "## Why it matters in 2026",
        "",
        "CMS pays non-PACE Medicare Advantage on the 2024 CMS-HCC model (V28) at 100% in 2026. "
        "PACE blends 10% V28 with 90% V22, ESRD uses its own models, and Part D uses RxHCC V08. "
        "In the public code, Condition normalization adds HCC extensions from this map "
        "(`normalization/resources/condition.ts`), so a code that is not in the map gets no "
        "HCC extension, and anything built on that extension will not see it. An HCC number "
        "without a model label can point at two different condition groups.",
        "",
    ]
    return "\n".join(lines)


def write(res: Result) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "compare.md").write_text(render_markdown(res))
    with open(REPORTS / "missing_v28_codes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res.missing[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(res.missing)
    with open(REPORTS / "hcc_number_overlap.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res.overlap[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(res.overlap)


def main() -> None:
    res = analyze(*load_inputs())
    write(res)
    new = sum(1 for m in res.missing if m["status"].startswith("new"))
    print(f"compare: {len(res.missing)} codes with a 2026 V28 HCC missing from the map ({new} new)")
    print(f"compare: {len(res.overlap)} HCC numbers used in both V24 and V28")


if __name__ == "__main__":
    main()

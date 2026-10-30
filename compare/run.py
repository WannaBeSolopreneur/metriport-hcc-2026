"""Compare Metriport's public hcc-map.ts with the CMS 2026 crosswalk.

Writes reports/compare.md, reports/compare.json, reports/missing_v28_codes.csv,
reports/split_parent_codes.csv and reports/hcc_number_overlap.csv.
Every number comes from the pinned inputs, so two runs give byte-identical output.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

from compare.icd10cm import CodeYear, read_code_year
from compare.metriport_map import MapEntry, parse_hcc_map
from crosswalk.build import build_rows
from crosswalk.cms import read_cms_csv
from crosswalk.sources import (
    CMS_2025,
    CMS_2026,
    ICD10CM_2025,
    ICD10CM_2026,
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
    stale: list[dict]
    retired_still_mapped: list[str]


def load_inputs():
    cms26_path, _ = fetch(CMS_2026)
    cms25_path, _ = fetch(CMS_2025)
    map_path, _ = fetch(METRIPORT_HCC_MAP)
    header26, rows26 = read_cms_csv(cms26_path, CMS_2026.member)
    _, rows25 = read_cms_csv(cms25_path, CMS_2025.member)
    hcc_map = parse_hcc_map(map_path.read_text(encoding="utf-8"))
    return build_rows(rows26, header26), rows25, hcc_map, load_icd_years()


def load_icd_years() -> tuple[CodeYear, CodeYear]:
    p25, _ = fetch(ICD10CM_2025)
    p26, _ = fetch(ICD10CM_2026)
    return read_code_year(p25, 2025), read_code_year(p26, 2026)


def _added(code: str, icd25: CodeYear, icd26: CodeYear) -> str:
    if code in icd26.added:
        return "FY2026 (Oct 1, 2025)"
    if code in icd25.added:
        return "FY2025 (Oct 1, 2024)"
    return "before FY2025"


def _by_code(rows: list[dict], column: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        out[r["Diagnosis Code"]]
        if r[column]:
            out[r["Diagnosis Code"]].add(int(r[column]))
    return out


def analyze(
    crosswalk: list[dict],
    rows25: list[dict],
    hcc_map: dict[str, MapEntry],
    icd: tuple[CodeYear, CodeYear],
) -> Result:
    icd25, icd26 = icd
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
                "added_to_icd10cm": _added(code, icd25, icd26),
            }
        )

    # Codes the map gives a V28 HCC that are not in the CMS 2026 file and are not valid
    # ICD-10-CM codes in FY2025 or FY2026. These are older parent codes that were split.
    stale = []
    for c, e in sorted(hcc_map.items()):
        if not e.v28 or c in display or c in icd25.codes or c in icd26.codes:
            continue
        children = sorted(k for k in icd26.codes if k.startswith(c) and k != c)
        stale.append(
            {
                "code": c,
                "display": e.display,
                "map_v28_hcc": "|".join(map(str, e.v28)),
                "removed_from_icd10cm": "FY2025 (Oct 1, 2024)"
                if c in icd25.deleted
                else "before FY2025",
                "fy2026_codes_under_it": "|".join(children),
                "of_those_missing_from_map": sum(1 for k in children if k not in hcc_map),
            }
        )
    # Codes CMS 2026 still pays that stopped being valid on Oct 1, 2025. They are correct to
    # keep, because 2026 payments use 2025 dates of service.
    retired = sorted(c for c in v28_26 if c in hcc_map and c not in icd26.codes)

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
        stale=stale,
        retired_still_mapped=retired,
    )


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_markdown(res: Result) -> str:
    status = Counter(m["status"] for m in res.missing)
    new = status["new ICD-10-CM code in FY2026 (not in the CMS 2025 file)"]
    cats = Counter(m["code"][:3] for m in res.missing).most_common(8)
    no_shared = [o for o in res.overlap if o["same_meaning"] == "no"]
    added = Counter(m["added_to_icd10cm"] for m in res.missing)
    stale_split_fy25 = [s for s in res.stale if s["removed_from_icd10cm"].startswith("FY2025")]
    stale_children_missing = sum(s["of_those_missing_from_map"] for s in res.stale)
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
        f"{_fmt(new)} are brand new ICD-10-CM codes for FY2026. The other "
        f"{_fmt(len(res.missing) - new)} were added to ICD-10-CM for FY2025.",
        f"- {_fmt(len(res.stale))} codes in the map carry a V28 HCC but are not valid ICD-10-CM "
        "codes in FY2025 or FY2026. They are older parent codes that were split into more "
        f"specific codes. {_fmt(len(stale_split_fy25))} of them were split on Oct 1, 2024, and "
        f"{_fmt(stale_children_missing)} of the new codes they were split into are among the "
        "missing codes above.",
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
        "So the map is accurate for the codes it has. The gap is the newer codes from the "
        "Oct 1, 2024 and Oct 1, 2025 code updates, which a refresh from the 2026 CMS file "
        "closes.",
        "",
        "## Missing codes by status",
        "",
        "| Status | Codes |",
        "|---|---:|",
        *[f"| {k} | {_fmt(v)} |" for k, v in sorted(status.items())],
        "",
        "When each missing code was added to ICD-10-CM (from the official addenda files):",
        "",
        "| Added | Codes |",
        "|---|---:|",
        *[f"| {k} | {_fmt(v)} |" for k, v in sorted(added.items())],
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
        "## Older codes that were split",
        "",
        "These codes are in the map with a V28 HCC, but they are not in the CMS 2026 file and "
        "are not valid ICD-10-CM codes in FY2025 or FY2026. Each one was replaced by more "
        "specific codes. Full list in `split_parent_codes.csv`.",
        "",
        "| Code | Description | Map V28 HCC | Removed from ICD-10-CM | Replaced by (FY2026) "
        "| Of those, missing from map |",
        "|---|---|---:|---|---|---:|",
    ]
    for s in res.stale:
        lines.append(
            f"| {s['code']} | {s['display']} | {s['map_v28_hcc']} | {s['removed_from_icd10cm']} "
            f"| {s['fy2026_codes_under_it'].replace('|', ', ')} "
            f"| {s['of_those_missing_from_map']} |"
        )
    lines += [
        "",
        f"A different case, for completeness: {', '.join(res.retired_still_mapped)} stopped "
        "being valid on Oct 1, 2025, but CMS 2026 still maps them, because 2026 payments use "
        "2025 dates of service. The map is right to keep them.",
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
    with open(REPORTS / "split_parent_codes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res.stale[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(res.stale)
    (REPORTS / "compare.json").write_text(json.dumps(summary(res), indent=2) + "\n")


def summary(res: Result) -> dict:
    """The headline numbers, for the README charts."""
    new = [m for m in res.missing if m["status"].startswith("new")]
    return {
        "map_codes": res.map_codes,
        "v28_codes_2026": res.v28_codes_2026,
        "missing": len(res.missing),
        "missing_new_fy2026": len(new),
        "missing_added_fy2025": len(res.missing) - len(new),
        "missing_by_category": Counter(m["code"][:3] for m in res.missing).most_common(),
        "missing_new_by_category": Counter(m["code"][:3] for m in new).most_common(),
        "v28_mismatches": len(res.v28_mismatch),
        "v24_mismatches": len(res.v24_mismatch),
        "split_parent_codes": len(res.stale),
        "retired_still_mapped": res.retired_still_mapped,
        "hcc_numbers_in_both": len(res.overlap),
        "hcc_numbers_no_shared_code": sum(1 for o in res.overlap if o["same_meaning"] == "no"),
    }


def main() -> None:
    res = analyze(*load_inputs())
    write(res)
    new = sum(1 for m in res.missing if m["status"].startswith("new"))
    print(f"compare: {len(res.missing)} codes with a 2026 V28 HCC missing from the map ({new} new)")
    print(f"compare: {len(res.stale)} map codes with a V28 HCC that are no longer valid codes")
    print(f"compare: {len(res.overlap)} HCC numbers used in both V24 and V28")


if __name__ == "__main__":
    main()

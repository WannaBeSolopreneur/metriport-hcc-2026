"""The comparison is pinned and reproducible."""

from compare.metriport_map import parse_hcc_map
from compare.run import analyze, render_markdown
from crosswalk.sources import REPORTS


def test_parser_reads_every_entry(hcc_map):
    assert len(hcc_map) == 11184
    assert hcc_map["E119"].v24 == (19,)
    assert hcc_map["E119"].v28 == (38,)
    assert hcc_map["Z992"].v28 == ()


def test_parser_handles_wrapped_entries():
    src = (
        "export const hccMap = {\n"
        '  A01: ["x", [1], []],\n'
        "  B02: [\n"
        '    "y \\"z\\"",\n'
        "    [2],\n"
        "    [3, 4],\n"
        "  ],\n"
        "};\n"
    )
    m = parse_hcc_map(src)
    assert m["B02"].display == 'y "z"'
    assert m["B02"].v28 == (3, 4)


def test_counts(crosswalk, cms25_rows, hcc_map, icd_years):
    res = analyze(crosswalk, cms25_rows, hcc_map, icd_years)
    assert len(res.missing) == 231
    assert sum(m["status"].startswith("new") for m in res.missing) == 134
    assert {"C50A0", "C50A1", "C50A2", "E66813"} <= {m["code"] for m in res.missing}
    assert res.v28_mismatch == []
    assert res.v24_mismatch == []
    assert len(res.overlap) == 26
    assert [o["hcc_number"] for o in res.overlap if o["same_meaning"] != "no"] == [1, 2, 6]
    nineteen = next(o for o in res.overlap if o["hcc_number"] == 19)
    assert nineteen["shared_codes"] == 0


def test_added_years(crosswalk, cms25_rows, hcc_map, icd_years):
    res = analyze(crosswalk, cms25_rows, hcc_map, icd_years)
    added = {m["code"]: m["added_to_icd10cm"] for m in res.missing}
    assert added["C50A0"].startswith("FY2026")
    assert added["E66813"].startswith("FY2025")
    assert added["C810A"].startswith("FY2025")
    # Every "new" code is an FY2026 addition, every other missing code an FY2025 one.
    for m in res.missing:
        assert m["status"].startswith("new") == m["added_to_icd10cm"].startswith("FY2026")


def test_parser_fails_on_empty_map():
    import pytest

    with pytest.raises(ValueError, match="0 entries"):
        parse_hcc_map("export const hccMap = {\n};\n")


def test_stale_codes(crosswalk, cms25_rows, hcc_map, icd_years):
    res = analyze(crosswalk, cms25_rows, hcc_map, icd_years)
    stale = {s["code"]: s for s in res.stale}
    assert len(stale) == 22
    expected = {f"C86{i}" for i in range(7)} | {"C880", "C882", "C883", "C884", "C888", "C889"}
    assert expected | {"G20", "I248"} <= set(stale)
    icd25, icd26 = icd_years
    for code in stale:
        assert code not in icd25.codes and code not in icd26.codes
        assert hcc_map[code].v28
    assert stale["C860"]["fy2026_codes_under_it"] == "C8600|C8601"
    assert stale["G20"]["removed_from_icd10cm"] == "before FY2025"
    assert res.retired_still_mapped == ["D71", "E7253", "G35"]
    # The 18 parents split on Oct 1, 2024 have 49 replacement codes, all missing from the map.
    split25 = [s for s in res.stale if s["removed_from_icd10cm"].startswith("FY2025")]
    assert len(split25) == 18
    children = [c for s in split25 for c in s["fy2026_codes_under_it"].split("|")]
    assert len(children) == 49
    missing = {m["code"] for m in res.missing}
    assert set(children) <= missing
    assert all(c in icd25.added for c in children)


def test_report_is_reproducible(crosswalk, cms25_rows, hcc_map, icd_years):
    first = render_markdown(analyze(crosswalk, cms25_rows, hcc_map, icd_years))
    second = render_markdown(analyze(crosswalk, cms25_rows, hcc_map, icd_years))
    assert first == second
    assert (REPORTS / "compare.md").read_text() == first

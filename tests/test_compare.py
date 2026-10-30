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


def test_counts(crosswalk, cms25_rows, hcc_map):
    res = analyze(crosswalk, cms25_rows, hcc_map)
    assert len(res.missing) == 231
    assert sum(m["status"].startswith("new") for m in res.missing) == 134
    assert {"C50A0", "C50A1", "C50A2", "E66813"} <= {m["code"] for m in res.missing}
    assert res.v28_mismatch == []
    assert res.v24_mismatch == []
    assert len(res.overlap) == 26
    assert [o["hcc_number"] for o in res.overlap if o["same_meaning"] != "no"] == [1, 2, 6]
    nineteen = next(o for o in res.overlap if o["hcc_number"] == 19)
    assert nineteen["shared_codes"] == 0


def test_report_is_reproducible(crosswalk, cms25_rows, hcc_map):
    first = render_markdown(analyze(crosswalk, cms25_rows, hcc_map))
    second = render_markdown(analyze(crosswalk, cms25_rows, hcc_map))
    assert first == second
    assert (REPORTS / "compare.md").read_text() == first

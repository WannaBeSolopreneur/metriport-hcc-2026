"""The crosswalk must say exactly what the CMS 2026 file says."""

import csv
import io
import zipfile
from collections import defaultdict

import pyarrow.parquet as pq

from crosswalk.build import COLUMNS, MODELS
from crosswalk.sources import CMS_2026, DATA, fetch, sha256_of


def _raw_cms() -> tuple[dict[tuple[str, str], set[str]], set[tuple[str, str]]]:
    """Independent re-read of the CMS CSV with fixed column positions.

    Returns the paying HCCs per (code, model), and the (code, model) keys CMS marks "No".
    """
    path, _ = fetch(CMS_2026)
    text = zipfile.ZipFile(path).read(CMS_2026.member).decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    # Columns in the CMS 2026 file: 0 code, 1 description, 2 ESRD V21, 3 ESRD V24, 4 V22,
    # 5 V28, 6 RxHCC V08, 7 to 11 the matching "for 2026 Payment Year" flags.
    positions = {"ESRD-V21": 2, "ESRD-V24": 3, "CMS-HCC-V22": 4, "CMS-HCC-V28": 5, "RxHCC-V08": 6}
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    no: set[tuple[str, str]] = set()
    for r in rows[4:]:
        if len(r) < 12 or not r[1] or not r[0][:1].isalpha():
            continue
        for model, i in positions.items():
            if r[i]:
                assert r[i + 5] == "Yes"
                out[(r[0], model)].add(r[i])
            elif r[i + 5] == "No":
                no.add((r[0], model))
    return out, no


def test_source_is_pinned():
    path, _ = fetch(CMS_2026)
    assert sha256_of(path) == CMS_2026.sha256


def test_every_cms_hcc_is_in_crosswalk_and_nothing_else(crosswalk):
    ours: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in crosswalk:
        if r["payment_flag"]:
            ours[(r["code"], r["hcc_model"])].add(r["hcc_code"])
    assert ours == _raw_cms()[0]


def test_non_paying_rows_match_cms(crosswalk):
    # Every (code, model) that CMS marks "No" has one empty row with payment_flag false.
    ours = {(r["code"], r["hcc_model"]) for r in crosswalk if not r["payment_flag"]}
    assert ours == _raw_cms()[1]
    for r in crosswalk:
        if not r["payment_flag"]:
            assert r["hcc_code"] is None


def test_shape(crosswalk, cms26):
    _, cms_rows = cms26
    assert len(cms_rows) == 11865
    assert len(crosswalk) == 58084
    assert len({r["code"] for r in crosswalk}) == 11346
    assert {r["hcc_model"] for r in crosswalk} == set(MODELS.values())
    assert all(r["payment_year"] == 2026 for r in crosswalk)
    keys = [(r["code"], r["hcc_model"], r["hcc_code"]) for r in crosswalk]
    assert len(keys) == len(set(keys))
    # A row without an HCC never pays, a row with one always does.
    assert all(bool(r["hcc_code"]) == r["payment_flag"] for r in crosswalk)


def _lookup(crosswalk, code):
    return {(r["hcc_model"], r["hcc_code"]) for r in crosswalk if r["code"] == code}


def test_known_codes(crosswalk):
    # Type 2 diabetes without complications: V28 38, V22 and ESRD 19, RxHCC 31.
    assert _lookup(crosswalk, "E119") == {
        ("CMS-HCC-V28", "38"),
        ("CMS-HCC-V22", "19"),
        ("ESRD-V24", "19"),
        ("ESRD-V21", "19"),
        ("RxHCC-V08", "31"),
    }
    # Peripheral vascular disease, unspecified: no V28 HCC in 2026, still counts in V22.
    i739 = _lookup(crosswalk, "I739")
    assert ("CMS-HCC-V28", None) in i739
    assert ("CMS-HCC-V22", "108") in i739
    # New FY2026 inflammatory breast cancer codes map to V28 HCC 23.
    for code in ("C50A0", "C50A1", "C50A2"):
        assert ("CMS-HCC-V28", "23") in _lookup(crosswalk, code)


def test_code_with_two_hccs_in_one_model(crosswalk):
    # CMS lists B377 (candidal sepsis) on two lines: V28 HCC 2 and HCC 6.
    v28 = {h for m, h in _lookup(crosswalk, "B377") if m == "CMS-HCC-V28"}
    assert v28 == {"2", "6"}


def test_written_files_match_rows(crosswalk):
    table = pq.read_table(DATA / "hcc_crosswalk_2026.parquet")
    assert table.column_names == COLUMNS
    assert table.to_pylist() == crosswalk
    with open(DATA / "hcc_crosswalk_2026.csv", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == len(crosswalk)
    assert csv_rows[0].keys() == set(COLUMNS)

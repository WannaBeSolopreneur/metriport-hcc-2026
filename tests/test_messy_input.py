"""Messy FHIR input: nothing crashes, nothing is lost without a count, both loaders agree."""

import logging
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crosswalk.sources import DATA
from fhir_loader import naive, single_pass
from fhir_loader.flatten import condition, normalize_icd10
from fhir_loader.ndjson import LoadStats

FIXTURES = Path(__file__).parent / "fixtures"
MESSY = FIXTURES / "messy_wrapped.ndjson"
PLAIN = FIXTURES / "plain_unwrapped.ndjson"
NO_ROWS = FIXTURES / "no_rows.ndjson"
CROSSWALK = DATA / "hcc_crosswalk_2026.parquet"
ICD = "http://hl7.org/fhir/sid/icd-10-cm"


def _load(path, tmp_path):
    stats = LoadStats()
    paths = single_pass.load([path], tmp_path, stats)
    rows = {t: pq.read_table(p).to_pylist() for t, p in paths.items()}
    return stats, paths, rows


def _codes(rows, cid):
    return [r["icd10_code_normalized"] for r in rows["Condition"] if r["id"] == cid]


@pytest.mark.parametrize(
    ("raw", "norm"),
    [("E11.9", "E119"), (" e11.9 ", "E119"), ("C50. A0", "C50A0"), ("i10", "I10"), (" ", None)],
)
def test_normalize(raw, norm):
    assert normalize_icd10(raw) == norm


def test_one_row_per_icd10_coding():
    r = {
        "resourceType": "Condition",
        "id": "c1",
        "code": {"coding": [{"system": ICD, "code": "I10"}, {"system": ICD, "code": "E11.9"}]},
    }
    rows = condition(r)
    assert [(x["coding_index"], x["icd10_code_normalized"]) for x in rows] == [
        ("0", "I10"),
        ("1", "E119"),
    ]


def test_messy_file_counts(tmp_path):
    stats, _, rows = _load(MESSY, tmp_path)
    assert stats.bom_lines == 1
    assert stats.blank_lines == 1
    assert stats.non_object_lines == 2
    assert stats.bad_json_lines == 1
    assert stats.entries_without_resource == 1
    assert stats.resources_without_type == 1
    assert stats.skipped_lines == 6
    assert stats.unwrapped_lines == 0
    assert stats.conditions == 12
    # snomed_only, empty_code, no_code, null_coding
    assert stats.conditions_without_icd10 == 4
    assert stats.duplicate_icd10_codings == 1
    assert stats.rows == {"Patient": 1, "Condition": 13, "Encounter": 1}
    assert len(rows["Condition"]) == 13


def test_messy_file_codes(tmp_path):
    _, _, rows = _load(MESSY, tmp_path)
    assert _codes(rows, "multi") == ["I10", "E119"]
    assert _codes(rows, "snomed_first") == ["E119"]
    assert _codes(rows, "oid") == ["E119"]
    assert _codes(rows, "who") == ["E119"]
    assert _codes(rows, "lower_space") == ["E119"]
    assert _codes(rows, "inner_space") == ["C50A0"]
    assert _codes(rows, "dup") == ["E119"]
    for cid in ("snomed_only", "empty_code", "no_code", "null_coding"):
        assert _codes(rows, cid) == [None]
    no_subject = next(r for r in rows["Condition"] if r["id"] == "no_subject")
    assert no_subject["patient_id"] is None
    assert no_subject["icd10_code_normalized"] == "E119"
    # The raw code is kept as sent, next to the normalized one.
    lower = next(r for r in rows["Condition"] if r["id"] == "lower_space")
    assert lower["icd10_code"] == " e11.9 "


def test_messy_file_join(tmp_path):
    _, paths, _ = _load(MESSY, tmp_path)
    out = single_pass.join_crosswalk(paths["Condition"], CROSSWALK, tmp_path)
    v28 = {
        (r["condition_id"], r["hcc_code"])
        for r in pq.read_table(out).to_pylist()
        if r["hcc_model"] == "CMS-HCC-V28"
    }
    # E11.9 maps to V28 HCC 38 whichever way it was written. C50A0 maps to 23.
    for cid in ("multi", "snomed_first", "oid", "who", "lower_space", "dup", "no_subject"):
        assert (cid, "38") in v28
    assert ("inner_space", "23") in v28
    # I10 on the "multi" Condition has no V28 HCC, so only E11.9 adds one.
    assert [h for c, h in v28 if c == "multi"] == ["38"]


def test_plain_unwrapped_ndjson(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="fhir_loader"):
        stats, _, rows = _load(PLAIN, tmp_path)
    assert stats.unwrapped_lines == 3
    assert stats.bom_lines == 1
    assert stats.rows == {"Patient": 1, "Condition": 3}
    assert _codes(rows, "plain1") == ["I10", "E119"]
    assert _codes(rows, "plain2") == [None]
    assert "not wrapped" in caplog.text
    assert "no usable ICD-10 code" in caplog.text


def test_warns_when_no_rows(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="fhir_loader"):
        stats, _, rows = _load(NO_ROWS, tmp_path)
    assert all(not r for r in rows.values())
    assert stats.non_object_lines == 1
    assert "no rows were produced" in caplog.text
    assert "not an object" in caplog.text


def test_clean_input_logs_nothing(tmp_path, caplog):
    p = tmp_path / "clean.ndjson"
    p.write_text('{"resource": {"resourceType": "Patient", "id": "p"}}\n')
    with caplog.at_level(logging.WARNING, logger="fhir_loader"):
        _load(p, tmp_path / "out")
    assert caplog.text == ""


@pytest.mark.parametrize("path", [MESSY, PLAIN, NO_ROWS])
def test_baseline_agrees_on_messy_input(path, tmp_path):
    expected = naive.run([path], tmp_path / "naive")
    _, _, rows = _load(path, tmp_path / "single")
    for t, got in rows.items():
        assert sorted(map(repr, got)) == sorted(map(repr, expected[t]))

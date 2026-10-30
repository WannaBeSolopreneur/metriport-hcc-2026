"""The single-pass loader must produce exactly what the re-read baseline produces."""

import csv
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crosswalk.sources import DATA
from fhir_loader import naive, single_pass, synth
from fhir_loader.flatten import COLUMNS
from fhir_loader.ndjson import LoadStats
from fhir_loader.resource_types import RESOURCE_TYPES, TABLES

CROSSWALK = DATA / "hcc_crosswalk_2026.parquet"


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    codes = synth.crosswalk_codes(CROSSWALK)
    return synth.generate(tmp_path_factory.mktemp("syn"), 120, codes, seed=7)


def _key(rows):
    return sorted(tuple((k, v) for k, v in r.items()) for r in rows)


def test_synthetic_data_covers_all_types(files):
    stats = LoadStats()
    seen = set()
    from fhir_loader.ndjson import iter_resources

    for f in files:
        seen |= {r["resourceType"] for r in iter_resources(f, stats)}
    assert len(RESOURCE_TYPES) == 28
    assert seen <= set(RESOURCE_TYPES)
    assert set(TABLES) <= seen


def test_synthetic_data_is_messy(files, tmp_path):
    stats = LoadStats()
    single_pass.load(files, tmp_path, stats)
    assert stats.unwrapped_lines > 0
    assert stats.bom_lines > 0
    assert stats.non_object_lines > 0
    assert stats.conditions_without_icd10 > 0
    assert stats.rows["Condition"] > stats.conditions  # some Conditions have two codings
    rows = pq.read_table(tmp_path / "condition.parquet").to_pylist()
    systems = {r["icd10_system"] for r in rows}
    assert {"http://hl7.org/fhir/sid/icd-10-cm", "urn:oid:2.16.840.1.113883.6.90"} <= systems
    # WHO ICD-10 codings are in the data, but they are skipped for the HCC join.
    assert "http://hl7.org/fhir/sid/icd-10" not in systems
    assert stats.who_icd10_codings_skipped > 0
    raw = [r["icd10_code"] for r in rows if r["icd10_code"]]
    assert any("." in c for c in raw)
    assert any(c != c.strip() or c != c.upper() for c in raw)


def test_single_pass_equals_baseline(files, tmp_path):
    base_stats, single_stats = LoadStats(), LoadStats()
    expected = naive.run(files, tmp_path / "naive", stats=base_stats)
    paths = single_pass.load(files, tmp_path / "single", single_stats)
    for t in TABLES:
        got = pq.read_table(paths[t])
        assert got.column_names == COLUMNS[t]
        assert _key(got.to_pylist()) == _key(expected[t])
        assert len(expected[t]) > 0
    assert base_stats.rows == single_stats.rows
    assert base_stats.conditions_without_icd10 == single_stats.conditions_without_icd10
    # The baseline also wrote per-patient CSVs with the same row counts.
    n = 0
    for p in (tmp_path / "naive").glob("*/condition.csv"):
        with open(p, newline="") as f:
            n += sum(1 for _ in csv.reader(f, escapechar="\\")) - 1
    assert n == len(expected["Condition"])
    # Temp files are cleaned up, like the original.
    assert not list((tmp_path / "naive").glob("*/temp_*.ndjson"))


def test_small_batches_give_the_same_rows(files, tmp_path):
    a = single_pass.load(files, tmp_path / "a")
    b = single_pass.load(files, tmp_path / "b", batch_rows=7)
    for t in TABLES:
        assert pq.read_table(a[t]).to_pylist() == pq.read_table(b[t]).to_pylist()
    assert pq.ParquetFile(b["Condition"]).metadata.num_row_groups > 1


def test_crosswalk_join(files, tmp_path):
    paths = single_pass.load(files, tmp_path)
    out = single_pass.join_crosswalk(paths["Condition"], CROSSWALK, tmp_path)
    joined = pq.read_table(out).to_pylist()
    rows = pq.read_table(paths["Condition"]).to_pylist()
    by_key = {(r["id"], r["coding_index"]): r for r in rows}
    assert joined
    for r in joined:
        c = by_key[(r["condition_id"], r["coding_index"])]
        assert c["icd10_code"].replace(".", "").replace(" ", "").upper() == r["code"]
        assert r["payment_year"] == 2026
    # I10 (hypertension) has an RxHCC but no V28 HCC. J06.9 is not in the CMS file at all.
    assert {r["hcc_model"] for r in joined if r["code"] == "I10"} <= {"RxHCC-V08"}
    assert not any(r["code"] == "J069" for r in joined)
    # Conditions with two codings get HCCs from both.
    assert len({r["coding_index"] for r in joined}) > 1


def test_generator_is_deterministic(tmp_path):
    codes = [("E119", "Type 2 diabetes mellitus without complications")]
    a = synth.generate(tmp_path / "a", 60, codes, seed=1)
    b = synth.generate(tmp_path / "b", 60, codes, seed=1)
    assert [Path(p).read_bytes() for p in a] == [Path(p).read_bytes() for p in b]


def test_condition_rows_are_valid_json_compatible(files):
    # Every synthetic line is either a JSON object or one of the planted messy lines.
    for f in files[:10]:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.lstrip("\ufeff")
            if line.strip() and line != "[]":
                assert isinstance(json.loads(line), dict)

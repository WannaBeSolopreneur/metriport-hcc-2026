"""The single-pass loader must produce exactly what the re-read baseline produces."""

import csv
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crosswalk.sources import DATA
from fhir_loader import naive, single_pass, synth
from fhir_loader.flatten import COLUMNS
from fhir_loader.resource_types import RESOURCE_TYPES, TABLES


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    codes = synth.crosswalk_codes(DATA / "hcc_crosswalk_2026.parquet")
    return synth.generate(tmp_path_factory.mktemp("syn"), 25, codes, seed=7)


def _key(rows):
    return sorted(tuple((k, v) for k, v in r.items()) for r in rows)


def test_synthetic_data_covers_all_types(files):
    import json

    seen = set()
    for f in files:
        with open(f) as fh:
            seen |= {json.loads(line)["resource"]["resourceType"] for line in fh}
    assert len(RESOURCE_TYPES) == 28
    assert seen <= set(RESOURCE_TYPES)
    assert set(TABLES) <= seen


def test_single_pass_equals_baseline(files, tmp_path):
    expected = naive.run(files, tmp_path / "naive")
    paths = single_pass.load(files, tmp_path / "single")
    for t in TABLES:
        got = pq.read_table(paths[t])
        assert got.column_names == COLUMNS[t]
        assert _key(got.to_pylist()) == _key(expected[t])
        assert len(expected[t]) > 0
    # The baseline also wrote per-patient CSVs with the same row counts.
    n = 0
    for p in (tmp_path / "naive").glob("*/condition.csv"):
        with open(p, newline="") as f:
            n += sum(1 for _ in csv.reader(f, escapechar="\\")) - 1
    assert n == len(expected["Condition"])
    # Temp files are cleaned up, like the original.
    assert not list((tmp_path / "naive").glob("*/temp_*.ndjson"))


def test_crosswalk_join(files, tmp_path):
    paths = single_pass.load(files, tmp_path)
    out = single_pass.join_crosswalk(
        paths["Condition"], DATA / "hcc_crosswalk_2026.parquet", tmp_path
    )
    joined = pq.read_table(out).to_pylist()
    conditions = {r["id"]: r for r in pq.read_table(paths["Condition"]).to_pylist()}
    assert joined
    for r in joined:
        c = conditions[r["condition_id"]]
        assert c["icd10_code"].replace(".", "") == r["code"]
        assert r["payment_year"] == 2026
    # I10 (hypertension) has an RxHCC but no V28 HCC. J06.9 is not in the CMS file at all.
    assert {r["hcc_model"] for r in joined if r["code"] == "I10"} <= {"RxHCC-V08"}
    assert not any(r["code"] == "J069" for r in joined)


def test_generator_is_deterministic(tmp_path):
    codes = [("E119", "Type 2 diabetes mellitus without complications")]
    a = synth.generate(tmp_path / "a", 2, codes, seed=1)
    b = synth.generate(tmp_path / "b", 2, codes, seed=1)
    assert [Path(p).read_bytes() for p in a] == [Path(p).read_bytes() for p in b]

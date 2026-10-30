"""Single-pass loader: read each FHIR NDJSON file once, route every resource by type, write
one Parquet file per table, then join Conditions to the CMS 2026 crosswalk with DuckDB."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from fhir_loader.flatten import COLUMNS, FLATTENERS


def load(files: list[Path], out_dir: Path) -> dict[str, Path]:
    cols: dict[str, dict[str, list]] = {t: {c: [] for c in COLUMNS[t]} for t in FLATTENERS}
    for path in files:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                try:
                    resource = json.loads(line).get("resource", {})
                except json.JSONDecodeError:
                    continue
                flatten = FLATTENERS.get(resource.get("resourceType"))
                if flatten is None:
                    continue
                table = cols[resource["resourceType"]]
                for k, v in flatten(resource).items():
                    table[k].append(v)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for t, data in cols.items():
        schema = pa.schema([(c, pa.string()) for c in COLUMNS[t]])
        paths[t] = out_dir / f"{t.lower()}.parquet"
        pq.write_table(pa.table(data, schema=schema), paths[t], compression="zstd")
    return paths


JOIN_SQL = """
COPY (
    SELECT c.id AS condition_id, c.patient_id, c.icd10_code,
           x.code, x.display, x.hcc_model, x.hcc_code, x.payment_year
    FROM read_parquet(?) c
    JOIN read_parquet(?) x
      ON x.code = upper(replace(trim(c.icd10_code), '.', ''))
    WHERE x.payment_flag
    ORDER BY condition_id, hcc_model, hcc_code
) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
"""


def join_crosswalk(condition_parquet: Path, crosswalk_parquet: Path, out_dir: Path) -> Path:
    out = out_dir / "condition_hcc.parquet"
    with duckdb.connect() as con:
        con.execute(
            JOIN_SQL.format(out=str(out).replace("'", "''")),
            [str(condition_parquet), str(crosswalk_parquet)],
        )
    return out

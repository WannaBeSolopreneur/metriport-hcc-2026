"""Single-pass loader: read each FHIR NDJSON file once, route every resource by type, write
one Parquet file per table, then join Conditions to the CMS 2026 crosswalk with DuckDB.

Rows are written in batches (BATCH_ROWS per table), so memory stays flat however many
files go in.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from fhir_loader.flatten import COLUMNS, FLATTENERS
from fhir_loader.ndjson import LoadStats, flatten_resource, iter_resources

BATCH_ROWS = 50_000


class _TableWriter:
    def __init__(self, table: str, path: Path, batch_rows: int):
        self.columns = COLUMNS[table]
        self.schema = pa.schema([(c, pa.string()) for c in self.columns])
        self.writer = pq.ParquetWriter(path, self.schema, compression="zstd")
        self.batch_rows = batch_rows
        self.buf: dict[str, list] = {c: [] for c in self.columns}
        self.n = 0

    def add(self, row: dict) -> None:
        for c in self.columns:
            self.buf[c].append(row[c])
        self.n += 1
        if self.n >= self.batch_rows:
            self.flush()

    def flush(self) -> None:
        if self.n:
            self.writer.write_table(pa.table(self.buf, schema=self.schema))
            self.buf = {c: [] for c in self.columns}
            self.n = 0

    def close(self) -> None:
        self.flush()
        self.writer.close()


def load(
    files: list[Path],
    out_dir: Path,
    stats: LoadStats | None = None,
    batch_rows: int = BATCH_ROWS,
) -> dict[str, Path]:
    """Write patient.parquet, condition.parquet and encounter.parquet into out_dir.

    Pass a LoadStats to get the counts back. Problems are logged as warnings either way.
    """
    stats = stats if stats is not None else LoadStats()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {t: out_dir / f"{t.lower()}.parquet" for t in FLATTENERS}
    writers = {t: _TableWriter(t, p, batch_rows) for t, p in paths.items()}
    try:
        for path in files:
            for resource in iter_resources(path, stats):
                rows = flatten_resource(resource, stats)
                if rows:
                    w = writers[resource["resourceType"]]
                    for row in rows:
                        w.add(row)
    finally:
        for w in writers.values():
            w.close()
    stats.log_summary()
    return paths


JOIN_SQL = """
COPY (
    SELECT c.id AS condition_id, c.patient_id, c.coding_index, c.icd10_code,
           x.code, x.display, x.hcc_model, x.hcc_code, x.payment_year
    FROM read_parquet(?) c
    JOIN read_parquet(?) x
      ON x.code = c.icd10_code_normalized
    WHERE x.payment_flag
    ORDER BY condition_id, coding_index, hcc_model, hcc_code
) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
"""


def join_crosswalk(condition_parquet: Path, crosswalk_parquet: Path, out_dir: Path) -> Path:
    """One row per Condition coding x payment model x HCC, only where the HCC pays."""
    out = out_dir / "condition_hcc.parquet"
    with duckdb.connect() as con:
        con.execute(
            JOIN_SQL.format(out=str(out).replace("'", "''")),
            [str(condition_parquet), str(crosswalk_parquet)],
        )
    return out

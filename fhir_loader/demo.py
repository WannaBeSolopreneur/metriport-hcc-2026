"""Print the DuckDB query shown in the README, plus a query over the benchmark output."""

from __future__ import annotations

import duckdb

from crosswalk.sources import CACHE, DATA

CROSSWALK_QUERY = f"""
SELECT code, display, hcc_model, hcc_code
FROM '{DATA / "hcc_crosswalk_2026.parquet"}'
WHERE code IN ('E119', 'I739', 'C50A0') AND payment_flag
ORDER BY code, hcc_model
"""

PATIENT_QUERY = f"""
SELECT patient_id, count(DISTINCT hcc_code) AS v28_hccs
FROM '{CACHE / "bench" / "single" / "condition_hcc.parquet"}'
WHERE hcc_model = 'CMS-HCC-V28'
GROUP BY patient_id
ORDER BY v28_hccs DESC, patient_id
LIMIT 5
"""


def main() -> None:
    with duckdb.connect() as con:
        print("Crosswalk: which 2026 models pay for these codes")
        con.sql(CROSSWALK_QUERY).show(max_width=200)
        path = CACHE / "bench" / "single" / "condition_hcc.parquet"
        if path.exists():
            print("Synthetic patients with the most distinct V28 HCCs (benchmark output)")
            con.sql(PATIENT_QUERY).show()


if __name__ == "__main__":
    main()

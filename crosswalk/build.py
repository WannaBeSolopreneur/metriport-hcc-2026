"""Build data/hcc_crosswalk_2026.csv and .parquet from the official CMS 2026 mapping file.

One row per ICD-10-CM code x payment model x HCC. A code that is valid but carries no HCC
in a model gets one row with an empty hcc_code and payment_flag false. A code that maps to
two HCCs in the same model (CMS lists it on two lines) gets two rows.
"""

from __future__ import annotations

import csv
import json

import pyarrow as pa
import pyarrow.parquet as pq

from crosswalk.cms import read_cms_csv
from crosswalk.sources import CMS_2026, DATA, fetch

ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
PAYMENT_YEAR = 2026

# CMS column name -> model label used in this crosswalk.
MODELS: dict[str, str] = {
    "CMS-HCC Model Category V28": "CMS-HCC-V28",
    "CMS-HCC Model Category V22": "CMS-HCC-V22",
    "CMS-HCC ESRD Model Category V24": "ESRD-V24",
    "CMS-HCC ESRD Model Category V21": "ESRD-V21",
    "RxHCC Model Category V08": "RxHCC-V08",
}
COLUMNS = ["code", "display", "system", "hcc_code", "hcc_model", "payment_year", "payment_flag"]

SCHEMA = pa.schema(
    [
        ("code", pa.string()),
        ("display", pa.string()),
        ("system", pa.string()),
        ("hcc_code", pa.string()),
        ("hcc_model", pa.string()),
        ("payment_year", pa.int16()),
        ("payment_flag", pa.bool_()),
    ]
)


def flag_column(model_column: str) -> str:
    return f"{model_column} for {PAYMENT_YEAR} Payment Year"


def build_rows(cms_rows: list[dict[str, str]], header: list[str]) -> list[dict]:
    missing = [c for m in MODELS for c in (m, flag_column(m)) if c not in header]
    if missing:
        raise ValueError(f"CMS file is missing expected columns: {missing}")
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in cms_rows:
        for col, model in MODELS.items():
            hcc, flag = r[col], r[flag_column(col)]
            if hcc:
                if flag != "Yes":
                    raise ValueError(f"{r['Diagnosis Code']} {model}: HCC {hcc} but flag {flag!r}")
                key = (r["Diagnosis Code"], model, hcc)
                paid = True
            elif flag == "No":
                key = (r["Diagnosis Code"], model, None)
                paid = False
            else:  # "--" marks the second line of a code that maps to two HCCs
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "code": key[0],
                    "display": r["Description"],
                    "system": ICD10_SYSTEM,
                    "hcc_code": key[2],
                    "hcc_model": model,
                    "payment_year": PAYMENT_YEAR,
                    "payment_flag": paid,
                }
            )
    out.sort(key=lambda d: (d["code"], d["hcc_model"], int(d["hcc_code"] or -1)))
    return out


def write(rows: list[dict]) -> None:
    DATA.mkdir(exist_ok=True)
    with open(DATA / "hcc_crosswalk_2026.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({**row, "payment_flag": str(row["payment_flag"]).lower()})
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    pq.write_table(table, DATA / "hcc_crosswalk_2026.parquet", compression="zstd")


def main() -> None:
    path, origin = fetch(CMS_2026)
    header, cms_rows = read_cms_csv(path, CMS_2026.member)
    rows = build_rows(cms_rows, header)
    write(rows)
    source = {
        "name": CMS_2026.name,
        "url": CMS_2026.url,
        "sha256": CMS_2026.sha256,
        "member": CMS_2026.member,
        "origin": "local fallback copy" if origin == "fallback" else "cms.gov download",
    }
    (DATA / "hcc_crosswalk_2026.source.json").write_text(json.dumps(source, indent=2) + "\n")
    by_model: dict[str, int] = {}
    for r in rows:
        if r["payment_flag"]:
            by_model[r["hcc_model"]] = by_model.get(r["hcc_model"], 0) + 1
    print(f"crosswalk: {len(cms_rows)} CMS lines, {len({r['code'] for r in rows})} codes")
    print(f"crosswalk: {len(rows)} rows written, paying rows by model {by_model}")
    if origin == "fallback":
        print("crosswalk: NOTE built from the local fallback copy, not a fresh download")


if __name__ == "__main__":
    main()

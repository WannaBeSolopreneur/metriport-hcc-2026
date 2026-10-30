# Details

This page has the full details behind the [README](../README.md).

## Contents

1. [Metriport context](#metriport-context)
2. [Why it matters in 2026](#why-it-matters-in-2026)
3. [Key results](#key-results)
4. [How it works](#how-it-works)
5. [Quick start](#quick-start)
6. [Query it with DuckDB](#query-it-with-duckdb)
7. [How it was verified](#how-it-was-verified)
8. [Limits](#limits)

## Metriport context

- Metriport turns patient data from many sources into one FHIR record. Customers can sync it to a data warehouse.
- Metriport's analytics flag suspected and under-coded conditions to help risk adjustment.
- Its FHIR HCC extension (system `http://terminology.hl7.org/CodeSystem/cmshcc`) labels each HCC coding as `v24` or `v28`.
- The warehouse docs show one `condition.hcc_code` column and a `condition_extension_vcc_coding` table (`code`, `display`, `system`, `code_rank`). Neither has a model or version column.
- `condition.hcc_code` takes the first matching HCC extension. The public code writes the V24 extension before the V28 one. So when a code has both, the column holds the V24 number. That is the clearest reason to store the model next to the HCC.
- In the public code, Condition normalization adds HCC extensions from `hcc-map.ts`. A code that is not in the map gets no HCC extension.
- The fhir-to-csv step (`parseNdjsonBundle.py`) turns FHIR NDJSON files into tables.

Based on Metriport's public repo and docs as of Oct 30, 2026. Their internal version may already be newer.

## Why it matters in 2026

- In 2026, CMS pays non-PACE Medicare Advantage plans on the V28 model at 100%.
- PACE plans use 10% V28 and 90% V22.
- Non-PACE ESRD members use the 2023 ESRD model (V24).
- PACE ESRD members use 10% of the 2023 ESRD model (V24) and 90% of the 2019 ESRD model (V21).
- Part D uses RxHCC V08.

So one ICD-10 code can have a different HCC in each model.
An HCC number on its own does not say which model it belongs to.
This table puts the model name next to every HCC.

The same HCC number can mean very different things in V24 and V28:

| HCC number | In V24 it means | In V28 it means |
|---:|---|---|
| 19 | Mostly diabetes without complications (E08.9, E09.9, E10.9, E11.9, E13.9), plus Z79.4 (long-term insulin use) | A cancer group (for example C45.0, mesothelioma) |

Type 2 diabetes (E11.9) is HCC 19 in V24 and HCC 38 in V28.
In Metriport's map, 26 HCC numbers are used by both versions. 23 of them share no codes at all.

## Key results

### 1. A tested 2026 table

- 58,084 rows covering 11,346 ICD-10-CM codes, built from the official CMS 2026 file.
- One row per code, payment model and HCC.
- Models: `CMS-HCC-V28`, `CMS-HCC-V22`, `ESRD-V24`, `ESRD-V21` and `RxHCC-V08`.
- Columns: `code, display, system, hcc_code, hcc_model, payment_year, payment_flag`.
- It is a lookup table. Join it on `code`, which is the ICD-10-CM code. The HCC is in `hcc_code`. In Metriport's `condition_extension_vcc_coding`, `code` is the HCC number, and there is one row per condition. So map the columns before you load it.
- For codes in the CMS file, a model with no HCC gets a row with an empty `hcc_code` and `payment_flag = false`. So "no HCC" is clear for those codes.
- This covers 11,346 codes. FY2026 has 74,719 ICD-10-CM codes. The rest are not in the CMS file, so they have no row at all (J06.9 is one example). No row also means no HCC.

Files: [`data/hcc_crosswalk_2026.csv`](../data/hcc_crosswalk_2026.csv) and `data/hcc_crosswalk_2026.parquet`.

### 2. Compared with Metriport's public map

Metriport's public map (`hcc-map.ts`) holds up well.
For codes still in the CMS 2026 file, every V28 value matches.
For codes in the CMS 2025 file, every V24 value matches. (The 2026 file has no community V24 column, so V24 is checked against 2025.)
The main gap is newer codes.

![8,019 codes pay under V28 in 2026. 7,788 are in the map. 231 are missing.](img/coverage.png)

- CMS 2026 gives a V28 HCC to **8,019** codes. **231** of them are not in the public map.
- **134** are brand new codes from Oct 1, 2025 (FY2026). One example is C50.A0 to C50.A2, inflammatory breast cancer, V28 HCC 23.
- The other **97** were added on Oct 1, 2024 (FY2025). Examples are E66.813 (obesity class 3, HCC 48) and C81.0A (Hodgkin lymphoma in remission, HCC 21).

![Where the 231 missing codes are, by ICD-10-CM category](img/missing_by_category.png)

Most of them are chronic skin ulcer codes (112), followed by eating disorders and lymphomas.

There is one more small finding.
**22** codes in the map still carry a V28 HCC, but they are not valid codes in FY2025 or FY2026.
They are older parent codes that were split into more specific codes.
Examples are C86.0 to C86.6, C88.0, C88.2, C88.3, C88.4, C88.8, C88.9, G20 (Parkinson's) and I24.8.
18 of them were split on Oct 1, 2024. Those 18 have 49 replacement codes, taken from the official add and delete lists. All 49 are among the 231 missing codes.
The other 4 (G20, G37.8, I24.8 and J15.6) were split earlier, and their replacement codes are already in the map.

Full details: [`reports/compare.md`](../reports/compare.md), [`reports/missing_v28_codes.csv`](../reports/missing_v28_codes.csv) and [`reports/split_parent_codes.csv`](../reports/split_parent_codes.csv).

### 3. A faster FHIR loader

Metriport's public `parseNdjsonBundle.py` scans each patient file once for the patient id. Then it reads and parses the file again for each of the 28 resource types. It writes a temp file per type and a CSV per patient.
This loader reads and parses each file once and writes Parquet.

![Benchmark: median seconds for each approach](img/benchmark.png)

On 3,000 synthetic patients, median of 3 runs (from the committed [`reports/benchmark.json`](../reports/benchmark.json)):

| Approach | Median seconds |
|---|---:|
| Baseline, all 28 types | 49.7 |
| Baseline, same 3 tables only (4 passes per file) | 8.7 |
| Single pass to Parquet | 2.2 |
| Single pass to Parquet, plus the DuckDB HCC join | 2.4 |

- **Fair test: 3.9x faster.** The baseline builds only the same 3 tables.
- **Whole pattern: 22.4x faster.** This compares all 28 passes, the temp files and the CSV writes with one pass to Parquet. It is not file reading alone.
- Both give exactly the same rows. The benchmark compares every row, sorted, and stops with an error if they differ.
- Your numbers will be a little different each run. Run `make bench` to measure on your machine.

These are synthetic files on one machine. Treat them as a direction, not a production estimate.
Details: [`reports/benchmark.md`](../reports/benchmark.md).

## How it works

```mermaid
flowchart LR
    A[CMS 2026 mapping file] --> B[crosswalk/build.py]
    B --> C[(hcc_crosswalk_2026.parquet)]
    D[FHIR NDJSON files] --> E[fhir_loader/single_pass.py]
    E --> F[(patient, condition, encounter Parquet)]
    C --> G[DuckDB join]
    F --> G
    G --> H[(condition_hcc.parquet)]
    I[Metriport hcc-map.ts] --> J[compare/run.py]
    C --> J
    J --> K[reports/compare.md]
```

- **Crosswalk.** `crosswalk/` downloads the CMS 2026 file, checks its sha256, and builds the table.
- **Compare.** `compare/` reads Metriport's public map at a pinned commit and the official ICD-10-CM code lists, then writes the reports.
- **Loader.** `fhir_loader/` reads each NDJSON file once and writes Parquet in batches, so memory stays flat.
  - Conditions get **one row per ICD-10-CM coding**. SNOMED is kept in a column. (Metriport's `config_Condition_code_coding.ini` is different. It gives one row per coding of any system.) So I10 plus E11.9 on one Condition gives two rows, and E11.9 still maps to V28 HCC 38.
  - Metriport's Condition normalization keeps one set of HCC extensions, from the last matching ICD-10 coding. Joining every coding keeps all of a patient's HCCs.
  - It joins only ICD-10-CM, the US version. The accepted system names are `http://hl7.org/fhir/sid/icd-10-cm` and `urn:oid:2.16.840.1.113883.6.90`. WHO ICD-10 (`http://hl7.org/fhir/sid/icd-10`) is counted and skipped, like Metriport's normalizer.
  - It cleans codes before the join. `" e11.9 "` becomes `E119`. A dot is only allowed after the third character, so `E1.19` is rejected, not turned into `E119`. The original code is kept in `icd10_code`.
  - It reads bundle entries (`{"resource": ...}`) and plain resource lines. It removes byte order marks.
  - Nothing is dropped silently. A Condition with no ICD-10-CM code is kept with an empty code. Bad lines, including bad UTF-8, are skipped, counted and logged as warnings.

## Quick start

You need Python 3.11 or newer, `make`, and internet access to cms.gov and GitHub.

```
make all
```

This takes about 4 minutes. It:

1. creates `.venv` and installs the tools,
2. builds the crosswalk,
3. runs the comparison,
4. recounts the headline numbers with a separate script (`scripts/verify_recount.py`),
5. runs the benchmark on 3,000 synthetic patients,
6. draws the charts in `docs/img/`,
7. prints a DuckDB demo,
8. runs ruff and pytest.

Each step also runs on its own: `make crosswalk`, `make compare`, `make verify`, `make bench`, `make charts`, `make test`.

Every download is checked against a pinned sha256.

## Query it with DuckDB

Which 2026 models pay for these codes?

```sql
SELECT code, display, hcc_model, hcc_code
FROM 'data/hcc_crosswalk_2026.parquet'
WHERE code IN ('E119', 'I739', 'C50A0') AND payment_flag
ORDER BY code, hcc_model
```

```
code   display                                                hcc_model    hcc_code
C50A0  Malignant inflammatory neoplasm of unspecified breast  CMS-HCC-V22  12
C50A0  Malignant inflammatory neoplasm of unspecified breast  CMS-HCC-V28  23
C50A0  Malignant inflammatory neoplasm of unspecified breast  ESRD-V21     12
C50A0  Malignant inflammatory neoplasm of unspecified breast  ESRD-V24     12
C50A0  Malignant inflammatory neoplasm of unspecified breast  RxHCC-V08    22
E119   Type 2 diabetes mellitus without complications         CMS-HCC-V22  19
E119   Type 2 diabetes mellitus without complications         CMS-HCC-V28  38
E119   Type 2 diabetes mellitus without complications         ESRD-V21     19
E119   Type 2 diabetes mellitus without complications         ESRD-V24     19
E119   Type 2 diabetes mellitus without complications         RxHCC-V08    31
I739   Peripheral vascular disease, unspecified               CMS-HCC-V22  108
I739   Peripheral vascular disease, unspecified               ESRD-V21     108
I739   Peripheral vascular disease, unspecified               ESRD-V24     108
```

I73.9 has no paying V28 line, so the filtered query shows none. The table still has a V28 row for I73.9, with an empty `hcc_code` and `payment_flag = false`. So it adds nothing to a 2026 non-PACE Medicare Advantage score. It still counts for PACE and ESRD.

Count V28 HCCs per patient, after `make bench`:

```sql
SELECT patient_id, count(DISTINCT hcc_code) AS v28_hccs
FROM '.cache/bench/single/condition_hcc.parquet'
WHERE hcc_model = 'CMS-HCC-V28'
GROUP BY patient_id
ORDER BY v28_hccs DESC
LIMIT 5
```

## How it was verified

Three separate checks run on every `make all`.

1. **An independent recount.** `scripts/verify_recount.py` uses only the Python standard library and none of this repo's code. It reads the raw CMS files and Metriport's map, and recounts the 231 missing codes, the 134 new ones, and the 23 HCC numbers that change meaning. It fails if any number is different.
2. **Every row checked.** The same script and `tests/test_crosswalk.py` match all 58,084 crosswalk rows against the CMS 2026 file, paying and non-paying.
3. **Spot checks.** The script also checks 25 codes one by one: 20 picked at random with a fixed seed, plus C50A0, E66813, C810A, I10 and Z992. It prints the list. A test confirms C50A0 is a new FY2026 code in the official ICD-10-CM addenda.

The tests also check that:

- the single pass loader and the baseline give exactly the same rows, on clean and messy data,
- messy input is handled: two codings on one Condition, the OID system name, WHO `icd-10` codings (skipped), dotted, lowercase and spaced codes, bad dots, byte order marks, bad UTF-8, non-object lines, plain unwrapped NDJSON and missing fields,
- the reports are the same every time they are built.

## Limits

- The loader only builds Patient, Condition and Encounter tables.
- The synthetic data is shaped like Metriport's output, but it is not real data. Real files differ in size and shape.
- The benchmark runs on one machine, in one process.
- The comparison uses Metriport's **public** repo and docs. Their internal version may already be newer.
- This table maps codes to HCCs. It does not compute risk scores. Scores also need demographics, hierarchies and coefficients.


# metriport-hcc-2026

**What this gives a Metriport customer in 2026:** every ICD-10-CM code labeled with the HCC it maps to in each CMS payment model that applies this year (V28 for Medicare Advantage, V22 for PACE, the ESRD models, and RxHCC for Part D), straight from the official CMS 2026 file and tested against it. That includes 231 codes with a 2026 V28 HCC that are not in the public map today, such as the new inflammatory breast cancer codes C50.A0 to C50.A2.

Based on Metriport's public repo and docs as of Oct 30, 2026. If this is already fixed internally, this is a tested CMS 2026 table to check against.

## What is in here

| Folder | What it does |
|---|---|
| `crosswalk/` | Downloads the CMS 2026 ICD-10-CM to HCC mapping (pinned URL and sha256) and builds `data/hcc_crosswalk_2026.csv` and `.parquet` |
| `compare/` | Reads Metriport's public `hcc-map.ts` at a pinned commit and writes `reports/compare.md` |
| `fhir_loader/` | Reads FHIR NDJSON once per file, writes Patient, Condition and Encounter to Parquet, and joins Conditions to the crosswalk in DuckDB |
| `tests/` | 14 tests. The crosswalk matches the CMS file, the comparison is reproducible, and the loader output equals the baseline |

## Run it

```
make all
```

This needs Python 3.11 or newer and internet access to cms.gov and GitHub. It creates `.venv`, builds the crosswalk, runs the comparison, runs the benchmark on 3,000 synthetic patients (about 3 minutes), prints a DuckDB demo, then runs ruff and pytest. `make crosswalk`, `make compare`, `make bench` and `make test` run one step each.

Every input is checked against a pinned sha256. If the CMS download fails, the build uses a local copy from `HCC_FALLBACK_DIR`, checks the same sha256, and says so in `data/hcc_crosswalk_2026.source.json`. The committed files were built from a fresh cms.gov download.

## Results

### The crosswalk

`data/hcc_crosswalk_2026.csv` has one row per code, payment model and HCC. Columns are `code, display, system, hcc_code, hcc_model, payment_year, payment_flag`, close to the `condition_extension_vcc_coding` columns in Metriport's warehouse docs, plus the model and year that table does not have.

- 11,346 ICD-10-CM codes from 11,865 lines in the CMS file, 58,084 rows
- Payable rows by model: CMS-HCC-V28 8,299, CMS-HCC-V22 10,106, ESRD-V24 10,339, ESRD-V21 10,589, RxHCC-V08 5,527
- A code that is valid but has no HCC in a model gets a row with an empty `hcc_code` and `payment_flag = false`, so "no HCC" is explicit
- ESRD-V21 is included because the CMS file has it and PACE ESRD blends it in 2026

### Compared with Metriport's public map

Full report in [`reports/compare.md`](reports/compare.md), full lists in `reports/*.csv`. Input is `packages/core/src/external/fhir/shared/hcc-map.ts` at commit `e1f26d5`, which is still the head of the public `develop` branch on Oct 30, 2026.

- The map has 11,184 codes. Every V28 value it has matches CMS 2026 and every V24 value matches CMS 2025. The map is accurate for the codes it covers.
- CMS 2026 gives a V28 HCC to 8,019 codes. **231 of them are not in the map.** 134 are new ICD-10-CM codes for FY2026 and 97 were already in the CMS 2025 file with a V28 HCC.
- Examples: C50A0, C50A1, C50A2 (inflammatory breast cancer, V28 HCC 23), E66813 (obesity class 3, V28 HCC 48), C810A (Hodgkin lymphoma in remission, V28 HCC 21), and 112 codes in category L98.
- 26 HCC numbers are used by both V24 and V28 in the map. 23 of them share no code between the two versions. HCC 19 is diabetes without complication in V24 and a cancer group in V28 (E089 vs C450). Only 1, 2 and 6 mean roughly the same thing in both. A model label next to every HCC number removes that ambiguity.

### Loader benchmark

Metriport's public `fhir-to-csv` step (`parseNdjsonBundle.py`) reads each patient file once for the patient id and then once more for each of 28 resource types. `fhir_loader/naive.py` re-implements that access pattern. `fhir_loader/single_pass.py` reads each file once. On 3,000 synthetic patients (350,291 resources, 280 MB), median of 3 runs:

| Approach | Median seconds |
|---|---:|
| Baseline, 28 passes per file | 44.52 |
| Baseline limited to the 3 output types | 7.43 |
| Single pass to Parquet | 1.69 |
| Single pass to Parquet plus DuckDB crosswalk join | 2.04 |

That is 26.4x faster for the load, 21.8x with the join. Both produce identical rows (tested). Machine: 8 vCPU Intel Xeon, 15.6 GB RAM, Linux, Python 3.13, single process, stdlib `json` on both sides. The baseline leaves out the extra per-config passes the real pipeline makes, so it is if anything flattering to the baseline. Synthetic data on one machine is a direction, not a production estimate. Details in [`reports/benchmark.md`](reports/benchmark.md).

## Query it with DuckDB

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

I73.9 has no V28 row, so it adds nothing to a 2026 non-PACE Medicare Advantage score, but it still counts for PACE and ESRD.

## 2026 payment models, for context

From the [CMS CY2026 Rate Announcement](https://www.cms.gov/files/document/2026-announcement.pdf): non-PACE Medicare Advantage uses the 2024 CMS-HCC model (V28) at 100%. PACE uses 10% V28 and 90% V22. ESRD members use the 2023 ESRD models (V24 categories), and PACE blends 10% of those with 90% of the 2019 ESRD models (V21 categories). Part D uses RxHCC V08. The CMS 2026 mapping file has no community V24 column.

## Credits

ICD-10-CM to HCC mappings are published by the Centers for Medicare & Medicaid Services ([2026 model software and ICD-10 mappings](https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics/risk-adjustment/2026-model-software-icd-10-mappings)). The comparison reads Metriport's public [metriport/metriport](https://github.com/metriport/metriport) repo. All patient data here is synthetic.

## License

MIT, by Asad Moulvi. See [LICENSE](LICENSE).

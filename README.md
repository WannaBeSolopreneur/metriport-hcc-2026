# metriport-hcc-2026

Hi Metriport team, I created this to demonstrate my skills for your Data Engineering position.

A tested 2026 diagnosis code to HCC table, a compare report, and a faster FHIR loader, built for Metriport.

## About me

I am Asad Moulvi, a Data Scientist at DataQHealth.

- I build healthcare data pipelines for claims, encounters and patient attribution, over 10M records a year.
- I automated CMS data collection and ACO doctor selection. Our ACO was approved in under 3 months.
- I built a FHIR-compliant AI scribe for doctors, and an AI tool that sums up heart device alerts. It saves nurses 3 hours a day.

MS Business Analytics and AI (UT Dallas). BSc Physics (University of Nottingham).
[LinkedIn](https://www.linkedin.com/in/asad-moulvi-aaa278175) · [GitHub](https://github.com/WannaBeSolopreneur) · asad.moulvi01@gmail.com

## What I noticed in Metriport's public repo

1. **Some 2026 codes are not in the map yet.** [`hcc-map.ts`](https://github.com/metriport/metriport/blob/e1f26d504cb9d132d66a7a9607ffb199be759168/packages/core/src/external/fhir/shared/hcc-map.ts) does not include 231 ICD-10 codes that pay under V28 in 2026. 134 of them are new codes from Oct 1, 2025.
2. **Some old codes were split.** 22 older parent codes are still mapped after CMS split them into more specific codes.
3. **The HCC model is not labeled.** The same HCC number can mean different things in V24 and V28. HCC 19 is diabetes in V24 but a cancer group in V28. [`hcc-extension.ts`](https://github.com/metriport/metriport/blob/e1f26d504cb9d132d66a7a9607ffb199be759168/packages/core/src/external/fhir/shared/extensions/hcc-extension.ts) lists V24 before V28, and the warehouse `hcc_code` column has no model label.
4. **Files are read many times.** [`parseNdjsonBundle.py`](https://github.com/metriport/metriport/blob/e1f26d504cb9d132d66a7a9607ffb199be759168/packages/data-transformation/fhir-to-csv/src/parseNdjsonBundle/parseNdjsonBundle.py) reads each file once per resource type. That is 28 passes.

Based on Metriport's public repo and docs as of Oct 30, 2026. If this is already fixed internally, this is a tested table to check against.

## What I built

- **For 1 and 2: a CMS 2026 HCC table.** Each code is labeled by payment model (V28, PACE V22, ESRD V24, RxHCC V08). All 58,084 rows are checked against the official CMS file.
- **For 1 and 2: a compare report.** It lists every missing code and every split parent code in `hcc-map.ts`.
- **For 3: a model label on every row.** You can always tell a V24 HCC from a V28 HCC.
- **For 4: a single-pass loader.** It reads each FHIR file once and writes Parquet. On the same 3 tables it is about 4x faster, with the exact same rows.
- **For trust: tests and a recount.** 42 tests pass. A separate script recounts every number from the CMS files on each build.

![How it fits together. The CMS 2026 HCC file builds the HCC table, labeled by payment model. The HCC table and Metriport hcc-map.ts feed the compare report. FHIR NDJSON files and the HCC table feed the fast loader, which writes conditions and HCCs to Parquet.](docs/img/flow.png)

![8,019 codes pay under V28 in 2026. 7,788 are in the map. 231 are missing.](docs/img/coverage.png)

## How it can help Metriport

- **A lookup table.** Join it on the ICD-10 code to fill the 231 gaps.
- **A model label.** Store the model next to `hcc_code` so V24 and V28 never mix.
- **A yearly check.** Run the report on each new CMS file to catch new codes early.

## Quick start

You need Python 3.11 or newer, `make`, and internet access.

```
make all
```

This builds the table, runs the report, recounts the numbers, runs the speed test and runs all tests. It takes about 4 minutes.

More detail, including the speed table, the checks and the limits, is in [docs/DETAILS.md](docs/DETAILS.md).

---

**Credits:** HCC mappings and ICD-10 code lists from [CMS](https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics/risk-adjustment/2026-model-software-icd-10-mappings). All patient data is synthetic.

**License:** MIT, by Asad Moulvi. See [LICENSE](LICENSE).

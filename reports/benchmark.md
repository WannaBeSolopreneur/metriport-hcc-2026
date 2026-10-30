# Loader benchmark

Input: 3,000 synthetic patients (seed 2026), one NDJSON file per patient, 349,876 resources across 28 resource types, 279.8 MB.
Output rows: 3,000 patients, 49,286 condition rows (one per ICD-10 coding) from 45,324 Conditions, 37,476 encounters, 162,438 condition to HCC rows.

| Approach | Median seconds | All runs |
|---|---:|---|
| Baseline, 28 passes per file (Metriport pattern) | 49.70 | 51.33, 49.70, 48.72 |
| Baseline limited to the 3 output types (4 passes per file) | 8.71 | 9.39, 8.71, 8.25 |
| Single pass, Parquet out | 2.22 | 2.51, 2.22, 2.17 |
| Single pass, Parquet out, plus DuckDB crosswalk join | 2.43 | 2.43, 2.42, 2.50 |

## In plain words

- **Fair test: 3.9x faster.** The baseline is limited to the same 3 tables the single pass builds (4 passes per file).
- **Whole pattern: 22.4x faster.** The baseline scans each file once for the patient id, then reads and parses it again for each of the 28 resource types. It writes a temp file per type and a CSV per patient. The single pass reads and parses each file once and writes Parquet. So this number is the whole pattern, not file reading alone.
- With the DuckDB crosswalk join included, the single pass is 20.4x faster than the 28-type baseline.
- Both sides give exactly the same rows. The benchmark compares every row, sorted, and stops with an error if they differ.

## Messy input in this data set

The generator adds a few messy cases on purpose. Both loaders handle them the same way.

- 5,548 Conditions with no usable ICD-10 code (kept, with an empty code)
- 43,738 ICD-10 codings in total, 0 duplicates dropped, 1,391 WHO ICD-10 codings skipped for the HCC join
- 6,251 plain resource lines, 62 byte order marks, 31 blank lines, 31 non-object lines, 0 broken lines, 0 bad UTF-8 lines

## Machine

- Linux-6.12.94+-x86_64-with-glibc2.41, Intel(R) Xeon(R) Processor, 8 logical CPUs, 15.6 GB RAM
- Python 3.13.5, pyarrow 26.0.0, DuckDB 2.0.0
- Single process, stdlib `json` on both sides, input files warm in the OS page cache
- Each approach ran 3 times. The table shows the median and every run.

## Notes

- The baseline re-implements the file access pattern of Metriport's public `parseNdjsonBundle.py`: one scan for the patient id, then one full read and json parse per resource type, a temp file per type, and a per-patient CSV.
- It flattens only Patient, Condition and Encounter, with the same code as the single pass loader. The real pipeline also runs every config per type (Patient has 4, Condition has 2), each reading the temp file again. Leaving that out makes the baseline faster than the real thing, not slower.
- Numbers come from synthetic data on one machine. Real bundles differ in size and shape, so treat this as a direction, not a production estimate.

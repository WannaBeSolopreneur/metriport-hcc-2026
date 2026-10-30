# Loader benchmark

Input: 3,000 synthetic patients (seed 2026), one NDJSON file per patient, 349,876 resources across 28 resource types, 279.8 MB.
Output rows: 3,000 patients, 49,802 condition rows (one per ICD-10 coding) from 45,324 Conditions, 37,476 encounters, 167,160 condition to HCC rows.

| Approach | Median seconds | All runs |
|---|---:|---|
| Baseline, 28 passes per file (Metriport pattern) | 49.20 | 49.15, 49.20, 50.60 |
| Baseline limited to the 3 output types (4 passes per file) | 8.51 | 8.58, 8.51, 8.19 |
| Single pass, Parquet out | 2.15 | 2.60, 2.15, 2.14 |
| Single pass, Parquet out, plus DuckDB crosswalk join | 2.56 | 2.53, 2.59, 2.56 |

## In plain words

- The single pass is **about 23x faster at reading the files** (22.9x). It reads each file once. The baseline reads it 28 times, once per resource type, plus once for the patient id.
- A fairer test limits the baseline to the same 3 tables (4 passes per file). Then the single pass is **about 4x faster** (4.0x).
- With the DuckDB crosswalk join included, the single pass is 19.2x faster than the 28-pass baseline.
- Both sides give exactly the same rows. The benchmark stops with an error if they do not.

## Messy input in this data set

The generator adds a few messy cases on purpose. Both loaders handle them the same way.

- 1,858 Conditions with no usable ICD-10 code (kept, with an empty code)
- 47,944 ICD-10 codings in total, 0 duplicates dropped
- 6,251 plain resource lines, 62 byte order marks, 31 blank lines, 31 non-object lines, 0 broken lines

## Machine

- Linux-6.12.94+-x86_64-with-glibc2.41, Intel(R) Xeon(R) Processor, 8 logical CPUs, 15.6 GB RAM
- Python 3.13.5, pyarrow 26.0.0, DuckDB 2.0.0
- Single process, stdlib `json` on both sides, input files warm in the OS page cache
- Each approach ran 3 times. The table shows the median and every run.

## Notes

- The baseline re-implements the file access pattern of Metriport's public `parseNdjsonBundle.py`: one scan for the patient id, then one full read and json parse per resource type, a temp file per type, and a per-patient CSV.
- It flattens only Patient, Condition and Encounter, with the same code as the single pass loader. The real pipeline also runs every config per type (Patient has 4, Condition has 2), each reading the temp file again. Leaving that out makes the baseline faster than the real thing, not slower.
- Numbers come from synthetic data on one machine. Real bundles differ in size and shape, so treat this as a direction, not a production estimate.

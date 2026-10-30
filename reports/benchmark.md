# Loader benchmark

Input: 3,000 synthetic patients (seed 2026), one NDJSON file per patient, 350,291 resources across 28 resource types, 280.1 MB.
Output rows: 3,000 patients, 45,154 conditions, 37,872 encounters, 155,956 condition to HCC rows.

| Approach | Median seconds | All runs |
|---|---:|---|
| Baseline, 28 passes per file (Metriport pattern) | 44.52 | 46.97, 44.29, 44.52 |
| Baseline limited to the 3 output types (4 passes per file) | 7.43 | 7.44, 7.43, 7.06 |
| Single pass, Parquet out | 1.69 | 1.85, 1.69, 1.68 |
| Single pass, Parquet out, plus DuckDB crosswalk join | 2.04 | 2.02, 2.04, 2.07 |

Single pass load is **26.4x** faster than the baseline. With the crosswalk join included it is 21.8x.

## Machine

- Linux-6.12.94+-x86_64-with-glibc2.41, Intel(R) Xeon(R) Processor, 8 logical CPUs, 15.6 GB RAM
- Python 3.13.5, pyarrow 26.0.0, DuckDB 2.0.0
- Single process, stdlib `json` on both sides, input files warm in the OS page cache

## Notes

- The baseline re-implements the file access pattern of Metriport's public `parseNdjsonBundle.py`: one scan for the patient id, then one full read and json parse per resource type, a temp file per type, and a per-patient CSV.
- It flattens only Patient, Condition and Encounter, with the same code as the single pass loader. The real pipeline also runs every config per type (Patient has 4, Condition has 2), each reading the temp file again. Leaving that out makes the baseline faster than the real thing, not slower.
- The second row shows how much of the gap is the extra passes: the same baseline limited to the 3 output types.
- Numbers come from synthetic data on one machine. Real bundles differ in size and shape, so treat this as a direction, not a production estimate.

"""Benchmark the single-pass loader against the re-read-per-resource-type baseline.

Writes reports/benchmark.md and reports/benchmark.json. Timings are wall clock on whatever
machine runs this, median of --repeats runs, with the synthetic files already on disk.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import statistics
import time
from importlib.metadata import version
from pathlib import Path

import pyarrow.parquet as pq

from crosswalk.sources import CACHE, DATA, REPORTS
from fhir_loader import naive, single_pass, synth
from fhir_loader.ndjson import LoadStats
from fhir_loader.resource_types import RESOURCE_TYPES, TABLES

CROSSWALK = DATA / "hcc_crosswalk_2026.parquet"


def machine() -> dict:
    cpu = platform.processor() or platform.machine()
    mem_gb = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return {
        "os": platform.platform(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "memory_gb": mem_gb,
        "python": platform.python_version(),
        "pyarrow": version("pyarrow"),
        "duckdb": version("duckdb"),
    }


def ensure_data(patients: int, seed: int) -> list[Path]:
    out = CACHE / f"synthetic_v2_{patients}_{seed}"
    marker = out / ".complete"
    if not marker.exists():
        shutil.rmtree(out, ignore_errors=True)
        synth.generate(out, patients, synth.crosswalk_codes(CROSSWALK), seed)
        marker.write_text("ok\n")
    return sorted(out.glob("patient_*.ndjson"))


def timed(fn, repeats: int, out_dir: Path) -> tuple[list[float], object]:
    times, result = [], None
    for _ in range(repeats):
        shutil.rmtree(out_dir, ignore_errors=True)
        t = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t)
    return times, result


def _sorted_rows(rows: list[dict]) -> list[tuple]:
    """Rows as sorted tuples of (column, value), so order does not matter."""
    return sorted(
        tuple(sorted((k, "" if v is None else str(v)) for k, v in r.items())) for r in rows
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", type=int, default=3000)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
    # The timed runs load the same files many times. Report input problems once, at the end.
    loader_log = logging.getLogger("fhir_loader")
    loader_log.setLevel(logging.ERROR)

    files = ensure_data(args.patients, args.seed)
    size_mb = sum(f.stat().st_size for f in files) / 1e6
    work = CACHE / "bench"
    single_dir = work / "single"

    def run_single():
        paths = single_pass.load(files, single_dir, LoadStats())
        single_pass.join_crosswalk(paths["Condition"], CROSSWALK, single_dir)
        return paths

    def run_single_load_only():
        return single_pass.load(files, single_dir, LoadStats())

    variants = [
        (
            "baseline_28_types",
            "Baseline, 28 passes per file (Metriport pattern)",
            lambda: naive.run(files, work / "naive"),
            work / "naive",
        ),
        (
            "baseline_3_types",
            "Baseline limited to the 3 output types (4 passes per file)",
            lambda: naive.run(files, work / "naive3", types=TABLES),
            work / "naive3",
        ),
        ("single_pass_load", "Single pass, Parquet out", run_single_load_only, single_dir),
        (
            "single_pass_load_join",
            "Single pass, Parquet out, plus DuckDB crosswalk join",
            run_single,
            single_dir,
        ),
    ]
    results = {}
    for key, label, fn, out_dir in variants:
        times, res = timed(fn, args.repeats, out_dir)
        results[key] = {"label": label, "seconds": times, "median": statistics.median(times)}
        print(f"bench: {label}: median {results[key]['median']:.2f}s over {args.repeats} runs")
        if key == "baseline_28_types":
            baseline = res

    single_rows = {
        t: pq.read_metadata(single_dir / f"{t.lower()}.parquet").num_rows for t in TABLES
    }
    hcc_rows = pq.read_metadata(single_dir / "condition_hcc.parquet").num_rows
    # Both sides must give exactly the same rows, not just the same number of rows.
    for t in TABLES:
        ours = pq.read_table(single_dir / f"{t.lower()}.parquet").to_pylist()
        if _sorted_rows(ours) != _sorted_rows(baseline[t]):
            raise SystemExit(f"{t} rows differ between the single pass and the baseline")
    print(f"bench: row content is identical on all {len(TABLES)} tables")
    stats = LoadStats()
    loader_log.setLevel(logging.WARNING)
    single_pass.load(files, work / "stats", stats)
    lines = stats.resources

    base = results["baseline_28_types"]["median"]
    report = {
        "patients": args.patients,
        "seed": args.seed,
        "files": len(files),
        "resources": lines,
        "input_mb": round(size_mb, 1),
        "resource_types": len(RESOURCE_TYPES),
        "rows": single_rows,
        "condition_hcc_rows": hcc_rows,
        "repeats": args.repeats,
        "results": results,
        "input_stats": stats.as_dict(),
        "speedup_load_vs_baseline": round(base / results["single_pass_load"]["median"], 1),
        "speedup_load_vs_baseline_3_types": round(
            results["baseline_3_types"]["median"] / results["single_pass_load"]["median"], 1
        ),
        "speedup_load_join_vs_baseline": round(
            base / results["single_pass_load_join"]["median"], 1
        ),
        "machine": machine(),
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPORTS / "benchmark.md").write_text(render(report))
    print(
        f"bench: {report['speedup_load_vs_baseline_3_types']:.1f}x faster on the same 3 tables, "
        f"{report['speedup_load_vs_baseline']:.1f}x faster than the whole 28-type pattern"
    )


def render(r: dict) -> str:
    m = r["machine"]
    st = r["input_stats"]
    rows = [
        f"| {v['label']} | {v['median']:.2f} | "
        + ", ".join(f"{s:.2f}" for s in v["seconds"])
        + " |"
        for v in r["results"].values()
    ]
    return "\n".join(
        [
            "# Loader benchmark",
            "",
            f"Input: {r['patients']:,} synthetic patients (seed {r['seed']}), one NDJSON file "
            f"per patient, {r['resources']:,} resources across {r['resource_types']} resource "
            f"types, {r['input_mb']} MB.",
            f"Output rows: {r['rows']['Patient']:,} patients, {r['rows']['Condition']:,} "
            f"condition rows (one per ICD-10 coding) from {st['conditions']:,} Conditions, "
            f"{r['rows']['Encounter']:,} encounters, "
            f"{r['condition_hcc_rows']:,} condition to HCC rows.",
            "",
            "| Approach | Median seconds | All runs |",
            "|---|---:|---|",
            *rows,
            "",
            "## In plain words",
            "",
            f"- **Fair test: {r['speedup_load_vs_baseline_3_types']:.1f}x faster.** The "
            "baseline is limited to the same 3 tables the single pass builds (4 passes per "
            "file).",
            f"- **Whole pattern: {r['speedup_load_vs_baseline']:.1f}x faster.** The baseline "
            "scans each file once for the patient id, then reads and parses it again for each "
            "of the 28 resource types. It writes a temp file per type and a CSV per patient. "
            "The single pass reads and parses each file once and writes Parquet. So this "
            "number is the whole pattern, not file reading alone.",
            f"- With the DuckDB crosswalk join included, the single pass is "
            f"{r['speedup_load_join_vs_baseline']:.1f}x faster than the 28-type baseline.",
            "- Both sides give exactly the same rows. The benchmark compares every row, sorted, "
            "and stops with an error if they differ.",
            "",
            "## Messy input in this data set",
            "",
            "The generator adds a few messy cases on purpose. Both loaders handle them the "
            "same way.",
            "",
            f"- {st['conditions_without_icd10']:,} Conditions with no usable ICD-10 code "
            "(kept, with an empty code)",
            f"- {st['icd10_codings']:,} ICD-10 codings in total, "
            f"{st['duplicate_icd10_codings']:,} duplicates dropped, "
            f"{st['who_icd10_codings_skipped']:,} WHO ICD-10 codings skipped for the HCC join",
            f"- {st['unwrapped_lines']:,} plain resource lines, {st['bom_lines']:,} byte "
            f"order marks, {st['blank_lines']:,} blank lines, {st['non_object_lines']:,} "
            f"non-object lines, {st['bad_json_lines']:,} broken lines, "
            f"{st['bad_utf8_lines']:,} bad UTF-8 lines",
            "",
            "## Machine",
            "",
            f"- {m['os']}, {m['cpu']}, {m['logical_cpus']} logical CPUs, {m['memory_gb']} GB RAM",
            f"- Python {m['python']}, pyarrow {m['pyarrow']}, DuckDB {m['duckdb']}",
            "- Single process, stdlib `json` on both sides, input files warm in the OS page cache",
            f"- Each approach ran {r['repeats']} times. The table shows the median and every run.",
            "",
            "## Notes",
            "",
            "- The baseline re-implements the file access pattern of Metriport's public "
            "`parseNdjsonBundle.py`: one scan for the patient id, then one full read and "
            "json parse per resource type, a temp file per type, and a per-patient CSV.",
            "- It flattens only Patient, Condition and Encounter, with the same code as the "
            "single pass loader. The real pipeline also runs every config per type (Patient "
            "has 4, Condition has 2), each reading the temp file again. Leaving that out makes "
            "the baseline faster than the real thing, not slower.",
            "- Numbers come from synthetic data on one machine. Real bundles differ in size and "
            "shape, so treat this as a direction, not a production estimate.",
            "",
        ]
    )


if __name__ == "__main__":
    main()

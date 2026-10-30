"""Benchmark the single-pass loader against the re-read-per-resource-type baseline.

Writes reports/benchmark.md and reports/benchmark.json. Timings are wall clock on whatever
machine runs this, median of --repeats runs, with the synthetic files already on disk.
"""

from __future__ import annotations

import argparse
import json
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
    out = CACHE / f"synthetic_{patients}_{seed}"
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", type=int, default=3000)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    files = ensure_data(args.patients, args.seed)
    size_mb = sum(f.stat().st_size for f in files) / 1e6
    lines = 0
    for f in files:
        with open(f) as fh:
            lines += sum(1 for _ in fh)
    work = CACHE / "bench"
    single_dir = work / "single"

    def run_single():
        paths = single_pass.load(files, single_dir)
        single_pass.join_crosswalk(paths["Condition"], CROSSWALK, single_dir)
        return paths

    def run_single_load_only():
        return single_pass.load(files, single_dir)

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
            baseline_rows = {t: len(r) for t, r in res.items()}

    single_rows = {
        t: pq.read_metadata(single_dir / f"{t.lower()}.parquet").num_rows for t in TABLES
    }
    hcc_rows = pq.read_metadata(single_dir / "condition_hcc.parquet").num_rows
    if single_rows != baseline_rows:
        raise SystemExit(f"row counts differ: {single_rows} vs {baseline_rows}")

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
        "speedup_load_vs_baseline": round(base / results["single_pass_load"]["median"], 1),
        "speedup_load_join_vs_baseline": round(
            base / results["single_pass_load_join"]["median"], 1
        ),
        "machine": machine(),
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPORTS / "benchmark.md").write_text(render(report))
    print(f"bench: single pass is {report['speedup_load_vs_baseline']}x faster than the baseline")


def render(r: dict) -> str:
    m = r["machine"]
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
            f"conditions, {r['rows']['Encounter']:,} encounters, "
            f"{r['condition_hcc_rows']:,} condition to HCC rows.",
            "",
            "| Approach | Median seconds | All runs |",
            "|---|---:|---|",
            *rows,
            "",
            f"Single pass load is **{r['speedup_load_vs_baseline']}x** faster than the baseline. "
            f"With the crosswalk join included it is {r['speedup_load_join_vs_baseline']}x.",
            "",
            "## Machine",
            "",
            f"- {m['os']}, {m['cpu']}, {m['logical_cpus']} logical CPUs, {m['memory_gb']} GB RAM",
            f"- Python {m['python']}, pyarrow {m['pyarrow']}, DuckDB {m['duckdb']}",
            "- Single process, stdlib `json` on both sides, input files warm in the OS page cache",
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
            "- The second row shows how much of the gap is the extra passes: the same baseline "
            "limited to the 3 output types.",
            "- Numbers come from synthetic data on one machine. Real bundles differ in size and "
            "shape, so treat this as a direction, not a production estimate.",
            "",
        ]
    )


if __name__ == "__main__":
    main()

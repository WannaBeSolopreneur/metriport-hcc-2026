"""Draw the README charts from the committed reports. Run with `make charts`.

Reads reports/compare.json, reports/missing_v28_codes.csv and reports/benchmark.json.
Writes PNG files to docs/img/.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
OUT = ROOT / "docs" / "img"

NAVY = "#1B2A41"
BLUE = "#A7C7E7"
GREY = "#5B6573"

# Plain-English names for ICD-10-CM categories. Checked against the official FY2026 order
# file and against the descriptions of the missing codes themselves.
CATEGORY_NAMES = {
    "L98": "Chronic skin ulcers (L98)",
    "F50": "Eating disorders (F50)",
    "C86": "T/NK-cell lymphoma (C86)",
    "C88": "Waldenstrom and other B-cell (C88)",
    "C82": "Follicular lymphoma (C82)",
    "C83": "Non-follicular lymphoma (C83)",
    "C84": "Mature T/NK-cell lymphoma (C84)",
    "G35": "Multiple sclerosis (G35)",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 12,
        "axes.edgecolor": GREY,
        "axes.labelcolor": NAVY,
        "xtick.color": NAVY,
        "ytick.color": NAVY,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.titlesize": 15,
        "axes.titlecolor": NAVY,
        "axes.titlelocation": "left",
        "figure.dpi": 100,
    }
)


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return path


def coverage(c: dict) -> Path:
    in_map = c["v28_codes_2026"] - c["missing"]
    fig, ax = plt.subplots(figsize=(10, 2.6))
    ax.barh([0], [in_map], color=BLUE, height=0.55)
    ax.barh([0], [c["missing"]], left=[in_map], color=NAVY, height=0.55)
    ax.text(in_map / 2, 0, f"{in_map:,} codes in the map", ha="center", va="center", color=NAVY)
    ax.annotate(
        f"{c['missing']} missing\n{c['missing_added_fy2025']} added Oct 2024\n"
        f"{c['missing_new_fy2026']} added Oct 2025",
        xy=(in_map + c["missing"] / 2, 0.3),
        xytext=(in_map - 1500, 0.95),
        color=NAVY,
        ha="left",
        arrowprops={"arrowstyle": "-", "color": NAVY},
    )
    ax.set_xlim(0, c["v28_codes_2026"])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_ylim(-0.5, 1.5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("ICD-10-CM codes with a V28 HCC in the CMS 2026 file")
    ax.set_title(f"{c['v28_codes_2026']:,} codes pay under V28 in 2026")
    return _save(fig, "coverage.png")


def missing_by_category() -> Path:
    with open(REPORTS / "missing_v28_codes.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    new = Counter(r["code"][:3] for r in rows if r["added_to_icd10cm"].startswith("FY2026"))
    old = Counter(r["code"][:3] for r in rows if not r["added_to_icd10cm"].startswith("FY2026"))
    total = new + old
    top = [k for k, _ in total.most_common() if k in CATEGORY_NAMES][:8]
    other = [k for k in total if k not in top]
    labels = [CATEGORY_NAMES[k] for k in top] + [f"Other ({len(other)} categories)"]
    n_new = [new[k] for k in top] + [sum(new[k] for k in other)]
    n_old = [old[k] for k in top] + [sum(old[k] for k in other)]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    y = list(range(len(labels)))[::-1]
    ax.barh(y, n_new, color=NAVY, label="New code, added Oct 1, 2025 (FY2026)")
    ax.barh(y, n_old, left=n_new, color=BLUE, label="Added Oct 1, 2024 (FY2025)")
    for yi, a, b in zip(y, n_new, n_old, strict=True):
        ax.text(a + b + 1.5, yi, str(a + b), va="center", color=NAVY)
    ax.set_yticks(y, labels)
    ax.set_xlabel("Missing codes")
    ax.set_xlim(0, max(a + b for a, b in zip(n_new, n_old, strict=True)) * 1.12)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title(f"Where the {len(rows)} missing codes are")
    return _save(fig, "missing_by_category.png")


def benchmark(b: dict) -> Path:
    order = [
        ("baseline_28_types", "Baseline, 28 passes per file"),
        ("baseline_3_types", "Baseline, same 3 tables (4 passes)"),
        ("single_pass_load", "Single pass"),
        ("single_pass_load_join", "Single pass plus HCC join"),
    ]
    labels = [label for _, label in order]
    secs = [b["results"][k]["median"] for k, _ in order]
    colors = [BLUE, BLUE, NAVY, NAVY]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = list(range(len(labels)))[::-1]
    ax.barh(y, secs, color=colors, height=0.6)
    for yi, s in zip(y, secs, strict=True):
        ax.text(s + max(secs) * 0.01, yi, f"{s:.1f} s", va="center", color=NAVY)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(secs) * 1.12)
    ax.set_xlabel(
        f"Median seconds over {b['repeats']} runs, {b['patients']:,} synthetic patients "
        "(lower is better)"
    )
    ax.set_title(
        f"About {b['speedup_load_vs_baseline']:.0f}x faster at reading the files, "
        f"about {b['speedup_load_vs_baseline_3_types']:.0f}x on the same 3 tables"
    )
    return _save(fig, "benchmark.png")


def main() -> None:
    c = json.loads((REPORTS / "compare.json").read_text())
    b = json.loads((REPORTS / "benchmark.json").read_text())
    for path in (coverage(c), missing_by_category(), benchmark(b)):
        print(f"charts: wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

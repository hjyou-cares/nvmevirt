"""Aggregate the SLC-resident/overflow/sustained crossover experiment."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/nvmevirt2-matplotlib")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
OUTPUT_DIR = REPO_ROOT / "report" / "crossover_results"
FIGURE_PATH = REPO_ROOT / "report" / "figures" / "practice2_ext_fig5_slc_crossover.png"

VARIANTS = ("resident", "overflow", "sustained")
VARIANT_LABELS = {
    "resident": "Resident\n1 GiB × 1",
    "overflow": "Overflow\n6 GiB × 1",
    "sustained": "Sustained\n22 GiB × 3",
}
EXPECTED_WORKLOAD = {
    "resident": ("1G", "1"),
    "overflow": ("6G", "1"),
    "sustained": ("22G", "3"),
}
RATIO_LABELS = {0: "TLC-only (0%)", 10: "SLC cache (10%)"}
RATIO_COLORS = {0: "#64748b", 10: "#3478d4"}
PAGES_PER_GIB_4K = (1024**3) / 4096


def read_kv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def read_summary(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in path.read_text().split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def load_run(run_dir: Path) -> dict[str, int | float | str]:
    required = (run_dir / "meta.txt", run_dir / "summary.txt", run_dir / "fio.json")
    if not all(path.is_file() for path in required):
        raise ValueError(f"Incomplete run: {run_dir}")

    meta = read_kv(run_dir / "meta.txt")
    summary = read_summary(run_dir / "summary.txt")
    fio = json.loads((run_dir / "fio.json").read_text())
    jobs = fio.get("jobs", [])
    if not jobs or any(int(job.get("error", 0)) != 0 for job in jobs):
        raise ValueError(f"Failed fio run: {run_dir}")

    variant = meta.get("experiment_variant", "")
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}: {run_dir}")
    if meta.get("write_early_completion") != "0":
        raise ValueError(f"write_early_completion is not 0: {run_dir}")
    if meta.get("fio_iodepth") != "1":
        raise ValueError(f"fio_iodepth is not 1: {run_dir}")
    if (meta.get("uniform_size"), meta.get("uniform_loops")) != EXPECTED_WORKLOAD[variant]:
        raise ValueError(f"Unexpected workload size/loops: {run_dir}")

    write = jobs[-1]["write"]
    written_gib = float(write.get("io_bytes", 0)) / (1024**3)
    if written_gib <= 0:
        raise ValueError(f"No written bytes: {run_dir}")

    slc_pages = float(summary.get("slc_migrate_pages", "0"))
    return {
        "run_dir": str(run_dir.relative_to(REPO_ROOT)),
        "variant": variant,
        "rep": int(meta["experiment_rep"]),
        "ratio": int(meta["slc_cache_ratio_percent"]),
        "written_gib": written_gib,
        "bw_mib": float(write.get("bw", 0)) / 1024,
        "iops": float(write.get("iops", 0)),
        "avg_us": float(write["lat_ns"]["mean"]) / 1000,
        "p99_us": float(write["clat_ns"]["percentile"]["99.000000"]) / 1000,
        "slc_migrate_pages": slc_pages,
        "migration_percent": 100 * slc_pages / (written_gib * PAGES_PER_GIB_4K),
        "tlc_gc_pages": float(summary.get("tlc_gc_migrate_pages", "0")),
        "erase_sum": float(summary.get("sum", "0")),
    }


def discover_runs() -> list[dict[str, int | float | str]]:
    keyed: dict[tuple[str, int, int], dict[str, int | float | str]] = {}
    for meta_path in sorted(RESULTS_DIR.rglob("meta.txt")):
        meta = read_kv(meta_path)
        if meta.get("experiment_suite") != "slc_crossover":
            continue
        run = load_run(meta_path.parent)
        key = (str(run["variant"]), int(run["rep"]), int(run["ratio"]))
        keyed[key] = run
    return sorted(
        keyed.values(),
        key=lambda row: (VARIANTS.index(str(row["variant"])), int(row["ratio"]), int(row["rep"])),
    )


def expected_keys(reps: tuple[int, ...]) -> set[tuple[str, int, int]]:
    return {(variant, rep, ratio) for variant in VARIANTS for rep in reps for ratio in (0, 10)}


def aggregate(rows: list[dict[str, int | float | str]]) -> list[dict[str, int | float | str]]:
    groups: dict[tuple[str, int], list[dict[str, int | float | str]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["variant"]), int(row["ratio"]))].append(row)

    metrics = ("written_gib", "bw_mib", "iops", "avg_us", "p99_us", "migration_percent")
    output: list[dict[str, int | float | str]] = []
    for variant in VARIANTS:
        for ratio in (0, 10):
            group = groups.get((variant, ratio), [])
            if not group:
                continue
            item: dict[str, int | float | str] = {
                "variant": variant,
                "ratio": ratio,
                "n": len(group),
            }
            for metric in metrics:
                values = [float(row[metric]) for row in group]
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            output.append(item)
    return output


def write_csv(rows: list[dict[str, int | float | str]], path: Path) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def validate_counters(rows: list[dict[str, int | float | str]]) -> list[str]:
    errors: list[str] = []
    for row in rows:
        ratio = int(row["ratio"])
        variant = str(row["variant"])
        migrated = float(row["slc_migrate_pages"])
        if ratio == 0 and migrated != 0:
            errors.append(f"TLC-only run migrated SLC pages: {row['run_dir']}")
        if ratio == 10 and variant == "resident" and migrated != 0:
            errors.append(f"Resident run overflowed SLC: {row['run_dir']}")
        if ratio == 10 and variant in {"overflow", "sustained"} and migrated <= 0:
            errors.append(f"Expected SLC migration was not observed: {row['run_dir']}")
    return errors


def plot(rows: list[dict[str, int | float | str]]) -> None:
    by_key = {(str(row["variant"]), int(row["ratio"])): row for row in rows}
    x = np.arange(len(VARIANTS), dtype=float)
    width = 0.34
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6), facecolor="#f5f7fa")

    panels = (
        ("bw_mib", "Write throughput", "MiB/s"),
        ("p99_us", "Host write p99 latency", "µs"),
        ("migration_percent", "SLC→TLC copied pages", "% of host-written pages"),
    )
    for axis, (metric, title, ylabel) in zip(axes, panels):
        axis.set_facecolor("white")
        for index, ratio in enumerate((0, 10)):
            means = [float(by_key[(variant, ratio)][f"{metric}_mean"]) for variant in VARIANTS]
            stds = [float(by_key[(variant, ratio)][f"{metric}_std"]) for variant in VARIANTS]
            positions = x + (index - 0.5) * width
            axis.bar(
                positions,
                means,
                width,
                yerr=stds,
                capsize=3,
                color=RATIO_COLORS[ratio],
                label=RATIO_LABELS[ratio],
            )
        axis.set_title(title, fontweight="bold")
        axis.set_ylabel(ylabel)
        axis.set_xticks(x, [VARIANT_LABELS[variant] for variant in VARIANTS])
        axis.grid(axis="y", color="#e5e9f0", linewidth=0.8)
        axis.set_axisbelow(True)

    axes[0].legend(frameon=False, loc="best")
    fig.suptitle("SLC cache crossover: benefit before saturation, migration cost after saturation", fontweight="bold")
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--reps", default="1,2,3", help="comma-separated repetition numbers")
    args = parser.parse_args()
    reps = tuple(int(value) for value in args.reps.split(",") if value)

    rows = discover_runs()
    actual = {(str(row["variant"]), int(row["rep"]), int(row["ratio"])) for row in rows}
    missing = sorted(expected_keys(reps) - actual)
    if missing:
        print(f"Missing {len(missing)} crossover runs:")
        for key in missing:
            print("  ", key)
        if not args.allow_partial:
            return 2

    errors = validate_counters(rows)
    if errors:
        print("Counter validation failed:")
        for error in errors:
            print("  ", error)
        return 3

    aggregate_rows = aggregate(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(rows, OUTPUT_DIR / "slc_crossover_raw.csv")
    write_csv(aggregate_rows, OUTPUT_DIR / "slc_crossover_aggregate.csv")

    if not missing:
        plot(aggregate_rows)

    print("variant,ratio,n,bw_mib_mean,bw_mib_std,p99_us_mean,p99_us_std,migration_percent_mean")
    for row in aggregate_rows:
        print(
            f"{row['variant']},{row['ratio']},{row['n']},"
            f"{float(row['bw_mib_mean']):.3f},{float(row['bw_mib_std']):.3f},"
            f"{float(row['p99_us_mean']):.3f},{float(row['p99_us_std']):.3f},"
            f"{float(row['migration_percent_mean']):.3f}"
        )
    print(f"Wrote {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    if not missing:
        print(f"Wrote {FIGURE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

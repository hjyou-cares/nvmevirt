"""Aggregate and plot the three extended Practice 2 experiment suites.

Expected suites are produced by scripts/run_practice2_extended_experiments.sh:

* ratio_sweep: ratio 0/5/10/20, burst/sustained, three repetitions
* policy_repeat: Zipf/Hot-cold, four policies, repetitions 2 and 3
  (the final server repetition 1 already in results/ is included automatically)
* workload_sensitivity: Uniform, four policies, three repetitions

The script writes raw/aggregate CSV files and four report-ready figures. By
default it refuses to present incomplete matrices. Use --allow-partial only to
check parsing and layout while experiments are still running.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/nvmevirt2-matplotlib")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"

POLICY_NAMES = {0: "Greedy", 1: "Random", 2: "FIFO", 3: "Cost-Benefit"}
POLICY_COLORS = ["#3478d4", "#e07a38", "#18a58b", "#7a5af8"]
WORKLOAD_COLORS = {"uniform": "#64748b", "zipf": "#3478d4", "hotcold": "#e07a38"}
VARIANT_COLORS = {"burst": "#3478d4", "sustained": "#e07a38"}

KNOWN_POLICY_REP1 = {
    "zipf": [
        "20260827_151606_slcpolicy0_greedy_zipf_nrm_server_22g_rep1",
        "20260827_151809_slcpolicy1_random_zipf_nrm_server_22g_rep1",
        "20260827_152000_slcpolicy2_fifo_zipf_nrm_server_22g_rep1",
        "20260827_152152_slcpolicy3_costbenefit_zipf_nrm_server_22g_rep1",
    ],
    "hotcold": [
        "20260827_193453_slcpolicy0_greedy_hotcold_server_greedy_full_guarded",
        "20260827_192853_slcpolicy1_random_hotcold_server_random_full_guarded",
        "20260827_193630_slcpolicy2_fifo_hotcold_server_fifo_full_guarded",
        "20260827_193804_slcpolicy3_costbenefit_hotcold_server_cb_full_guarded",
    ],
}

CANVAS = "#f5f7fa"
SURFACE = "#ffffff"
INK = "#172033"
INK_SOFT = "#667085"
GRID = "#e5e9f0"

plt.rcParams.update(
    {
        "figure.facecolor": CANVAS,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SOFT,
        "text.color": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "font.size": 10,
    }
)

METRICS = [
    "written_gib",
    "bw_mib",
    "iops",
    "avg_us",
    "p99_us",
    "slc_migration_cnt",
    "slc_migrate_pages",
    "slc_pages_per_gib",
    "tlc_gc_cnt",
    "tlc_gc_pages",
    "tlc_gc_pages_per_gib",
    "erase_sum",
    "erase_per_gib",
    "erase_max",
    "erase_cv_all",
]


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def read_summary(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in path.read_text().split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        result[key] = value
    return result


def number(mapping: dict[str, str], key: str, default: float = 0.0) -> float:
    value = mapping.get(key, "")
    return float(value) if value != "" else default


def load_run(
    run_dir: Path,
    *,
    suite_override: str | None = None,
    variant_override: str | None = None,
    rep_override: int | None = None,
) -> dict[str, float | int | str]:
    required = [run_dir / "meta.txt", run_dir / "summary.txt", run_dir / "fio.json"]
    if not all(path.is_file() for path in required):
        raise FileNotFoundError(f"Incomplete run: {run_dir}")

    meta = read_kv(run_dir / "meta.txt")
    summary = read_summary(run_dir / "summary.txt")
    fio = json.loads((run_dir / "fio.json").read_text())
    jobs = fio.get("jobs", [])
    if not jobs:
        raise ValueError(f"No fio jobs in {run_dir}")
    if any(int(job.get("error", 0)) != 0 for job in jobs):
        raise ValueError(f"Nonzero fio error in {run_dir}")

    # run_experiment.sh uses group_reporting, so the last (normally only) job
    # contains aggregate write metrics for both single-job and Hot-cold runs.
    write = jobs[-1]["write"]
    written_gib = float(write.get("io_bytes", 0)) / (1024.0**3)
    if written_gib <= 0:
        raise ValueError(f"No written bytes in {run_dir}")

    suite = suite_override or meta.get("experiment_suite", "")
    variant = variant_override or meta.get("experiment_variant", "")
    rep_text = meta.get("experiment_rep", "")
    rep = rep_override if rep_override is not None else int(rep_text)
    policy = int(meta.get("policy", meta.get("slc_migration_policy", "0")))
    ratio = int(meta.get("slc_cache_ratio_percent", "10"))
    slc_pages = number(summary, "slc_migrate_pages")
    tlc_pages = number(summary, "tlc_gc_migrate_pages")
    erase_sum = number(summary, "sum")

    return {
        "run_dir": str(run_dir.relative_to(REPO_ROOT)),
        "suite": suite,
        "variant": variant,
        "rep": rep,
        "policy": policy,
        "policy_name": POLICY_NAMES[policy],
        "ratio": ratio,
        "written_gib": written_gib,
        "bw_mib": float(write.get("bw", 0)) / 1024.0,
        "iops": float(write.get("iops", 0)),
        "avg_us": float(write["lat_ns"]["mean"]) / 1000.0,
        "p99_us": float(write["clat_ns"]["percentile"]["99.000000"]) / 1000.0,
        "slc_migration_cnt": number(summary, "slc_migration_cnt"),
        "slc_migrate_pages": slc_pages,
        "slc_pages_per_gib": slc_pages / written_gib,
        "tlc_gc_cnt": number(summary, "tlc_gc_cnt"),
        "tlc_gc_pages": tlc_pages,
        "tlc_gc_pages_per_gib": tlc_pages / written_gib,
        "erase_sum": erase_sum,
        "erase_per_gib": erase_sum / written_gib,
        "erase_max": number(summary, "max"),
        "erase_cv_all": number(summary, "erase_cv_all"),
    }


def discover_runs() -> list[dict[str, float | int | str]]:
    keyed: dict[tuple[str, str, int, int, int], dict[str, float | int | str]] = {}

    for meta_path in sorted(RESULTS_DIR.rglob("meta.txt")):
        meta = read_kv(meta_path)
        suite = meta.get("experiment_suite", "")
        if suite not in {"ratio_sweep", "policy_repeat", "workload_sensitivity"}:
            continue
        try:
            run = load_run(meta_path.parent)
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Skipping incomplete/failed run {meta_path.parent}: {error}")
            continue
        key = (
            str(run["suite"]),
            str(run["variant"]),
            int(run["rep"]),
            int(run["policy"]),
            int(run["ratio"]),
        )
        keyed[key] = run

    # Reuse the already accepted final server rep1. If a new extended rep1 was
    # explicitly run, it wins because it was inserted above.
    for variant, directory_names in KNOWN_POLICY_REP1.items():
        for directory_name in directory_names:
            run_dir = RESULTS_DIR / directory_name
            if not run_dir.exists():
                continue
            run = load_run(
                run_dir,
                suite_override="policy_repeat",
                variant_override=variant,
                rep_override=1,
            )
            key = ("policy_repeat", variant, 1, int(run["policy"]), 10)
            keyed.setdefault(key, run)

    return sorted(
        keyed.values(),
        key=lambda row: (
            str(row["suite"]),
            str(row["variant"]),
            int(row["ratio"]),
            int(row["policy"]),
            int(row["rep"]),
        ),
    )


def expected_keys() -> set[tuple[str, str, int, int, int]]:
    keys: set[tuple[str, str, int, int, int]] = set()
    for variant in ("burst", "sustained"):
        for ratio in (0, 5, 10, 20):
            for rep in (1, 2, 3):
                keys.add(("ratio_sweep", variant, rep, 0, ratio))
    for variant in ("zipf", "hotcold"):
        for policy in range(4):
            for rep in (1, 2, 3):
                keys.add(("policy_repeat", variant, rep, policy, 10))
    for policy in range(4):
        for rep in (1, 2, 3):
            keys.add(("workload_sensitivity", "uniform", rep, policy, 10))
    return keys


def actual_keys(rows: Iterable[dict[str, float | int | str]]) -> set[tuple[str, str, int, int, int]]:
    return {
        (
            str(row["suite"]),
            str(row["variant"]),
            int(row["rep"]),
            int(row["policy"]),
            int(row["ratio"]),
        )
        for row in rows
    }


def write_raw_csv(rows: list[dict[str, float | int | str]], path: Path) -> None:
    fields = [
        "suite",
        "variant",
        "rep",
        "ratio",
        "policy",
        "policy_name",
        *METRICS,
        "run_dir",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def mean_std(rows: list[dict[str, float | int | str]], metric: str) -> tuple[float, float]:
    values = [float(row[metric]) for row in rows]
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, std


def aggregate_rows(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    grouped: dict[tuple[str, str, int, int], list[dict[str, float | int | str]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["suite"]), str(row["variant"]), int(row["ratio"]), int(row["policy"]))].append(row)

    output: list[dict[str, float | int | str]] = []
    for (suite, variant, ratio, policy), group in sorted(grouped.items()):
        item: dict[str, float | int | str] = {
            "suite": suite,
            "variant": variant,
            "ratio": ratio,
            "policy": policy,
            "policy_name": POLICY_NAMES[policy],
            "n": len(group),
        }
        for metric in METRICS:
            mean, std = mean_std(group, metric)
            item[f"{metric}_mean"] = mean
            item[f"{metric}_std"] = std
        output.append(item)
    return output


def write_aggregate_csv(rows: list[dict[str, float | int | str]], path: Path) -> None:
    fields = ["suite", "variant", "ratio", "policy", "policy_name", "n"]
    for metric in METRICS:
        fields.extend([f"{metric}_mean", f"{metric}_std"])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def style_axes(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=18)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_SOFT, fontsize=8.7)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.tick_params(length=0, labelsize=9)
    ax.grid(axis="x", visible=False)


def save_figure(fig, path: Path, title: str, subtitle: str) -> None:
    fig.suptitle(title, x=0.075, y=0.975, ha="left", fontsize=18, fontweight="bold", color=INK)
    fig.text(0.075, 0.925, subtitle, fontsize=10, color=INK_SOFT)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def select_rows(
    rows: list[dict[str, float | int | str]],
    suite: str,
    variant: str,
    *,
    ratio: int | None = None,
    policy: int | None = None,
) -> list[dict[str, float | int | str]]:
    selected = [row for row in rows if row["suite"] == suite and row["variant"] == variant]
    if ratio is not None:
        selected = [row for row in selected if int(row["ratio"]) == ratio]
    if policy is not None:
        selected = [row for row in selected if int(row["policy"]) == policy]
    return selected


def plot_ratio_sweep(rows: list[dict[str, float | int | str]], figure_dir: Path) -> Path | None:
    if not any(row["suite"] == "ratio_sweep" for row in rows):
        return None
    ratios = [0, 5, 10, 20]
    panels = [
        ("bw_mib", "Write throughput", "Higher is better · MiB/s"),
        ("p99_us", "p99 write latency", "Lower is better · microseconds"),
        ("slc_pages_per_gib", "SLC migration cost", "Valid pages copied per written GiB"),
        ("tlc_gc_pages_per_gib", "Downstream TLC GC cost", "Valid pages copied per written GiB"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 7.7))
    fig.subplots_adjust(left=0.075, right=0.97, top=0.84, bottom=0.11, wspace=0.28, hspace=0.45)

    for ax, (metric, title, subtitle) in zip(axes.ravel(), panels):
        style_axes(ax, title, subtitle)
        for variant in ("burst", "sustained"):
            means: list[float] = []
            stds: list[float] = []
            for ratio in ratios:
                group = select_rows(rows, "ratio_sweep", variant, ratio=ratio, policy=0)
                if group:
                    mean, std = mean_std(group, metric)
                else:
                    mean, std = np.nan, 0.0
                means.append(mean)
                stds.append(std)
            ax.errorbar(
                ratios,
                means,
                yerr=stds,
                marker="o",
                markersize=5,
                linewidth=2,
                capsize=3,
                color=VARIANT_COLORS[variant],
                label=variant.title(),
            )
        ax.set_xticks(ratios)
        ax.set_xlabel("SLC ratio (%)")
    axes[0, 0].legend(frameon=False, ncol=2, loc="best")

    path = figure_dir / "practice2_ext_fig1_ratio_sensitivity.png"
    save_figure(
        fig,
        path,
        "SLC ratio sensitivity: cache benefit versus sustained migration cost",
        "Greedy migration and TLC GC are fixed; points show mean ± sample standard deviation",
    )
    return path


def draw_policy_panel(
    ax,
    rows: list[dict[str, float | int | str]],
    variant: str,
    metric: str,
    title: str,
    subtitle: str,
) -> None:
    means: list[float] = []
    stds: list[float] = []
    for policy in range(4):
        group = select_rows(rows, "policy_repeat", variant, ratio=10, policy=policy)
        if group:
            mean, std = mean_std(group, metric)
        else:
            mean, std = 0.0, 0.0
        means.append(mean)
        stds.append(std)
    style_axes(ax, title, subtitle)
    x = np.arange(4)
    ax.bar(x, means, yerr=stds, capsize=3, color=POLICY_COLORS, width=0.64)
    ax.set_xticks(x)
    ax.set_xticklabels(["Greedy", "Random", "FIFO", "Cost-\nBenefit"], fontsize=8.7)
    ax.margins(y=0.18)


def plot_policy_repeat(
    rows: list[dict[str, float | int | str]], variant: str, figure_dir: Path
) -> Path | None:
    selected = select_rows(rows, "policy_repeat", variant, ratio=10)
    if not selected:
        return None
    fourth = (
        ("erase_max", "Peak wear", "Maximum block erase count")
        if variant == "zipf"
        else ("tlc_gc_pages_per_gib", "Downstream TLC GC cost", "Valid pages/GiB")
    )
    panels = [
        ("bw_mib", "Write throughput", "Higher is better · MiB/s"),
        ("p99_us", "p99 write latency", "Lower is better · microseconds"),
        ("slc_pages_per_gib", "SLC migration cost", "Valid pages/GiB"),
        fourth,
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 7.7))
    fig.subplots_adjust(left=0.075, right=0.97, top=0.84, bottom=0.11, wspace=0.28, hspace=0.48)
    for ax, (metric, title, subtitle) in zip(axes.ravel(), panels):
        draw_policy_panel(ax, rows, variant, metric, title, subtitle)

    display = "Zipf" if variant == "zipf" else "Hot-cold"
    path = figure_dir / f"practice2_ext_fig{'2' if variant == 'zipf' else '3'}_{variant}_repeat.png"
    save_figure(
        fig,
        path,
        f"{display} policy comparison with repeated measurements",
        "SLC ratio 10% · TLC GC Greedy fixed · bars show mean ± sample standard deviation",
    )
    return path


def workload_rows(rows: list[dict[str, float | int | str]], workload: str, policy: int) -> list[dict[str, float | int | str]]:
    if workload == "uniform":
        return select_rows(rows, "workload_sensitivity", "uniform", ratio=10, policy=policy)
    return select_rows(rows, "policy_repeat", workload, ratio=10, policy=policy)


def plot_workload_sensitivity(
    rows: list[dict[str, float | int | str]], figure_dir: Path
) -> Path | None:
    if not any(row["suite"] == "workload_sensitivity" for row in rows):
        return None
    workloads = ["uniform", "zipf", "hotcold"]
    panels = [
        ("bw_mib", "Write throughput", "Compare policies within each workload · MiB/s"),
        ("p99_us", "p99 write latency", "Compare policies within each workload · microseconds"),
        ("slc_pages_per_gib", "SLC migration cost", "Valid pages copied per written GiB"),
        ("tlc_gc_pages_per_gib", "Downstream TLC GC cost", "Valid pages copied per written GiB"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.8))
    fig.subplots_adjust(left=0.075, right=0.97, top=0.84, bottom=0.11, wspace=0.28, hspace=0.48)
    x = np.arange(4)
    width = 0.23

    for ax, (metric, title, subtitle) in zip(axes.ravel(), panels):
        style_axes(ax, title, subtitle)
        for index, workload in enumerate(workloads):
            means: list[float] = []
            stds: list[float] = []
            for policy in range(4):
                group = workload_rows(rows, workload, policy)
                if group:
                    mean, std = mean_std(group, metric)
                else:
                    mean, std = 0.0, 0.0
                means.append(mean)
                stds.append(std)
            ax.bar(
                x + (index - 1) * width,
                means,
                width,
                yerr=stds,
                capsize=2,
                color=WORKLOAD_COLORS[workload],
                label=workload.title(),
            )
        ax.set_xticks(x)
        ax.set_xticklabels(["Greedy", "Random", "FIFO", "Cost-\nBenefit"], fontsize=8.7)
        ax.margins(y=0.16)
    axes[0, 0].legend(frameon=False, ncol=3, loc="best")

    path = figure_dir / "practice2_ext_fig4_workload_sensitivity.png"
    save_figure(
        fig,
        path,
        "Migration policy sensitivity to workload locality",
        "Uniform, Zipf, and Hot-cold use ratio 10% and TLC GC Greedy; compare policies within a workload",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--figure-dir", type=Path, default=REPO_ROOT / "report" / "figures")
    parser.add_argument("--table-dir", type=Path, default=REPO_ROOT / "report" / "extended_results")
    args = parser.parse_args()

    rows = discover_runs()
    missing = sorted(expected_keys() - actual_keys(rows))
    if missing:
        print(f"Extended experiment matrix: {len(rows)}/60 runs available; {len(missing)} missing")
        for key in missing[:12]:
            print("  missing", key)
        if len(missing) > 12:
            print(f"  ... and {len(missing) - 12} more")
        if not args.allow_partial:
            print("Run the remaining experiments or pass --allow-partial for a parsing/layout check.")
            return 2

    args.figure_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    write_raw_csv(rows, args.table_dir / "practice2_extended_raw.csv")
    write_aggregate_csv(aggregate_rows(rows), args.table_dir / "practice2_extended_aggregate.csv")

    generated = [
        plot_ratio_sweep(rows, args.figure_dir),
        plot_policy_repeat(rows, "zipf", args.figure_dir),
        plot_policy_repeat(rows, "hotcold", args.figure_dir),
        plot_workload_sensitivity(rows, args.figure_dir),
    ]
    for path in generated:
        if path is not None:
            print(path)
    print(args.table_dir / "practice2_extended_raw.csv")
    print(args.table_dir / "practice2_extended_aggregate.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

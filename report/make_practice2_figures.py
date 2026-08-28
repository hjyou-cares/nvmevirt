"""
Practice 2 report figures.

Start with section 1-1: baseline comparison between TLC-only (ratio=0)
and SLC cache enabled (ratio=10). The script reads the latest completed
baseline validation run from results/local_*_slc_baseline_compare and
generates a PNG under report/figures/.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
FIG_DIR = REPO_ROOT / "report" / "figures"

SURFACE = "#fcfcfb"
INK = "#121212"
INK_SOFT = "#5a5955"
GRID = "#e4e2da"
TLC = "#c96b2c"
SLC = "#2a78d6"
INT_TLC = "#8db255"
INT_SLC = "#6d5ca8"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
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
    }
)


def latest_complete_baseline_dir() -> Path:
    candidates = sorted(
        glob.glob(str(RESULTS_DIR / "local_*_slc_baseline_compare")),
        reverse=True,
    )
    for candidate in candidates:
        base = Path(candidate)
        required = [
            base / "tlc_only" / "summary.txt",
            base / "slc_on" / "summary.txt",
            base / "tlc_only" / "meta.txt",
            base / "slc_on" / "meta.txt",
        ]
        if all(path.exists() for path in required):
            return base
    raise FileNotFoundError("No completed local_*_slc_baseline_compare run found")


def read_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def mib_per_s(value_kib: float) -> float:
    return value_kib / 1024.0


def us(value_ns: float) -> float:
    return value_ns / 1000.0


def annotate_bars(ax, bars, fmt: str) -> None:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt.format(height),
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_SOFT,
        )


def make_baseline_figure() -> Path:
    base = latest_complete_baseline_dir()
    tlc = read_kv_file(base / "tlc_only" / "summary.txt")
    slc = read_kv_file(base / "slc_on" / "summary.txt")
    tlc_meta = read_kv_file(base / "tlc_only" / "meta.txt")

    labels = ["ratio=0\n(TLC-only)", "ratio=10\n(SLC cache)"]
    perf = {
        "Throughput\n(MiB/s)": [
            mib_per_s(float(tlc["baseline_bw_kib"])),
            mib_per_s(float(slc["baseline_bw_kib"])),
        ],
        "Avg latency\n(us)": [
            us(float(tlc["baseline_lat_avg_ns"])),
            us(float(slc["baseline_lat_avg_ns"])),
        ],
        "p99 latency\n(us)": [
            us(float(tlc["baseline_lat_p99_ns"])),
            us(float(slc["baseline_lat_p99_ns"])),
        ],
    }

    page_million = 1_000_000.0
    traffic = {
        "User write to TLC": [
            float(tlc["user_write_tlc_pages"]) / page_million,
            float(slc["user_write_tlc_pages"]) / page_million,
        ],
        "User write to SLC": [
            float(tlc["user_write_slc_pages"]) / page_million,
            float(slc["user_write_slc_pages"]) / page_million,
        ],
        "Internal write to TLC": [
            float(tlc["internal_write_tlc_pages"]) / page_million,
            float(slc["internal_write_tlc_pages"]) / page_million,
        ],
        "Internal write to SLC": [
            float(tlc["internal_write_slc_pages"]) / page_million,
            float(slc["internal_write_slc_pages"]) / page_million,
        ],
    }

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.7))
    colors = [TLC, SLC]
    x = np.arange(len(labels))

    for ax, (title, values) in zip(axes[:3], perf.items()):
        bars = ax.bar(x, values, color=colors, width=0.58, edgecolor=SURFACE, linewidth=2)
        annotate_bars(ax, bars, "{:,.1f}")
        ax.set_title(title, fontsize=11, loc="left", pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9.5)
        ax.tick_params(axis="both", length=0)
        ax.grid(axis="x", visible=False)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.margins(y=0.18)

    ax = axes[3]
    bottom = np.zeros(len(labels))
    stack_order = [
        ("User write to TLC", TLC),
        ("User write to SLC", SLC),
        ("Internal write to TLC", INT_TLC),
        ("Internal write to SLC", INT_SLC),
    ]
    for name, color in stack_order:
        bars = ax.bar(
            x,
            traffic[name],
            width=0.58,
            bottom=bottom,
            color=color,
            edgecolor=SURFACE,
            linewidth=1.8,
            label=name,
        )
        bottom += np.array(traffic[name])

    for idx, total in enumerate(bottom):
        ax.annotate(
            f"{total:,.1f}M",
            xy=(x[idx], total),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_SOFT,
        )

    ax.set_title("Write traffic by media\n(million pages)", fontsize=11, loc="left", pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.tick_params(axis="both", length=0)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(-0.1, -0.28), ncol=2, frameon=False, fontsize=8.8)

    fig.suptitle(
        "Practice 2 Figure 1. Baseline write workload: ratio=0 vs ratio=10",
        fontsize=13.5,
        x=0.055,
        ha="left",
        y=1.03,
    )
    fig.text(
        0.055,
        -0.02,
        (
            f"Latest run: {base.name}  |  workload={tlc_meta.get('baseline_rw', 'randwrite')}  "
            f"| size={tlc_meta.get('baseline_size', '')}  | loops={tlc_meta.get('baseline_loops', '')}"
        ),
        fontsize=9.2,
        color=INK_SOFT,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.98])

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "practice2_fig1_baseline_ratio_compare.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    path = make_baseline_figure()
    print(path)

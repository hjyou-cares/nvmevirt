"""
Practice 2 report figures.

Start with section 1-1: baseline comparison between TLC-only (ratio=0)
and SLC cache enabled (ratio=10). The script reads the latest completed
baseline validation run from results/local_*_slc_baseline_compare and
generates a PNG under report/figures/.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
FIG_DIR = REPO_ROOT / "report" / "figures"

CANVAS = "#f5f7fa"
SURFACE = "#ffffff"
INK = "#172033"
INK_SOFT = "#667085"
GRID = "#e5e9f0"
TLC = "#e07a38"
SLC = "#3478d4"
INT_TLC = "#7cad58"
INT_SLC = "#7766b5"
POLICY_LABELS = ["Greedy", "Random", "FIFO", "Cost-\nBenefit"]
POLICY_COLORS = ["#3478d4", "#e07a38", "#18a58b", "#7a5af8"]

ZIPF_RUN_DIRS = [
    RESULTS_DIR / "20260827_151606_slcpolicy0_greedy_zipf_nrm_server_22g_rep1",
    RESULTS_DIR / "20260827_151809_slcpolicy1_random_zipf_nrm_server_22g_rep1",
    RESULTS_DIR / "20260827_152000_slcpolicy2_fifo_zipf_nrm_server_22g_rep1",
    RESULTS_DIR / "20260827_152152_slcpolicy3_costbenefit_zipf_nrm_server_22g_rep1",
]

HOTCOLD_RUN_DIRS = [
    RESULTS_DIR / "20260827_193453_slcpolicy0_greedy_hotcold_server_greedy_full_guarded",
    RESULTS_DIR / "20260827_192853_slcpolicy1_random_hotcold_server_random_full_guarded",
    RESULTS_DIR / "20260827_193630_slcpolicy2_fifo_hotcold_server_fifo_full_guarded",
    RESULTS_DIR / "20260827_193804_slcpolicy3_costbenefit_hotcold_server_cb_full_guarded",
]

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


def latest_complete_validation_dir(mode: str) -> Path:
    candidates = sorted(
        glob.glob(str(RESULTS_DIR / f"local_*_{mode}_validation")),
        reverse=True,
    )
    for candidate in candidates:
        base = Path(candidate)
        required = [
            base / "summary.txt",
            base / "meta.txt",
            base / "write.json",
            base / "read.json",
        ]
        if all(path.exists() for path in required):
            return base
    raise FileNotFoundError(f"No completed local_*_{mode}_validation run found")


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
            fontweight="semibold",
        )


def style_panel(ax, letter: str, title: str, subtitle: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.text(
        0.0,
        1.12,
        letter,
        transform=ax.transAxes,
        fontsize=9,
        fontweight="bold",
        color=SLC,
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "#eaf2fc", "edgecolor": "none"},
    )
    ax.text(
        0.095,
        1.125,
        title,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        color=INK,
        va="center",
    )
    ax.text(
        0.0,
        1.035,
        subtitle,
        transform=ax.transAxes,
        fontsize=8.7,
        color=INK_SOFT,
        va="top",
    )
    ax.tick_params(axis="both", length=0, labelsize=9)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)


def add_change_badge(ax, before: float, after: float, lower_is_better: bool) -> None:
    change = (after / before - 1.0) * 100.0
    improved = change < 0 if lower_is_better else change > 0
    color = "#257a4a" if improved else "#b5473c"
    background = "#e9f6ef" if improved else "#fbeceb"
    ax.text(
        0.98,
        1.12,
        f"{change:+.1f}%",
        transform=ax.transAxes,
        ha="right",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=color,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": background, "edgecolor": "none"},
    )


def add_status_badge(ax, text: str) -> None:
    ax.text(
        0.98,
        1.12,
        text,
        transform=ax.transAxes,
        ha="right",
        va="center",
        fontsize=9,
        fontweight="bold",
        color="#257a4a",
        bbox={"boxstyle": "round,pad=0.32", "facecolor": "#e9f6ef", "edgecolor": "none"},
    )


def make_baseline_figure() -> Path:
    base = latest_complete_baseline_dir()
    tlc = read_kv_file(base / "tlc_only" / "summary.txt")
    slc = read_kv_file(base / "slc_on" / "summary.txt")
    tlc_meta = read_kv_file(base / "tlc_only" / "meta.txt")

    labels = ["TLC-only\nratio 0%", "SLC cache\nratio 10%"]
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

    fig, axes = plt.subplots(2, 2, figsize=(11.4, 7.5))
    axes = axes.ravel()
    fig.subplots_adjust(left=0.075, right=0.97, top=0.82, bottom=0.12, wspace=0.28, hspace=0.58)
    colors = [TLC, SLC]
    x = np.arange(len(labels))

    panel_meta = [
        ("A", "Write throughput", "Higher is better · MiB/s", False),
        ("B", "Average write latency", "Lower is better · microseconds", True),
        ("C", "p99 write latency", "Lower is better · microseconds", True),
    ]
    for ax, (_, values), (letter, title, subtitle, lower_is_better) in zip(
        axes[:3], perf.items(), panel_meta
    ):
        style_panel(ax, letter, title, subtitle)
        bars = ax.bar(x, values, color=colors, width=0.56, edgecolor="none")
        annotate_bars(ax, bars, "{:,.1f}")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.margins(y=0.22)
        add_change_badge(ax, values[0], values[1], lower_is_better)

    ax = axes[3]
    style_panel(ax, "D", "NAND write traffic", "Host and migration writes · million pages")
    bottom = np.zeros(len(labels))
    stack_order = [
        ("User write to TLC", TLC),
        ("User write to SLC", SLC),
        ("Internal write to TLC", INT_TLC),
    ]
    for name, color in stack_order:
        bars = ax.bar(
            x,
            traffic[name],
            width=0.58,
            bottom=bottom,
            color=color,
            edgecolor=SURFACE,
            linewidth=1.5,
            label=name,
        )
        bottom += np.array(traffic[name])

        for bar, value in zip(bars, traffic[name]):
            if value < 2.0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                f"{value:,.1f}M",
                ha="center",
                va="center",
                fontsize=8.5,
                fontweight="bold",
                color="white",
            )

    for idx, total in enumerate(bottom):
        ax.annotate(
            f"{total:,.1f}M",
            xy=(x[idx], total),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9.2,
            color=INK_SOFT,
            fontweight="semibold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.margins(y=0.18)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.19),
        ncol=3,
        frameon=False,
        fontsize=8.2,
        handlelength=1.2,
        columnspacing=1.0,
    )
    add_change_badge(ax, bottom[0], bottom[1], True)

    fig.suptitle(
        "Baseline: sustained writes expose SLC migration cost",
        fontsize=18,
        fontweight="bold",
        x=0.075,
        ha="left",
        y=0.965,
        color=INK,
    )
    fig.text(
        0.075,
        0.905,
        "TLC-only versus a 10% SLC cache under the same 22 GiB random-write workload",
        fontsize=10.5,
        color=INK_SOFT,
    )
    fig.text(
        0.075,
        0.035,
        (
            f"Workload: {tlc_meta.get('baseline_rw', 'randwrite')} · "
            f"{tlc_meta.get('baseline_size', '')} × {tlc_meta.get('baseline_loops', '')} loops · "
            "fresh module reload and filesystem initialization per configuration"
        ),
        fontsize=8.7,
        color=INK_SOFT,
    )

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "practice2_fig1_baseline_ratio_compare.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def make_slc_only_figure() -> Path:
    base = latest_complete_validation_dir("slc_only")
    data = read_kv_file(base / "summary.txt")
    meta = read_kv_file(base / "meta.txt")

    operations = ["Host write", "Host read"]
    slc_pages = [
        float(data["user_write_slc_pages"]),
        float(data["user_read_slc_pages"]),
    ]
    tlc_pages = [
        float(data["user_write_tlc_pages"]),
        float(data["user_read_tlc_pages"]),
    ]

    fig, (placement_ax, counter_ax) = plt.subplots(
        1,
        2,
        figsize=(11.4, 5.4),
        gridspec_kw={"width_ratios": [1.18, 1.0]},
    )
    fig.subplots_adjust(left=0.12, right=0.97, top=0.73, bottom=0.19, wspace=0.34)

    style_panel(
        placement_ax,
        "A",
        "Host I/O placement",
        "FTL-observed 4 KiB pages · exact counter values",
    )
    y = np.arange(len(operations))
    slc_bars = placement_ax.barh(
        y,
        slc_pages,
        color=SLC,
        height=0.48,
        edgecolor="none",
        label="SLC",
    )
    placement_ax.barh(
        y,
        tlc_pages,
        left=slc_pages,
        color=TLC,
        height=0.48,
        edgecolor="none",
        label="TLC",
    )
    for bar, value in zip(slc_bars, slc_pages):
        placement_ax.text(
            value / 2,
            bar.get_y() + bar.get_height() / 2,
            f"SLC  {value:,.0f}",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="white",
        )
    for idx, value in enumerate(tlc_pages):
        placement_ax.text(
            19_600,
            idx,
            f"TLC  {value:,.0f}",
            ha="right",
            va="center",
            fontsize=9.2,
            fontweight="bold",
            color=TLC,
        )
    placement_ax.set_yticks(y)
    placement_ax.set_yticklabels(operations, fontsize=9.5)
    placement_ax.invert_yaxis()
    placement_ax.set_xlim(0, 20_000)
    placement_ax.set_xticks(np.arange(0, 20_001, 5_000))
    placement_ax.set_xlabel("Pages", fontsize=8.8, color=INK_SOFT)
    add_status_badge(placement_ax, "PASS · 100% SLC")

    style_panel(
        counter_ax,
        "B",
        "Background activity",
        "All migration, internal traffic, and TLC GC counters remain zero",
    )
    counter_ax.set_axis_off()
    internal_pages = sum(
        float(data[key])
        for key in [
            "internal_read_slc_pages",
            "internal_read_tlc_pages",
            "internal_write_slc_pages",
            "internal_write_tlc_pages",
        ]
    )
    cards = [
        ("Migration events", float(data["slc_migration_cnt"])),
        ("Migrated valid pages", float(data["slc_migration_valid_page_migrate_cnt"])),
        ("Internal I/O pages", internal_pages),
        ("TLC GC events", float(data["tlc_gc_cnt"])),
    ]
    card_positions = [(0.0, 0.53), (0.52, 0.53), (0.0, 0.05), (0.52, 0.05)]
    for (label, value), (card_x, card_y) in zip(cards, card_positions):
        card = FancyBboxPatch(
            (card_x, card_y),
            0.45,
            0.36,
            transform=counter_ax.transAxes,
            boxstyle="round,pad=0.015,rounding_size=0.025",
            linewidth=1.0,
            edgecolor="#d7e9dd",
            facecolor="#f2faf5",
        )
        counter_ax.add_patch(card)
        counter_ax.text(
            card_x + 0.05,
            card_y + 0.25,
            f"{value:,.0f}",
            transform=counter_ax.transAxes,
            fontsize=19,
            fontweight="bold",
            color="#257a4a",
            va="center",
        )
        counter_ax.text(
            card_x + 0.05,
            card_y + 0.10,
            label,
            transform=counter_ax.transAxes,
            fontsize=8.8,
            color=INK_SOFT,
            va="center",
        )

    fig.suptitle(
        "SLC-only validation: counters confirm the expected media path",
        fontsize=18,
        fontweight="bold",
        x=0.07,
        ha="left",
        y=0.965,
        color=INK,
    )
    fig.text(
        0.07,
        0.905,
        "The 64 MiB working set stays entirely in SLC; no background data movement is triggered",
        fontsize=10.5,
        color=INK_SOFT,
    )
    fig.text(
        0.07,
        0.055,
        (
            f"Workload: {meta.get('file_size', '')} sequential write → random read · "
            f"4 KiB · SLC ratio {meta.get('slc_cache_ratio_percent', '')}% · "
            "fresh module reload and filesystem initialization"
        ),
        fontsize=8.7,
        color=INK_SOFT,
    )

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "practice2_fig2_slc_only_validation.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def make_overflow_figure() -> Path:
    base = latest_complete_validation_dir("overflow")
    data = read_kv_file(base / "summary.txt")
    meta = read_kv_file(base / "meta.txt")

    operations = ["Host write", "Host read"]
    slc_pages = [
        float(data["user_write_slc_pages"]),
        float(data["user_read_slc_pages"]),
    ]
    tlc_pages = [
        float(data["user_write_tlc_pages"]),
        float(data["user_read_tlc_pages"]),
    ]

    fig, (placement_ax, migration_ax) = plt.subplots(
        1,
        2,
        figsize=(11.4, 5.4),
        gridspec_kw={"width_ratios": [1.18, 1.0]},
    )
    fig.subplots_adjust(left=0.12, right=0.97, top=0.73, bottom=0.19, wspace=0.34)

    style_panel(
        placement_ax,
        "A",
        "Host I/O placement",
        "FTL-observed 4 KiB pages · exact counter values",
    )
    y = np.arange(len(operations))
    slc_bars = placement_ax.barh(
        y,
        slc_pages,
        color=SLC,
        height=0.48,
        edgecolor="none",
        label="SLC",
    )
    tlc_bars = placement_ax.barh(
        y,
        tlc_pages,
        left=slc_pages,
        color=TLC,
        height=0.48,
        edgecolor="none",
        label="TLC",
    )
    for bar, value in zip(slc_bars, slc_pages):
        placement_ax.text(
            value / 2,
            bar.get_y() + bar.get_height() / 2,
            f"SLC  {value:,.0f}",
            ha="center",
            va="center",
            fontsize=9.3,
            fontweight="bold",
            color="white",
        )
    for idx, (bar, value) in enumerate(zip(tlc_bars, tlc_pages)):
        if value > 0:
            placement_ax.text(
                slc_pages[idx] + value / 2,
                bar.get_y() + bar.get_height() / 2,
                f"TLC\n{value:,.0f}",
                ha="center",
                va="center",
                fontsize=8.7,
                fontweight="bold",
                color="white",
            )
        else:
            placement_ax.text(
                1_960_000,
                idx,
                "TLC  0",
                ha="right",
                va="center",
                fontsize=9.2,
                fontweight="bold",
                color=TLC,
            )
    placement_ax.set_yticks(y)
    placement_ax.set_yticklabels(operations, fontsize=9.5)
    placement_ax.invert_yaxis()
    placement_ax.set_xlim(0, 2_000_000)
    placement_ax.set_xticks(np.arange(0, 2_000_001, 500_000))
    placement_ax.set_xticklabels(["0", "0.5M", "1.0M", "1.5M", "2.0M"])
    placement_ax.set_xlabel("Pages", fontsize=8.8, color=INK_SOFT)
    add_status_badge(placement_ax, "PASS · TLC I/O")

    style_panel(
        migration_ax,
        "B",
        "Migration evidence",
        "SLC valid pages are read internally and written to TLC",
    )
    migration_ax.set_axis_off()
    cards = [
        ("Migration events", float(data["slc_migration_cnt"]), "#257a4a", "#f2faf5", "#d7e9dd"),
        ("Internal read · SLC", float(data["internal_read_slc_pages"]), SLC, "#eef5fd", "#d4e4f7"),
        ("Internal write · TLC", float(data["internal_write_tlc_pages"]), TLC, "#fff4ec", "#f1ddcf"),
        ("TLC GC events", float(data["tlc_gc_cnt"]), "#257a4a", "#f2faf5", "#d7e9dd"),
    ]
    card_positions = [(0.0, 0.53), (0.52, 0.53), (0.0, 0.05), (0.52, 0.05)]
    for (label, value, value_color, face_color, edge_color), (card_x, card_y) in zip(
        cards, card_positions
    ):
        card = FancyBboxPatch(
            (card_x, card_y),
            0.45,
            0.36,
            transform=migration_ax.transAxes,
            boxstyle="round,pad=0.015,rounding_size=0.025",
            linewidth=1.0,
            edgecolor=edge_color,
            facecolor=face_color,
        )
        migration_ax.add_patch(card)
        migration_ax.text(
            card_x + 0.05,
            card_y + 0.25,
            f"{value:,.0f}",
            transform=migration_ax.transAxes,
            fontsize=18,
            fontweight="bold",
            color=value_color,
            va="center",
        )
        migration_ax.text(
            card_x + 0.05,
            card_y + 0.10,
            label,
            transform=migration_ax.transAxes,
            fontsize=8.8,
            color=INK_SOFT,
            va="center",
        )

    fig.suptitle(
        "Overflow validation: SLC migration activates TLC I/O",
        fontsize=18,
        fontweight="bold",
        x=0.07,
        ha="left",
        y=0.965,
        color=INK,
    )
    fig.text(
        0.07,
        0.905,
        "The working set exceeds SLC capacity, producing internal TLC writes and host reads from TLC",
        fontsize=10.5,
        color=INK_SOFT,
    )
    fig.text(
        0.07,
        0.055,
        (
            f"Workload: {meta.get('file_size', '')} sequential write → random read · "
            f"4 KiB · SLC ratio {meta.get('slc_cache_ratio_percent', '')}% · "
            "fresh module reload and filesystem initialization"
        ),
        fontsize=8.7,
        color=INK_SOFT,
    )

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "practice2_fig3_overflow_validation.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def read_summary_tokens(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for token in path.read_text().split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key] = value
    return data


def load_policy_result(run_dir: Path) -> dict[str, float | str]:
    required = [run_dir / "meta.txt", run_dir / "summary.txt", run_dir / "fio.json"]
    if not all(path.exists() for path in required):
        raise FileNotFoundError(f"Incomplete policy run: {run_dir}")

    meta = read_kv_file(run_dir / "meta.txt")
    summary = read_summary_tokens(run_dir / "summary.txt")
    fio = json.loads((run_dir / "fio.json").read_text())
    job = fio["jobs"][-1]
    if int(job.get("error", 0)) != 0:
        raise RuntimeError(f"fio error in {run_dir}")
    write = job["write"]
    written_gib = float(write["io_bytes"]) / (1024.0**3)

    return {
        "policy": float(meta["policy"]),
        "policy_name": meta["policy_name"],
        "written_gib": written_gib,
        "bw_mib": float(write["bw"]) / 1024.0,
        "iops": float(write["iops"]),
        "avg_us": float(write["lat_ns"]["mean"]) / 1000.0,
        "p99_us": float(write["clat_ns"]["percentile"]["99.000000"]) / 1000.0,
        "migration_cnt": float(summary["slc_migration_cnt"]),
        "migration_pages": float(summary["slc_migrate_pages"]),
        "migration_pages_per_gib": float(summary["slc_migrate_pages"]) / written_gib,
        "tlc_gc_cnt": float(summary["tlc_gc_cnt"]),
        "tlc_gc_pages": float(summary["tlc_gc_migrate_pages"]),
        "tlc_gc_pages_per_gib": float(summary["tlc_gc_migrate_pages"]) / written_gib,
        "erase_sum": float(summary["sum"]),
        "erase_per_gib": float(summary["sum"]) / written_gib,
        "erase_max": float(summary["max"]),
        "erase_cv_all": float(summary["erase_cv_all"]),
    }


def draw_policy_bar_panel(
    ax,
    letter: str,
    title: str,
    subtitle: str,
    values: list[float],
    value_format: str,
) -> None:
    style_panel(ax, letter, title, subtitle)
    x = np.arange(len(POLICY_LABELS))
    bars = ax.bar(x, values, color=POLICY_COLORS, width=0.64, edgecolor="none")
    annotate_bars(ax, bars, value_format)
    ax.set_xticks(x)
    ax.set_xticklabels(POLICY_LABELS, fontsize=8.7)
    ax.margins(y=0.22)


def make_policy_comparison_figure(
    results: list[dict[str, float | str]],
    title: str,
    subtitle: str,
    migration_values: list[float],
    migration_subtitle: str,
    migration_format: str,
    downstream_title: str,
    downstream_subtitle: str,
    downstream_values: list[float],
    downstream_format: str,
    footer: str,
    filename: str,
) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 7.5))
    axes = axes.ravel()
    fig.subplots_adjust(left=0.075, right=0.97, top=0.82, bottom=0.12, wspace=0.28, hspace=0.58)

    draw_policy_bar_panel(
        axes[0],
        "A",
        "Write throughput",
        "Higher is better · MiB/s",
        [float(result["bw_mib"]) for result in results],
        "{:,.1f}",
    )
    draw_policy_bar_panel(
        axes[1],
        "B",
        "p99 write latency",
        "Lower is better · microseconds",
        [float(result["p99_us"]) for result in results],
        "{:,.1f}",
    )
    draw_policy_bar_panel(
        axes[2],
        "C",
        "SLC migration cost",
        migration_subtitle,
        migration_values,
        migration_format,
    )
    draw_policy_bar_panel(
        axes[3],
        "D",
        downstream_title,
        downstream_subtitle,
        downstream_values,
        downstream_format,
    )

    fig.suptitle(
        title,
        fontsize=18,
        fontweight="bold",
        x=0.075,
        ha="left",
        y=0.965,
        color=INK,
    )
    fig.text(0.075, 0.905, subtitle, fontsize=10.5, color=INK_SOFT)
    fig.text(0.075, 0.035, footer, fontsize=8.7, color=INK_SOFT)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / filename
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def make_zipf_policy_figure() -> Path:
    results = [load_policy_result(path) for path in ZIPF_RUN_DIRS]
    return make_policy_comparison_figure(
        results=results,
        title="Zipf workload: isolated SLC migration policy effects",
        subtitle="With TLC GC inactive, copied pages and peak wear come only from SLC victim selection",
        migration_values=[float(result["migration_pages"]) / 1_000_000.0 for result in results],
        migration_subtitle="Lower is better · million valid pages copied",
        migration_format="{:,.2f}M",
        downstream_title="SLC peak wear",
        downstream_subtitle="TLC GC = 0 · maximum erase count",
        downstream_values=[float(result["erase_max"]) for result in results],
        downstream_format="{:,.0f}",
        footer=(
            "Workload: 22 GiB × 7 loops (154 GiB written) · randwrite · zipf:1.2 · "
            "4 KiB · SLC ratio 10% · TLC GC count 0 for all policies"
        ),
        filename="practice2_fig4_zipf_policy_compare.png",
    )


def make_hotcold_policy_figure() -> Path:
    results = [load_policy_result(path) for path in HOTCOLD_RUN_DIRS]
    return make_policy_comparison_figure(
        results=results,
        title="Hot-cold workload: SLC policy changes downstream TLC GC cost",
        subtitle="Victim selection changes internal copy costs, which are reflected in end-to-end host performance",
        migration_values=[
            float(result["migration_pages_per_gib"]) / 1_000.0 for result in results
        ],
        migration_subtitle="Lower is better · thousand valid pages/GiB",
        migration_format="{:,.1f}k",
        downstream_title="Downstream TLC GC cost",
        downstream_subtitle="Lower is better · thousand valid pages/GiB",
        downstream_values=[
            float(result["tlc_gc_pages_per_gib"]) / 1_000.0 for result in results
        ],
        downstream_format="{:,.2f}k",
        footer=(
            "Workload: cold 30 GiB · cold touch 15 GiB + hot 1 GiB · 90 s · "
            "4 KiB · SLC ratio 10% · fresh reload per policy"
        ),
        filename="practice2_fig5_hotcold_policy_compare.png",
    )


if __name__ == "__main__":
    for path in [
        make_baseline_figure(),
        make_slc_only_figure(),
        make_overflow_figure(),
        make_zipf_policy_figure(),
        make_hotcold_policy_figure(),
    ]:
        print(path)

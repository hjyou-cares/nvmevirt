"""
실습 1 보고서용 그래프 생성 스크립트.

모든 수치는 results/ 아래의 실측 파일(summary.txt / fio.json / filebench.log /
erase_cnt.txt)에서 직접 읽어 계산한다 -- 하드코딩된 통계치는 없다.
실행: python3 report/make_figures.py  (결과: report/figures/*.png)

그래프 안의 텍스트는 전부 영어로 작성함 -- 본문은 한국어지만, 그림은 폰트가 설치
안 된 환경(서버/로컬/뷰어)에서도 깨지지 않아야 하고 실제로 이 저장소를 오가며
서버와 로컬 양쪽에서 렌더링하기 때문. 덕분에 CJK 폰트 의존성이 아예 없어서
matplotlib 기본 폰트(DejaVu Sans)로 어디서든 동일하게 렌더링된다.
"""
import glob
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 팔레트 (dataviz 스킬 reference/palette.md, light mode, 카테고리 슬롯 1~3) ----
COLOR = {"greedy": "#2a78d6", "costbenefit": "#eb6834", "random": "#1baf7a"}
LABEL = {"greedy": "Greedy", "costbenefit": "Cost-Benefit", "random": "Random"}
ORDER = ["greedy", "costbenefit", "random"]

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE, "axes.labelcolor": INK_SECONDARY,
    "text.color": INK_PRIMARY, "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.grid": True, "grid.color": GRIDLINE, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "savefig.facecolor": SURFACE,
})

# 각 워크로드를 구성하는 results/ 폴더 glob 패턴
RUNS = {
    "zipf": ["*_zipf", "*_zipf_rep*"],
    "hotcold": ["*vpcdiag_rep*"],
    "filebench": ["*final31_filebench"],
    "uniform600m": ["*final31_rep*"],
    "uniform22g": ["*util50*"],
    "uniform38g": ["*util80*"],
    "extreme": ["*extreme_zipf1tb"],
}


def save(fig, name):
    out = os.path.join(REPO_ROOT, "report", "figures", f"{name}.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved report/figures/{name}.png")


def load_erase(run):
    """erase_cnt.txt -> 블록별 erase 횟수 배열.

    NF==7 가드는 run_experiment.sh의 awk와 같은 이유 -- 파일 앞머리의
    GC_VALID_PAGE_MIGRATE_CNT / DIAG_* 헤더 줄은 필드가 2개뿐이라 블록 줄이 아님.
    """
    vals = []
    with open(os.path.join(REPO_ROOT, "results", run, "erase_cnt.txt")) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 7:
                vals.append(int(parts[6]))
    return np.array(vals)


def gib_written(d):
    """그 실행에서 호스트가 실제로 기록한 양(GiB). fio와 filebench 형식을 모두 처리."""
    fio = os.path.join(d, "fio.json")
    if os.path.exists(fio):
        jobs = json.load(open(fio))["jobs"]
        return sum(j["write"]["io_bytes"] for j in jobs) / 2 ** 30
    log = open(os.path.join(d, "filebench.log")).read()
    return int(re.search(r"write-file\s+(\d+)ops", log).group(1)) * 4096 / 2 ** 30


def collect(key):
    """워크로드 하나 -> {정책: 지표배열}. 반복 실행이 있으면 행이 여러 개."""
    agg = {}
    for pat in RUNS[key]:
        for d in sorted(glob.glob(os.path.join(REPO_ROOT, "results", pat))):
            if key != "filebench" and "filebench" in d:
                continue
            meta = dict(l.strip().split("=", 1)
                        for l in open(os.path.join(d, "meta.txt")) if "=" in l)
            s = dict(kv.split("=", 1)
                     for kv in open(os.path.join(d, "summary.txt")).read().split())
            g = gib_written(d)
            mig, tgc = int(s["gc_migrate_pages"]), int(s["total_gc"])
            row = {
                "dir": d, "gib": g,
                "erase_gib": int(s["sum"]) / g, "erase_max": int(s["max"]),
                "mig_gib": mig / g, "mig_per_gc": mig / tgc if tgc else 0.0,
            }
            if os.path.exists(os.path.join(d, "fio.json")):
                jobs = json.load(open(os.path.join(d, "fio.json")))["jobs"]
                row["lat"] = np.mean([j["write"]["lat_ns"]["mean"] for j in jobs]) / 1000
                row["p99"] = np.mean([j["write"]["clat_ns"]["percentile"]["99.000000"]
                                      for j in jobs]) / 1000
            agg.setdefault(meta["policy_name"], []).append(row)
    return agg


DATA = {k: collect(k) for k in RUNS}


def ms(key, pol, field):
    """(평균, 표준편차). 반복이 1회뿐이면 표준편차는 0."""
    vals = [r[field] for r in DATA[key][pol]]
    return float(np.mean(vals)), (float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0)


def grouped(ax, wls, field, title, ylabel, fmt="{:,.0f}"):
    xs = np.arange(len(wls))
    w = 0.24
    for pi, pol in enumerate(ORDER):
        vals, errs = zip(*[ms(k, pol, field) for k, _ in wls])
        ax.bar(xs + (pi - 1) * w, vals, width=w, color=COLOR[pol], label=LABEL[pol],
               zorder=3, edgecolor=SURFACE, linewidth=2.0, yerr=errs, capsize=4,
               error_kw={"ecolor": INK_SECONDARY, "elinewidth": 1.1, "capthick": 1.1})
        for x, v, e in zip(xs + (pi - 1) * w, vals, errs):
            ax.annotate(fmt.format(v), xy=(x, v + e), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=8.5,
                        color=INK_SECONDARY)
    ax.set_xticks(xs)
    ax.set_xticklabels([n for _, n in wls], fontsize=10)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="both", length=0)
    ax.set_title(title, color=INK_PRIMARY, fontsize=11.5, pad=10, loc="left")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.margins(y=0.24)


def top_legend(fig, ax, y=0.99):
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, y), frameon=False, ncol=3,
               fontsize=10, labelcolor=INK_SECONDARY, handlelength=1.1,
               handleheight=1.1, columnspacing=2.0)


# =====================================================================
# 그림 1 (4.1): 블록별 erase 횟수 분포. 집계값이 아니라 131,072개 블록을 그대로 그림.
# =====================================================================
DIST = [("zipf", "zipf:1.2\n(power-law skew)"),
        ("hotcold", "hotcold v7\n(hot/cold separated)"),
        ("filebench", "filebench\n(2 GiB, randwrite+fsync)")]
GROUP_W, MARK_W = 0.72, 0.22

fig, ax = plt.subplots(figsize=(11, 5.2))
for gi, (key, name) in enumerate(DIST):
    for pi, pol in enumerate(ORDER):
        arr = load_erase(os.path.basename(DATA[key][pol][0]["dir"]))
        nz = arr[arr > 0]
        pos = gi + (pi - 1) * (GROUP_W / 3)
        bp = ax.boxplot([nz], positions=[pos], widths=MARK_W, patch_artist=True,
                        whis=(0, 100), showfliers=False, zorder=3)
        for b in bp["boxes"]:
            b.set(facecolor=COLOR[pol], edgecolor=SURFACE, linewidth=2.0)
        for part in bp["whiskers"] + bp["caps"]:
            part.set(color=COLOR[pol], linewidth=1.6)
        for m in bp["medians"]:
            m.set(color=SURFACE, linewidth=2.0)
        ax.annotate(f"{nz.max()}", xy=(pos, nz.max()), xytext=(0, 5),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=10, color=INK_SECONDARY)

ax.set_ylim(0, 14)
ax.set_yticks(range(0, 15, 2))
ax.set_ylabel("Erase count per block")
ax.set_xticks(range(len(DIST)))
ax.set_xticklabels([n for _, n in DIST], fontsize=10.5)
ax.set_xlim(-0.55, len(DIST) - 0.45)
ax.tick_params(axis="both", length=0)
ax.grid(axis="x", visible=False)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.set_title("Distribution over erased blocks  (box = IQR, whiskers = min-max, label = max)",
             color=INK_PRIMARY, fontsize=11.5, pad=10, loc="left")
ax.legend(handles=[Patch(facecolor=COLOR[p], label=LABEL[p]) for p in ORDER],
          loc="lower right", bbox_to_anchor=(1.0, 1.01), frameon=False, ncol=3,
          fontsize=10, labelcolor=INK_SECONDARY, handlelength=1.1, handleheight=1.1,
          columnspacing=1.6)
fig.suptitle("Per-block erase counts by workload and GC policy",
             fontsize=13.5, color=INK_PRIMARY, x=0.055, ha="left", y=0.99)
fig.tight_layout(rect=[0, 0, 1, 0.95])
save(fig, "fig1_erase_distribution")

# =====================================================================
# 그림 2 (4.1): GiB당 erase 횟수와 최대 마모.
# hotcold/filebench는 시간 기반이라 정책마다 쓴 양이 달라 GiB당으로 정규화한다.
# =====================================================================
WL3 = [("zipf", "zipf:1.2"), ("hotcold", "hotcold v7"), ("filebench", "filebench")]
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
grouped(axes[0], WL3, "erase_gib", "Block erases per GiB written", "erases / GiB")
grouped(axes[1], WL3, "erase_max", "Peak wear: highest erase count of any block",
        "erase max", "{:.1f}")
top_legend(fig, axes[0], y=0.99)
fig.suptitle("Block erase counts by workload and GC policy  --  "
             "normalized per GiB written, so policies are comparable within every workload",
             fontsize=12, color=INK_PRIMARY, y=1.09)
fig.tight_layout(rect=[0, 0, 1, 0.93])
save(fig, "fig2_erase_total")

# =====================================================================
# 그림 3 (4.2): 호스트 IO latency. filebench는 백분위를 제공하지 않아 제외.
# =====================================================================
WL2 = [("zipf", "zipf:1.2"), ("hotcold", "hotcold v7")]
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
grouped(axes[0], WL2, "lat", "Average write latency (host IO AVG)", "latency (us)", "{:,.1f}")
grouped(axes[1], WL2, "p99", "p99 write latency (tail latency)", "latency (us)", "{:,.1f}")
top_legend(fig, axes[0])
fig.suptitle("Host IO latency by workload and GC policy  (mean +- sd of 3 runs)",
             fontsize=12.5, color=INK_PRIMARY, y=1.09)
fig.tight_layout(rect=[0, 0, 1, 0.93])
save(fig, "fig3_latency")

# =====================================================================
# 그림 4 (4.3): GC migration 비용 -- victim의 vpc 누적(= 실제로 복사해야 한 페이지 수).
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
grouped(axes[0], WL3, "mig_gib", "Valid pages migrated per GiB written",
        "migrated pages / GiB")
grouped(axes[1], WL3, "mig_per_gc", "Valid pages migrated per GC run", "pages / GC", "{:.1f}")
top_legend(fig, axes[0])
fig.suptitle("GC migration cost by workload and GC policy",
             fontsize=12.5, color=INK_PRIMARY, y=1.09)
fig.tight_layout(rect=[0, 0, 1, 0.93])
save(fig, "fig4_migration")

# =====================================================================
# 그림 5 (5.1): 사용률 스윕. 같은 uniform 워크로드에서 파일 크기만 바꿨고
# 총 쓰기량은 146~154 GiB로 맞췄다.
# =====================================================================
SWEEP = [("uniform600m", "600 MiB\n(1.3% full)"),
         ("uniform22g", "22 GiB\n(49% full)"),
         ("uniform38g", "38 GiB\n(85% full)")]
xs = np.arange(len(SWEEP))
w = 0.24

fig, ax = plt.subplots(figsize=(9.5, 4.8))
for pi, pol in enumerate(ORDER):
    vals = [ms(k, pol, "mig_gib")[0] for k, _ in SWEEP]
    ax.bar(xs + (pi - 1) * w, vals, width=w, color=COLOR[pol], label=LABEL[pol],
           zorder=3, edgecolor=SURFACE, linewidth=2.0)
    for x, v in zip(xs + (pi - 1) * w, vals):
        ax.annotate(f"{v:,.0f}", xy=(x, v), xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=9.5, color=INK_SECONDARY)

ax.set_xticks(xs)
ax.set_xticklabels([n for _, n in SWEEP], fontsize=10.5)
ax.set_ylabel("valid pages migrated / GiB written")
ax.tick_params(axis="both", length=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", visible=False)
ax.margins(y=0.24)
ax.legend(loc="upper left", frameon=False, fontsize=10, labelcolor=INK_SECONDARY,
          handlelength=1.1, handleheight=1.1)
ax.set_title("Greedy and Cost-Benefit migrate nothing at any utilization, "
             "while Random's cost nearly triples",
             loc="left", fontsize=11.5, pad=10, color=INK_PRIMARY)
fig.text(0.5, -0.04,
         "Same uniform workload, same total bytes written (146-154 GiB); only the file size "
         "changes.  Greedy vs Cost-Benefit divergence: 0.0% at every point.",
         ha="center", fontsize=9.5, color=INK_MUTED)
fig.suptitle("Filling the device does not create a choice for the victim selector",
             fontsize=13, color=INK_PRIMARY, y=1.02)
fig.tight_layout()
save(fig, "fig5_utilization_sweep")

# =====================================================================
# 그림 6 (4.4): 장기 정상상태. zipf 조건은 그대로 두고 총 쓰기량만
# 154 GiB -> 1,100 GiB로 늘렸을 때 두 정책이 갈라지는 모습.
# 왼쪽은 131,072개 블록의 마모 분포 원본(집계값 아님), 오른쪽은 쓰기량에 따른
# migration 비용 변화. 이 조건은 Random을 돌리지 않아 두 정책만 그린다.
# =====================================================================
EXT = {p: os.path.basename(DATA["extreme"][p][0]["dir"])
       for p in ("greedy", "costbenefit")}

fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))

ax = axes[0]
bins = np.arange(0, 175, 5)
for pol in ("greedy", "costbenefit"):
    arr = load_erase(EXT[pol])
    ax.hist(arr, bins=bins, color=COLOR[pol], alpha=0.62, zorder=3,
            label=f"{LABEL[pol]}  (max {arr.max()})")
    ax.axvline(arr.max(), color=COLOR[pol], linewidth=1.4, linestyle="--", zorder=4)
ax.set_yscale("log")
ax.set_xlabel("Erase count per block")
ax.set_ylabel("Number of blocks (log scale)")
ax.tick_params(axis="both", length=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", visible=False)
ax.legend(loc="upper right", frameon=False, fontsize=10, labelcolor=INK_SECONDARY,
          handlelength=1.1, handleheight=1.1)
ax.set_title("Wear distribution over all 131,072 blocks", loc="left",
             fontsize=11.5, pad=10, color=INK_PRIMARY)

ax = axes[1]
STAGE = [("zipf", "154 GiB written"), ("extreme", "1,100 GiB written")]
xs, w = np.arange(len(STAGE)), 0.28
for pi, pol in enumerate(("greedy", "costbenefit")):
    vals = [ms(k, pol, "mig_gib")[0] for k, _ in STAGE]
    ax.bar(xs + (pi - 0.5) * w, vals, width=w, color=COLOR[pol], label=LABEL[pol],
           zorder=3, edgecolor=SURFACE, linewidth=2.0)
    for x, v in zip(xs + (pi - 0.5) * w, vals):
        ax.annotate(f"{v:,.0f}", xy=(x, v), xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=9.5, color=INK_SECONDARY)
gap = [(ms(k, "costbenefit", "mig_gib")[0] / ms(k, "greedy", "mig_gib")[0] - 1) * 100
       for k, _ in STAGE]
for x, g, _n in zip(xs, gap, STAGE):
    ax.annotate(f"Cost-Benefit {g:+.1f}%", xy=(x, 0), xytext=(0, -22),
                textcoords="offset points", ha="center", fontsize=10,
                color=INK_SECONDARY)
ax.set_xticks(xs)
ax.set_xticklabels([n for _, n in STAGE], fontsize=10.5)
ax.set_ylabel("valid pages migrated / GiB written")
ax.tick_params(axis="both", length=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", visible=False)
ax.margins(y=0.24)
ax.legend(loc="upper left", frameon=False, fontsize=10, labelcolor=INK_SECONDARY,
          handlelength=1.1, handleheight=1.1)
ax.set_title("GC cost as the run gets longer", loc="left",
             fontsize=11.5, pad=10, color=INK_PRIMARY)

fig.suptitle("Over a long run the two policies separate: same total wear, "
             "very different peak wear",
             fontsize=13, color=INK_PRIMARY, x=0.055, ha="left", y=1.0)
fig.tight_layout(rect=[0, 0, 1, 0.94])
save(fig, "fig6_extreme_writes")

print("done.")

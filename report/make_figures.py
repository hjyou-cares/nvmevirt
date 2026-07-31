"""
실습 1 보고서용 그래프 생성 스크립트.
가능한 한 raw 반복측정값에서 직접 mean/stdev를 계산 (하드코딩된 통계치 최소화).
데이터 출처: CLAUDE.md / EXPERIMENT_LOG.md 2026-07-30~31 항목, results/*.
실행: python3 report/make_figures.py  (결과: report/figures/*.png)

그래프 안의 텍스트는 전부 영어로 작성함 -- 본문은 한국어지만, 그림은 폰트가 설치
안 된 환경(서버/로컬/뷰어)에서도 깨지지 않아야 하고 실제로 이 저장소를 오가며
서버와 로컬 양쪽에서 렌더링하기 때문. 덕분에 CJK 폰트 의존성이 아예 없어서
matplotlib 기본 폰트(DejaVu Sans)로 어디서든 동일하게 렌더링된다.
"""
import glob
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL_BLOCKS = 131072  # 8ch x 4partition topology, 고정값 (memmap 크기와 무관)

# ---- 팔레트 (dataviz 스킬 reference/palette.md, light mode, 카테고리 슬롯 1~3) ----
COLOR = {
    "greedy": "#2a78d6",       # slot 1: blue
    "costbenefit": "#eb6834",  # slot 2: orange
    "random": "#1baf7a",       # slot 3: aqua
}
LABEL = {"greedy": "Greedy", "costbenefit": "Cost-Benefit", "random": "Random"}
ORDER = ["greedy", "costbenefit", "random"]

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK_PRIMARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "axes.grid": True,
    "grid.color": GRIDLINE,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "savefig.facecolor": SURFACE,
})


def stats(d):
    """dict[key] -> list of reps  =>  (mean dict, stdev dict)"""
    mean = {k: float(np.mean(v)) for k, v in d.items()}
    std = {k: (float(np.std(v, ddof=1)) if len(v) > 1 else 0.0) for k, v in d.items()}
    return mean, std


def bar_panel(ax, values, errs, title, ylabel, value_fmt="{:.0f}"):
    x = np.arange(len(ORDER))
    heights = [values[k] for k in ORDER]
    errors = [errs[k] for k in ORDER] if errs else None
    colors = [COLOR[k] for k in ORDER]
    bars = ax.bar(x, heights, color=colors, width=0.6, zorder=3,
                   yerr=errors, capsize=5,
                   error_kw={"ecolor": INK_SECONDARY, "elinewidth": 1.2, "capthick": 1.2})
    ax.set_xticks(x)
    ax.set_xticklabels([LABEL[k] for k in ORDER])
    ax.set_ylabel(ylabel)
    ax.set_title(title, color=INK_PRIMARY, fontsize=12, pad=10, loc="left")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", visible=False)
    for rect, k in zip(bars, ORDER):
        h = rect.get_height()
        err = errs[k] if errs else 0
        ax.annotate(value_fmt.format(h),
                    xy=(rect.get_x() + rect.get_width() / 2, h + err),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, color=INK_SECONDARY)
    ax.margins(y=0.20)


def save(fig, name):
    fig.tight_layout()
    out = os.path.join(REPO_ROOT, "report", "figures", f"{name}.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved report/figures/{name}.png")


def load_erase(run):
    """results/<run>/erase_cnt.txt -> 블록별 erase 횟수 배열.

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


# =====================================================================
# raw 데이터 (results/*_vpcdiag_rep{1,2,3}/summary.txt + fio.json, 2026-07-30 밤)
# =====================================================================
GiB = {
    "greedy": [165.5386619567871, 166.92438888549805, 167.50824356079102],
    "costbenefit": [158.60545349121094, 160.50725173950195, 159.83475875854492],
    "random": [101.82323455810547, 102.33063507080078, 101.75477981567383],
}
migrate_raw = {
    "greedy": [8267595, 8030620, 7944094],
    "costbenefit": [8944921, 8676857, 8755612],
    "random": [13681992, 13640220, 13757160],
}
erase_sum_raw = {
    "greedy": [409760, 411080, 411768],
    "costbenefit": [397884, 400288, 399272],
    "random": [292180, 293128, 292776],
}
erase_max_raw = {
    "greedy": [10, 11, 10],
    "costbenefit": [9, 8, 8],
    "random": [11, 12, 11],
}
nonzero_raw = {
    "greedy": [85548, 85676, 85648],
    "costbenefit": [89436, 89436, 89428],
    "random": [86408, 86552, 86540],
}
erase_cv_raw = {
    "greedy": [0.2377, 0.2429, 0.2355],
    "costbenefit": [0.2406, 0.2212, 0.2311],
    "random": [0.4905, 0.4853, 0.4915],
}
lat_avg_ns_raw = {  # cold_touch+hot_churn 병합 그룹 (group_reporting)
    "greedy": [80847.929712, 80027.018639, 79687.931571],
    "costbenefit": [85216.178907, 83972.316306, 84406.235761],
    "random": [152757.327015, 151683.070346, 152906.254787],
}
lat_p99_ns_raw = {
    "greedy": [419840, 440320, 436224],
    "costbenefit": [448512, 419840, 448512],
    "random": [1548288, 1482752, 1531904],
}

migrate_gib_raw = {k: [m / g for m, g in zip(migrate_raw[k], GiB[k])] for k in ORDER}
erase_gib_raw = {k: [s / g for s, g in zip(erase_sum_raw[k], GiB[k])] for k in ORDER}

migrate_gib, migrate_gib_err = stats(migrate_gib_raw)
erase_gib, erase_gib_err = stats(erase_gib_raw)
erase_max, erase_max_err = stats(erase_max_raw)
nonzero, nonzero_err = stats(nonzero_raw)
lat_avg_us_raw = {k: [v / 1000 for v in lat_avg_ns_raw[k]] for k in ORDER}
lat_p99_us_raw = {k: [v / 1000 for v in lat_p99_ns_raw[k]] for k in ORDER}
lat_avg, lat_avg_err = stats(lat_avg_us_raw)
lat_p99, lat_p99_err = stats(lat_p99_us_raw)

# =====================================================================
# Fig 1: 워크로드별 블록 마모 분포 (세 워크로드 x 세 정책, 블록 단위 raw 분포)
# 집계값이 아니라 erase_cnt.txt의 131,072개 블록을 그대로 읽어서 그림.
# 워크로드마다 기록한 총 바이트가 달라(uniform 146.5GiB / hotcold 102~167GiB /
# filebench 87~90GiB) 워크로드 간 절대 높이 비교는 의미가 없음 -- 이 그림이
# 보여주는 건 "같은 워크로드 안에서 정책별로 마모가 어떻게 퍼지는가"의 형태.
# =====================================================================
DIST_RUNS = {
    "uniform\n(600 MiB file, 1.3% util.)": {
        "greedy": "20260731_110103_policy0_greedy_final31_rep1",
        "costbenefit": "20260731_110936_policy2_costbenefit_final31_rep1",
        "random": "20260731_110520_policy1_random_final31_rep1"},
    "hotcold v7\n(separated hot / cold)": {
        "greedy": "20260730_231827_policy0_greedy_vpcdiag_rep1",
        "costbenefit": "20260730_232507_policy2_costbenefit_vpcdiag_rep1",
        "random": "20260730_234613_policy1_random_vpcdiag_rep1"},
    "filebench\n(2 GiB, randwrite + fsync)": {
        "greedy": "20260731_111951_policy0_greedy_final31_filebench",
        "costbenefit": "20260731_112358_policy2_costbenefit_final31_filebench",
        "random": "20260731_112155_policy1_random_final31_filebench"},
}

dist = {wl: {p: load_erase(r) for p, r in runs.items()} for wl, runs in DIST_RUNS.items()}
wls = list(DIST_RUNS.keys())
GROUP_W, MARK_W = 0.72, 0.20

fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(11, 8.6),
                                 gridspec_kw={"height_ratios": [1.55, 1]})

for gi, wl in enumerate(wls):
    for pi, pol in enumerate(ORDER):
        arr = dist[wl][pol]
        nz = arr[arr > 0]
        pos = gi + (pi - 1) * (GROUP_W / 3)
        bp = ax_a.boxplot([nz], positions=[pos], widths=MARK_W, patch_artist=True,
                          whis=(0, 100), showfliers=False, zorder=3)
        for box in bp["boxes"]:
            box.set(facecolor=COLOR[pol], edgecolor=SURFACE, linewidth=2.0)
        for part in bp["whiskers"] + bp["caps"]:
            part.set(color=COLOR[pol], linewidth=1.6)
        for med in bp["medians"]:
            med.set(color=SURFACE, linewidth=2.0)
        ax_a.annotate(f"{nz.max()}", xy=(pos, nz.max()), xytext=(0, 5),
                      textcoords="offset points", ha="center", va="bottom",
                      fontsize=8.5, color=INK_SECONDARY)

ax_a.set_yscale("log")
ax_a.set_ylim(0.8, 420)
ax_a.set_yticks([1, 2, 5, 10, 20, 50, 100, 200])
ax_a.set_yticklabels(["1", "2", "5", "10", "20", "50", "100", "200"])
ax_a.minorticks_off()
ax_a.set_ylabel("Erase count per block (log scale)")
ax_a.set_xticks(range(len(wls)))
ax_a.set_xticklabels([])
ax_a.set_xlim(-0.55, len(wls) - 0.45)
ax_a.tick_params(axis="both", length=0)
ax_a.grid(axis="x", visible=False)
ax_a.spines[["top", "right", "left"]].set_visible(False)
ax_a.set_title("Distribution of erase counts over erased blocks  "
               "(box = IQR, whiskers = min-max, label = max)",
               color=INK_PRIMARY, fontsize=11.5, pad=10, loc="left")
ax_a.legend(handles=[Patch(facecolor=COLOR[p], label=LABEL[p]) for p in ORDER],
            loc="lower right", bbox_to_anchor=(1.0, 1.01), frameon=False, ncol=3,
            fontsize=9.5, labelcolor=INK_SECONDARY, handlelength=1.1,
            handleheight=1.1, columnspacing=1.6)

for gi, wl in enumerate(wls):
    for pi, pol in enumerate(ORDER):
        arr = dist[wl][pol]
        pct = float((arr > 0).sum()) / TOTAL_BLOCKS * 100
        pos = gi + (pi - 1) * (GROUP_W / 3)
        ax_b.bar([pos], [pct], width=MARK_W, color=COLOR[pol], zorder=3,
                 edgecolor=SURFACE, linewidth=2.0)
        ax_b.annotate(f"{pct:.1f}%", xy=(pos, pct), xytext=(0, 4),
                      textcoords="offset points", ha="center", va="bottom",
                      fontsize=8.5, color=INK_SECONDARY)

ax_b.set_xticks(range(len(wls)))
ax_b.set_xticklabels(wls, fontsize=10)
ax_b.set_xlim(-0.55, len(wls) - 0.45)
ax_b.set_ylim(0, 100)
ax_b.set_ylabel("Blocks erased at least once (%)")
ax_b.tick_params(axis="both", length=0)
ax_b.grid(axis="x", visible=False)
ax_b.spines[["top", "right", "left"]].set_visible(False)
ax_b.set_title(f"Share of the {TOTAL_BLOCKS:,} physical blocks that were erased at least once",
               color=INK_PRIMARY, fontsize=11.5, pad=10, loc="left")

fig.suptitle("Per-block wear distribution by workload and GC policy",
             fontsize=13.5, color=INK_PRIMARY, x=0.055, ha="left", y=0.985)
fig.tight_layout(rect=[0, 0, 1, 0.955])
save(fig, "fig1_wear_distribution")

# =====================================================================
# Fig 2: hotcold v7 최종 비교 (fix 적용 후, 3회 반복) — migration/erase 효율
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], migrate_gib, migrate_gib_err,
          "Valid pages migrated per GiB written", "migrate pages / GiB", "{:.0f}")
bar_panel(axes[1], erase_gib, erase_gib_err,
          "Block erases per GiB written", "erases / GiB", "{:.1f}")
fig.suptitle("hotcold v7 — GC efficiency (after bug fix, mean ± sd of 3 runs)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig2_hotcold_efficiency")

# =====================================================================
# Fig 3: hotcold v7 — 웨어 레벨링 (erase max, nonzero_blocks)
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], erase_max, erase_max_err,
          "Peak wear: highest erase count of any block", "erase max", "{:.1f}")
bar_panel(axes[1], nonzero, nonzero_err,
          "Blocks erased at least once", "nonzero blocks", "{:.0f}")
fig.suptitle("hotcold v7 — wear leveling (after bug fix, 3 runs)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig3_hotcold_wear_leveling")

# =====================================================================
# Fig 4: hotcold v7 — latency
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], lat_avg, lat_avg_err, "Average write latency", "latency avg (us)", "{:.1f}")
bar_panel(axes[1], lat_p99, lat_p99_err, "p99 tail write latency", "latency p99 (us)", "{:.0f}")
fig.suptitle("hotcold v7 — host IO latency (after bug fix, 3 runs)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig4_hotcold_latency")

# =====================================================================
# Fig 5: uniform 비교 (raw, 정규화 불필요 — 항상 동일 바이트 기록)
# 출처: results/*_final31_rep{1,2,3} (2026-07-31, migration 카운터/진단 포함된 최종 빌드)
# =====================================================================
uni_sum_raw = {
    "greedy": [271620, 271620, 271620],
    "costbenefit": [271620, 271620, 271620],
    "random": [273380, 273380, 273380],
}
uni_max_raw = {
    "greedy": [161, 161, 161],
    "costbenefit": [161, 161, 161],
    "random": [10, 10, 9],
}
uni_migrate_raw = {
    "greedy": [0, 0, 0],
    "costbenefit": [0, 0, 0],
    "random": [170670, 171086, 171211],
}
uni_sum, uni_sum_err = stats(uni_sum_raw)
uni_max, uni_max_err = stats(uni_max_raw)
uni_migrate, uni_migrate_err = stats(uni_migrate_raw)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
bar_panel(axes[0], uni_migrate, uni_migrate_err, "Total valid pages migrated by GC", "migrate pages", "{:.0f}")
bar_panel(axes[1], uni_sum, uni_sum_err, "Total block erases (raw, no normalization)", "erase sum", "{:.0f}")
bar_panel(axes[2], uni_max, uni_max_err, "Peak wear: highest erase count", "erase max", "{:.1f}")
fig.suptitle("uniform — Greedy and Cost-Benefit converge structurally (migrate = 0); "
             "Random trades off (3 runs)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig5_uniform_comparison")

# =====================================================================
# Fig 6: uniform 사용률 스윕 — 디바이스를 채우면 두 정책이 갈리기 시작하는가
# 같은 uniform 워크로드를 파일 크기만 바꿔가며 측정 (총 쓰기량은 146~154GiB로 맞춤).
# results/에서 직접 읽으므로 새 지점을 돌리면 아래 목록에만 추가하면 됨.
# =====================================================================
DEVICE_GIB = 44.86    # lsblk 기준 노출 용량
PHYSICAL_GIB = 48.0   # memmap_size=48G

SWEEP_POINTS = [
    ("final31_rep", 0.5859),   # 600 MiB
    ("util50", 22.0),          # 22 GiB
    ("util80", 38.0),          # 38 GiB
]


def collect_sweep(tag):
    """results/*<tag>* 에서 정책별 (migrate/GiB, divergence%) 평균을 모은다."""
    out = {}
    for d in sorted(glob.glob(os.path.join(REPO_ROOT, "results", f"*{tag}*"))):
        if "filebench" in d:
            continue
        meta = dict(l.strip().split("=", 1) for l in open(os.path.join(d, "meta.txt")) if "=" in l)
        s = dict(kv.split("=", 1) for kv in open(os.path.join(d, "summary.txt")).read().split())
        gib = json.load(open(os.path.join(d, "fio.json")))["jobs"][0]["write"]["io_bytes"] / 2 ** 30
        total_gc = int(s["total_gc"])
        out.setdefault(meta["policy_name"], []).append((
            int(s["gc_migrate_pages"]) / gib,
            (int(s["greedy_vs_cb_identity_diverge"]) / total_gc * 100) if total_gc else 0.0,
        ))
    return {k: (float(np.mean([x[0] for x in v])), float(np.mean([x[1] for x in v])))
            for k, v in out.items()}

sweep = [(live, collect_sweep(tag)) for tag, live in SWEEP_POINTS]
sweep = [(live, d) for live, d in sweep if d]
missing = [tag for tag, live in SWEEP_POINTS if not collect_sweep(tag)]
if missing:
    print(f"  (fig6: 아직 데이터 없는 지점 건너뜀 -> {missing})")

xs = np.arange(len(sweep))
xlabels = [f"{live * 1024:.0f} MiB\n({live / DEVICE_GIB * 100:.1f}% full)" if live < 1
           else f"{live:.0f} GiB\n({live / DEVICE_GIB * 100:.0f}% full)"
           for live, _ in sweep]

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
w = 0.24
for pi, pol in enumerate(ORDER):
    vals = [d.get(pol, (0.0, 0.0))[0] for _, d in sweep]
    axes[0].bar(xs + (pi - 1) * w, vals, width=w, color=COLOR[pol], label=LABEL[pol],
                zorder=3, edgecolor=SURFACE, linewidth=2.0)
    for xi, v in zip(xs + (pi - 1) * w, vals):
        axes[0].annotate(f"{v:.0f}", xy=(xi, v), xytext=(0, 4), textcoords="offset points",
                         ha="center", fontsize=8.5, color=INK_SECONDARY)
axes[0].set_ylabel("valid pages migrated / GiB written")
axes[0].set_title("GC migration cost as the device fills up", loc="left", fontsize=11.5, pad=10)
axes[0].legend(loc="lower right", bbox_to_anchor=(1.0, 1.005), frameon=False, ncol=3,
               fontsize=9, labelcolor=INK_SECONDARY, handlelength=1.1, handleheight=1.1,
               columnspacing=1.4)

div = [d.get("greedy", (0.0, 0.0))[1] for _, d in sweep]
bars = axes[1].bar(xs, div, width=0.45, color=COLOR["costbenefit"], zorder=3)
for r, v in zip(bars, div):
    axes[1].annotate(f"{v:.1f}%", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=9.5, color=INK_SECONDARY)
axes[1].set_ylabel("GC decisions where Greedy and CB differ (%)")
axes[1].set_title("Do the two policies ever disagree?", loc="left", fontsize=11.5, pad=10)
axes[1].set_ylim(0, max(max(div) * 1.35, 5))

for ax in axes:
    ax.set_xticks(xs)
    ax.set_xticklabels(xlabels, fontsize=9.5)
    ax.tick_params(axis="both", length=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.margins(y=0.18)

fig.suptitle("uniform utilization sweep — filling the device does not make the policies diverge",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig6_utilization_sweep")

# =====================================================================
# Fig 8: filebench 비교 (1회 측정, 보조 데이터)
# 출처: results/*_final31_filebench (2026-07-31, migration 카운터/진단 포함된 최종 빌드)
# =====================================================================
fb_migrate_gib = {"greedy": 0.0, "costbenefit": 0.0, "random": 8590.8}
fb_erase_gib = {"greedy": 1355.3, "costbenefit": 1379.7, "random": 1463.8}
fb_max = {"greedy": 3.0, "costbenefit": 3.0, "random": 8.0}
fb_nonzero = {"greedy": 57212.0, "costbenefit": 55472.0, "random": 82588.0}

fig, axes = plt.subplots(1, 4, figsize=(17.5, 4.2))
bar_panel(axes[0], fb_migrate_gib, None, "Migration cost per GiB", "migrate pages / GiB", "{:.0f}")
bar_panel(axes[1], fb_erase_gib, None, "Erase cost per GiB", "erases / GiB", "{:.0f}")
bar_panel(axes[2], fb_max, None, "Peak wear", "erase max", "{:.0f}")
bar_panel(axes[3], fb_nonzero, None, "Blocks erased at least once", "nonzero blocks", "{:.0f}")
fig.suptitle("Filebench — secondary benchmark confirming the fio result "
             "(single run, final build, 2 GiB / 120 s / 4 threads)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig8_filebench_comparison")

# =====================================================================
# Fig 9: vpc divergence 분석 (diag_scan_greedy_vs_cb, 3회 반복 평균)
# =====================================================================
avg_greedy_vpc_raw = {
    "greedy": [80.707, 78.142, 77.171],
    "costbenefit": [55.235, 53.854, 53.884],
    "random": [8.965, 8.099, 8.928],
}
avg_cb_vpc_raw = {
    "greedy": [92.581, 89.217, 88.191],
    "costbenefit": [89.925, 86.706, 87.716],
    "random": [10.887, 9.242, 9.996],
}
abs_diff_raw = {
    "greedy": [11.874, 11.076, 11.021],
    "costbenefit": [34.689, 32.852, 33.832],
    "random": [1.922, 1.143, 1.067],
}

avg_greedy_vpc, _ = stats(avg_greedy_vpc_raw)
avg_cb_vpc, _ = stats(avg_cb_vpc_raw)
abs_diff, abs_diff_err = stats(abs_diff_raw)

fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
groups = ["running Greedy", "running Cost-Benefit", "running Random"]
x = np.arange(len(groups))
w = 0.32
axes[0].bar(x - w / 2, [avg_greedy_vpc[k] for k in ORDER], width=w, color=COLOR["greedy"],
            label="vpc of the line Greedy would pick", zorder=3)
axes[0].bar(x + w / 2, [avg_cb_vpc[k] for k in ORDER], width=w, color=COLOR["costbenefit"],
            label="vpc of the line Cost-Benefit would pick", zorder=3)
axes[0].set_xticks(x)
axes[0].set_xticklabels(groups)
axes[0].set_ylabel("mean vpc of victim line (valid pages)")
axes[0].set_title("Victim each policy would pick, under each running policy",
                  loc="left", fontsize=11.5, pad=10)
axes[0].spines[["top", "right", "left"]].set_visible(False)
axes[0].grid(axis="x", visible=False)
axes[0].legend(frameon=False, fontsize=9, loc="upper right")
axes[0].margins(y=0.18)

ax2 = axes[1]
heights = [abs_diff[k] for k in ORDER]
errors = [abs_diff_err[k] for k in ORDER]
bars = ax2.bar(x, heights, yerr=errors, width=0.5, color=[COLOR[k] for k in ORDER], zorder=3,
               capsize=5, error_kw={"ecolor": INK_SECONDARY, "elinewidth": 1.2, "capthick": 1.2})
ax2.set_xticks(x)
ax2.set_xticklabels(["running\nGreedy", "running\nCost-Benefit", "running\nRandom"])
ax2.set_ylabel("avg |vpc_greedy - vpc_cb|")
ax2.set_title("Cost gap between the two picks (avg_abs_vpc_diff)",
              loc="left", fontsize=11.5, pad=10)
ax2.spines[["top", "right", "left"]].set_visible(False)
ax2.grid(axis="x", visible=False)
for rect, k in zip(bars, ORDER):
    h = rect.get_height()
    ax2.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h + abs_diff_err[k]),
                 xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9, color=INK_SECONDARY)
ax2.margins(y=0.2)

fig.suptitle("Victim divergence — when the two policies pick different lines, "
             "does the cost (vpc) differ too?",
             fontsize=13, color=INK_PRIMARY, y=1.04)
save(fig, "fig9_vpc_divergence")

# =====================================================================
# Fig 10 (보너스): 힙 staleness 버그 수정 전/후 — Cost-Benefit의 migrate_pages/GiB
# 출처: results/*_migtest*(수정 전), results/*_vpcdiag_rep*(수정 후)
# =====================================================================
prefix_cb = [53209.2, 54392.9, 48883.2]
postfix_cb = migrate_gib_raw["costbenefit"]
greedy_ref = migrate_gib["greedy"]  # 버그와 무관 (Greedy 코드는 안 건드림), 참고선

fig, ax = plt.subplots(figsize=(7.5, 4.6))
x = np.array([0, 1])
means = [float(np.mean(prefix_cb)), float(np.mean(postfix_cb))]
stds = [float(np.std(prefix_cb, ddof=1)), float(np.std(postfix_cb, ddof=1))]
ax.bar(x, means, yerr=stds, width=0.45, color=COLOR["costbenefit"], zorder=3,
       capsize=6, error_kw={"ecolor": INK_SECONDARY, "elinewidth": 1.2, "capthick": 1.2})
for xi, pts in zip(x, [prefix_cb, postfix_cb]):
    jitter = np.linspace(-0.08, 0.08, len(pts))
    ax.scatter(xi + jitter, pts, color=INK_PRIMARY, s=22, zorder=4, alpha=0.75)
ax.axhline(greedy_ref, color=COLOR["greedy"], linestyle="--", linewidth=1.4, zorder=2)
ax.annotate("Greedy mean (reference, unaffected by the bug)", xy=(1.0, greedy_ref),
            xytext=(0.02, greedy_ref - 4200), fontsize=9, color=COLOR["greedy"])
ax.set_xticks(x)
ax.set_xticklabels(["before fix\n(heap staleness bug)", "after fix\n(replaced with a full scan)"])
ax.set_ylabel("Cost-Benefit migrate pages / GiB")
ax.set_title("Cost-Benefit migration cost, before and after the heap staleness fix",
             loc="left", fontsize=12.5, pad=12)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", visible=False)
ax.margins(y=0.22)
save(fig, "fig10_bugfix_before_after")

# =====================================================================
# Fig 7: 워크로드가 정책 차이를 만드는가 — uniform vs hotcold 대비
# 출처: results/*_uniformdiag/ (2026-07-31), results/*_vpcdiag_rep*/
# =====================================================================
fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
wl = ["uniform", "hotcold v7"]
xw = np.arange(len(wl))
NEUTRAL = "#898781"

# (1) 두 정책이 서로 다른 line을 고른 비율
diverge_pct = [0.0, 90.3]
b = axes[0].bar(xw, diverge_pct, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[0].set_ylabel("GC decisions where Greedy and CB differ (%)")
axes[0].set_title("Do the policies pick differently?", loc="left", fontsize=11.5, pad=10)
axes[0].set_ylim(0, 100)
for r, v in zip(b, diverge_pct):
    axes[0].annotate(f"{v:.1f}%", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

# (2) 고른 line의 비용(vpc) 차이
vpc_diff = [0.0, 33.8]
b = axes[1].bar(xw, vpc_diff, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[1].set_ylabel("avg |vpc_greedy - vpc_cb|")
axes[1].set_title("Does a different pick cost differently?", loc="left", fontsize=11.5, pad=10)
for r, v in zip(b, vpc_diff):
    axes[1].annotate(f"{v:.1f}", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

# (3) GC 한 번당 실제로 옮긴 valid page 수
mig_per_gc = [0.0, 88.1]
b = axes[2].bar(xw, mig_per_gc, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[2].set_ylabel("valid pages migrated per GC")
axes[2].set_title("Does GC cost anything at all? (Cost-Benefit)", loc="left", fontsize=11.5, pad=10)
for r, v in zip(b, mig_per_gc):
    axes[2].annotate(f"{v:.1f}", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

for ax in axes:
    ax.set_xticks(xw)
    ax.set_xticklabels(wl)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.margins(y=0.2)

fig.suptitle("The workload decides whether the policies can differ — "
             "under uniform they are provably identical",
             fontsize=13, color=INK_PRIMARY, y=1.04)
save(fig, "fig7_workload_decides")

print("done.")

"""
실습 1 보고서용 그래프 생성 스크립트.
가능한 한 raw 반복측정값에서 직접 mean/stdev를 계산 (하드코딩된 통계치 최소화).
데이터 출처: CLAUDE.md / EXPERIMENT_LOG.md 2026-07-30 항목, results/*_vpcdiag_rep*.
실행: python3 report/make_figures.py  (결과: report/figures/*.png)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

fm.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = "Noto Sans CJK JP"

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
    fig.savefig(f"report/figures/{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved report/figures/{name}.png")


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
# Fig 1: hotcold v7 최종 비교 (fix 적용 후, 3회 반복) — migration/erase 효율
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], migrate_gib, migrate_gib_err,
          "GC당 이동한 valid page 수 (GiB당)", "migrate pages / GiB", "{:.0f}")
bar_panel(axes[1], erase_gib, erase_gib_err,
          "블록 erase 횟수 (GiB당)", "erases / GiB", "{:.1f}")
fig.suptitle("hotcold v7 — GC 효율 비교 (버그 수정 후, 3회 반복 평균 ± 표준편차)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig1_hotcold_efficiency")

# =====================================================================
# Fig 2: hotcold v7 — 웨어 레벨링 (erase max, nonzero_blocks)
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], erase_max, erase_max_err,
          "블록 하나의 최대 erase 횟수 (peak wear)", "erase max (회)", "{:.1f}")
bar_panel(axes[1], nonzero, nonzero_err,
          "erase가 1회 이상 일어난 블록 수", "nonzero blocks (개)", "{:.0f}")
fig.suptitle("hotcold v7 — 웨어 레벨링 비교 (버그 수정 후, 3회 반복)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig2_hotcold_wear_leveling")

# =====================================================================
# Fig 3: hotcold v7 — latency
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
bar_panel(axes[0], lat_avg, lat_avg_err, "쓰기 평균 지연시간", "latency avg (μs)", "{:.1f}")
bar_panel(axes[1], lat_p99, lat_p99_err, "쓰기 p99 tail 지연시간", "latency p99 (μs)", "{:.0f}")
fig.suptitle("hotcold v7 — 호스트 IO 지연시간 비교 (버그 수정 후, 3회 반복)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig3_hotcold_latency")

# =====================================================================
# Fig 4: uniform 비교 (raw, 정규화 불필요 — 항상 동일 바이트 기록)
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
bar_panel(axes[0], uni_migrate, uni_migrate_err, "GC 중 옮긴 valid page 총합", "migrate pages (개)", "{:.0f}")
bar_panel(axes[1], uni_sum, uni_sum_err, "총 erase 횟수 (raw, 정규화 불필요)", "erase sum (회)", "{:.0f}")
bar_panel(axes[2], uni_max, uni_max_err, "블록 하나의 최대 erase 횟수", "erase max (회)", "{:.1f}")
fig.suptitle("uniform 워크로드 — Greedy=Cost-Benefit 구조적 수렴(migrate=0), Random 트레이드오프 (3회 반복)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig4_uniform_comparison")

# =====================================================================
# Fig 5: filebench 비교 (1회 측정, 보조 데이터)
# 출처: results/*_final31_filebench (2026-07-31, migration 카운터/진단 포함된 최종 빌드)
# =====================================================================
fb_migrate_gib = {"greedy": 0.0, "costbenefit": 0.0, "random": 8590.8}
fb_erase_gib = {"greedy": 1355.3, "costbenefit": 1379.7, "random": 1463.8}
fb_max = {"greedy": 3.0, "costbenefit": 3.0, "random": 8.0}
fb_nonzero = {"greedy": 57212.0, "costbenefit": 55472.0, "random": 82588.0}

fig, axes = plt.subplots(1, 4, figsize=(17.5, 4.2))
bar_panel(axes[0], fb_migrate_gib, None, "migration 비용 (GiB당)", "migrate pages / GiB", "{:.0f}")
bar_panel(axes[1], fb_erase_gib, None, "erase 효율 (GiB당)", "erases / GiB", "{:.0f}")
bar_panel(axes[2], fb_max, None, "블록 최대 erase 횟수", "erase max (회)", "{:.0f}")
bar_panel(axes[3], fb_nonzero, None, "erase된 블록 수", "nonzero blocks (개)", "{:.0f}")
fig.suptitle("Filebench — fio 결과 재확인용 보조 벤치마크 (1회 측정, 최종 빌드, 2GB/120초/4스레드)",
             fontsize=13, color=INK_PRIMARY, y=1.03)
save(fig, "fig5_filebench_comparison")

# =====================================================================
# Fig 6: vpc divergence 분석 (diag_scan_greedy_vs_cb, 3회 반복 평균)
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
groups = ["Greedy 구동 중", "Cost-Benefit 구동 중", "Random 구동 중"]
x = np.arange(len(groups))
w = 0.32
axes[0].bar(x - w / 2, [avg_greedy_vpc[k] for k in ORDER], width=w, color=COLOR["greedy"],
            label="Greedy가 골랐을 line의 vpc", zorder=3)
axes[0].bar(x + w / 2, [avg_cb_vpc[k] for k in ORDER], width=w, color=COLOR["costbenefit"],
            label="Cost-Benefit이 골랐을 line의 vpc", zorder=3)
axes[0].set_xticks(x)
axes[0].set_xticklabels(groups)
axes[0].set_ylabel("victim line의 평균 vpc (valid page 수)")
axes[0].set_title("실제 구동 정책별, 두 정책이 '골랐을' victim의 vpc", loc="left", fontsize=11.5, pad=10)
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
ax2.set_xticklabels(["Greedy 구동\n중", "Cost-Benefit 구동\n중", "Random 구동\n중"])
ax2.set_ylabel("avg |vpc_greedy − vpc_cb|  (평균 vpc 차이)")
ax2.set_title("다르게 고른 line 간 vpc 차이 (avg_abs_vpc_diff)", loc="left", fontsize=11.5, pad=10)
ax2.spines[["top", "right", "left"]].set_visible(False)
ax2.grid(axis="x", visible=False)
for rect, k in zip(bars, ORDER):
    h = rect.get_height()
    ax2.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h + abs_diff_err[k]),
                 xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9, color=INK_SECONDARY)
ax2.margins(y=0.2)

fig.suptitle("victim divergence 분석 — 다른 line을 고르면 실제로 비용(vpc)도 다른가?",
             fontsize=13, color=INK_PRIMARY, y=1.04)
save(fig, "fig6_vpc_divergence")

# =====================================================================
# Fig 7 (보너스): 힙 staleness 버그 수정 전/후 — Cost-Benefit의 migrate_pages/GiB
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
ax.annotate("Greedy 평균 (참고선, 버그와 무관)", xy=(1.0, greedy_ref),
            xytext=(0.02, greedy_ref - 4200), fontsize=9, color=COLOR["greedy"])
ax.set_xticks(x)
ax.set_xticklabels(["수정 전\n(힙 staleness 버그 있음)", "수정 후\n(전체 스캔으로 교체)"])
ax.set_ylabel("Cost-Benefit migrate pages / GiB")
ax.set_title("힙 staleness 버그 수정 전후 — Cost-Benefit의 migration 비용 변화",
              loc="left", fontsize=12.5, pad=12)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", visible=False)
ax.margins(y=0.22)
save(fig, "fig7_bugfix_before_after")

# =====================================================================
# Fig 8: 워크로드가 정책 차이를 만드는가 — uniform vs hotcold 대비
# 출처: results/*_uniformdiag/ (2026-07-31), results/*_vpcdiag_rep*/
# =====================================================================
fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
wl = ["uniform", "hotcold v7"]
xw = np.arange(len(wl))
NEUTRAL = "#898781"

# (1) 두 정책이 서로 다른 line을 고른 비율
diverge_pct = [0.0, 90.3]
b = axes[0].bar(xw, diverge_pct, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[0].set_ylabel("Greedy와 CB가 다른 line을 고른 비율 (%)")
axes[0].set_title("정책 선택이 갈리는가", loc="left", fontsize=11.5, pad=10)
axes[0].set_ylim(0, 100)
for r, v in zip(b, diverge_pct):
    axes[0].annotate(f"{v:.1f}%", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

# (2) 고른 line의 비용(vpc) 차이
vpc_diff = [0.0, 33.8]
b = axes[1].bar(xw, vpc_diff, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[1].set_ylabel("avg |vpc_greedy − vpc_cb|")
axes[1].set_title("갈린 선택이 비용 차이로 이어지는가", loc="left", fontsize=11.5, pad=10)
for r, v in zip(b, vpc_diff):
    axes[1].annotate(f"{v:.1f}", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

# (3) GC 한 번당 실제로 옮긴 valid page 수
mig_per_gc = [0.0, 88.1]
b = axes[2].bar(xw, mig_per_gc, width=0.5, color=[NEUTRAL, COLOR["costbenefit"]], zorder=3)
axes[2].set_ylabel("GC 1회당 이동한 valid page 수")
axes[2].set_title("GC에 비용이 드는가 (Cost-Benefit 기준)", loc="left", fontsize=11.5, pad=10)
for r, v in zip(b, mig_per_gc):
    axes[2].annotate(f"{v:.1f}", xy=(r.get_x() + r.get_width() / 2, v), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=10, color=INK_SECONDARY)

for ax in axes:
    ax.set_xticks(xw)
    ax.set_xticklabels(wl)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.margins(y=0.2)

fig.suptitle("워크로드가 정책 차이를 결정한다 — uniform에서는 두 정책이 '증명 가능하게' 동일",
             fontsize=13, color=INK_PRIMARY, y=1.04)
save(fig, "fig8_workload_decides")

print("done.")

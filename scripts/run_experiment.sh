#!/bin/bash
# 사용법: ./scripts/run_experiment.sh <policy: 0|1|2|3> <label> [workload: uniform|hotcold]
#   policy:   SLC migration policy
#             0=Greedy, 1=Random, 2=FIFO, 3=Cost-Benefit
#   label:    결과 폴더 구분용 자유 문자열 (예: randwrite6g, hotcold1)
#   workload: uniform(기본값, 균등 랜덤쓰기 6G) | hotcold(콜드 500M 1회 + 핫 50M x120루프)
#
# 환경마다 디바이스 경로/insmod 파라미터가 다르므로 환경변수로 오버라이드할 것:
#   NVME_DEV      기본값 /dev/nvme0n1 (로컬 VM). 서버는 부팅용 NVMe가 이미 nvme0n1을
#                 쓰고 있어서 NVMeVirt 가상 디바이스가 /dev/nvme1n1로 잡힘 (2026-07-29 확인).
#   MEMMAP_START  기본값 2G (로컬 VM). 서버는 16G.
#   MEMMAP_SIZE   기본값 1G (로컬 VM). 서버는 48G.
#   NVME_CPUS     기본값 2,3 (로컬 VM). 서버는 7,8.
#   MOUNT_DIR     기본값 $HOME/nvme_mount
#   TLC_GC_POLICY 기본값 0. 실습2에서는 TLC GC와 SLC migration 의미가 분리됐으므로
#                 이 스크립트는 TLC GC를 고정하고 slc_migration_policy만 비교한다.
#   SLC_CACHE_RATIO_PERCENT 기본값 10. 0이면 TLC-only baseline, 10이면 현재 기본 SLC cache.
#
# 예) 서버에서: NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
#              ./scripts/run_experiment.sh 3 randwrite6g uniform
#
# 정책 간 비교는 sysfs로 runtime parameter만 바꾸는 게 아니라 매번 모듈을 완전히
# 리로드해야 cb_clock/write pointer/free line list 같은 FTL 내부 상태가 오염되지
# 않는다는 게 2026-07-27에 확인됨 -> 이 스크립트는 매 실행마다
# umount -> rmmod -> insmod(TLC GC 고정 + SLC migration policy 지정) -> mkfs -> mount
# 를 처음부터 다시 수행함.
# sudo가 필요한 명령이 있어서 반드시 사용자 터미널에서 직접 실행할 것.
set -euo pipefail

POLICY="${1:?policy(0|1|2|3) 필요}"
LABEL="${2:?label 필요}"
WORKLOAD="${3:-uniform}"

NVME_DEV="${NVME_DEV:-/dev/nvme0n1}"
MEMMAP_START="${MEMMAP_START:-2G}"
MEMMAP_SIZE="${MEMMAP_SIZE:-1G}"
NVME_CPUS="${NVME_CPUS:-2,3}"
MOUNT_DIR="${MOUNT_DIR:-$HOME/nvme_mount}"
TLC_GC_POLICY="${TLC_GC_POLICY:-0}"
SLC_CACHE_RATIO_PERCENT="${SLC_CACHE_RATIO_PERCENT:-10}"
# hotcold 워크로드 전용 (v7, 2026-07-30): 콜드/핫을 물리적으로 분리된 line에
# 쓰기 위해 cold_fill 이후 cold_touch/hot_churn을 병렬 실행함 (자세한 이유는
# scripts/workloads/hotcold.fio 상단 주석 참고). v6(size 기반, COLD_TOUCH_SIZE=15G)는
# printk 진단으로 실제 Greedy/CB 선택이 갈리는 걸 확인했으나, cold_touch가
# hot_churn보다 훨씬 먼저 끝나버려서(15G vs 100G) 전체 GC 판정의 17%에서만
# divergence가 나고 나머지 83%는 균일하게 수렴 -> 최종 erase 통계에는 안 드러남.
# v7은 둘 다 time_based+동일 runtime(HOTCOLD_RUNTIME)으로 바꿔서 콜드 후보가
# 실행 시간 내내 끊이지 않고 공급되도록 함. 서버(44.9G 용량) 기준 기본값 --
# 로컬 VM처럼 용량이 훨씬 작은 환경에서는 반드시 오버라이드할 것.
COLD_SIZE="${COLD_SIZE:-30G}"
COLD_TOUCH_SIZE="${COLD_TOUCH_SIZE:-15G}"
HOT_SIZE="${HOT_SIZE:-1G}"
HOTCOLD_RUNTIME="${HOTCOLD_RUNTIME:-90}"
export COLD_SIZE COLD_TOUCH_SIZE HOT_SIZE HOTCOLD_RUNTIME

# uniform 워크로드 전용 (2026-07-31 파라미터화). 기본값 600M/250은 기존 결과와의
# 재현성을 위해 그대로 유지함 -- 서버 용량 44.86GiB 기준 워킹셋이 1.3%밖에 안 되는
# 조건이라, GC victim이 사실상 전부 vpc=0("고를 것이 없는" 상태)이 되어 Greedy와
# Cost-Benefit이 구조적으로 완전히 수렴함(2026-07-31 uniformdiag에서 divergence 0회,
# migrate 0페이지로 확인). 이 수렴이 "워킹셋이 작아서"임을 통제된 실험으로 보이려면
# UNIFORM_SIZE를 키워 디바이스 사용률을 올린 조건을 같이 측정해야 함.
#   예) UNIFORM_SIZE=22G UNIFORM_LOOPS=7  -> 사용률 약 49%, 총 154GiB 기록
UNIFORM_SIZE="${UNIFORM_SIZE:-600M}"
UNIFORM_LOOPS="${UNIFORM_LOOPS:-250}"

# RANDOM_DIST: fio의 --random_distribution 값 (예: zipf:1.2, pareto:0.3, zoned:...).
# 비워두면 fio 기본값인 균등 분포를 쓴다.
#
# 사용률 스윕(4.2.1절)에서 확인했듯이 균등 분포에서는 디바이스를 85%까지 채워도
# 완전히 무효화된 line이 항상 남아 있어서 Greedy와 Cost-Benefit의 선택이 전혀
# 갈리지 않는다. 이 변수만 zipf로 바꾸면 파일 크기와 총 쓰기량을 그대로 둔 채
# 접근 분포만 바꿀 수 있어서, "정책 차이를 만드는 건 용량이 아니라 스큐"라는
# 주장을 대조 실험으로 검증할 수 있다.
RANDOM_DIST="${RANDOM_DIST:-}"
DIST_OPT=""
[ -n "$RANDOM_DIST" ] && DIST_OPT="--random_distribution=$RANDOM_DIST"

# NORANDOMMAP=1 로 fio의 --norandommap을 켠다. 기본값(끔)에서 fio는 비트맵을 유지해
# 한 loop 안에서 각 블록을 정확히 한 번씩만 방문하므로, 균등 분포라 해도 실제로는
# i.i.d. 랜덤 쓰기가 아니라 "매 pass마다 전체를 한 번씩 훑는 무작위 순열"이 된다.
# 이러면 모든 페이지가 pass당 정확히 한 번 무효화되어 오래된 line은 반드시 100%
# 무효화되고, Greedy가 항상 vpc=0인 line을 찾아내 GC 비용이 0이 된다(사용률 85%
# 조건에서도 gc_migrate_pages=0이 나온 것에 대한 유력한 설명).
# 이 변수를 켜면 블록이 중복/누락 방문되는 진짜 i.i.d. 랜덤 쓰기가 되어 valid page가
# 남은 채로 회수되는 line이 생기는지 확인할 수 있다. 총 쓰기량은 그대로 유지된다.
NORANDOMMAP="${NORANDOMMAP:-}"
NORANDOMMAP_OPT=""
[ -n "$NORANDOMMAP" ] && NORANDOMMAP_OPT="--norandommap=1"

case "$POLICY" in
  0) POLICY_NAME=greedy ;;
  1) POLICY_NAME=random ;;
  2) POLICY_NAME=fifo ;;
  3) POLICY_NAME=costbenefit ;;
  *) echo "policy는 0/1/2/3 중 하나여야 함" >&2; exit 1 ;;
esac

case "$WORKLOAD" in
  uniform|hotcold) ;;
  *) echo "workload는 uniform/hotcold 중 하나여야 함" >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$REPO_ROOT/results/${TS}_slcpolicy${POLICY}_${POLICY_NAME}_${LABEL}"
mkdir -p "$OUTDIR"
mkdir -p "$MOUNT_DIR"

# 정책 간 공정 비교를 위해 매 실험마다 모듈을 완전히 리로드해서 FTL 내부 상태를
# fresh하게 만든 뒤, 그 위에 새 파일시스템까지 새로 만듦 (2026-07-27/29 결정)
sudo umount "$MOUNT_DIR" 2>/dev/null || true
sudo rmmod nvmev 2>/dev/null || true
sudo insmod "$REPO_ROOT/nvmev.ko" memmap_start="$MEMMAP_START" memmap_size="$MEMMAP_SIZE" \
    cpus="$NVME_CPUS" gc_policy="$TLC_GC_POLICY" slc_migration_policy="$POLICY" \
    slc_cache_ratio_percent="$SLC_CACHE_RATIO_PERCENT"

if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm settle
fi
[ -b "$NVME_DEV" ] || { echo "$NVME_DEV 가 생성되지 않았음 (dmesg 확인 필요)" >&2; exit 1; }

sudo mkfs -t ext4 -F "$NVME_DEV"
sudo mount "$NVME_DEV" "$MOUNT_DIR"
sudo chown "$USER:$USER" "$MOUNT_DIR"

echo reset | sudo tee /proc/nvmev/debug > /dev/null

if [ "$WORKLOAD" = "uniform" ]; then
  # loops=250: 서버(48G memmap)는 SSD 전체 용량이 44.9GB나 되고 블록 하나 용량도
  # 로컬 VM보다 훨씬 커서(로컬 32KB vs 서버 ~360KB), 로컬 VM 기준으로 잡았던
  # loops=10(총 6GB)로는 용량의 13%밖에 못 채워 GC가 전혀 안 돌았음(2026-07-29 확인).
  # loops=250이면 총 146GB(용량의 약 3.3배)를 써서 GC가 확실히 여러 번 트리거됨.
  FIO_CMD="fio --name=gc_stress --filename=\$MOUNT_DIR/testfile2 --size=$UNIFORM_SIZE --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=$UNIFORM_LOOPS $DIST_OPT $NORANDOMMAP_OPT --group_reporting"
  fio --name=gc_stress --filename="$MOUNT_DIR/testfile2" --size="$UNIFORM_SIZE" --rw=randwrite \
      --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops="$UNIFORM_LOOPS" \
      $DIST_OPT $NORANDOMMAP_OPT \
      --group_reporting --output-format=json --output="$OUTDIR/fio.json"
else
  FIO_CMD="COLD_SIZE=$COLD_SIZE COLD_TOUCH_SIZE=$COLD_TOUCH_SIZE HOT_SIZE=$HOT_SIZE HOTCOLD_RUNTIME=$HOTCOLD_RUNTIME fio $REPO_ROOT/scripts/workloads/hotcold.fio --directory=\$MOUNT_DIR"
  fio "$REPO_ROOT/scripts/workloads/hotcold.fio" --directory="$MOUNT_DIR" \
      --output-format=json --output="$OUTDIR/fio.json"
fi

cat /proc/nvmev/debug > "$OUTDIR/erase_cnt.txt"

awk '
  /^GC_VALID_PAGE_MIGRATE_CNT/{legacy_migrate=$2}
  /^TLC_GC_CNT/{tlc_gc_cnt=$2}
  /^TLC_GC_VALID_PAGE_MIGRATE_CNT/{tlc_gc_migrate=$2}
  /^SLC_MIGRATION_CNT/{slc_migration_cnt=$2}
  /^SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT/{slc_migrate=$2}
  /^DIAG_TOTAL_GC/{diag_total=$2}
  /^DIAG_IDENTITY_DIVERGE/{diag_diverge=$2}
  /^DIAG_SUM_GREEDY_VPC/{diag_sum_greedy=$2}
  /^DIAG_SUM_CB_VPC/{diag_sum_cb=$2}
  /^DIAG_SUM_ABS_VPC_DIFF/{diag_sum_absdiff=$2}
  /^DIAG_SAME_VPC_DIFF_LINE/{diag_same_vpc=$2}
  # NF==7 가드 필수: 위 헤더 줄들은 필드가 2개뿐이라 $7이 uninitialized인데,
  # mawk는 uninitialized 필드를 문자열 ""로 보고 "" != 0 을 참으로 평가함 ->
  # 가드가 없으면 헤더 줄 개수만큼 nonzero_blocks가 부풀려짐 (2026-07-31 발견).
  NF==7 && $7!=0{sum+=$7; n++; if($7>max) max=$7; blk_sum+=$7; blk_sumsq+=$7*$7; blk_n++}
  # erase_cv_all: 전체 블록(erase 0회인 블록 포함) 기준 변동계수.
  # erase_cv(아래, nonzero만)는 정책마다 모집단 크기가 달라져서(예: Greedy 85,624 vs
  # CB 89,433) 엄밀한 비교가 아님 -> 마모 균등도는 모집단이 고정된 이 값으로 볼 것.
  NF==7 {all_sum+=$7; all_sumsq+=$7*$7; all_n++}
  END {
    printf "nonzero_blocks=%d sum=%d max=%d", n, sum, max
    printf " slc_migration_cnt=%d slc_migrate_pages=%d", slc_migration_cnt, slc_migrate
    printf " tlc_gc_cnt=%d tlc_gc_migrate_pages=%d", tlc_gc_cnt, tlc_gc_migrate
    printf " legacy_gc_migrate_pages=%d", legacy_migrate
    printf " total_gc=%d greedy_vs_cb_identity_diverge=%d", diag_total, diag_diverge
    if (diag_total > 0) {
      printf " avg_greedy_vpc=%.3f avg_cb_vpc=%.3f avg_abs_vpc_diff=%.3f same_vpc_different_line_ratio=%.4f",
             diag_sum_greedy/diag_total, diag_sum_cb/diag_total, diag_sum_absdiff/diag_total,
             (diag_diverge>0 ? diag_same_vpc/diag_diverge : 0)
    }
    if (blk_n > 1) {
      mean = blk_sum/blk_n
      var = (blk_sumsq/blk_n) - (mean*mean)
      if (var < 0) var = 0
      printf " erase_cv=%.4f", sqrt(var)/mean
    }
    if (all_n > 1 && all_sum > 0) {
      amean = all_sum/all_n
      avar = (all_sumsq/all_n) - (amean*amean)
      if (avar < 0) avar = 0
      printf " erase_cv_all=%.4f", sqrt(avar)/amean
    }
    printf "\n"
  }' "$OUTDIR/erase_cnt.txt" > "$OUTDIR/summary.txt"

{
  echo "timestamp=$TS"
  echo "policy=$POLICY"
  echo "policy_name=$POLICY_NAME"
  echo "policy_target=slc_migration"
  echo "label=$LABEL"
  echo "workload=$WORKLOAD"
  echo "uniform_size=$UNIFORM_SIZE"
  echo "uniform_loops=$UNIFORM_LOOPS"
  echo "random_dist=${RANDOM_DIST:-uniform}"
  echo "norandommap=${NORANDOMMAP:-0}"
  echo "cold_size=$COLD_SIZE"
  echo "cold_touch_size=$COLD_TOUCH_SIZE"
  echo "hot_size=$HOT_SIZE"
  echo "hotcold_runtime=$HOTCOLD_RUNTIME"
  echo "disk_condition=fresh_module_reload_and_mkfs"
  echo "nvme_dev=$NVME_DEV"
  echo "memmap_start=$MEMMAP_START"
  echo "memmap_size=$MEMMAP_SIZE"
  echo "cpus=$NVME_CPUS"
  echo "tlc_gc_policy=$TLC_GC_POLICY"
  echo "slc_migration_policy=$POLICY"
  echo "slc_cache_ratio_percent=$SLC_CACHE_RATIO_PERCENT"
  echo "fio_cmd=$FIO_CMD"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"

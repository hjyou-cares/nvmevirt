#!/bin/bash
# 사용법: ./scripts/run_experiment.sh <policy: 0|1|2> <label> [workload: uniform|hotcold]
#   policy:   0=Greedy, 1=Random, 2=Cost-Benefit
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
#
# 예) 서버에서: NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
#              ./scripts/run_experiment.sh 0 randwrite6g uniform
#
# 정책 간 비교는 sysfs로 gc_policy만 바꾸는 게 아니라 매번 모듈을 완전히 리로드해야
# cb_clock/write pointer/free line list 같은 FTL 내부 상태가 오염되지 않는다는 게
# 2026-07-27에 확인됨 -> 이 스크립트는 매 실행마다 umount -> rmmod -> insmod(gc_policy
# 파라미터로 정책 지정) -> mkfs -> mount 를 처음부터 다시 수행함.
# sudo가 필요한 명령이 있어서 반드시 사용자 터미널에서 직접 실행할 것.
set -euo pipefail

POLICY="${1:?policy(0|1|2) 필요}"
LABEL="${2:?label 필요}"
WORKLOAD="${3:-uniform}"

NVME_DEV="${NVME_DEV:-/dev/nvme0n1}"
MEMMAP_START="${MEMMAP_START:-2G}"
MEMMAP_SIZE="${MEMMAP_SIZE:-1G}"
NVME_CPUS="${NVME_CPUS:-2,3}"
MOUNT_DIR="${MOUNT_DIR:-$HOME/nvme_mount}"
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

case "$POLICY" in
  0) POLICY_NAME=greedy ;;
  1) POLICY_NAME=random ;;
  2) POLICY_NAME=costbenefit ;;
  *) echo "policy는 0/1/2 중 하나여야 함" >&2; exit 1 ;;
esac

case "$WORKLOAD" in
  uniform|hotcold) ;;
  *) echo "workload는 uniform/hotcold 중 하나여야 함" >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$REPO_ROOT/results/${TS}_policy${POLICY}_${POLICY_NAME}_${LABEL}"
mkdir -p "$OUTDIR"
mkdir -p "$MOUNT_DIR"

# 정책 간 공정 비교를 위해 매 실험마다 모듈을 완전히 리로드해서 FTL 내부 상태를
# fresh하게 만든 뒤, 그 위에 새 파일시스템까지 새로 만듦 (2026-07-27/29 결정)
sudo umount "$MOUNT_DIR" 2>/dev/null || true
sudo rmmod nvmev 2>/dev/null || true
sudo insmod "$REPO_ROOT/nvmev.ko" memmap_start="$MEMMAP_START" memmap_size="$MEMMAP_SIZE" \
    cpus="$NVME_CPUS" gc_policy="$POLICY"

# insmod 직후 디바이스 노드가 바로 안 보일 수 있어 잠깐 대기
for i in $(seq 1 20); do
  [ -e "$NVME_DEV" ] && break
  sleep 0.5
done
[ -e "$NVME_DEV" ] || { echo "$NVME_DEV 가 생성되지 않았음 (dmesg 확인 필요)" >&2; exit 1; }

sudo mkfs -t ext4 -F "$NVME_DEV"
sudo mount "$NVME_DEV" "$MOUNT_DIR"
sudo chown "$USER:$USER" "$MOUNT_DIR"

echo reset | sudo tee /proc/nvmev/debug > /dev/null

if [ "$WORKLOAD" = "uniform" ]; then
  # loops=250: 서버(48G memmap)는 SSD 전체 용량이 44.9GB나 되고 블록 하나 용량도
  # 로컬 VM보다 훨씬 커서(로컬 32KB vs 서버 ~360KB), 로컬 VM 기준으로 잡았던
  # loops=10(총 6GB)로는 용량의 13%밖에 못 채워 GC가 전혀 안 돌았음(2026-07-29 확인).
  # loops=250이면 총 146GB(용량의 약 3.3배)를 써서 GC가 확실히 여러 번 트리거됨.
  FIO_CMD="fio --name=gc_stress --filename=\$MOUNT_DIR/testfile2 --size=$UNIFORM_SIZE --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=$UNIFORM_LOOPS --group_reporting"
  fio --name=gc_stress --filename="$MOUNT_DIR/testfile2" --size="$UNIFORM_SIZE" --rw=randwrite \
      --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops="$UNIFORM_LOOPS" \
      --group_reporting --output-format=json --output="$OUTDIR/fio.json"
else
  FIO_CMD="COLD_SIZE=$COLD_SIZE COLD_TOUCH_SIZE=$COLD_TOUCH_SIZE HOT_SIZE=$HOT_SIZE HOTCOLD_RUNTIME=$HOTCOLD_RUNTIME fio $REPO_ROOT/scripts/workloads/hotcold.fio --directory=\$MOUNT_DIR"
  fio "$REPO_ROOT/scripts/workloads/hotcold.fio" --directory="$MOUNT_DIR" \
      --output-format=json --output="$OUTDIR/fio.json"
fi

cat /proc/nvmev/debug > "$OUTDIR/erase_cnt.txt"

awk '
  /^GC_VALID_PAGE_MIGRATE_CNT/{migrate=$2}
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
    printf "nonzero_blocks=%d sum=%d max=%d gc_migrate_pages=%d", n, sum, max, migrate
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
  echo "label=$LABEL"
  echo "workload=$WORKLOAD"
  echo "uniform_size=$UNIFORM_SIZE"
  echo "uniform_loops=$UNIFORM_LOOPS"
  echo "cold_size=$COLD_SIZE"
  echo "cold_touch_size=$COLD_TOUCH_SIZE"
  echo "hot_size=$HOT_SIZE"
  echo "hotcold_runtime=$HOTCOLD_RUNTIME"
  echo "disk_condition=fresh_module_reload_and_mkfs"
  echo "nvme_dev=$NVME_DEV"
  echo "memmap_start=$MEMMAP_START"
  echo "memmap_size=$MEMMAP_SIZE"
  echo "cpus=$NVME_CPUS"
  echo "fio_cmd=$FIO_CMD"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"

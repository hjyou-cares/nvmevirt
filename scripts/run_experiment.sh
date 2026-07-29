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
  FIO_CMD="fio --name=gc_stress --filename=\$MOUNT_DIR/testfile2 --size=600M --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=250 --group_reporting"
  fio --name=gc_stress --filename="$MOUNT_DIR/testfile2" --size=600M --rw=randwrite \
      --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=250 \
      --group_reporting --output-format=json --output="$OUTDIR/fio.json"
else
  FIO_CMD="fio $REPO_ROOT/scripts/workloads/hotcold.fio --directory=\$MOUNT_DIR"
  fio "$REPO_ROOT/scripts/workloads/hotcold.fio" --directory="$MOUNT_DIR" \
      --output-format=json --output="$OUTDIR/fio.json"
fi

cat /proc/nvmev/debug > "$OUTDIR/erase_cnt.txt"

awk '$7!=0{sum+=$7; n++; if($7>max) max=$7} END {print "nonzero_blocks="n, "sum="sum, "max="max}' \
    "$OUTDIR/erase_cnt.txt" > "$OUTDIR/summary.txt"

{
  echo "timestamp=$TS"
  echo "policy=$POLICY"
  echo "policy_name=$POLICY_NAME"
  echo "label=$LABEL"
  echo "workload=$WORKLOAD"
  echo "disk_condition=fresh_module_reload_and_mkfs"
  echo "nvme_dev=$NVME_DEV"
  echo "memmap_start=$MEMMAP_START"
  echo "memmap_size=$MEMMAP_SIZE"
  echo "cpus=$NVME_CPUS"
  echo "fio_cmd=$FIO_CMD"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"

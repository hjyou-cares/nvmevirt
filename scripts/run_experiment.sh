#!/bin/bash
# 사용법: ./scripts/run_experiment.sh <policy: 0|1|2> <label> [workload: uniform|hotcold]
#   policy:   0=Greedy, 1=Random, 2=Cost-Benefit
#   label:    결과 폴더 구분용 자유 문자열 (예: randwrite6g, hotcold1)
#   workload: uniform(기본값, 균등 랜덤쓰기 6G) | hotcold(콜드 500M 1회 + 핫 50M x120루프)
# sudo가 필요한 명령이 있어서 반드시 사용자 터미널에서 직접 실행할 것.
set -euo pipefail

POLICY="${1:?policy(0|1|2) 필요}"
LABEL="${2:?label 필요}"
WORKLOAD="${3:-uniform}"

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

echo "$POLICY" | sudo tee /sys/module/nvmev/parameters/gc_policy > /dev/null

# 정책 간 공정 비교를 위해 매 실험마다 완전히 새 파일시스템으로 시작 (2026-07-27 결정)
sudo umount "$HOME/nvme_mount" 2>/dev/null || true
sudo mkfs -t ext4 /dev/nvme0n1
sudo mount /dev/nvme0n1 "$HOME/nvme_mount"
sudo chown "$USER:$USER" "$HOME/nvme_mount"

echo reset | sudo tee /proc/nvmev/debug > /dev/null

if [ "$WORKLOAD" = "uniform" ]; then
  FIO_CMD="fio --name=gc_stress --filename=\$HOME/nvme_mount/testfile2 --size=600M --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 --group_reporting"
  fio --name=gc_stress --filename="$HOME/nvme_mount/testfile2" --size=600M --rw=randwrite \
      --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 \
      --group_reporting --output-format=json --output="$OUTDIR/fio.json"
else
  FIO_CMD="fio $REPO_ROOT/scripts/workloads/hotcold.fio --directory=\$HOME/nvme_mount"
  fio "$REPO_ROOT/scripts/workloads/hotcold.fio" --directory="$HOME/nvme_mount" \
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
  echo "disk_condition=fresh_mkfs"
  echo "fio_cmd=$FIO_CMD"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"

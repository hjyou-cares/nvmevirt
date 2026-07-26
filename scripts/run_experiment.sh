#!/bin/bash
# 사용법: ./scripts/run_experiment.sh <policy: 0|1|2> <label>
#   policy: 0=Greedy, 1=Random, 2=Cost-Benefit
#   label:  워크로드 구분용 자유 문자열 (예: randwrite6g, hotcold1)
# sudo가 필요한 명령이 있어서 반드시 사용자 터미널에서 직접 실행할 것.
set -euo pipefail

POLICY="${1:?policy(0|1|2) 필요}"
LABEL="${2:?label 필요}"

case "$POLICY" in
  0) POLICY_NAME=greedy ;;
  1) POLICY_NAME=random ;;
  2) POLICY_NAME=costbenefit ;;
  *) echo "policy는 0/1/2 중 하나여야 함" >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$REPO_ROOT/results/${TS}_policy${POLICY}_${POLICY_NAME}_${LABEL}"
mkdir -p "$OUTDIR"

echo "$POLICY" | sudo tee /sys/module/nvmev/parameters/gc_policy > /dev/null
echo reset | sudo tee /proc/nvmev/debug > /dev/null

fio --name=gc_stress --filename="$HOME/nvme_mount/testfile2" --size=600M --rw=randwrite \
    --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 \
    --group_reporting --output-format=json --output="$OUTDIR/fio.json"

cat /proc/nvmev/debug > "$OUTDIR/erase_cnt.txt"

awk '$7!=0{sum+=$7; n++; if($7>max) max=$7} END {print "nonzero_blocks="n, "sum="sum, "max="max}' \
    "$OUTDIR/erase_cnt.txt" > "$OUTDIR/summary.txt"

{
  echo "timestamp=$TS"
  echo "policy=$POLICY"
  echo "policy_name=$POLICY_NAME"
  echo "label=$LABEL"
  echo "fio_cmd=fio --name=gc_stress --filename=\$HOME/nvme_mount/testfile2 --size=600M --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 --group_reporting"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"

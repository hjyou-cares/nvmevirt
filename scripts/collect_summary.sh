#!/bin/bash
# results/ 밑의 모든 run을 훑어서 정책별 erase 통계 + latency를 CSV 한 줄씩으로 모음.
# 사용법: ./scripts/collect_summary.sh > results/summary.csv
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "timestamp,policy,policy_name,label,nonzero_blocks,erase_sum,erase_max,lat_avg_ns,lat_p99_ns"

for dir in "$REPO_ROOT"/results/*/; do
  [ -f "$dir/meta.txt" ] || continue

  timestamp=$(grep '^timestamp=' "$dir/meta.txt" | cut -d= -f2)
  policy=$(grep '^policy=' "$dir/meta.txt" | cut -d= -f2)
  policy_name=$(grep '^policy_name=' "$dir/meta.txt" | cut -d= -f2)
  label=$(grep '^label=' "$dir/meta.txt" | cut -d= -f2)

  nonzero_blocks=$(grep -o 'nonzero_blocks=[0-9]*' "$dir/summary.txt" | cut -d= -f2)
  erase_sum=$(grep -o 'sum=[0-9]*' "$dir/summary.txt" | cut -d= -f2)
  erase_max=$(grep -o 'max=[0-9]*' "$dir/summary.txt" | cut -d= -f2)

  lat_avg_ns=$(jq '.jobs[0].write.lat_ns.mean' "$dir/fio.json")
  lat_p99_ns=$(jq '.jobs[0].write.clat_ns.percentile["99.000000"]' "$dir/fio.json")

  echo "$timestamp,$policy,$policy_name,$label,$nonzero_blocks,$erase_sum,$erase_max,$lat_avg_ns,$lat_p99_ns"
done

#!/bin/bash
# results/ 밑의 모든 run을 훑어서 정책별 erase 통계 + latency를 CSV 한 줄씩으로 모음.
# 사용법: ./scripts/collect_summary.sh > results/summary.csv
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "timestamp,policy,policy_name,label,workload,nonzero_blocks,erase_sum,erase_max,lat_avg_ns,lat_p99_ns"

for dir in "$REPO_ROOT"/results/*/; do
  [ -f "$dir/meta.txt" ] || continue

  timestamp=$(grep '^timestamp=' "$dir/meta.txt" | cut -d= -f2)
  policy=$(grep '^policy=' "$dir/meta.txt" | cut -d= -f2)
  policy_name=$(grep '^policy_name=' "$dir/meta.txt" | cut -d= -f2)
  label=$(grep '^label=' "$dir/meta.txt" | cut -d= -f2)
  workload=$(grep '^workload=' "$dir/meta.txt" | cut -d= -f2 || true)

  nonzero_blocks=$(grep -o 'nonzero_blocks=[0-9]*' "$dir/summary.txt" | cut -d= -f2)
  erase_sum=$(grep -o 'sum=[0-9]*' "$dir/summary.txt" | cut -d= -f2)
  erase_max=$(grep -o 'max=[0-9]*' "$dir/summary.txt" | cut -d= -f2)

  # hotcold 워크로드는 fio job이 여러 개(cold_fill/cold_touch/hot_churn)라
  # jobs[0]은 콜드파일 순차쓰기 구간이 되어버림 -- GC 부하가 실제로 걸리는
  # 마지막 job(그룹)을 봐야 함 (2026-07-30 발견). uniform은 job이 하나뿐이라
  # jobs[-1]이 jobs[0]과 동일해서 영향 없음.
  lat_avg_ns=$(jq '.jobs[-1].write.lat_ns.mean' "$dir/fio.json")
  lat_p99_ns=$(jq '.jobs[-1].write.clat_ns.percentile["99.000000"]' "$dir/fio.json")

  echo "$timestamp,$policy,$policy_name,$label,$workload,$nonzero_blocks,$erase_sum,$erase_max,$lat_avg_ns,$lat_p99_ns"
done

#!/bin/bash
# results/ 밑의 모든 run을 훑어서 실험 조건/erase 통계/migration 통계/latency를 CSV로 모은다.
# 사용법: ./scripts/collect_summary.sh > results/summary.csv
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

infer_timestamp_from_path() {
  local path="$1"

  printf '%s\n' "$path" | sed -nE 's#.*(local_[0-9]{8}_[0-9]{6}|[0-9]{8}_[0-9]{6}).*#\1#p' | head -n1
}

get_meta_value() {
  local file="$1"
  local key="$2"

  [ -f "$file" ] || return 0
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, "", $0); print $0; exit }' "$file"
}

get_first_meta_value() {
  local file="$1"
  shift
  local key
  local value

  for key in "$@"; do
    value=$(get_meta_value "$file" "$key")
    if [ -n "$value" ]; then
      printf '%s\n' "$value"
      return 0
    fi
  done
}

get_summary_value() {
  local file="$1"
  local key="$2"

  [ -f "$file" ] || return 0
  awk -v key="$key" '
    {
      for (i = 1; i <= NF; i++) {
        if ($i ~ ("^" key "=")) {
          split($i, kv, "=")
          print kv[2]
          exit
        }
      }
    }' "$file"
}

get_counter_value() {
  local file="$1"
  local key="$2"

  [ -f "$file" ] || return 0
  awk -v key="$key" '$1 == key { print $2; exit }' "$file"
}

get_fio_value() {
  local file="$1"
  local expr="$2"

  [ -f "$file" ] || return 0
  jq -r "$expr // \"\"" "$file"
}

echo "timestamp,policy,policy_name,policy_target,label,workload,slc_migration_policy,tlc_gc_policy,slc_cache_ratio_percent,random_dist,norandommap,uniform_size,uniform_loops,cold_size,cold_touch_size,hot_size,hotcold_runtime,memmap_size,nonzero_blocks,erase_sum,erase_max,slc_migration_cnt,slc_migrate_pages,tlc_gc_cnt,tlc_gc_migrate_pages,legacy_gc_migrate_pages,erase_cv,erase_cv_all,write_bw_kib,write_iops,write_lat_avg_ns,write_lat_p99_ns,read_bw_kib,read_iops,read_lat_avg_ns,read_lat_p99_ns"

while IFS= read -r -d '' meta_file; do
  dir="${meta_file%/meta.txt}"
  summary_file="$dir/summary.txt"
  fio_file="$dir/fio.json"
  debug_file=""

  if [ -f "$dir/debug.txt" ]; then
    debug_file="$dir/debug.txt"
  elif [ -f "$dir/erase_cnt.txt" ]; then
    debug_file="$dir/erase_cnt.txt"
  fi

  timestamp=$(get_meta_value "$meta_file" "timestamp")
  [ -n "$timestamp" ] || timestamp=$(infer_timestamp_from_path "$dir")
  policy=$(get_first_meta_value "$meta_file" "policy" "slc_migration_policy")
  policy_name=$(get_meta_value "$meta_file" "policy_name")
  policy_target=$(get_meta_value "$meta_file" "policy_target")
  label=$(get_meta_value "$meta_file" "label")
  workload=$(get_meta_value "$meta_file" "workload")
  slc_migration_policy=$(get_first_meta_value "$meta_file" "slc_migration_policy" "policy")
  tlc_gc_policy=$(get_first_meta_value "$meta_file" "tlc_gc_policy" "gc_policy")
  slc_cache_ratio_percent=$(get_meta_value "$meta_file" "slc_cache_ratio_percent")
  random_dist=$(get_meta_value "$meta_file" "random_dist")
  norandommap=$(get_meta_value "$meta_file" "norandommap")
  uniform_size=$(get_first_meta_value "$meta_file" "uniform_size" "baseline_size")
  uniform_loops=$(get_first_meta_value "$meta_file" "uniform_loops" "baseline_loops")
  cold_size=$(get_meta_value "$meta_file" "cold_size")
  cold_touch_size=$(get_meta_value "$meta_file" "cold_touch_size")
  hot_size=$(get_meta_value "$meta_file" "hot_size")
  hotcold_runtime=$(get_meta_value "$meta_file" "hotcold_runtime")
  memmap_size=$(get_meta_value "$meta_file" "memmap_size")
  [ -n "$label" ] || label=$(get_first_meta_value "$meta_file" "variant" "mode")
  [ -n "$workload" ] || workload=$(get_meta_value "$meta_file" "mode")

  nonzero_blocks=$(get_summary_value "$summary_file" "nonzero_blocks")
  erase_sum=$(get_summary_value "$summary_file" "sum")
  erase_max=$(get_summary_value "$summary_file" "max")
  slc_migration_cnt=$(get_summary_value "$summary_file" "slc_migration_cnt")
  slc_migrate_pages=$(get_summary_value "$summary_file" "slc_migrate_pages")
  tlc_gc_cnt=$(get_summary_value "$summary_file" "tlc_gc_cnt")
  tlc_gc_migrate_pages=$(get_summary_value "$summary_file" "tlc_gc_migrate_pages")
  legacy_gc_migrate_pages=$(get_summary_value "$summary_file" "legacy_gc_migrate_pages")
  erase_cv=$(get_summary_value "$summary_file" "erase_cv")
  erase_cv_all=$(get_summary_value "$summary_file" "erase_cv_all")

  if [ -n "$debug_file" ]; then
    [ -n "$slc_migration_cnt" ] || slc_migration_cnt=$(get_counter_value "$debug_file" "SLC_MIGRATION_CNT")
    [ -n "$slc_migrate_pages" ] || slc_migrate_pages=$(get_counter_value "$debug_file" "SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT")
    [ -n "$tlc_gc_cnt" ] || tlc_gc_cnt=$(get_counter_value "$debug_file" "TLC_GC_CNT")
    [ -n "$tlc_gc_migrate_pages" ] || tlc_gc_migrate_pages=$(get_counter_value "$debug_file" "TLC_GC_VALID_PAGE_MIGRATE_CNT")
    [ -n "$legacy_gc_migrate_pages" ] || legacy_gc_migrate_pages=$(get_counter_value "$debug_file" "GC_VALID_PAGE_MIGRATE_CNT")
  fi

  # hotcold 워크로드는 fio job이 여러 개(cold_fill/cold_touch/hot_churn)라
  # jobs[0]은 콜드파일 순차쓰기 구간이 되어버림 -- GC 부하가 실제로 걸리는
  # 마지막 job(그룹)을 봐야 함 (2026-07-30 발견). uniform은 job이 하나뿐이라
  # jobs[-1]이 jobs[0]과 동일해서 영향 없음.
  write_bw_kib=$(get_fio_value "$fio_file" '.jobs[-1].write.bw')
  write_iops=$(get_fio_value "$fio_file" '.jobs[-1].write.iops')
  write_lat_avg_ns=$(get_fio_value "$fio_file" '.jobs[-1].write.lat_ns.mean')
  write_lat_p99_ns=$(get_fio_value "$fio_file" '.jobs[-1].write.clat_ns.percentile["99.000000"]')
  read_bw_kib=$(get_fio_value "$fio_file" '.jobs[-1].read.bw')
  read_iops=$(get_fio_value "$fio_file" '.jobs[-1].read.iops')
  read_lat_avg_ns=$(get_fio_value "$fio_file" '.jobs[-1].read.lat_ns.mean')
  read_lat_p99_ns=$(get_fio_value "$fio_file" '.jobs[-1].read.clat_ns.percentile["99.000000"]')

  echo "$timestamp,$policy,$policy_name,$policy_target,$label,$workload,$slc_migration_policy,$tlc_gc_policy,$slc_cache_ratio_percent,$random_dist,$norandommap,$uniform_size,$uniform_loops,$cold_size,$cold_touch_size,$hot_size,$hotcold_runtime,$memmap_size,$nonzero_blocks,$erase_sum,$erase_max,$slc_migration_cnt,$slc_migrate_pages,$tlc_gc_cnt,$tlc_gc_migrate_pages,$legacy_gc_migrate_pages,$erase_cv,$erase_cv_all,$write_bw_kib,$write_iops,$write_lat_avg_ns,$write_lat_p99_ns,$read_bw_kib,$read_iops,$read_lat_avg_ns,$read_lat_p99_ns"
done < <(find "$REPO_ROOT/results" -type f -name meta.txt -print0 | sort -z)

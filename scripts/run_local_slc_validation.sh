#!/bin/bash

set -euo pipefail

MODE="${1:-all}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NVME_DEV="${NVME_DEV:-/dev/nvme0n1}"
MEMMAP_START="${MEMMAP_START:-2G}"
MEMMAP_SIZE="${MEMMAP_SIZE:-1G}"
NVME_CPUS="${NVME_CPUS:-2,3}"
MOUNT_DIR="${MOUNT_DIR:-$HOME/nvme_mount}"
TLC_GC_POLICY="${TLC_GC_POLICY:-0}"
SLC_POLICY="${SLC_POLICY:-0}"
SLC_RATIO_ON="${SLC_RATIO_ON:-10}"
SLC_RATIO_OFF="${SLC_RATIO_OFF:-0}"

BASELINE_SIZE="${BASELINE_SIZE:-600M}"
BASELINE_LOOPS="${BASELINE_LOOPS:-10}"
BASELINE_RW="${BASELINE_RW:-randwrite}"

SLC_ONLY_SIZE="${SLC_ONLY_SIZE:-64M}"
SLC_ONLY_READ_BS="${SLC_ONLY_READ_BS:-4k}"

OVERFLOW_SIZE="${OVERFLOW_SIZE:-384M}"
OVERFLOW_READ_BS="${OVERFLOW_READ_BS:-4k}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_local_slc_validation.sh baseline
  ./scripts/run_local_slc_validation.sh slc_only
  ./scripts/run_local_slc_validation.sh overflow
  ./scripts/run_local_slc_validation.sh all

Modes:
  baseline  Compare TLC-only baseline (ratio=0) vs SLC cache on (ratio=10 by default).
  slc_only  Run a write+read workload that should remain inside SLC.
  overflow  Run a write+read workload that should trigger SLC->TLC migration.
  all       Run baseline, slc_only, and overflow in sequence.

Environment overrides:
  NVME_DEV / MEMMAP_START / MEMMAP_SIZE / NVME_CPUS / MOUNT_DIR
  TLC_GC_POLICY     default: 0
  SLC_POLICY        default: 0
  SLC_RATIO_ON      default: 10
  SLC_RATIO_OFF     default: 0
  BASELINE_SIZE     default: 600M
  BASELINE_LOOPS    default: 10
  BASELINE_RW       default: randwrite
  SLC_ONLY_SIZE     default: 64M
  OVERFLOW_SIZE     default: 384M
EOF
}

require_block_device() {
  if command -v udevadm >/dev/null 2>&1; then
    sudo udevadm settle
  fi

  [ -b "$NVME_DEV" ] || {
    echo "$NVME_DEV not found after insmod" >&2
    exit 1
  }
}

cleanup_mount() {
  sudo umount "$MOUNT_DIR" 2>/dev/null || true
  sudo rmmod nvmev 2>/dev/null || true
}

reload_module() {
  local slc_ratio="$1"

  sudo umount "$MOUNT_DIR" 2>/dev/null || true
  sudo rmmod nvmev 2>/dev/null || true

  sudo insmod "$REPO_ROOT/nvmev.ko" \
    memmap_start="$MEMMAP_START" \
    memmap_size="$MEMMAP_SIZE" \
    cpus="$NVME_CPUS" \
    gc_policy="$TLC_GC_POLICY" \
    slc_migration_policy="$SLC_POLICY" \
    slc_cache_ratio_percent="$slc_ratio"

  require_block_device

  sudo mkfs.ext4 -F "$NVME_DEV"
  sudo mount "$NVME_DEV" "$MOUNT_DIR"
  sudo chown "$USER:$USER" "$MOUNT_DIR"
  echo reset | sudo tee /proc/nvmev/debug >/dev/null
}

counter_value() {
  local file="$1"
  local key="$2"

  awk -v key="$key" '$1 == key { print $2; exit }' "$file"
}

fio_value() {
  local file="$1"
  local expr="$2"

  jq -r "$expr // \"\"" "$file"
}

append_fio_metrics() {
  local outfile="$1"
  local prefix="$2"
  local file="$3"

  {
    echo "${prefix}_bw_kib=$(fio_value "$file" '.jobs[-1].write.bw')"
    echo "${prefix}_iops=$(fio_value "$file" '.jobs[-1].write.iops')"
    echo "${prefix}_lat_avg_ns=$(fio_value "$file" '.jobs[-1].write.lat_ns.mean')"
    echo "${prefix}_lat_p99_ns=$(fio_value "$file" '.jobs[-1].write.clat_ns.percentile["99.000000"]')"
    echo "${prefix}_read_bw_kib=$(fio_value "$file" '.jobs[-1].read.bw')"
    echo "${prefix}_read_iops=$(fio_value "$file" '.jobs[-1].read.iops')"
    echo "${prefix}_read_lat_avg_ns=$(fio_value "$file" '.jobs[-1].read.lat_ns.mean')"
    echo "${prefix}_read_lat_p99_ns=$(fio_value "$file" '.jobs[-1].read.clat_ns.percentile["99.000000"]')"
  } >> "$outfile"
}

append_debug_counters() {
  local outfile="$1"
  local debug_file="$2"
  local key

  for key in \
    SLC_MIGRATION_CNT \
    SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT \
    TLC_GC_CNT \
    TLC_GC_VALID_PAGE_MIGRATE_CNT \
    USER_READ_SLC_PAGES \
    USER_READ_TLC_PAGES \
    USER_WRITE_SLC_PAGES \
    USER_WRITE_TLC_PAGES \
    INTERNAL_READ_SLC_PAGES \
    INTERNAL_READ_TLC_PAGES \
    INTERNAL_WRITE_SLC_PAGES \
    INTERNAL_WRITE_TLC_PAGES; do
    echo "$(printf '%s' "$key" | tr 'A-Z' 'a-z')=$(counter_value "$debug_file" "$key")" >> "$outfile"
  done
}

run_baseline_once() {
  local slc_ratio="$1"
  local label="$2"
  local outdir="$3"

  reload_module "$slc_ratio"

  fio --name=baseline_compare \
      --filename="$MOUNT_DIR/baseline_file" \
      --size="$BASELINE_SIZE" \
      --rw="$BASELINE_RW" \
      --bs=4k \
      --numjobs=1 \
      --iodepth=16 \
      --ioengine=libaio \
      --direct=1 \
      --loops="$BASELINE_LOOPS" \
      --group_reporting \
      --output-format=json \
      --output="$outdir/fio.json"

  cat /proc/nvmev/debug > "$outdir/debug.txt"
  {
    echo "mode=baseline"
    echo "variant=$label"
    echo "policy=$SLC_POLICY"
    echo "slc_cache_ratio_percent=$slc_ratio"
    echo "baseline_size=$BASELINE_SIZE"
    echo "baseline_loops=$BASELINE_LOOPS"
    echo "baseline_rw=$BASELINE_RW"
    echo "nvme_dev=$NVME_DEV"
    echo "memmap_start=$MEMMAP_START"
    echo "memmap_size=$MEMMAP_SIZE"
    echo "cpus=$NVME_CPUS"
    echo "tlc_gc_policy=$TLC_GC_POLICY"
  } > "$outdir/meta.txt"
  append_fio_metrics "$outdir/summary.txt" "baseline" "$outdir/fio.json"
  append_debug_counters "$outdir/summary.txt" "$outdir/debug.txt"
  cleanup_mount
}

run_baseline() {
  local base="$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_baseline_compare"
  mkdir -p "$base/tlc_only" "$base/slc_on" "$MOUNT_DIR"

  run_baseline_once "$SLC_RATIO_OFF" "tlc_only" "$base/tlc_only"
  run_baseline_once "$SLC_RATIO_ON" "slc_on" "$base/slc_on"

  echo "result_dir=$base"
}

run_validation_case() {
  local mode="$1"
  local slc_ratio="$2"
  local file_size="$3"
  local read_bs="$4"
  local outdir="$5"
  local filename="$MOUNT_DIR/${mode}_file"

  mkdir -p "$outdir"
  reload_module "$slc_ratio"

  fio --name="${mode}_write" \
      --filename="$filename" \
      --size="$file_size" \
      --rw=write \
      --bs=4k \
      --numjobs=1 \
      --iodepth=16 \
      --ioengine=libaio \
      --direct=1 \
      --group_reporting \
      --output-format=json \
      --output="$outdir/write.json"

  fio --name="${mode}_read" \
      --filename="$filename" \
      --size="$file_size" \
      --rw=randread \
      --bs="$read_bs" \
      --numjobs=1 \
      --iodepth=16 \
      --ioengine=libaio \
      --direct=1 \
      --group_reporting \
      --output-format=json \
      --output="$outdir/read.json"

  cat /proc/nvmev/debug > "$outdir/debug.txt"
  {
    echo "mode=$mode"
    echo "policy=$SLC_POLICY"
    echo "slc_cache_ratio_percent=$slc_ratio"
    echo "file_size=$file_size"
    echo "read_bs=$read_bs"
    echo "nvme_dev=$NVME_DEV"
    echo "memmap_start=$MEMMAP_START"
    echo "memmap_size=$MEMMAP_SIZE"
    echo "cpus=$NVME_CPUS"
    echo "tlc_gc_policy=$TLC_GC_POLICY"
  } > "$outdir/meta.txt"
  append_fio_metrics "$outdir/summary.txt" "write_phase" "$outdir/write.json"
  append_fio_metrics "$outdir/summary.txt" "read_phase" "$outdir/read.json"
  append_debug_counters "$outdir/summary.txt" "$outdir/debug.txt"
  cleanup_mount

  echo "result_dir=$outdir"
  rg 'SLC_MIGRATION_CNT|SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT|TLC_GC_CNT|TLC_GC_VALID_PAGE_MIGRATE_CNT|USER_.*_PAGES|INTERNAL_.*_PAGES' \
    "$outdir/debug.txt" || true
}

run_slc_only() {
  run_validation_case \
    "slc_only" \
    "$SLC_RATIO_ON" \
    "$SLC_ONLY_SIZE" \
    "$SLC_ONLY_READ_BS" \
    "$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_only_validation"
}

run_overflow() {
  run_validation_case \
    "overflow" \
    "$SLC_RATIO_ON" \
    "$OVERFLOW_SIZE" \
    "$OVERFLOW_READ_BS" \
    "$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_overflow_validation"
}

trap cleanup_mount EXIT

case "$MODE" in
  baseline)
    mkdir -p "$MOUNT_DIR"
    run_baseline
    ;;
  slc_only)
    mkdir -p "$MOUNT_DIR"
    run_slc_only
    ;;
  overflow)
    mkdir -p "$MOUNT_DIR"
    run_overflow
    ;;
  all)
    mkdir -p "$MOUNT_DIR"
    run_baseline
    run_slc_only
    run_overflow
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

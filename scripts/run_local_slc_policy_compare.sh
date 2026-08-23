#!/bin/bash

set -euo pipefail

MODE="${1:-compare}"
SINGLE_POLICY="${2:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NVME_DEV="${NVME_DEV:-/dev/nvme0n1}"
MEMMAP_START="${MEMMAP_START:-2G}"
MEMMAP_SIZE="${MEMMAP_SIZE:-1G}"
NVME_CPUS="${NVME_CPUS:-2,3}"
MOUNT_DIR="${MOUNT_DIR:-$HOME/nvme_mount}"
TLC_GC_POLICY="${TLC_GC_POLICY:-0}"

SMOKE_SIZE="${SMOKE_SIZE:-128M}"
SMOKE_LOOPS="${SMOKE_LOOPS:-20}"
COMPARE_SIZE="${COMPARE_SIZE:-600M}"
COMPARE_LOOPS="${COMPARE_LOOPS:-10}"
VERIFY_SIZE="${VERIFY_SIZE:-600M}"
VERIFY_LOOPS="${VERIFY_LOOPS:-10}"
VERIFY_BS="${VERIFY_BS:-4k}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_local_slc_policy_compare.sh smoke [policy]
  ./scripts/run_local_slc_policy_compare.sh compare
  ./scripts/run_local_slc_policy_compare.sh verify [policy]

Modes:
  smoke    Run a short local smoke test. Default policy is 0 unless a policy is given.
  compare  Run slc_migration_policy=0/1/2/3 with fresh reload for each run.
  verify   Run fio CRC verification for one policy. Default policy is 0.

Environment overrides:
  NVME_DEV         default: /dev/nvme0n1
  MEMMAP_START     default: 2G
  MEMMAP_SIZE      default: 1G
  NVME_CPUS        default: 2,3
  MOUNT_DIR        default: $HOME/nvme_mount
  TLC_GC_POLICY    default: 0
  SMOKE_SIZE       default: 128M
  SMOKE_LOOPS      default: 20
  COMPARE_SIZE     default: 600M
  COMPARE_LOOPS    default: 10
  VERIFY_SIZE      default: 600M
  VERIFY_LOOPS     default: 10
  VERIFY_BS        default: 4k
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

reload_module() {
  local slc_policy="$1"

  sudo umount "$MOUNT_DIR" 2>/dev/null || true
  sudo rmmod nvmev 2>/dev/null || true

  sudo insmod "$REPO_ROOT/nvmev.ko" \
    memmap_start="$MEMMAP_START" \
    memmap_size="$MEMMAP_SIZE" \
    cpus="$NVME_CPUS" \
    gc_policy="$TLC_GC_POLICY" \
    slc_migration_policy="$slc_policy"

  require_block_device

  sudo mkfs.ext4 -F "$NVME_DEV"
  sudo mount "$NVME_DEV" "$MOUNT_DIR"
  sudo chown "$USER:$USER" "$MOUNT_DIR"
  echo reset | sudo tee /proc/nvmev/debug >/dev/null
}

cleanup_mount() {
  sudo umount "$MOUNT_DIR" 2>/dev/null || true
  sudo rmmod nvmev 2>/dev/null || true
}

run_smoke() {
  local policy="${1:-0}"
  local outdir

  outdir="$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_smoke_policy${policy}"
  mkdir -p "$outdir" "$MOUNT_DIR"

  reload_module "$policy"

  fio --name=smoke \
      --filename="$MOUNT_DIR/testfile" \
      --size="$SMOKE_SIZE" \
      --rw=randwrite \
      --bs=4k \
      --numjobs=1 \
      --iodepth=16 \
      --ioengine=libaio \
      --direct=1 \
      --loops="$SMOKE_LOOPS" \
      --group_reporting \
      --output-format=json \
      --output="$outdir/fio.json"

  cat /proc/nvmev/debug > "$outdir/debug.txt"
  cleanup_mount

  echo "result_dir=$outdir"
  rg 'SLC_MIGRATION_CNT|SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT|TLC_GC_CNT|TLC_GC_VALID_PAGE_MIGRATE_CNT|DIAG_' \
    "$outdir/debug.txt" || true
}

run_compare() {
  local outdir
  local policy

  outdir="$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_policy_compare"
  mkdir -p "$outdir" "$MOUNT_DIR"

  for policy in 0 1 2 3; do
    echo "=== slc_migration_policy=$policy ==="
    reload_module "$policy"

    fio --name=gc_stress \
        --filename="$MOUNT_DIR/testfile" \
        --size="$COMPARE_SIZE" \
        --rw=randwrite \
        --bs=4k \
        --numjobs=1 \
        --iodepth=16 \
        --ioengine=libaio \
        --direct=1 \
        --loops="$COMPARE_LOOPS" \
        --group_reporting \
        --output-format=json \
        --output="$outdir/fio_policy${policy}.json"

    cat /proc/nvmev/debug > "$outdir/debug_policy${policy}.txt"
    cleanup_mount
  done

  echo "result_dir=$outdir"
  for policy in 0 1 2 3; do
    echo "== policy $policy =="
    rg 'SLC_MIGRATION_CNT|SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT|TLC_GC_CNT|TLC_GC_VALID_PAGE_MIGRATE_CNT|DIAG_' \
      "$outdir/debug_policy${policy}.txt" || true
  done
}

run_verify() {
  local policy="${1:-0}"
  local outdir
  local fio_cmd

  outdir="$REPO_ROOT/results/local_$(date +%Y%m%d_%H%M%S)_slc_verify_policy${policy}"
  mkdir -p "$outdir" "$MOUNT_DIR"

  reload_module "$policy"

  fio_cmd="fio --name=verify_crc --filename=$MOUNT_DIR/verifyfile --size=$VERIFY_SIZE --rw=randwrite --bs=$VERIFY_BS --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=$VERIFY_LOOPS --verify=crc32c --verify_fatal=1 --verify_state_save=0 --do_verify=1 --group_reporting"
  echo "$fio_cmd" > "$outdir/fio_cmd.txt"

  fio --name=verify_crc \
      --filename="$MOUNT_DIR/verifyfile" \
      --size="$VERIFY_SIZE" \
      --rw=randwrite \
      --bs="$VERIFY_BS" \
      --numjobs=1 \
      --iodepth=16 \
      --ioengine=libaio \
      --direct=1 \
      --loops="$VERIFY_LOOPS" \
      --verify=crc32c \
      --verify_fatal=1 \
      --verify_state_save=0 \
      --do_verify=1 \
      --group_reporting \
      --output-format=json \
      --output="$outdir/fio.json"

  cat /proc/nvmev/debug > "$outdir/debug.txt"
  {
    echo "policy=$policy"
    echo "verify_size=$VERIFY_SIZE"
    echo "verify_loops=$VERIFY_LOOPS"
    echo "verify_bs=$VERIFY_BS"
    echo "nvme_dev=$NVME_DEV"
    echo "memmap_start=$MEMMAP_START"
    echo "memmap_size=$MEMMAP_SIZE"
    echo "cpus=$NVME_CPUS"
    echo "tlc_gc_policy=$TLC_GC_POLICY"
    echo "verify_status=pass"
  } > "$outdir/meta.txt"
  cleanup_mount

  echo "result_dir=$outdir"
  rg 'SLC_MIGRATION_CNT|SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT|TLC_GC_CNT|TLC_GC_VALID_PAGE_MIGRATE_CNT|DIAG_' \
    "$outdir/debug.txt" || true
}

trap cleanup_mount EXIT

case "$MODE" in
  smoke)
    mkdir -p "$MOUNT_DIR"
    run_smoke "${SINGLE_POLICY:-0}"
    ;;
  compare)
    mkdir -p "$MOUNT_DIR"
    run_compare
    ;;
  verify)
    mkdir -p "$MOUNT_DIR"
    run_verify "${SINGLE_POLICY:-0}"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

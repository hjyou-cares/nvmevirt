#!/bin/bash
# SLC cache가 이득을 보는 resident 구간과 migration 때문에 불리해지는 구간을
# 같은 binary/completion 설정에서 비교한다.

set -euo pipefail

MODE="${1:-dry-run}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO_ROOT/scripts/run_experiment.sh"
RESULTS_DIR="$REPO_ROOT/results"

CROSSOVER_REPS="${CROSSOVER_REPS:-1 2 3}"
CROSSOVER_RATIOS="0 10"
CROSSOVER_IODEPTH="1"
CROSSOVER_EARLY_COMPLETION="0"

RESIDENT_SIZE="1G"
RESIDENT_LOOPS="1"
OVERFLOW_SIZE="6G"
OVERFLOW_LOOPS="1"
SUSTAINED_SIZE="22G"
SUSTAINED_LOOPS="3"

FORCE_RERUN="${FORCE_RERUN:-0}"
DRY_RUN="${DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_slc_crossover_experiments.sh dry-run
  ./scripts/run_slc_crossover_experiments.sh resident
  ./scripts/run_slc_crossover_experiments.sh overflow
  ./scripts/run_slc_crossover_experiments.sh sustained
  ./scripts/run_slc_crossover_experiments.sh all

Default matrix (18 fresh-reload runs):
  resident   1G x 1,  ratio 0/10, 3 repetitions
  overflow   6G x 1,  ratio 0/10, 3 repetitions
  sustained 22G x 3,  ratio 0/10, 3 repetitions

Common controls:
  slc_migration_policy=Greedy, gc_policy=Greedy, bs=4k, iodepth=1,
  randrepeat=1, norandommap=1, write_early_completion=0.

Important overrides:
  CROSSOVER_REPS="1 2 3"       Run selected repetitions; aggregate with --reps.
  FORCE_RERUN=0|1               DRY_RUN=0|1

Ratios, workload sizes, iodepth, and completion mode are intentionally fixed so
completed labels always refer to the same report condition.
EOF
}

completed_label_exists() {
  local label="$1"
  local dir

  [ "$FORCE_RERUN" = "0" ] || return 1
  shopt -s nullglob
  for dir in "$RESULTS_DIR"/*_"$label"; do
    [ -s "$dir/meta.txt" ] || continue
    [ -s "$dir/summary.txt" ] || continue
    [ -s "$dir/fio.json" ] || continue
    if grep -Eq '"error"[[:space:]]*:[[:space:]]*[1-9][0-9]*' "$dir/fio.json"; then
      continue
    fi
    if grep -Eq '"error"[[:space:]]*:[[:space:]]*0' "$dir/fio.json"; then
      shopt -u nullglob
      return 0
    fi
  done
  shopt -u nullglob
  return 1
}

run_case() {
  local variant="$1"
  local rep="$2"
  local ratio="$3"
  local size="$4"
  local loops="$5"
  local label="slc_crossover_${variant}_ratio${ratio}_rep${rep}"

  if completed_label_exists "$label"; then
    echo "SKIP completed: $label"
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    printf 'suite=slc_crossover variant=%s rep=%s ratio=%s size=%s loops=%s iodepth=%s early_completion=%s label=%s\n' \
      "$variant" "$rep" "$ratio" "$size" "$loops" "$CROSSOVER_IODEPTH" \
      "$CROSSOVER_EARLY_COMPLETION" "$label"
    return 0
  fi

  echo "RUN: $label"
  EXPERIMENT_SUITE=slc_crossover \
  EXPERIMENT_VARIANT="$variant" \
  EXPERIMENT_REP="$rep" \
  SLC_CACHE_RATIO_PERCENT="$ratio" \
  WRITE_EARLY_COMPLETION="$CROSSOVER_EARLY_COMPLETION" \
  FIO_IODEPTH="$CROSSOVER_IODEPTH" \
  TLC_GC_POLICY=0 \
  UNIFORM_SIZE="$size" \
  UNIFORM_LOOPS="$loops" \
  RANDOM_DIST="" \
  NORANDOMMAP=1 \
  FIO_RANDREPEAT=1 \
    "$RUNNER" 0 "$label" uniform
}

run_variant() {
  local variant="$1"
  local size="$2"
  local loops="$3"
  local rep ratio

  for rep in $CROSSOVER_REPS; do
    for ratio in $CROSSOVER_RATIOS; do
      run_case "$variant" "$rep" "$ratio" "$size" "$loops"
    done
  done
}

case "$MODE" in
  dry-run)
    DRY_RUN=1
    run_variant resident "$RESIDENT_SIZE" "$RESIDENT_LOOPS"
    run_variant overflow "$OVERFLOW_SIZE" "$OVERFLOW_LOOPS"
    run_variant sustained "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS"
    ;;
  resident)
    run_variant resident "$RESIDENT_SIZE" "$RESIDENT_LOOPS"
    ;;
  overflow)
    run_variant overflow "$OVERFLOW_SIZE" "$OVERFLOW_LOOPS"
    ;;
  sustained)
    run_variant sustained "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS"
    ;;
  all)
    run_variant resident "$RESIDENT_SIZE" "$RESIDENT_LOOPS"
    run_variant overflow "$OVERFLOW_SIZE" "$OVERFLOW_LOOPS"
    run_variant sustained "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

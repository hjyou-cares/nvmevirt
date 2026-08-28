#!/bin/bash
# Practice 2 추가 실험 orchestrator.
#
# 세 실험축을 서로 분리한다.
#   ratio       Greedy migration을 고정하고 SLC ratio 0/5/10/20을 비교한다.
#   policy      ratio 10%, TLC GC Greedy를 고정하고 Zipf/Hot-cold 정책 반복을 채운다.
#   sensitivity ratio 10%에서 Uniform 정책 비교를 추가해 Zipf/Hot-cold와 함께 본다.
#
# 각 개별 run은 run_experiment.sh가 fresh reload + mkfs를 수행한다. 중간에 실패해도
# 같은 명령을 다시 실행하면 완료된 label은 건너뛰므로 이어서 실행할 수 있다.

set -euo pipefail

MODE="${1:-dry-run}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO_ROOT/scripts/run_experiment.sh"
RESULTS_DIR="$REPO_ROOT/results"

RATIO_VALUES="${RATIO_VALUES:-0 5 10 20}"
RATIO_REPS="${RATIO_REPS:-1 2 3}"
# Zipf rep1 이후 guarded reclaim code가 바뀌었으므로 통계용 세트는 현재 binary로
# rep1~rep3을 모두 다시 측정한다. 시간이 부족할 때만 POLICY_REPS="2 3"으로 줄인다.
POLICY_REPS="${POLICY_REPS:-1 2 3}"
SENSITIVITY_REPS="${SENSITIVITY_REPS:-1 2 3}"
POLICIES="${POLICIES:-0 1 2 3}"

BURST_SIZE="${BURST_SIZE:-1G}"
BURST_LOOPS="${BURST_LOOPS:-1}"
SUSTAINED_SIZE="${SUSTAINED_SIZE:-22G}"
SUSTAINED_LOOPS="${SUSTAINED_LOOPS:-7}"

COLD_SIZE="${COLD_SIZE:-30G}"
COLD_TOUCH_SIZE="${COLD_TOUCH_SIZE:-15G}"
HOT_SIZE="${HOT_SIZE:-1G}"
HOTCOLD_RUNTIME="${HOTCOLD_RUNTIME:-90}"

FORCE_RERUN="${FORCE_RERUN:-0}"
DRY_RUN="${DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_practice2_extended_experiments.sh dry-run
  ./scripts/run_practice2_extended_experiments.sh ratio
  ./scripts/run_practice2_extended_experiments.sh policy
  ./scripts/run_practice2_extended_experiments.sh sensitivity
  ./scripts/run_practice2_extended_experiments.sh all

Server example:
  NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
    ./scripts/run_practice2_extended_experiments.sh all

Important overrides:
  RATIO_VALUES="0 5 10 20"       RATIO_REPS="1 2 3"
  POLICY_REPS="1 2 3"            SENSITIVITY_REPS="1 2 3"
  POLICIES="0 1 2 3"             FORCE_RERUN=0|1
  DRY_RUN=1                        Print only, even for a real mode.

The default reruns all three policy repetitions with the current binary. If time is
tight, POLICY_REPS="2 3" reuses the accepted existing server rep1 as a fallback.
EOF
}

policy_name() {
  case "$1" in
    0) printf '%s\n' greedy ;;
    1) printf '%s\n' random ;;
    2) printf '%s\n' fifo ;;
    3) printf '%s\n' costbenefit ;;
    *) echo "Unknown policy: $1" >&2; return 1 ;;
  esac
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

print_case() {
  local suite="$1"
  local variant="$2"
  local rep="$3"
  local ratio="$4"
  local policy="$5"
  local workload="$6"
  local size="$7"
  local loops="$8"
  local dist="$9"
  local norandommap="${10}"
  local label="${11}"

  printf 'suite=%s variant=%s rep=%s ratio=%s policy=%s workload=%s size=%s loops=%s dist=%s norandommap=%s label=%s\n' \
    "$suite" "$variant" "$rep" "$ratio" "$policy" "$workload" "$size" "$loops" \
    "${dist:-uniform}" "$norandommap" "$label"
}

run_case() {
  local suite="$1"
  local variant="$2"
  local rep="$3"
  local ratio="$4"
  local policy="$5"
  local workload="$6"
  local size="$7"
  local loops="$8"
  local dist="$9"
  local norandommap="${10}"
  local label="${11}"

  if completed_label_exists "$label"; then
    echo "SKIP completed: $label"
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    print_case "$suite" "$variant" "$rep" "$ratio" "$policy" "$workload" \
      "$size" "$loops" "$dist" "$norandommap" "$label"
    return 0
  fi

  echo "RUN: $label"
  EXPERIMENT_SUITE="$suite" \
  EXPERIMENT_VARIANT="$variant" \
  EXPERIMENT_REP="$rep" \
  SLC_CACHE_RATIO_PERCENT="$ratio" \
  TLC_GC_POLICY=0 \
  UNIFORM_SIZE="$size" \
  UNIFORM_LOOPS="$loops" \
  RANDOM_DIST="$dist" \
  NORANDOMMAP="$norandommap" \
  COLD_SIZE="$COLD_SIZE" \
  COLD_TOUCH_SIZE="$COLD_TOUCH_SIZE" \
  HOT_SIZE="$HOT_SIZE" \
  HOTCOLD_RUNTIME="$HOTCOLD_RUNTIME" \
    "$RUNNER" "$policy" "$label" "$workload"
}

run_ratio_suite() {
  local ratio rep variant size loops label

  for ratio in $RATIO_VALUES; do
    for rep in $RATIO_REPS; do
      for variant in burst sustained; do
        if [ "$variant" = "burst" ]; then
          size="$BURST_SIZE"
          loops="$BURST_LOOPS"
        else
          size="$SUSTAINED_SIZE"
          loops="$SUSTAINED_LOOPS"
        fi
        label="ext_ratio_r${ratio}_${variant}_rep${rep}"
        run_case ratio_sweep "$variant" "$rep" "$ratio" 0 uniform \
          "$size" "$loops" "" 1 "$label"
      done
    done
  done
}

run_policy_suite() {
  local policy pname rep label

  for rep in $POLICY_REPS; do
    for policy in $POLICIES; do
      pname="$(policy_name "$policy")"
      label="ext_zipf_policy${policy}_${pname}_rep${rep}"
      run_case policy_repeat zipf "$rep" 10 "$policy" uniform \
        "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS" "zipf:1.2" 1 "$label"

      label="ext_hotcold_policy${policy}_${pname}_rep${rep}"
      run_case policy_repeat hotcold "$rep" 10 "$policy" hotcold \
        "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS" "" 0 "$label"
    done
  done
}

run_sensitivity_suite() {
  local policy pname rep label

  for rep in $SENSITIVITY_REPS; do
    for policy in $POLICIES; do
      pname="$(policy_name "$policy")"
      label="ext_uniform_policy${policy}_${pname}_rep${rep}"
      run_case workload_sensitivity uniform "$rep" 10 "$policy" uniform \
        "$SUSTAINED_SIZE" "$SUSTAINED_LOOPS" "" 1 "$label"
    done
  done
}

case "$MODE" in
  dry-run)
    DRY_RUN=1
    run_ratio_suite
    run_policy_suite
    run_sensitivity_suite
    ;;
  ratio)
    run_ratio_suite
    ;;
  policy)
    run_policy_suite
    ;;
  sensitivity)
    run_sensitivity_suite
    ;;
  all)
    run_ratio_suite
    run_policy_suite
    run_sensitivity_suite
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

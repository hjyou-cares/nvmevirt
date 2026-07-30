#!/bin/bash
# 사용법: ./scripts/run_filebench_experiment.sh <policy: 0|1|2> <label>
#   policy: 0=Greedy, 1=Random, 2=Cost-Benefit
#   label:  결과 폴더 구분용 자유 문자열
#
# run_experiment.sh(fio)와 같은 이유로 매 실행마다 모듈을 완전히 리로드함
# (cb_clock/write pointer/free line list 오염 방지, 2026-07-27 결정 참고).
# filebench는 WML 파일 안에서 셸 환경변수를 직접 못 읽어서, 이 스크립트가
# 매 실행마다 $MOUNT_DIR을 박아넣은 .f 파일을 결과 폴더 안에 새로 생성함.
#
# 환경변수 (fio 버전과 동일한 이름/기본값):
#   NVME_DEV, MEMMAP_START, MEMMAP_SIZE, NVME_CPUS, MOUNT_DIR
# filebench 워크로드 전용:
#   FB_FILESIZE (기본 2g)   파일 하나 크기 -- 작게 잡아서 짧은 시간에도 여러 번 덮어써지게 함
#   FB_RUNTIME  (기본 120)  filebench `run` 초 단위 (time-based, 정책 간 동일 시간 비교)
#   FB_NTHREADS (기본 4)    동시 writer 스레드 수
#
# sudo가 필요한 명령이 있어서 반드시 사용자 터미널에서 직접 실행할 것.
set -euo pipefail

POLICY="${1:?policy(0|1|2) 필요}"
LABEL="${2:?label 필요}"

NVME_DEV="${NVME_DEV:-/dev/nvme0n1}"
MEMMAP_START="${MEMMAP_START:-2G}"
MEMMAP_SIZE="${MEMMAP_SIZE:-1G}"
NVME_CPUS="${NVME_CPUS:-2,3}"
MOUNT_DIR="${MOUNT_DIR:-$HOME/nvme_mount}"

FB_FILESIZE="${FB_FILESIZE:-2g}"
FB_RUNTIME="${FB_RUNTIME:-120}"
FB_NTHREADS="${FB_NTHREADS:-4}"

case "$POLICY" in
  0) POLICY_NAME=greedy ;;
  1) POLICY_NAME=random ;;
  2) POLICY_NAME=costbenefit ;;
  *) echo "policy는 0/1/2 중 하나여야 함" >&2; exit 1 ;;
esac

command -v filebench >/dev/null 2>&1 || { echo "filebench가 설치되어 있지 않음 (sudo make install 필요)" >&2; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$REPO_ROOT/results/${TS}_policy${POLICY}_${POLICY_NAME}_${LABEL}_filebench"
mkdir -p "$OUTDIR"
mkdir -p "$MOUNT_DIR"

sudo umount "$MOUNT_DIR" 2>/dev/null || true
sudo rmmod nvmev 2>/dev/null || true
sudo insmod "$REPO_ROOT/nvmev.ko" memmap_start="$MEMMAP_START" memmap_size="$MEMMAP_SIZE" \
    cpus="$NVME_CPUS" gc_policy="$POLICY"

for i in $(seq 1 20); do
  [ -e "$NVME_DEV" ] && break
  sleep 0.5
done
[ -e "$NVME_DEV" ] || { echo "$NVME_DEV 가 생성되지 않았음 (dmesg 확인 필요)" >&2; exit 1; }

sudo mkfs -t ext4 -F "$NVME_DEV"
sudo mount "$NVME_DEV" "$MOUNT_DIR"
sudo chown "$USER:$USER" "$MOUNT_DIR"

echo reset | sudo tee /proc/nvmev/debug > /dev/null

# 워크로드: 작은 파일(FB_FILESIZE)에 4KB 랜덤쓰기 + 매 write마다 fsync로 실제 디바이스에
# 반영시킴(버퍼링으로 인해 filebench 종료 시점까지 반영이 안 되는 걸 방지). 파일이 작아서
# FB_RUNTIME 동안 여러 번 통째로 덮어써지며 invalid page가 누적 -> GC 트리거.
WORKLOAD_F="$OUTDIR/workload.f"
cat > "$WORKLOAD_F" <<EOF
set \$dir=$MOUNT_DIR
set \$filesize=$FB_FILESIZE
set \$iosize=4k
set \$nthreads=$FB_NTHREADS

define file name=gcfile,path=\$dir,size=\$filesize,prealloc,reuse

define process name=filewriter,instances=1
{
  thread name=filewriterthread,memsize=10m,instances=\$nthreads
  {
    flowop write name=write-file,filename=gcfile,random,iosize=\$iosize
    flowop fsync name=sync-file,filename=gcfile
  }
}

run $FB_RUNTIME
EOF

filebench -f "$WORKLOAD_F" 2>&1 | tee "$OUTDIR/filebench.log"
sync

cat /proc/nvmev/debug > "$OUTDIR/erase_cnt.txt"

# NF==7 가드 필수: 헤더 줄(GC_VALID_PAGE_MIGRATE_CNT/DIAG_*)은 필드가 2개뿐이라
# $7이 uninitialized인데 mawk는 이를 ""로 보고 "" != 0 을 참으로 평가함 -> 가드가
# 없으면 헤더 줄 개수만큼 nonzero_blocks가 부풀려짐 (2026-07-31 발견).
awk '/^GC_VALID_PAGE_MIGRATE_CNT/{migrate=$2}
     /^DIAG_TOTAL_GC/{diag_total=$2}
     /^DIAG_IDENTITY_DIVERGE/{diag_diverge=$2}
     /^DIAG_SUM_GREEDY_VPC/{diag_sum_greedy=$2}
     /^DIAG_SUM_CB_VPC/{diag_sum_cb=$2}
     /^DIAG_SUM_ABS_VPC_DIFF/{diag_sum_absdiff=$2}
     /^DIAG_SAME_VPC_DIFF_LINE/{diag_same_vpc=$2}
     NF==7 && $7!=0{sum+=$7; n++; if($7>max) max=$7}
     NF==7 {all_sum+=$7; all_sumsq+=$7*$7; all_n++}
    END {
      printf "nonzero_blocks=%d sum=%d max=%d gc_migrate_pages=%d", n, sum, max, migrate
      printf " total_gc=%d greedy_vs_cb_identity_diverge=%d", diag_total, diag_diverge
      if (diag_total > 0) {
        printf " avg_greedy_vpc=%.3f avg_cb_vpc=%.3f avg_abs_vpc_diff=%.3f same_vpc_different_line_ratio=%.4f",
               diag_sum_greedy/diag_total, diag_sum_cb/diag_total, diag_sum_absdiff/diag_total,
               (diag_diverge>0 ? diag_same_vpc/diag_diverge : 0)
      }
      if (all_n > 1 && all_sum > 0) {
        amean = all_sum/all_n
        avar = (all_sumsq/all_n) - (amean*amean)
        if (avar < 0) avar = 0
        printf " erase_cv_all=%.4f", sqrt(avar)/amean
      }
      printf "\n"
    }' "$OUTDIR/erase_cnt.txt" > "$OUTDIR/summary.txt"

{
  echo "timestamp=$TS"
  echo "policy=$POLICY"
  echo "policy_name=$POLICY_NAME"
  echo "label=$LABEL"
  echo "tool=filebench"
  echo "fb_filesize=$FB_FILESIZE"
  echo "fb_runtime=$FB_RUNTIME"
  echo "fb_nthreads=$FB_NTHREADS"
  echo "disk_condition=fresh_module_reload_and_mkfs"
  echo "nvme_dev=$NVME_DEV"
  echo "memmap_start=$MEMMAP_START"
  echo "memmap_size=$MEMMAP_SIZE"
  echo "cpus=$NVME_CPUS"
} > "$OUTDIR/meta.txt"

echo "결과 저장 위치: $OUTDIR"
cat "$OUTDIR/summary.txt"
grep -i "IO Summary" "$OUTDIR/filebench.log" || true

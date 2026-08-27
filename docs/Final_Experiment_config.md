# Final Experiment Config

기준 날짜: 2026-08-26 (수)

이 문서는 최종 실측 전에 한 번 보고 들어가는 요약 문서다.
목적은 두 가지다.

1. 2026-08-26에 로컬에서 무엇을 검증했는지 다시 확인한다.
2. 2026-08-27에 서버에서 어떤 명령으로 최종 실측을 돌릴지 고정한다.

최종 보고서 표에 들어갈 값은 서버 실측만 사용한다.
로컬 결과는 스크립트/계측/counter 검증용이다.

## 1. 현재 코드 상태

- `slc_cache_ratio_percent` insmod parameter가 추가돼 같은 빌드 산출물로 `0`(TLC-only baseline)과 `10`(SLC cache on)을 런타임에 바꿀 수 있다.
- `/proc/nvmev/debug`에는 아래 counter가 추가돼 host/internal I/O가 어느 media로 갔는지 직접 확인할 수 있다.
  - `USER_READ_SLC_PAGES`
  - `USER_READ_TLC_PAGES`
  - `USER_WRITE_SLC_PAGES`
  - `USER_WRITE_TLC_PAGES`
  - `INTERNAL_READ_SLC_PAGES`
  - `INTERNAL_READ_TLC_PAGES`
  - `INTERNAL_WRITE_SLC_PAGES`
  - `INTERNAL_WRITE_TLC_PAGES`
- `scripts/collect_summary.sh`는 정책 비교 실험용으로 `slc_cache_ratio_percent`, throughput/iops, read/write latency를 CSV로 뽑는다.
- 1번 결과물용 검증 스크립트 `scripts/run_local_slc_validation.sh`가 추가돼 `baseline`, `slc_only`, `overflow`, `all` 모드를 지원한다.

## 2. 2026-08-26 로컬 검증 결과

실행 디렉터리:

- `results/local_20260826_170836_slc_baseline_compare/`
- `results/local_20260826_171153_slc_only_validation/`
- `results/local_20260826_171226_slc_overflow_validation/`

### 2.1 Baseline Compare

`results/local_20260826_170836_slc_baseline_compare/tlc_only/summary.txt`

- `slc_cache_ratio_percent=0`
- `baseline_bw_kib=87124`
- `baseline_iops=21781.05502`
- `baseline_lat_avg_ns=733948.864036`
- `baseline_lat_p99_ns=1531904`
- `user_write_slc_pages=0`
- `user_write_tlc_pages=1540968`
- `slc_migration_cnt=0`

`results/local_20260826_170836_slc_baseline_compare/slc_on/summary.txt`

- `slc_cache_ratio_percent=10`
- `baseline_bw_kib=87964`
- `baseline_iops=21991.237866`
- `baseline_lat_avg_ns=726872.942466`
- `baseline_lat_p99_ns=1335296`
- `user_write_slc_pages=1541160`
- `user_write_tlc_pages=0`
- `slc_migration_cnt=45024`

해석:

- `ratio=0`에서는 host write가 TLC로만 갔다.
- `ratio=10`에서는 host write가 SLC로만 들어가고 migration이 발생했다.
- baseline 비교용 경로는 정상적으로 갈린다.

### 2.2 SLC-only Validation

`results/local_20260826_171153_slc_only_validation/summary.txt`

- `write_phase_bw_kib=76920`
- `write_phase_iops=19230.046948`
- `write_phase_lat_avg_ns=828733.864319`
- `write_phase_lat_p99_ns=2179072`
- `read_phase_read_bw_kib=46119`
- `read_phase_read_iops=11529.908515`
- `read_phase_read_lat_avg_ns=1386432.112488`
- `read_phase_read_lat_p99_ns=2039808`
- `slc_migration_cnt=0`
- `user_write_slc_pages=20236`
- `user_write_tlc_pages=0`
- `user_read_slc_pages=16388`
- `user_read_tlc_pages=0`

해석:

- host read/write가 모두 SLC에서만 처리됐다.
- migration과 TLC access가 없다.

### 2.3 Overflow Validation

`results/local_20260826_171226_slc_overflow_validation/summary.txt`

- `write_phase_bw_kib=76740`
- `write_phase_iops=19185.01171`
- `write_phase_lat_avg_ns=833157.058838`
- `write_phase_lat_p99_ns=2441216`
- `read_phase_read_bw_kib=39835`
- `read_phase_read_iops=9958.869415`
- `read_phase_read_lat_avg_ns=1605230.078807`
- `read_phase_read_lat_p99_ns=5079040`
- `slc_migration_cnt=54`
- `slc_migration_valid_page_migrate_cnt=1618`
- `user_read_slc_pages=98274`
- `user_read_tlc_pages=34`
- `user_write_slc_pages=102160`
- `internal_read_slc_pages=1618`
- `internal_write_tlc_pages=1618`

해석:

- SLC가 찬 뒤 SLC to TLC migration이 실제로 발생했다.
- migration write는 TLC로 들어갔다.
- host read 중 일부가 TLC로 갔다.
- 즉 "SLC가 차면 TLC에 read/write가 수행되는지"에 대한 로컬 검증은 통과했다.

## 3. 서버 실측 전 체크리스트

서버 접속 기록:

- `ssh hjyoo@147.46.241.107 -p 220`

서버 기본 환경 기록:

- 저장소 경로: `~/nvmevirt`
- 예상 device: `/dev/nvme1n1`
- 예상 insmod parameter:
  - `MEMMAP_START=16G`
  - `MEMMAP_SIZE=48G`
  - `NVME_CPUS=7,8`

실측 전 최소 체크:

1. `cd ~/nvmevirt`
2. `git status --short`
3. `git branch --show-current`
4. `lsblk`
5. `make -j$(nproc)` 또는 `make -j4`
6. 가능하면 `tmux` 세션 안에서 실행

`lsblk`에서 NVMeVirt 장치가 정말 `/dev/nvme1n1`인지 다시 확인한다.
장치명이 다르면 아래 명령의 `NVME_DEV`를 같이 바꾼다.

## 4. 서버에서 돌릴 명령

공통 환경:

```bash
cd ~/nvmevirt
export NVME_DEV=/dev/nvme1n1
export MEMMAP_START=16G
export MEMMAP_SIZE=48G
export NVME_CPUS=7,8
```

빌드:

```bash
make -j$(nproc)
```

### 4.1 1번 결과물: SLC Cache 구현 및 정상동작 검증

한 번에 전부:

```bash
NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
./scripts/run_local_slc_validation.sh all
```

개별 실행:

```bash
NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
./scripts/run_local_slc_validation.sh baseline

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
./scripts/run_local_slc_validation.sh slc_only

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
./scripts/run_local_slc_validation.sh overflow
```

실험 후 수동 확인 파일:

- `results/local_*_slc_baseline_compare/tlc_only/summary.txt`
- `results/local_*_slc_baseline_compare/slc_on/summary.txt`
- `results/local_*_slc_only_validation/summary.txt`
- `results/local_*_slc_overflow_validation/summary.txt`

### 4.2 2번 결과물: Migration Policy 4종 비교

`zipf_nrm` 4정책:

- 서버에서는 로컬 검증용 `600M x 10`을 쓰지 않는다.
- 서버 권장 조건은 `UNIFORM_SIZE=22G`, `UNIFORM_LOOPS=7`, `RANDOM_DIST=zipf:1.2`, `NORANDOMMAP=1`이다.

```bash
NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=22G UNIFORM_LOOPS=7 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 0 zipf_nrm_server_22g_rep1 uniform

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=22G UNIFORM_LOOPS=7 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 1 zipf_nrm_server_22g_rep1 uniform

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=22G UNIFORM_LOOPS=7 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 2 zipf_nrm_server_22g_rep1 uniform

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=22G UNIFORM_LOOPS=7 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 3 zipf_nrm_server_22g_rep1 uniform
```

`hotcold` 4정책:

- 서버에서는 로컬 검증용 `512M / 256M / 64M / 60s`를 쓰지 않는다.
- 서버 권장 조건은 스크립트 기본값 그대로 `COLD_SIZE=30G`, `COLD_TOUCH_SIZE=15G`, `HOT_SIZE=1G`, `HOTCOLD_RUNTIME=90`이다.

```bash
NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
COLD_SIZE=30G COLD_TOUCH_SIZE=15G HOT_SIZE=1G HOTCOLD_RUNTIME=90 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 0 hotcold_server_30g15g1g_rep1 hotcold

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
COLD_SIZE=30G COLD_TOUCH_SIZE=15G HOT_SIZE=1G HOTCOLD_RUNTIME=90 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 1 hotcold_server_30g15g1g_rep1 hotcold

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
COLD_SIZE=30G COLD_TOUCH_SIZE=15G HOT_SIZE=1G HOTCOLD_RUNTIME=90 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 2 hotcold_server_30g15g1g_rep1 hotcold

NVME_DEV=$NVME_DEV MEMMAP_START=$MEMMAP_START MEMMAP_SIZE=$MEMMAP_SIZE NVME_CPUS=$NVME_CPUS \
COLD_SIZE=30G COLD_TOUCH_SIZE=15G HOT_SIZE=1G HOTCOLD_RUNTIME=90 TLC_GC_POLICY=0 SLC_CACHE_RATIO_PERCENT=10 \
./scripts/run_experiment.sh 3 hotcold_server_30g15g1g_rep1 hotcold
```

정책 비교 집계:

```bash
./scripts/collect_summary.sh > /tmp/nvmevirt_summary.csv
```

## 5. 수동 검토가 필요한 부분

아래는 내일 서버 실측 전에 다시 확인해야 한다.

### 5.1 Validation 결과는 `collect_summary.sh` 자동 집계 대상이 아님

- `baseline`은 결과가 `tlc_only/`, `slc_on/` 하위 디렉터리에 들어간다.
- `slc_only`, `overflow`는 `write.json`, `read.json`, `summary.txt` 구조라 정책 비교 CSV 포맷과 다르다.
- 따라서 1번 결과물 표는 `summary.txt`를 직접 읽어서 수동 정리하는 편이 빠르다.

### 5.2 `overflow` 크기는 서버에서 다시 볼 필요가 있음

- 로컬에서는 `OVERFLOW_SIZE=384M`으로 migration이 발생했다.
- 서버에서는 용량과 line 규모가 다르므로 migration이 충분히 안 보이면 `OVERFLOW_SIZE`를 더 키워야 한다.
- 목적은 `SLC_MIGRATION_CNT > 0`, `INTERNAL_WRITE_TLC_PAGES > 0`, 가능하면 `USER_READ_TLC_PAGES > 0`를 확인하는 것이다.

### 5.3 정책 비교는 서버에서 fresh reload 조건 유지

- `run_experiment.sh`는 이미 `umount -> rmmod -> insmod -> mkfs -> mount`를 포함한다.
- 정책 비교는 반드시 이 fresh reload 조건으로만 해석한다.

### 5.4 최종 표에 넣을 값과 보조 지표를 분리

1번 결과물 표:

- Throughput
- Latency
- SLC/TLC read/write counter

2번 결과물 표:

- Throughput
- Latency
- 보조 지표: `slc_migrate_pages`, `erase_sum`, `erase_max`, 필요하면 `erase_cv_all`

### 5.5 필요 시 추가 workload

- 현재 대부분의 로컬 정책 비교는 `TLC_GC_CNT=0`이라 사실상 SLC migration policy 비교다.
- 과제 설명상 더 강한 해석이 필요하면 `TLC_GC_CNT > 0`가 나오는 workload 1세트를 추가할 수 있다.
- 다만 제출 시간 대비 우선순위는 낮다. 우선은 baseline, `SLC-only`, `overflow`, 정책 4종 비교를 서버에서 재수집하는 것이 먼저다.

## 6. 내일 실험 끝나면 바로 할 일

1. validation 결과에서 1번 결과물 표 초안 작성
2. `/tmp/nvmevirt_summary.csv`에서 정책 비교용 행만 뽑기
3. `zipf_nrm`와 `hotcold`를 분리해 2번 결과물 표 작성
4. 보고서 문장 정리:
   - `SLC-only`는 SLC에서만 처리됨
   - `overflow`는 migration과 TLC 접근이 확인됨
   - `ratio=0` 대비 `ratio=10` baseline 차이
   - 정책 비교에서는 `Random` 열세, `Cost-Benefit` migration cost 우세권, `FIFO` 낮은 `erase_max`

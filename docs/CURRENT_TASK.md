# Current Task

## 현재 흐름

- 실습2 WIP는 commit `8aa39ca`로 로컬/원격에 반영됐다.
- 핵심 변경 파일은 `conv_ftl.c`, `conv_ftl.h`, `main.c`, `ssd_config.h`이며, 실험 스크립트로 `scripts/run_local_slc_policy_compare.sh`, `scripts/run_experiment.sh`를 현재 실습2 의미에 맞게 정리 중이다.
- 현재 코드는 SLC/TLC pool metadata, pool-aware write path, SLC migration 첫 연결, migration/TLC GC counter 분리, migration policy 분리까지 들어간 상태다.
- 현재 worktree 기준 `SLC_CACHE_RATIO_PERCENT`는 `10`이라 SLC path가 컴파일 시 기본 활성이다.
- 로컬 VM smoke test와 fresh reload 기반 4정책 비교에서 SLC write, SLC to TLC migration, TLC GC가 모두 실제로 발생하는 것까지 확인했다.
- 서버 저장소 `~/nvmevirt`도 `practice2-slc-cache` 브랜치의 `8aa39ca`까지 동기화돼 있지만, 현재는 서버 이슈 때문에 로컬 우선으로 진행한다.

## 다음에 바로 할 일

1. `zipf_nrm`은 차이를 잘 드러냈으므로, 같은 조건으로 반복측정하거나 `collect_summary.sh`에 migration counter 열을 추가해 집계 자동화를 붙인다.
2. 그 다음에 local-sized `hotcold v7`도 한 번 돌려 `zipf_nrm`과 차이를 비교할지 결정한다.
3. 이후 SLC/TLC timing 분리와 legacy write path 정리로 다시 돌아간다.

## 미구현 핵심 항목

- SLC/TLC read-write timing 분리
- SLC/TLC `oneshot page size` 차이 반영
- read path timing 분리
- 데이터 정합성 검증

## 주의할 점

- 현재 기본 `SLC_CACHE_RATIO_PERCENT`는 `10`이다.
- `echo reset > /proc/nvmev/debug`는 counter만 초기화하고 FTL state는 초기화하지 않는다.
- 정책 비교는 반드시 `umount -> rmmod -> insmod -> mkfs -> mount`의 fresh reload 조건으로 수행한다.
- 로컬 VM은 용량이 작아 `No space left on device` 같은 파일시스템 노이즈가 섞이기 쉽다. 정책 비교는 서버 우선으로 진행한다.
- 실제 I/O는 아직 legacy `lm/wp/gc_wp`를 많이 공유한다.
- `gc_policy`는 TLC GC 전용 의미로 유지되고, `slc_migration_policy`가 별도로 추가됐다.
- 실습1의 heap staleness 교훈은 migration Cost-Benefit에도 그대로 다시 검토해야 한다.

## 오늘 확인한 결과

- 로컬 environment에서 `make`는 사용 가능했고, 사용자는 로컬 VM에서 smoke test와 fresh reload 기반 4정책 비교를 직접 완료했다.
- smoke test는 저장 파일이 남진 않았지만, 기존과 같은 방향으로 SLC migration/TLC GC가 실제로 도는 것을 확인했다.
- 4정책 비교 결과는 `results/local_20260823_212734_slc_policy_compare/`에 저장됐다.
  - policy `0` Greedy:
    - `TLC_GC_CNT 15540`
    - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
    - `SLC_MIGRATION_CNT 45060`
    - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440939`
    - fio runtime 약 `292211 ms`
  - policy `1` Random:
    - `TLC_GC_CNT 5835`
    - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
    - `SLC_MIGRATION_CNT 45018`
    - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1130392`
    - fio runtime 약 `73571 ms`
  - policy `2` FIFO:
    - `TLC_GC_CNT 15527`
    - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
    - `SLC_MIGRATION_CNT 45020`
    - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440508`
    - fio runtime 약 `94600 ms`
  - policy `3` Cost-Benefit:
    - `TLC_GC_CNT 15526`
    - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
    - `SLC_MIGRATION_CNT 45030`
    - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440485`
    - fio runtime 약 `100708 ms`
- 위 결과에서 Random(`1`)만 다른 3개와 꽤 다르고, Greedy/FIFO/Cost-Benefit(`0/2/3`)은 현재 로컬 workload(`600M x 10`)에서 거의 같은 범주로 묶였다.
- 같은 비교에서 `DIAG_*` 값은 네 정책 모두 `0`이라 TLC GC Greedy vs Cost-Benefit 차이는 이 로컬 조건에서 드러나지 않았다.
- 서버용 `600M x 250` workload를 로컬에 그대로 쓰면 과도하게 오래 걸릴 수 있어, 로컬 기준은 `smoke=128M x 20`, `compare=600M x 10`으로 별도 분리했다.
- 로컬 재실행 편의를 위해 `scripts/run_local_slc_policy_compare.sh`를 추가했다.
- `scripts/run_experiment.sh`도 실습2 기준으로 수정했다.
  - 첫 번째 `policy` 인자는 이제 `slc_migration_policy` 의미다.
  - `0=Greedy`, `1=Random`, `2=FIFO`, `3=Cost-Benefit`을 받는다.
  - `gc_policy`는 `TLC_GC_POLICY` 환경변수로 분리했고 기본값은 `0`이다.
  - `insmod` 시 `gc_policy="$TLC_GC_POLICY"`와 `slc_migration_policy="$POLICY"`를 함께 넘긴다.
  - 결과 디렉터리 이름은 `slcpolicy*` 형태로 바뀌고, `meta.txt`에 `policy_target=slc_migration`, `tlc_gc_policy`, `slc_migration_policy`가 추가 기록된다.
  - device 대기는 기존 sleep loop 대신 `udevadm settle` 우선 방식으로 바뀌었다.
- `scripts/run_local_slc_policy_compare.sh`에 `verify` 모드를 추가했다.
  - `fio --verify=crc32c --verify_fatal=1 --do_verify=1` 기반으로 단일 policy CRC 검증을 수행한다.
  - 기본 verify workload는 `VERIFY_SIZE=600M`, `VERIFY_LOOPS=10`, `VERIFY_BS=4k`다.
  - 결과는 `results/local_*_slc_verify_policyN/` 아래에 `fio.json`, `debug.txt`, `meta.txt`, `fio_cmd.txt`로 저장된다.
- `zipf:1.2 + NORANDOMMAP=1` 조건으로 `run_experiment.sh` 4정책 비교를 수행했고, 이 로컬 workload에서는 기존 uniform보다 정책 차이가 분명히 커졌다.
  - 공통 조건: `UNIFORM_SIZE=600M`, `UNIFORM_LOOPS=10`, `RANDOM_DIST=zipf:1.2`, `NORANDOMMAP=1`, `TLC_GC_POLICY=0`
  - Greedy(`0`): `sum=180772`, `max=42`, `slc_migrate_pages=112766`, `tlc_gc_cnt=0`
  - Random(`1`): `sum=180904`, `max=37`, `slc_migrate_pages=154228`, `tlc_gc_cnt=0`
  - FIFO(`2`): `sum=180844`, `max=21`, `slc_migrate_pages=122230`, `tlc_gc_cnt=0`
  - Cost-Benefit(`3`): `sum=180700`, `max=32`, `slc_migrate_pages=104875`, `tlc_gc_cnt=0`
  - 해석:
    - `0/2/3`도 이제 더 이상 완전히 수렴하지 않는다.
    - Cost-Benefit(`3`)가 `slc_migrate_pages` 기준으로 가장 낮다.
    - FIFO(`2`)는 `max`가 가장 낮지만 migration cost는 CB보다 높다.
    - TLC GC는 `0`이라, 이 조건은 사실상 SLC migration policy만 비교한 결과로 읽을 수 있다.
- CRC verify도 로컬에서 실제로 돌렸다.
  - `results/local_20260823_224010_slc_verify_policy0/`: `error=0`
  - `results/local_20260823_224607_slc_verify_policy1/`: `error=0`
  - `results/local_20260823_232744_slc_verify_policy2/`: `error=0`
  - `results/local_20260823_233241_slc_verify_policy3/`: `error=0`
  - 네 경우 모두 verify run 중 `SLC_MIGRATION_CNT`와 `TLC_GC_CNT`가 실제로 증가해, migration/GC가 섞인 상태에서도 CRC mismatch 없이 통과했다.

## 다음 세션 시작점

- 다음 세션은 로컬 `~/nvmevirt`에서 시작하는 것을 우선으로 한다.
- 시작 확인 순서는 `git status --short`, `ls results/local_* | tail`, `sed -n '1,220p' scripts/run_local_slc_policy_compare.sh` 정도면 충분하다.
- 목표는 `zipf_nrm` 결과를 반복측정 또는 요약 자동화로 정리한 뒤, local-sized `hotcold v7` 비교 여부를 결정하는 것이다.

## 참고 문서

- 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 과제 요구사항 확인: `docs/PRACTICE2_AGENTS`

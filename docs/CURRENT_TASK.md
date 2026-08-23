# Current Task

## 현재 흐름

- 실습2 WIP는 commit `8aa39ca`로 로컬/원격에 반영됐다.
- 핵심 변경 파일은 `conv_ftl.c`, `conv_ftl.h`, `main.c`, `ssd_config.h`이며, 로컬 실행용 스크립트 `scripts/run_local_slc_policy_compare.sh`가 추가됐다.
- 현재 코드는 SLC/TLC pool metadata, pool-aware write path, SLC migration 첫 연결, migration/TLC GC counter 분리, migration policy 분리까지 들어간 상태다.
- 현재 worktree 기준 `SLC_CACHE_RATIO_PERCENT`는 `10`이라 SLC path가 컴파일 시 기본 활성이다.
- 로컬 VM smoke test와 fresh reload 기반 4정책 비교에서 SLC write, SLC to TLC migration, TLC GC가 모두 실제로 발생하는 것까지 확인했다.
- 서버 저장소 `~/nvmevirt`도 `practice2-slc-cache` 브랜치의 `8aa39ca`까지 동기화돼 있지만, 현재는 서버 이슈 때문에 로컬 우선으로 진행한다.

## 다음에 바로 할 일

1. 오늘 추가한 `scripts/run_local_slc_policy_compare.sh`로 로컬 재실행이 재현되는지 필요 시 다시 확인한다.
2. `scripts/run_experiment.sh`가 `slc_migration_policy`까지 받도록 정리한다.
3. policy별 victim selection과 migration/TLC GC counter 차이가 더 크게 드러나는 workload를 찾거나 조정한다.
4. `fio verify` 또는 read-back 기반 데이터 정합성 검증을 추가한다.

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

## 다음 세션 시작점

- 다음 세션은 로컬 `~/nvmevirt`에서 시작하는 것을 우선으로 한다.
- 시작 확인 순서는 `git status --short`, `ls results/local_* | tail`, `sed -n '1,220p' scripts/run_local_slc_policy_compare.sh` 정도면 충분하다.
- 목표는 로컬 결과를 바탕으로 `scripts/run_experiment.sh`의 `slc_migration_policy` 지원과 데이터 정합성 검증을 정리하는 것이다.

## 참고 문서

- 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 과제 요구사항 확인: `docs/PRACTICE2_AGENTS`

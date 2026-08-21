# Current Task

## 현재 흐름

- 실습2 WIP는 commit `8aa39ca`로 로컬/원격에 반영됐다.
- 핵심 변경 파일은 `conv_ftl.c`, `conv_ftl.h`, `main.c`, `ssd_config.h`다.
- 현재 코드는 SLC/TLC pool metadata, pool-aware write path, SLC migration 첫 연결, migration/TLC GC counter 분리, migration policy 분리까지 들어간 상태다.
- 현재 worktree 기준 `SLC_CACHE_RATIO_PERCENT`는 `10`이라 SLC path가 컴파일 시 기본 활성이다.
- 로컬 VM smoke test에서는 SLC write, SLC to TLC migration, TLC GC가 모두 실제로 발생하는 것까지 확인했다.
- 서버 저장소 `~/nvmevirt`도 `practice2-slc-cache` 브랜치의 `8aa39ca`까지 동기화된 상태다.

## 다음에 바로 할 일

1. 서버 환경에서 `slc_migration_policy=0/1/2/3`를 fresh reload 조건으로 반복 실행한다.
2. `scripts/run_experiment.sh`가 `slc_migration_policy`까지 받도록 정리한다.
3. policy별 victim selection과 migration/TLC GC counter 차이가 실제로 드러나는지 확인한다.
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

- 로컬 환경에서는 `make` 바이너리가 없어 이 세션 셸에서 직접 빌드 검증은 못 했다.
- 사용자 VM smoke test 결과 `/proc/nvmev/debug`에서 다음을 확인했다.
  - `SLC_MIGRATION_CNT 45059`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1397376`
  - `TLC_GC_CNT 15253`
  - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
- 위 결과는 현재 코드에서 SLC migration과 TLC GC 경로가 실제로 동작함을 보여준다.
- 같은 smoke workload에서는 `DIAG_*` 값이 모두 `0`이라 Greedy와 Cost-Benefit 차이는 아직 드러나지 않았다.
- 로컬 변경은 commit `8aa39ca` (`Add SLC migration scaffolding and session docs`)로 정리했고, 원격 `origin/practice2-slc-cache`에도 push 완료했다.
- 서버에서는 `main`이 아니라 `practice2-slc-cache`로 checkout 후 `git pull origin practice2-slc-cache`까지 완료했고, `git log`에서 `8aa39ca`를 확인했다.

## 다음 세션 시작점

- 다음 세션은 서버에 SSH 접속한 뒤 `~/nvmevirt`에서 시작한다.
- 서버 시작 확인 순서는 `git branch --show-current`, `git status --short`, `make` 정도면 충분하다.
- 목표는 서버에서 `slc_migration_policy=0/1/2/3` 비교와 실험 스크립트 정리다.

## 참고 문서

- 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 과제 요구사항 확인: `docs/PRACTICE2_AGENTS`

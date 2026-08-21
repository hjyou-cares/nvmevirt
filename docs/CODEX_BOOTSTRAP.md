# Codex Bootstrap

이 문서는 새 세션이 처음에 빠르게 읽는 시작 요약이다.

## 프로젝트 목표

- NVMeVirt Conventional FTL에 SLC cache를 구현한다.
- 기본 host write는 SLC에 먼저 기록한다.
- SLC가 차면 valid data를 TLC로 migration한다.
- migration victim policy 4종을 비교한다.

## 현재 기준선

- 권장 실습1 기준 commit: `ae28ab11cd11769358c0bc578ee65f055b28c5a9`
- 현재 작업 branch: `practice2-slc-cache`
- 현재 실습2 구현은 branch 커밋보다 worktree 변경에 더 많이 남아 있다.

## 현재까지 구현된 흐름

- `ssd_config.h`에 `SLC_CACHE_RATIO_PERCENT`가 추가됐다.
- `conv_ftl.h`에 SLC/TLC pool metadata와 close sequence 뼈대가 추가됐다.
- line이 SLC pool인지 TLC pool인지 초기화 시 고정 분할하도록 metadata가 들어갔다.
- free line accounting이 pool-aware 하게 바뀌었다.
- host write pointer는 SLC pool을 우선 사용하고, GC write pointer는 TLC pool을 사용한다.
- SLC free line이 떨어질 때 Greedy 기반 SLC to TLC migration 첫 경로가 연결됐다.
- `gc_policy`는 TLC GC 의미로 유지하고, `slc_migration_policy`가 별도 추가됐다.
- SLC migration victim policy 4종(Greedy/Random/FIFO/Cost-Benefit) 분기가 연결됐다.
- `/proc/nvmev/debug`에 TLC GC 통계와 SLC migration 통계가 분리돼 노출된다.
- 로컬 VM smoke test에서 SLC write, SLC to TLC migration, TLC GC가 실제로 발생하는 것까지 확인했다.

## 아직 안 된 것

- `SLC_CACHE_RATIO_PERCENT` 기본값은 현재 `10`이다.
- SLC/TLC별 `oneshot page size`와 latency model 분리가 없다.
- read path는 mapping은 공용이지만 timing은 아직 SLC/TLC를 구분하지 않는다.
- `slc_rt.slc_wp`, `slc_rt.tlc_wp`, `slc_rt.tlc_gc_wp`는 구조체만 있고 실제 I/O 경로는 아직 legacy `wp/gc_wp`를 쓴다.
- 정책 비교 실험과 데이터 정합성 검증은 아직 남아 있다.

## 다음 우선순위

1. 서버 환경에서 `slc_migration_policy=0/1/2/3`를 fresh reload 조건으로 비교한다.
2. `scripts/run_experiment.sh`가 `slc_migration_policy`를 받도록 정리한다.
3. `fio verify` 또는 read-back으로 데이터 정합성을 검증한다.
4. SLC/TLC별 timing과 oneshot 차이를 모델에 반영한다.
5. read/write path가 pool별 timing을 실제로 타도록 구조를 정리한다.

## 작업 시 주의사항

- 시작할 때 긴 조사 문서를 전부 다시 읽지 않는다.
- 현재 흐름 확인은 `git status`, `git diff --stat`, `docs/CURRENT_TASK.md`로 끝낸다.
- 과제 공식 문구가 다시 필요할 때만 `docs/PRACTICE2_AGENTS`를 읽는다.
- 실습1의 TLC GC 정책과 실습2의 SLC migration 정책을 같은 문제로 취급하지 않는다.
- 정책 비교에서는 `echo reset`만 쓰지 말고 `umount -> rmmod -> insmod -> mkfs -> mount`로 fresh reload 한다.
- 로컬 VM은 용량이 작아 smoke test 이상 비교 실험에는 부적합할 수 있다.
- 기존 사용자 변경은 절대 되돌리지 않는다.

## 필요할 때만 보는 문서

- 실습2 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 긴 조사/설계 기록: `docs/PRACTICE2_LOG.md`
- 실습1 기록: `Note.md`
- 과제 PDF 대체 텍스트: `docs/PRACTICE2_AGENTS`
- 학습 노트: `codestudy/studynote.md`

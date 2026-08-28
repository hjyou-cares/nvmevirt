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
- 현재 worktree HEAD는 `1898ac6` (`Add greedy SLC crossover rep1 results`)다.
- 서버 형제 저장소 `~/nvmevirt`는 아직 `9eb9f0b` 기준 `nvmev.ko`만 남아 있어, 현재 검증/실험에는 재빌드가 필요하다.
- 현재 worktree에는 `conv_ftl.c`, `conv_ftl.h` 중심의 guarded reclaim/write-credit WIP가 있다.

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
- 2026-08-23 로컬 fresh reload 4정책 비교(`results/local_20260823_212734_slc_policy_compare`)까지 수행했다.
- 로컬 재실행용 `scripts/run_local_slc_policy_compare.sh`가 추가됐다.
- `scripts/run_experiment.sh`도 `gc_policy` 고정 + `slc_migration_policy=0/1/2/3` 비교용으로 정리했다.
- `scripts/run_local_slc_policy_compare.sh`에 CRC 기반 `verify` 모드가 추가됐다.
- `zipf:1.2 + NORANDOMMAP=1` 로컬 조건(`zipf_nrm`)에서 `0/2/3`도 실제로 갈리는 첫 결과를 확보했다.
- 2026-08-24에 같은 `zipf_nrm` 조건으로 `rep2` 네 정책도 완료했다.
- 2026-08-24에 같은 조건으로 `rep2_rerun`과 유효한 `rep3` 네 정책도 완료했다.
- `zipf_nrm` 4회분에서 `slc_migrate_pages` 순위는 일관되게 `Cost-Benefit < Greedy < FIFO < Random`으로 유지됐다.
- 2026-08-25에 local-sized `hotcold v7` 4정책 1회(`COLD_SIZE=512M`, `COLD_TOUCH_SIZE=256M`, `HOT_SIZE=64M`, `HOTCOLD_RUNTIME=60`)를 돌린 뒤, `cold_touch` 뒤 `stonewall`이 남아 있던 문제를 확인했다.
- `stonewall` 제거 후 `hotcold_v7_local_fix1` 4정책을 다시 돌렸고, `slc_migrate_pages` 순위는 `Cost-Benefit < FIFO < Greedy < Random`으로 정리됐다.
- 수정 후 `hotcold v7`는 `zipf_nrm`과 같은 큰 방향(`Cost-Benefit` 최저, `Random` 최고)을 보였고, `max erase`는 여전히 `FIFO`가 가장 낮았다.
- 2026-08-25에 구조 정리 후 `hotcold_v7_local_fix2`를 다시 돌렸고, `slc_migrate_pages` 순위는 `FIFO < Cost-Benefit < Greedy < Random`이었다.
- 2026-08-25에 SLC/TLC별 oneshot page size와 NAND read/write timing 분기를 코드에 추가했다.
- 같은 날 host/migration write pointer는 `slc_wp/tlc_wp/tlc_gc_wp`를 직접 쓰도록 바꿨고, free/full/victim list와 PQ도 `slc_lm/tlc_lm`로 직접 나눴다.
- 2026-08-25 새 `verify 0/1/2/3`도 모두 통과했고, 예전 빈 verify 실패 흔적 2개는 삭제했다.
- `scripts/collect_summary.sh`는 이제 migration counter와 workload 조건까지 CSV로 집계한다.
- 2026-08-28 현재 `scripts/collect_summary.sh`는 `results/**/meta.txt`를 재귀 집계하고, baseline validation의 중첩 디렉터리도 CSV에 포함한다.
- `slc_cache_ratio_percent` insmod parameter가 추가돼, 같은 빌드 산출물로 `0`(TLC-only baseline)과 `10`(SLC cache on)을 런타임에 바꿔 실험할 수 있다.
- `/proc/nvmev/debug`에는 `USER_*_SLC/TLC_PAGES`, `INTERNAL_*_SLC/TLC_PAGES`가 추가돼 SLC-only/overflow 검증 근거를 직접 뽑을 수 있다.
- `scripts/run_local_slc_validation.sh`가 추가돼 `baseline`, `slc_only`, `overflow`, `all` 모드로 1번 결과물 검증을 자동화했다.
- 2026-08-27 현재 worktree WIP에는 reclaim 시작 전 TLC GC capacity precheck, TLC GC 성공 시에만 write credit refill, host write path의 hidden reclaim 제거가 들어갔다.
- 같은 날 추가 WIP로 SLC migration이 reclaim 후에도 TLC GC 1 line capacity를 남기도록 reserve-style admission control이 들어갔다.
- 2026-08-27 서버 일반 shell에서 guarded/reserve WIP 기준 `random hotcold full`, `greedy/fifo/cost-benefit hotcold full`, `overflow` 재검증, `CRC verify policy1`까지 성공했다.
- 2026-08-28 확장 실험 60개는 `60/60`, fio 오류 0, 조건 누락 0으로 완료됐다.
- 같은 날 SLC가 유리한 resident 구간과 migration으로 불리해지는 구간을 함께 측정하는
  18-run crossover 실험 스크립트와 전용 집계기를 추가했다.
- 시간 제약에 따라 crossover는 3회 반복 대신 resident/overflow/sustained × ratio 0/10의 6개 rep1으로 완료했다.
- Crossover tail 분석 지표는 p99에서 p99.9로 변경했다. Resident에서는 SLC가 유리하고, overflow부터 p99.9가 역전되며, sustained에서는 throughput 이점이 사라지고 p99.9와 erase cost가 크게 증가했다.
- 확장 결과 CSV/그림 4개와 crossover CSV/그림 1개를 생성했으며, 전체 결과를 `report/REPORT.md`에 반영했다.

## 아직 안 된 것

- `SLC_CACHE_RATIO_PERCENT` 기본값은 현재 `10`이다.
- 서버 `baseline` / `SLC-only` / `overflow` / `zipf_nrm` / `hotcold` 결과와 보고서 전체 초안은 정리됐다.
- 전체 원고에 대한 사용자 검토와 수정, 스타일 적용 DOCX 및 최종 PDF 생성이 남아 있다.
- Crossover 서버 실행과 결과 집계는 완료됐다.
- 현재 Codex 서버 세션에서는 `sudo`, `lsblk`, `/proc`, `/sys` 접근이 막혀 있어 모듈 로드와 실험 실행을 직접 수행할 수 없다.

## 보고서 진행 방식

- 원고 파일은 `report/REPORT.md`다. 현재 브랜치의 GitHub 보고서와 Word 생성기의 단일 원본으로 사용한다.
- 목차는 `실습 목표 -> 구현 내용 -> 실험 방법 -> 실험 결과 -> 분석 -> 결론`으로 확정했다.
- 결과는 `Baseline -> SLC-only -> Overflow -> Zipf -> Hot-cold` 순서로 하나씩 작성하고, 각 항목의 표/그래프/본문을 사용자에게 컨펌받은 뒤 다음으로 넘어간다.
- Markdown은 내용 원본이며, 검토본은 스타일 적용 DOCX, 제출본은 PDF로 만든다.
- Baseline은 throughput/latency 중심 성능 비교 그래프를 유지한다.
- SLC-only는 media별 host I/O counter와 migration/internal I/O/TLC GC의 0 값을 보여주는 검증 그래프로 수정했다.
- Overflow counter 그래프와 본문까지 작성했으며, SLC-only 수정본과 함께 사용자 컨펌 전이다.
- SLC-only/Overflow의 throughput과 latency는 참고 표로만 남긴다.
- fig2/fig3의 겹치던 SLC/TLC 범례는 제거하고 막대 내부 직접 라벨만 유지한다.
- Zipf와 Hot-cold 4정책 비교 그래프 및 4.4/4.5 본문까지 작성했다.
- Hot-cold migration/erase 비용은 시간 기반 실행량 차이를 보정하기 위해 GiB당으로 정규화했다.
- Hot-cold 그래프 D는 downstream TLC GC valid-page copies/GiB로 변경했고 peak wear는 표에 남겼다. Zipf는 TLC GC=0이므로 D를 `SLC peak wear`로 유지한다.
- p99 latency는 migration 전용 실행시간이 아니라 fio host write end-to-end latency다.
- 2026-08-28 현재 1~3장과 5~6장을 포함한 전체 Markdown 초안이 작성됐다.
- Pandoc HTML/DOCX 변환 검증은 통과했으며, 실제 스타일 적용 DOCX는 사용자 내용 검토 후 생성한다.
- 현재 보고서 전체가 사용자 검토 대기 상태다.
- 점수 보강용 추가 실험은 `ratio 0/5/10/20`, `Zipf/Hot-cold 3회 반복`,
  `Uniform/Zipf/Hot-cold workload 민감도`의 세 축으로 확정했다.
- `scripts/run_practice2_extended_experiments.sh`가 60-run 매트릭스를 fresh reload 조건으로
  실행하며, 완료 label skip으로 중단 후 재시작할 수 있다.
- `report/make_practice2_extended_figures.py`는 60개 조건 완성 여부를 검사하고 raw/aggregate
  CSV 및 평균±표준편차 그래프 4개를 생성한다.
- 실행 방법과 매트릭스는 `docs/PRACTICE2_EXTENDED_EXPERIMENTS.md`에 정리했다.
- 확장 실험 raw 결과 snapshot은 원격 commit `eeee1c9`까지 반영돼 있다.
- Crossover 실행 중에는 source/workload 파일을 수정하지 않고 결과 조건을 고정한다.
- 확장 실험 60개와 crossover 6개의 CSV/그래프 생성 및 보고서 반영을 완료했다.
- Crossover 실행법은 `docs/PRACTICE2_SLC_CROSSOVER_EXPERIMENT.md`에 정리했다.

## 다음 우선순위

1. 전체 원고와 새 그래프를 사용자와 최종 검토한다.
2. 스타일 적용 DOCX와 최종 PDF를 만든다.

## 작업 시 주의사항

- 시작할 때 긴 조사 문서를 전부 다시 읽지 않는다.
- 다음 세션 시작점은 로컬 고정이 아니다. 현재 작업본 `~/nvmevirt2`와 서버 일반 shell 중, `sudo`/`make`/`fio`가 실제로 되는 쪽을 우선 사용한다.
- 현재 흐름 확인은 `git status`, `git diff --stat`, `docs/CURRENT_TASK.md`로 끝낸다.
- 과제 공식 문구가 다시 필요할 때만 `docs/PRACTICE2_AGENTS`를 읽는다.
- 실습1의 TLC GC 정책과 실습2의 SLC migration 정책을 같은 문제로 취급하지 않는다.
- 정책 비교에서는 `echo reset`만 쓰지 말고 `umount -> rmmod -> insmod -> mkfs -> mount`로 fresh reload 한다.
- 로컬 VM에서는 서버용 `600M x 250`를 그대로 쓰지 말고, 현재 기준 `smoke=128M x 20`, `compare=600M x 10`을 우선 사용한다.
- 로컬 `zipf_nrm` 재실행 시 `RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=600M UNIFORM_LOOPS=10`을 명시하지 않으면 기본 `uniform 600M x 250`로 돌아간다.
- 2026-08-25 이전 `results/*hotcold_v7_local/` 첫 실행은 `stonewall` 버그가 섞인 결과라 최종 비교에서는 제외한다.
- 현재 최종 비교 기준 `hotcold` 세트는 `*hotcold_v7_local_fix2*`다.
- 로컬에서 반복 실행 중 VS Code Remote가 끊기면 대체로 `rmmod -> insmod -> mkfs -> mount` 재초기화 경계에서 guest가 잠깐 멎는 경우이므로 `tmux` 안에서 돌리는 편이 안전하다.
- 2026-08-27 현재 Codex 서버 세션에서는 `sudo`, `lsblk`, `/proc`, `/sys`가 막혀 있으므로, 실제 insmod/mkfs/mount/fio 실행은 일반 로그인 shell에서 해야 한다.
- 집계 자동화 확인은 `./scripts/collect_summary.sh > /tmp/nvmevirt_summary.csv`로 먼저 검증한다.
- `results/20260824_173844_slcpolicy1_random_zipf_nrm_rep2/`는 비어 있는 실패 흔적이라 집계 대상이 아니다.
- `results/*zipf_nrm_rep2_rerun`와 `results/*zipf_nrm_rep3` 중 `meta.txt`/`summary.txt`가 없는 디렉터리는 중간 실패 흔적이므로 집계 대상이 아니다.
- 기존 사용자 변경은 절대 되돌리지 않는다.

## 필요할 때만 보는 문서

- 실습2 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 긴 조사/설계 기록: `docs/PRACTICE2_LOG.md`
- 실습1 기록: `Note.md`
- 과제 PDF 대체 텍스트: `docs/PRACTICE2_AGENTS`
- 학습 노트: `codestudy/studynote.md`

# Current Task

## 2026-08-28 최신 상태

- 현재 HEAD는 `1898ac6`이며 crossover 6개(rep1)가 저장돼 있다.
- 확장 60-run과 crossover 6-run 모두 fio 오류와 조건 누락 없이 집계 검증을 통과했다.
- `report/make_practice2_extended_figures.py`로 확장 실험 raw/aggregate CSV와 그림 4개를 생성했다.
- `report/make_slc_crossover_figure.py --reps 1`은 tail 지표를 p99.9로 집계하고 crossover 그림을 생성한다.
- `report/REPORT.md`에는 ratio 0/5/10/20 민감도, Zipf/Hot-cold/Uniform 3회 반복, resident/overflow/sustained crossover 결과를 반영했다. 이 파일은 현재 브랜치에서 GitHub가 그림과 함께 바로 렌더링하는 원본이다.
- `report/build_practice2_docx.py`로 제출 형식의 `report/PRACTICE2_REPORT.docx`를 생성했다. A4 여백, 표지/목차 분리, 장별 새 페이지, 그림 폭 맞춤, 표 머리행 반복, 페이지 번호와 필드 자동 갱신을 적용했다.
- 사용자 가독성 요청에 따라 원고의 반복 설명은 압축했고, 이후 4장 결과 검토를 위해 Baseline/SLC-only/Overflow 그래프를 복원했다. 현재 `report/REPORT.md`는 2,323단어와 최종 그래프 8개를 사용한다.
- 제출 안내용 `Code_Structure_Notice.txt`에 Word와 핵심 코드 7개의 첨부 목록 및 파일별 역할을 정리했다.
- 핵심 crossover 결과는 resident에서 SLC throughput +23.5%, p99.9 -44.3%; overflow에서 throughput +16.9%지만 p99.9 +76.2%; sustained에서 throughput +0.6%, p99.9 13.6배, erase 3.43배다.
- 다음 단계는 생성물과 보고서 최종 검토 후 DOCX/PDF 변환이다.

## 현재 흐름

- 현재 HEAD는 `bf666a3`, 원격 `origin/practice2-slc-cache`는 확장 결과 snapshot `eeee1c9`다.
- Crossover 준비 변경은 아직 worktree WIP이며 서버 실행 전에 현재 소스로 재빌드해야 한다.
- 핵심 변경 파일은 `conv_ftl.c`, `conv_ftl.h`, `ssd.c`, `ssd.h`, `ssd_config.h`, `main.c`다.
- 현재 코드는 SLC/TLC pool metadata, pool-aware write path, SLC migration 4정책, migration/TLC GC counter 분리, SLC/TLC oneshot/timing 분기, `slc_wp/tlc_wp/tlc_gc_wp` direct path, `slc_lm/tlc_lm` direct manager path까지 들어간 상태다.
- 현재 worktree 기준 `SLC_CACHE_RATIO_PERCENT`는 `10`이라 SLC path가 컴파일 시 기본 활성이다.
- 2026-08-26 현재 worktree에는 `slc_cache_ratio_percent` insmod parameter가 추가돼, 같은 빌드 산출물로 `0`(TLC-only baseline)과 `10`(SLC cache on)을 런타임에 바꿔 실험할 수 있게 정리 중이다.
- `/proc/nvmev/debug`에는 이제 `USER_*_SLC/TLC_PAGES`, `INTERNAL_*_SLC/TLC_PAGES`가 추가돼 SLC-only/overflow 검증에서 host/internal read/write가 어느 media로 갔는지 직접 확인할 수 있게 됐다.
- `scripts/collect_summary.sh`는 이제 `slc_cache_ratio_percent`, `write_bw_kib`, `write_iops`, `read_bw_kib`, `read_iops`, read/write latency를 함께 CSV로 모은다.
- 2026-08-28 현재 `scripts/collect_summary.sh`는 `results/**/meta.txt`를 재귀 수집하므로 `local_*_slc_baseline_compare/{tlc_only,slc_on}` 같은 중첩 run도 CSV에 포함된다.
- 같은 수정으로 baseline 메타의 `baseline_size`/`baseline_loops`, `variant`/`mode`도 기존 CSV 필드(`uniform_size`, `uniform_loops`, `label`, `workload`)로 fallback 집계된다.
- 새 로컬 검증 스크립트 `scripts/run_local_slc_validation.sh`가 추가됐다. `baseline`, `slc_only`, `overflow`, `all` 모드로 1번 결과물용 실험을 바로 돌리도록 만든 상태다.
- 로컬 VM 기준 `make`, smoke, CRC verify, `zipf_nrm`, `hotcold_v7_local_fix2`까지 사용자 확인으로 정상 수행됐다.
- 서버 형제 저장소 `~/nvmevirt`에는 `9eb9f0b` 시점의 `nvmev.ko`만 확인됐고, 현재 HEAD `09f41ac`와는 커널 코드 차이가 있어 재빌드 없이 재사용하면 안 된다.
- 최종 보고서용 `baseline`, `SLC-only`, `overflow`, `zipf_nrm`, `hotcold full guarded` 서버 실측값은 수집을 마쳤다. 로컬 VM 결과는 스크립트/계측 검증과 방향 확인용으로만 취급한다.
- 2026-08-27 현재 Codex 서버 세션에서는 `sudo`, `lsblk`, `/proc`, `/sys` 접근이 막혀 있어서, 여기서 직접 `insmod -> mkfs -> mount -> fio` 흐름을 실행할 수는 없다.
- 2026-08-27 현재 이 세션 PATH 기준으로 `make`, `gcc`, `clang`, `fio`, `tmux`는 보이지 않고 `jq`만 확인된다. 따라서 실제 빌드/실험은 일반 로그인 shell에서 다시 확인해야 한다.
- 2026-08-27 현재 worktree WIP에는 `conv_ftl.c`, `conv_ftl.h` 기준으로 reclaim 시작 전 TLC capacity precheck, TLC GC 성공 시에만 write credit refill, host write path의 hidden reclaim 제거가 추가됐다.
- 같은 날 추가 WIP로 SLC migration은 reclaim 후에도 TLC GC 1 line capacity를 남기는 후보만 선택하도록 reserve-style admission control을 넣었다.
- 이 guarded WIP는 2026-08-27 서버 일반 shell에서 실제로 build/실행 검증됐다.
- 검증 완료 범위: `overflow` 재검증 성공, `random/greedy/fifo/cost-benefit hotcold full guarded` 성공, `CRC verify policy1` 성공.
- 2026-08-27 서버 일반 shell에서 `SLC-only` 검증도 완료됐다. 디렉터리 이름은 스크립트 관례상 `local_*`이지만 서버 실측 결과이며, 최신 확인 대상은 `results/local_20260827_192113_slc_only_validation/`이다.
- 2026-08-28 확장 실험은 ratio 24개, Zipf/Hot-cold policy repeat 24개,
  Uniform sensitivity 12개로 총 `60/60` 완료됐다. 동일 집계 로직 검사에서 누락과 fio 오류는 0이었다.
- 새 worktree WIP는 `write_early_completion`을 insmod parameter로 노출하고,
  resident/overflow/sustained 구간을 ratio 0/10으로 비교하는 18-run crossover suite를 추가한다.

## 보고서 작성 방식

- 보고서 원고는 `report/REPORT.md`에서 관리한다.
- 제출용 문서 구성은 `1. 실습 목표`, `2. 구현 내용`, `3. 실험 방법`, `4. 실험 결과`, `5. 분석`, `6. 결론`이다.
- 실험 결과는 `Baseline -> SLC-only -> Overflow -> Zipf -> Hot-cold` 순서로 하나씩 작성한다.
- 각 항목은 표, 그래프, 본문을 사용자에게 먼저 보여주고 컨펌받은 뒤 다음 항목으로 넘어간다.
- Markdown은 내용 원본으로 사용하고, 사용자 검토본은 스타일을 적용한 DOCX로 생성한다. 최종 제출본은 DOCX 또는 스타일 적용 HTML에서 PDF로 변환한다.
- DOCX에는 표지, 목차, 장/절 번호, A4 여백, 일관된 표와 그림 캡션, 페이지 번호, 표 제목 행 반복을 적용한다.
- `4.1 Baseline`은 성능 비교 목적에 맞춰 throughput/latency/write traffic 그래프를 유지한다.
- `4.2 SLC-only`는 성능 그래프를 제거하고 host I/O media counter와 migration/internal I/O/TLC GC의 0 값을 보여주는 검증 그래프로 수정했다.
- `4.3 Overflow` 본문과 `report/figures/practice2_fig3_overflow_validation.png`를 추가했다. host read의 TLC 접근과 SLC internal read/TLC internal write counter로 migration 경로를 보여준다.
- SLC-only와 Overflow의 throughput/latency는 그래프에서 제외하고 보고서 참고 표에만 기록한다.
- fig2/fig3의 SLC/TLC 범례는 막대의 직접 라벨과 중복되고 그래프에 겹쳐 제거했다.
- `4.4 Zipf`는 서버 22 GiB x 7회 4정책 결과로 throughput, p99, migrated pages, peak erase 그래프와 본문을 작성했다.
- `4.5 Hot-cold`는 서버 full guarded 4정책 결과로 같은 형식의 그래프와 본문을 작성했다. 시간 기반 workload이므로 migration/erase 비용은 written GiB로 정규화했다.
- Hot-cold 그래프의 D 패널은 peak wear 대신 downstream TLC GC migrated pages/GiB로 바꿔 `SLC policy -> SLC copy cost -> TLC GC copy cost -> host performance` 흐름을 보여준다. Peak wear는 보고서 표에 유지한다.
- Zipf는 TLC GC가 네 정책 모두 0이므로 peak wear를 유지하되 `SLC peak wear`로 명시해 SLC victim 선택의 직접 결과임을 드러냈다.
- 그래프의 p99 latency는 migration 시작/종료 시간이 아니라 내부 migration/GC 영향을 포함한 fio host write end-to-end latency다.
- 현재 4.1~4.5 결과 절의 그래프와 본문뿐 아니라 1~3장, 5장 분석, 6장 결론까지 전체 Markdown 초안이 작성됐다.
- 1~3장은 공식 요구사항과 현재 코드의 SLC/TLC pool, 공통 mapping, oneshot/timing, guarded migration 구현을 대조해 작성했다.
- 5~6장은 Zipf를 SLC policy의 격리 효과, Hot-cold를 downstream TLC GC까지 포함한 전체 효과로 구분해 종합했다.
- Pandoc을 이용한 HTML/DOCX 구문 및 그림 포함 변환 검증은 통과했다. 실제 스타일 적용 DOCX는 내용 검토 후 만든다.
- 현재 보고서 전체가 사용자 검토 대기 상태다.
- 추가 점수 보강 작업은 세 축으로 확정했다.
  - Greedy 고정, SLC ratio `0/5/10/20%`, burst 1 GiB와 sustained 22 GiB x 7을 각 3회
  - ratio 10%, TLC GC Greedy 고정, Zipf와 Hot-cold 네 정책을 현재 binary에서 각 3회
  - ratio 10%, 22 GiB x 7, `norandommap=1` Uniform 네 정책을 각 3회 추가해 workload 민감도 비교
- `scripts/run_practice2_extended_experiments.sh`에 위 60-run 매트릭스와 완료 label 기반 resume을 구현했다.
- `report/make_practice2_extended_figures.py`에 완성도 검사, raw/aggregate CSV, error bar 그래프 4개 생성을 구현했다.
- 실행 가이드는 `docs/PRACTICE2_EXTENDED_EXPERIMENTS.md`다.
- 확장 60-run raw 결과는 완료됐고, 전용 CSV/그래프와 보고서 반영은 아직 남아 있다.
- 실험 매트릭스는 ratio 24회, Zipf/Hot-cold policy repeat 24회, Uniform sensitivity 12회로 총 60회다.
- 실험 완료 후 `python3 report/make_practice2_extended_figures.py`를 실행해 결과 CSV와 error-bar 그래프를 생성한다.

## 다음에 바로 할 일

1. Workload 설명과 8개 결과 그래프를 반영한 Markdown/Word의 사용자 육안 검토를 반영한다.
2. 확정 원고를 최종 PDF로 변환한다.

## 새 세션 인계 메모

- 확장 60-run은 완료됐다. 현재 목표는 SLC cache의 유리/불리 구간을 직접 보여주는 crossover 18-run이다.
- 실행 가이드는 `docs/PRACTICE2_SLC_CROSSOVER_EXPERIMENT.md`다.
- 서버에서 실행할 명령:
  - `export NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8`
  - `make -j"$(nproc)"`
  - `tmux new -A -s p2-crossover`
  - `./scripts/run_slc_crossover_experiments.sh all`
- 다음 세션 시작 시 먼저 `git status --short`, `git log -1 --oneline`, `docs/CURRENT_TASK.md`를 확인한다.
- crossover 완료 후 `python3 report/make_slc_crossover_figure.py`로 18개 완성 여부와 counter를 검증한다.
- 기존 확장 결과는 `python3 report/make_practice2_extended_figures.py`로 집계한다.
- 현재 작업본에서 추가 수정이 필요하면 실험이 끝난 뒤 진행한다. 실험 중에는 `conv_ftl.c`, workload 설정, 실행 스크립트를 바꾸지 않아 결과 조건을 고정한다.

## 미구현 핵심 항목

- 전체 보고서 사용자 검토 반영
- 스타일 적용 DOCX 및 최종 PDF 생성

## 주의할 점

- 현재 기본 `SLC_CACHE_RATIO_PERCENT`는 `10`이다.
- 현재 Codex 셸은 WSL2 kernel header가 없어 module build가 실패하며, `sudo`/장치 접근도 제한된다. 실제 빌드와 실험은 일반 서버 로그인 shell에서 해야 한다.
- `echo reset > /proc/nvmev/debug`는 counter만 초기화하고 FTL state는 초기화하지 않는다.
- 정책 비교는 반드시 `umount -> rmmod -> insmod -> mkfs -> mount`의 fresh reload 조건으로 수행한다.
- 로컬 VM은 용량이 작아 `No space left on device` 같은 파일시스템 노이즈가 섞이기 쉽다. 최종 실측과 결과 표는 서버 결과만 기준으로 쓴다.
- `scripts/run_local_slc_validation.sh`는 `SLC_RATIO_OFF=0`, `SLC_RATIO_ON=10`을 기본으로 baseline/validation을 구성한다. `OVERFLOW_SIZE`가 너무 작아 migration이 안 보이면 더 키워야 한다.
- 로컬 `zipf_nrm` 재실행은 `RANDOM_DIST=zipf:1.2 NORANDOMMAP=1 UNIFORM_SIZE=600M UNIFORM_LOOPS=10 TLC_GC_POLICY=0`를 반드시 명시한다. 빠뜨리면 기본 `uniform 600M x 250`가 돌아간다.
- 로컬에서 정책별 `for` 루프를 돌릴 때 VS Code Remote가 끊기면 대개 `umount/rmmod/insmod/mkfs/mount` 재초기화 경계 문제라서 `tmux` 안에서 실행하는 편이 안전하다.
- active I/O path는 `slc_wp/tlc_wp/tlc_gc_wp`와 `slc_lm/tlc_lm` 기준으로 나뉘었지만, line metadata 저장소는 아직 `conv_ftl->lines` 하나를 공유한다.
- `gc_policy`는 TLC GC 전용 의미로 유지되고, `slc_migration_policy`가 별도로 추가됐다.
- 현재 결과 대부분은 `TLC_GC_CNT=0`이라 사실상 SLC migration policy 비교로 읽어야 한다.
- 실습1의 heap staleness 교훈은 migration Cost-Benefit에도 그대로 다시 검토해야 한다.

## 최신 검증 요약

- 로컬 VM에서 `make` 정상 동작 확인.
- 2026-08-28 서버 일반 shell에서 `baseline` 최종 실측도 완료했다.
  - `results/local_20260828_113345_slc_baseline_compare/tlc_only/`: `slc_cache_ratio_percent=0`, `write_bw_kib=1383760`, `write_iops=345940.135565`, `write_lat_avg_ns=45986.563729`, `write_lat_p99_ns=146432`
  - `results/local_20260828_113345_slc_baseline_compare/slc_on/`: `slc_cache_ratio_percent=10`, `write_bw_kib=841641`, `write_iops=210410.374015`, `write_lat_avg_ns=75815.745342`, `write_lat_p99_ns=634880`
  - `slc_on`에서는 `SLC_MIGRATION_CNT=102812`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT=39472631`, `INTERNAL_WRITE_TLC_PAGES=39472631`가 확인돼 baseline 조건이 SLC cache upside보다 overflow/migration cost를 크게 드러내는 쪽으로 해석된다.
- 2026-08-27 서버 일반 shell에서 guarded/reserve WIP 기준 `hotcold full guarded` 4정책이 모두 성공했다.
  - Greedy(`0`) `results/20260827_193453_slcpolicy0_greedy_hotcold_server_greedy_full_guarded/`: `sum=361104`, `max=41`, `slc_migrate_pages=18352180`, `tlc_gc_cnt=18828`
  - Random(`1`) `results/20260827_192853_slcpolicy1_random_hotcold_server_random_full_guarded/`: `sum=375216`, `max=42`, `slc_migrate_pages=18794946`, `tlc_gc_cnt=19670`
  - FIFO(`2`) `results/20260827_193630_slcpolicy2_fifo_hotcold_server_fifo_full_guarded/`: `sum=361344`, `max=25`, `slc_migrate_pages=15852568`, `tlc_gc_cnt=11922`
  - Cost-Benefit(`3`) `results/20260827_193804_slcpolicy3_costbenefit_hotcold_server_cb_full_guarded/`: `sum=363748`, `max=31`, `slc_migrate_pages=17472902`, `tlc_gc_cnt=16177`
  - `slc_migrate_pages` 순위는 `FIFO < Cost-Benefit < Greedy < Random`
  - `max`는 FIFO(`2`)가 최소
- 2026-08-27 서버 일반 shell에서 `overflow` 재검증도 성공했다.
  - `results/local_20260827_193407_slc_overflow_validation/`: `SLC_MIGRATION_CNT=1476`, `USER_READ_TLC_PAGES=476118`, `INTERNAL_WRITE_TLC_PAGES=566781`
- 2026-08-27 서버 일반 shell에서 `CRC verify policy1`도 성공했다.
  - `results/local_20260827_194155_slc_verify_policy1/`: `fio error=0`, `verify_status=pass`, `SLC_MIGRATION_CNT=38380`, `USER_READ_TLC_PAGES=6563552`
- `./scripts/run_local_slc_policy_compare.sh verify 0/1/2/3` 새 run 4개 모두 통과.
  - `results/local_20260825_170050_slc_verify_policy0/`
  - `results/local_20260825_170446_slc_verify_policy1/`
  - `results/local_20260825_172028_slc_verify_policy2/`
  - `results/local_20260825_172411_slc_verify_policy3/`
  - 각 `fio.json`의 `error=0`, `meta.txt`의 `verify_status=pass`
- 예전 빈 verify 실패 흔적 `results/local_20260823_232719_slc_verify_policy2/`, `results/local_20260823_232711_slc_verify_policy2/`는 삭제했다.
- `hotcold_v7_local_fix2` 4정책도 완료했고, 현재 가장 최신 비교 세트는 이것이다.
  - 공통 조건: `COLD_SIZE=512M`, `COLD_TOUCH_SIZE=256M`, `HOT_SIZE=64M`, `HOTCOLD_RUNTIME=60`, `TLC_GC_POLICY=0`
  - Greedy(`0`) `results/20260825_173008_slcpolicy0_greedy_hotcold_v7_local_fix2/`: `sum=203816`, `max=24`, `slc_migrate_pages=621486`
  - Random(`1`) `results/20260825_173122_slcpolicy1_random_hotcold_v7_local_fix2/`: `sum=204448`, `max=29`, `slc_migrate_pages=833622`
  - FIFO(`2`) `results/20260825_173309_slcpolicy2_fifo_hotcold_v7_local_fix2/`: `sum=174796`, `max=14`, `slc_migrate_pages=537958`
  - Cost-Benefit(`3`) `results/20260825_173433_slcpolicy3_costbenefit_hotcold_v7_local_fix2/`: `sum=189400`, `max=20`, `slc_migrate_pages=573157`
  - `slc_migrate_pages` 순위는 `FIFO < Cost-Benefit < Greedy < Random`
  - `max`는 이번에도 FIFO(`2`)가 최소
  - `tlc_gc_cnt`는 네 정책 모두 `0`

## 이전 핵심 결과

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
- `scripts/collect_summary.sh`를 확장했다.
  - 기존 `erase_sum`/`erase_max`/latency 외에 `policy_target`, `slc_migration_policy`, `tlc_gc_policy`, `random_dist`, `norandommap`, `uniform_size`, `uniform_loops`, `cold_size`, `cold_touch_size`, `hot_size`, `hotcold_runtime`, `memmap_size`, `slc_migration_cnt`, `slc_migrate_pages`, `tlc_gc_cnt`, `tlc_gc_migrate_pages`, `legacy_gc_migrate_pages`, `erase_cv`, `erase_cv_all`도 CSV 열로 수집한다.
  - `summary.txt`가 있는 실험은 해당 값을 우선 사용하고, `debug.txt`/`erase_cnt.txt`만 있는 결과는 counter를 fallback으로 읽는다.
  - 로컬 verify 결과처럼 `summary.txt`가 없는 디렉터리도 빈 칸 허용 형태로 함께 집계된다.
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
- 2026-08-24에 `zipf_nrm_rep2`도 로컬에서 네 정책 모두 완료됐다.
  - 공통 조건: `UNIFORM_SIZE=600M`, `UNIFORM_LOOPS=10`, `RANDOM_DIST=zipf:1.2`, `NORANDOMMAP=1`, `TLC_GC_POLICY=0`
  - Greedy(`0`) `results/20260824_173902_slcpolicy0_greedy_zipf_nrm_rep2/`: `sum=180644`, `max=42`, `slc_migrate_pages=112686`
  - Random(`1`) `results/20260824_174027_slcpolicy1_random_zipf_nrm_rep2/`: `sum=180660`, `max=36`, `slc_migrate_pages=152216`
  - FIFO(`2`) `results/20260824_174206_slcpolicy2_fifo_zipf_nrm_rep2/`: `sum=180608`, `max=21`, `slc_migrate_pages=120384`
  - Cost-Benefit(`3`) `results/20260824_175416_slcpolicy3_costbenefit_zipf_nrm_rep2/`: `sum=180608`, `max=31`, `slc_migrate_pages=104229`
  - baseline과 같은 방향으로 Random은 migration cost가 가장 높고, Cost-Benefit은 가장 낮다.
  - `results/20260824_173844_slcpolicy1_random_zipf_nrm_rep2/`는 파일이 없는 빈 디렉터리라 중간 실패 흔적으로 본다.
- 2026-08-24에 같은 조건으로 `zipf_nrm_rep2_rerun`도 로컬에서 네 정책 모두 완료됐다.
  - Greedy(`0`) `results/20260824_223708_slcpolicy0_greedy_zipf_nrm_rep2_rerun/`: `sum=182804`, `max=45`, `slc_migrate_pages=113526`
  - Random(`1`) `results/20260824_224519_slcpolicy1_random_zipf_nrm_rep2_rerun/`: `sum=182204`, `max=37`, `slc_migrate_pages=163745`
  - FIFO(`2`) `results/20260824_225438_slcpolicy2_fifo_zipf_nrm_rep2_rerun/`: `sum=181648`, `max=21`, `slc_migrate_pages=128099`
  - Cost-Benefit(`3`) `results/20260824_230218_slcpolicy3_costbenefit_zipf_nrm_rep2_rerun/`: `sum=182148`, `max=32`, `slc_migrate_pages=105106`
- 2026-08-24에 유효한 `zipf_nrm_rep3` 네 정책도 완료됐다.
  - Greedy(`0`) `results/20260824_232544_slcpolicy0_greedy_zipf_nrm_rep3/`: `sum=181416`, `max=43`, `slc_migrate_pages=113104`
  - Random(`1`) `results/20260824_232938_slcpolicy1_random_zipf_nrm_rep3/`: `sum=181736`, `max=34`, `slc_migrate_pages=159498`
  - FIFO(`2`) `results/20260824_233522_slcpolicy2_fifo_zipf_nrm_rep3/`: `sum=181420`, `max=21`, `slc_migrate_pages=126602`
  - Cost-Benefit(`3`) `results/20260824_234119_slcpolicy3_costbenefit_zipf_nrm_rep3/`: `sum=182148`, `max=31`, `slc_migrate_pages=105195`
  - baseline, `rep2`, `rep2_rerun`, `rep3` 4회 모두에서 `slc_migrate_pages` 순위는 `Cost-Benefit < Greedy < FIFO < Random`으로 유지됐다.
  - `max`는 네 번 모두 FIFO(`2`)가 가장 낮았다.
  - `results/20260824_223531_*`, `results/20260824_223532_*`, `results/20260824_223533_*`, `results/20260824_223543_*` 계열과 `results/20260824_231943_*`, `results/20260824_232208_*`, `results/20260824_232209_*`, `results/20260824_232225_*`는 비어 있거나 불완전한 실패 흔적이라 집계 대상이 아니다.
- 2026-08-25에 local-sized `hotcold v7` 4정책 1회도 완료했다.
  - 공통 조건: `COLD_SIZE=512M`, `COLD_TOUCH_SIZE=256M`, `HOT_SIZE=64M`, `HOTCOLD_RUNTIME=60`, `TLC_GC_POLICY=0`
  - Greedy(`0`) `results/20260825_160146_slcpolicy0_greedy_hotcold_v7_local/`: `sum=166664`, `max=38`, `slc_migrate_pages=859714`
  - Random(`1`) `results/20260825_160313_slcpolicy1_random_hotcold_v7_local/`: `sum=164660`, `max=26`, `slc_migrate_pages=694948`
  - FIFO(`2`) `results/20260825_160454_slcpolicy2_fifo_hotcold_v7_local/`: `sum=186236`, `max=15`, `slc_migrate_pages=598783`
  - Cost-Benefit(`3`) `results/20260825_160728_slcpolicy3_costbenefit_hotcold_v7_local/`: `sum=182388`, `max=41`, `slc_migrate_pages=934689`
  - 이번 `slc_migrate_pages` 순위는 `FIFO < Random < Greedy < Cost-Benefit`이라 `zipf_nrm`과 달랐다.
  - 1차 원인 후보는 `[scripts/workloads/hotcold.fio]`의 `cold_touch` 뒤 `stonewall`이다. 파일상 v7 설명은 병렬 churn인데 실제 정의는 `cold_fill -> cold_touch -> hot_churn` 직렬 실행처럼 보인다.
  - `fio.json`에서도 Greedy/Random/Cost-Benefit은 aggregate `job_runtime`이 약 `120000 ms`, FIFO는 `201699 ms`까지 늘어, "60초 병렬 churn" 가정보다 직렬/비대칭 실행 쪽 해석이 더 맞다.
- 위 문제를 수정하려고 `[scripts/workloads/hotcold.fio]`에서 `cold_touch` 뒤 `stonewall`을 제거했고, `hotcold_v7_local_fix1` 4정책을 다시 수행했다.
  - Greedy(`0`) `results/20260825_162504_slcpolicy0_greedy_hotcold_v7_local_fix1/`: `sum=175592`, `max=21`, `slc_migrate_pages=545773`
  - Random(`1`) `results/20260825_162633_slcpolicy1_random_hotcold_v7_local_fix1/`: `sum=175500`, `max=30`, `slc_migrate_pages=723055`
  - FIFO(`2`) `results/20260825_162900_slcpolicy2_fifo_hotcold_v7_local_fix1/`: `sum=178064`, `max=14`, `slc_migrate_pages=543900`
  - Cost-Benefit(`3`) `results/20260825_163008_slcpolicy3_costbenefit_hotcold_v7_local_fix1/`: `sum=175692`, `max=19`, `slc_migrate_pages=534360`
  - 수정 후 `slc_migrate_pages` 순위는 `Cost-Benefit < FIFO < Greedy < Random`으로 바뀌었고, `zipf_nrm`의 큰 방향(`Cost-Benefit` 최저, `Random` 최고)과 일치했다.
  - `max`는 이번에도 FIFO(`2`)가 가장 낮았다.
  - 따라서 최종 비교에는 `*hotcold_v7_local_fix1*`만 사용하고, 첫 `*hotcold_v7_local*` run은 `stonewall` 버그가 섞인 참고용 흔적으로만 둔다.
- 2026-08-25에 SLC/TLC별 oneshot/timing 분기도 코드에 추가했다.
  - `[ssd_config.h]`에 `SLC_ONESHOT_PAGE_SIZE`, `TLC_ONESHOT_PAGE_SIZE`, SLC read/write latency 기본값을 추가했다.
  - `[ssd.h]`, `[ssd.c]`에 `nand_cmd.media`, `slc_pgs_per_oneshotpg`, `slc_pg_*_lat`를 추가해 SLC/TLC NAND timing을 분기했다.
  - `[conv_ftl.c]`에서 `last_pg_in_wordline()`, write pointer 전진, host write NAND 발행 크기, migration/GC read-write, host read NAND timing이 SLC/TLC pool에 따라 다른 oneshot/timing을 타도록 바꿨다.
- 같은 날 active I/O path의 legacy `wp/gc_wp` 의존도 제거했다.
  - `[conv_ftl.h]`에서 legacy `wp`, `gc_wp` 필드를 제거했다.
  - `[conv_ftl.c]`의 `__get_wp()`는 이제 host write를 `slc_wp` 또는 `tlc_wp`, migration/GC write를 `tlc_gc_wp`로 직접 매핑한다.
  - 즉 host/migration write pointer 경로는 이제 `slc_rt` 구조를 직접 사용한다.
- 같은 날 free/full/victim manager도 pool별로 직접 분리했다.
  - `[conv_ftl.h]`에서 shared `line_mgmt lm`를 제거하고, top-level에는 `conv_ftl->lines` 배열만 남겼다.
  - `[conv_ftl.c]`의 victim 선택, free line 할당, line close, invalidation, free 반환은 이제 `slc_lm` 또는 `tlc_lm`의 list/PQ/count를 직접 사용한다.
  - 즉 active manager state는 `slc_lm/tlc_lm`로 넘어갔고, 남은 공유 상태는 line metadata 배열 자체다.

## 다음 세션 시작점

- 다음 세션은 로컬 고정이 아니다. `sudo`, `make`, `fio`가 실제로 되는 일반 서버 shell 또는 로컬 VM 중 실행 가능한 쪽에서 시작한다.
- 시작 확인 순서는 `git status --short`, `ls -td results/*hotcold_v7_local_fix2* | head`, `sed -n '1,220p' docs/CURRENT_TASK.md`, `sed -n '1,220p' scripts/run_experiment.sh` 정도면 충분하다.
- 그 다음 목표는 서버 실측을 확보한 뒤 `zipf_nrm` 4회분과 `hotcold_v7_local_fix2`를 묶어 최종 비교 표와 본문을 만드는 것이다.

## 참고 문서

- 구현 이력: `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
- 과제 요구사항 확인: `docs/PRACTICE2_AGENTS`

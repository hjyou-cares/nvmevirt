# NVMeVirt 프로그래밍 실습2 진행 기록

이 문서는 “NVMeVirt 활용 SLC cache 구현” 실습의 조사, 설계 결정, 코드 변경,
검증 결과와 남은 질문을 시간순으로 기록한다.

기록할 때 다음을 구분한다.

- **확정된 사실**: 과제 PDF, 현재 코드, Git history 또는 실제 실험에서 확인한 내용
- **합리적인 추정**: 현재 근거로 가능성이 높지만 아직 확정되지 않은 내용
- **확인 필요**: 사용자 또는 조교의 답변이 필요한 내용

코드 변경의 최종 근거는 Git commit으로 남기고, 이 문서에는 변경 이유와 검증 결과를
중심으로 기록한다.

## 2026-08-13: 선행 조사 및 출발점 승인

### 확인한 사실

- 작업 저장소는 `/home/hjyou/nvmevirt` 하나이다.
- remote는 `https://github.com/hjyou-cares/nvmevirt.git`이다.
- 실습1 완료 HEAD는 `ae28ab11cd11769358c0bc578ee65f055b28c5a9`이다.
- 실습1 이전 skeleton 기준 commit의 가장 강한 후보는
  `61c90f7758cbd9545b4a4727e89377bf88eab060`이다.
- `main`과 `origin/main`은 선행 조사 시점에 같은 commit을 가리켰다.
- `Note.md`는 HEAD의 `CLAUDE.md`와 내용이 완전히 같으며, 현재 worktree에서는
  `CLAUDE.md` 삭제와 `Note.md` 추가로 표시된다.
- `AGENTS.md`, `Note.md`, `docs/`는 아직 Git에 추적되지 않은 상태다.
- 현재 `ssd_config.h`에는 SLC 비율, SLC/TLC별 oneshot page size 및 latency 설정이
  존재하지 않는다.
- 현재 Conventional FTL에는 mapping table, reverse mapping table, line manager가
  각각 하나씩 있으며, SLC/TLC 영역은 분리되어 있지 않다.
- 실습1에서 추가된 GC policy와 counter는 TLC GC를 대상으로 하므로 SLC→TLC
  migration policy 및 통계와 분리해야 한다.
- 시간에 따라 변하는 Cost-Benefit priority는 heap root가 현재 최적 victim임을
  보장하지 못하므로 현재 후보 전체 재평가가 필요할 수 있다.

### 공식 과제 요구사항

- Conventional FTL에 SLC cache를 구현한다.
- 기본 write는 SLC에서 처리한다.
- SLC가 가득 차면 valid data를 TLC로 migration한다.
- read는 단일 mapping을 통해 SLC 또는 TLC에서 처리한다.
- TLC 영역에서는 기존 TLC→TLC GC를 수행한다.
- SLC line manager와 TLC line manager를 별도로 관리한다.
- mapping table은 하나만 사용한다.
- SLC와 TLC의 서로 다른 oneshot page size를 반영한다.
- config를 통해 SLC 비율을 dynamic하게 설정한다.
- migration victim 정책 Greedy, Random, FIFO, Cost-Benefit을 비교한다.
- throughput과 latency를 측정하며 구현 코드, 그래프, 간단한 분석 보고서를 제출한다.

### 출발점 결정

- **사용자 승인일**: 2026-08-13
- **기준 commit**: `ae28ab11cd11769358c0bc578ee65f055b28c5a9`
- **실습2 branch**: `practice2-slc-cache`
- **결정**: 실습1 완료 코드를 출발점으로 사용하되, TLC GC의 manager, policy,
  queue 및 counter를 SLC migration과 혼용하지 않는다.

### 유지할 실습1 요소

- module unload/load를 이용한 독립된 FTL 초기 상태 확보 절차
- fio JSON과 실험 metadata 보존
- CRC/read-back 데이터 정합성 검증
- erase count 및 TLC GC 비용 계측
- 동적 Cost-Benefit priority의 heap staleness 교훈

### 수정하여 재사용할 요소

- migration policy 선택 경로
- `/proc/nvmev/debug` 계측
- 실험 자동화 및 결과 집계 스크립트
- line close timestamp 또는 sequence metadata

### 제외 또는 비활성화 검토 요소

- 실습1 보고서 전용 Greedy/Cost-Benefit divergence 전체 scan
- hot path를 과도하게 왜곡할 수 있는 진단 코드
- 실습1 결과와 실습2 결과를 혼합하는 집계 경로
- 학습용으로 남은 일회성 inline 주석

### 검증하지 않은 사항

- 아직 build하지 않았다.
- module load/unload를 수행하지 않았다.
- benchmark, mount, unmount 또는 `mkfs`를 수행하지 않았다.
- SLC cache 구현 코드는 아직 변경하지 않았다.

### 확인이 필요한 질문

1. 과제용 별도 `ssd_config.h` 또는 skeleton patch가 있는가?
2. SLC 비율의 단위, 범위와 0%/100% 지원 여부는 무엇인가?
3. “dynamic”은 초기화 시 설정을 뜻하는가, 실행 중 resize도 포함하는가?
4. SLC/TLC의 정확한 oneshot page size와 latency 값은 무엇인가?
5. SLC/TLC line은 초기화 시 고정 분할되는가?
6. migration trigger와 foreground/background 실행 방식은 무엇인가?
7. FIFO와 Cost-Benefit의 공식 정의 및 age 기준은 무엇인가?

### 다음 단계

1. 현재 branch와 worktree 상태를 확인한다.
2. 기존 Conventional FTL을 build하고 baseline 정합성을 검증한다.
3. SLC/TLC 설정의 누락 여부를 사용자 또는 조교 자료에서 확인한다.
4. 설정이 확정되면 동작 변경 없이 config와 경계값 검증부터 추가한다.

## 2026-08-13: baseline build 1차 확인

### 수행한 작업

- 실습1 완료 코드를 변경하지 않은 상태에서 `make`를 실행했다.
- module load, mount, `mkfs` 및 benchmark는 수행하지 않았다.

### 검증 결과

- **build 실패 (환경 문제)**
- 현재 실행 커널은 `6.18.33.2-microsoft-standard-WSL2`이다.
- Makefile이 요구한 kernel build directory
  `/lib/modules/6.18.33.2-microsoft-standard-WSL2/build`가 존재하지 않아 module
  compilation이 시작되기 전에 종료됐다.
- 따라서 이번 결과는 NVMeVirt source의 compile error를 의미하지 않는다.

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

## 2026-08-14: 실습2 선행 학습 정리

### 수행한 작업

- 실습2 구현 전 학습 단계로 다음 11개 주제를 현재 코드와 과제 자료 기준으로 순서대로 정리했다.
  - SLC/TLC와 SLC cache의 의미
  - Conventional FTL 전체 구조
  - channel/lun/block/page/line 관계
  - logical page, physical page, mapping table
  - 기존 host write 경로
  - 기존 host read 경로
  - line manager와 write pointer
  - 기존 TLC GC 경로
  - SLC/TLC line manager를 분리해야 하는 이유
  - SLC→TLC migration 전체 흐름
  - SLC/TLC oneshot page size 차이
- 학습 기록은 `codestudy/studynote.md`에 단계별 상세 설명 형태로 남겼다.
- 추가로 “실습2에서 현재 코드의 어디를 바꿔야 하는지”를 구현 큰 그림 관점에서 별도 정리했다.

### 확정된 사실

- 현재 Conventional FTL은 단일 `line_mgmt`, 단일 host write pointer, 단일 TLC GC 구조를 전제로 한다.
- 실습2는 mapping table은 하나로 유지하되, SLC/TLC line manager, write 목적지, migration/TLC GC 의미를 분리해야 한다.
- 현재 코드는 `ONESHOT_PAGE_SIZE`를 전역 단일 값으로 사용하므로, 실습2의 SLC/TLC oneshot 차이를 그대로 반영하지 못한다.

### 변경한 내용

- 구현 코드 변경 없음
- 학습 노트 `codestudy/studynote.md` 갱신
- 이 진행 기록만 추가 갱신

## 2026-08-14: 다음 작업 합의 및 선행 학습 메모

### 현재까지 합의한 다음 단계

- 실습2 구현은 바로 write/migration부터 건드리지 않고, 먼저 구조 분리부터 시작한다.
- 첫 구현 단위는 다음 세 부분이다.
  1. `ssd_config.h`에 SLC 비율 설정값 추가
  2. `conv_ftl.h`에서 SLC/TLC line manager로 분리 가능한 metadata 구조 추가
  3. 초기화 코드에서 전체 line을 SLC/TLC로 나누어 manager 2개를 세팅
- 그 다음 순서는
  1. host write를 SLC로 보내기
  2. 단일 mapping 기반 read 유지
  3. Greedy 기반 SLC→TLC migration 구현
  4. Random/FIFO/Cost-Benefit 확장
  5. 계측과 스크립트 분리

### 구현 전 공부가 필요한 기본 개념

- SLC란 무엇인지
- TLC란 무엇인지
- SLC가 TLC보다 왜 빠르고 내구성이 높은지
- SLC cache가 왜 필요한지
- host write가 SLC에 먼저 기록된 뒤 TLC로 migration되는 이유
- mapping table이 왜 필요한지
- valid page와 invalid page의 의미
- garbage collection과 migration의 차이

### 오늘 시점의 상태 요약

- NVMeVirt module load, `/dev/nvme0n1` 생성, ext4 mount, 사용자 write는 정상 확인됨
- 과제 PDF 대체 텍스트와 현재 코드 조사는 완료됨
- SLC 비율 경계값 방침(`0%` 허용, `100%` 비허용 초안)도 기록됨
- 아직 실습2 구현 코드는 시작하지 않았음

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

## 2026-08-14: SLC 비율 경계값 설계 방침 초안

### 설계 결정 초안

- `slc_ratio_percent`는 config에서 `0~100` 범위를 받는 형태로 설계한다.
- `0%`는 SLC를 비활성화한 TLC-only baseline 모드로 허용한다.
- `1~99%`는 실습2의 정상 SLC cache + SLC→TLC migration 모드로 사용한다.
- `100%`는 허용하지 않는 방향을 기본안으로 잡는다.

### 결정 이유

- 과제는 SLC 비율을 config로 설정 가능하게 하라고 요구하지만, `0%`와 `100%`
  경계값의 의미는 명시하지 않는다.
- `0%`는 기존 Conventional FTL과의 baseline 비교에 유용하며 구조적으로도 자연스럽다.
- `100%`는 TLC 영역이 없어 SLC→TLC migration의 목적지가 사라지므로 과제의 핵심
  동작과 충돌한다.
- 따라서 입력 인터페이스는 일반적으로 설계하되, 과제 목표와 충돌하는 경계값은
  명시적으로 제한하는 것이 가장 보수적이고 설명 가능한 선택이다.

### 구현 시 반영 계획

- 초기화 시 `slc_ratio_percent < 0 || slc_ratio_percent > 100`은 즉시 오류 처리한다.
- `slc_ratio_percent == 100`도 명시적으로 오류 처리하거나 비지원으로 보고한다.
- 보고서와 진행 기록에는 `100%`를 막은 이유를
  “migration destination인 TLC 영역이 필요하기 때문”이라고 남긴다.

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

## 2026-08-14: NVMeVirt block device load 및 mount 확인

### 수행한 작업

- Ubuntu VM에서 `make`, `insmod`, `mkfs.ext4`, `mount`를 사용자와 함께 수행했다.
- 현재 세션에서는 시스템 조회가 제한되어 있어, 장치 생성과 마운트 결과는 사용자
  터미널 출력으로 확인했다.

### 확정된 사실

- `insmod` 이후 `/dev/nvme0`와 `/dev/nvme0n1`이 생성되었다.
- `mount | grep nvme` 결과 `/dev/nvme0n1`이
  `/home/hjyu216/nvme_mount`에 `ext4 (rw,relatime)`로 마운트되어 있다.
- `df -h | grep nvme` 결과 `/dev/nvme0n1`의 사용 가능 용량은 약 `923M`로 표시된다.
- `touch ~/nvme_mount/testfile`가 성공했고, 생성된 파일의 owner는 `hjyu216:hjyu216`
  이다.
- 따라서 현재 VM에서는 NVMeVirt block device 생성, ext4 마운트, 사용자 쓰기 권한이
  모두 정상 동작한다.

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

### 남은 위험과 다음 확인

- mount 성공은 확인됐지만, 실습2 공식 명세의 SLC/TLC 설정 항목은 아직 과제 PDF에서
  직접 대조하지 않았다.
- 다음 단계로 과제 PDF를 읽어 SLC 비율, dynamic 설정 의미, oneshot page size,
  latency, migration trigger와 policy 정의가 실제로 명시돼 있는지 확인한다.

## 2026-08-14: 실습2 코드 조사 결과 정리

### 수행한 작업

- `docs/PRACTICE2_AGENTS`를 공식 과제 PDF 대체 텍스트로 읽고 요구사항을 다시 정리했다.
- `ssd_config.h`, `ssd.c`, `conv_ftl.h`, `conv_ftl.c`, `main.c`,
  `scripts/run_experiment.sh`, `scripts/run_filebench_experiment.sh`를 읽어
  과제 요구사항별 현재 구현 상태를 대조했다.
- 현재 branch/HEAD와 worktree 상태를 확인했다.

### 확정된 사실

- 현재 branch는 `practice2-slc-cache`이고 HEAD는
  `cc7bd53efb1918a815586ac924bf8f49552a73aa`이다.
- 현재 worktree의 변경은 `docs/PRACTICE2_LOG.md` 수정과
  `docs/PRACTICE2_AGENTS` 추가뿐이다.
- 현재 `ssd_config.h`는 Samsung Conventional profile에서 단일 `CELL_MODE`,
  단일 `FLASH_PAGE_SIZE`, 단일 `ONESHOT_PAGE_SIZE`만 정의한다.
- 현재 `ssd_config.h`에는 SLC 비율, SLC/TLC별 oneshot page size, SLC/TLC별
  latency 설정이 없다.
- `ssd_init_params()`는 단일 `CELL_MODE`와 단일 `ONESHOT_PAGE_SIZE`를 사용해
  전체 geometry를 한 번만 계산한다.
- `struct conv_ftl`에는 `maptbl` 하나, `rmap` 하나, `line_mgmt lm` 하나,
  host용 write pointer 하나(`wp`), GC용 write pointer 하나(`gc_wp`)만 있다.
- 현재 Conventional FTL에는 SLC line manager와 TLC line manager의 분리가 없다.
- 현재 host write 경로는 모든 write를 단일 `USER_IO` write pointer로 기록한다.
- 현재 read 경로는 단일 mapping table을 통해 PPA를 읽는다.
- 현재 GC 경로는 victim line의 valid page를 같은 공간의 `GC_IO` write pointer로
  다시 쓰고 free line으로 반환하는 TLC→TLC GC다.
- 현재 `gc_policy` module parameter는 `0=Greedy, 1=Random, 2=Cost-Benefit`
  뿐이며 FIFO는 없다.
- 실습1의 Cost-Benefit 구현에는 `line.mtime`, `cb_clock`,
  stale heap 회피를 위한 현재 후보 전체 재평가가 포함되어 있다.
- `/proc/nvmev/debug`는 현재 TLC GC 관련 통계와 실습1 진단값만 출력한다.
- 실험 스크립트는 모두 실습1의 `gc_policy` 기반 TLC GC 정책 비교를 전제로 한다.

### 과제 요구사항별 조사 표

| 과제 요구사항 | 관련 파일·구조체·함수 | 현재 구현 상태 | 필요한 변경 | 불확실한 부분 |
|---|---|---|---|---|
| Config 기반 SLC 비율 | `ssd_config.h`, `ssd.c:ssd_init_params()` | SLC 비율 설정 없음 | `ssd_config.h`에 SLC 비율 설정 추가, 초기화 시 line 수를 SLC/TLC로 분할 | `dynamic`이 실행 중 변경까지 뜻하는지는 미확정 |
| SLC line manager | `conv_ftl.h:struct line_mgmt`, `conv_ftl.h:struct conv_ftl` | line manager 하나만 존재 | SLC 전용 free/full/victim 상태 추가 | line 고정 분할 방식은 코드 설계 필요 |
| TLC line manager | 동일 | 현재 유일한 manager가 사실상 TLC-only 구조 | 기존 manager를 TLC manager로 재해석하고 SLC manager를 별도 추가 | SLC migration과 TLC GC의 free line 경쟁 처리 필요 |
| 단일 mapping table | `conv_ftl.h:maptbl`, `conv_ftl.c:get_maptbl_ent/set_maptbl_ent` | 이미 mapping table 하나 | 유지 | migration ordering과 overwrite race 처리 방식 재검토 필요 |
| SLC oneshot page | `ssd_config.h`, `ssd.c`, `conv_ftl.c:last_pg_in_wordline()` | 단일 전역 oneshot page size만 존재 | SLC 전용 write/program 단위 추가 | 정확한 값은 현재 skeleton에 없음 |
| TLC oneshot page | 동일 | 단일 전역 oneshot page size만 존재 | TLC 경로도 SLC와 분기되는 구조 필요 | 정확한 값과 표현 방식 미확정 |
| SLC write | `conv_ftl.c:conv_write()`, `prepare_write_pointer()`, `advance_write_pointer()` | 모든 host write가 단일 공간으로 감 | host write를 SLC write pointer로 보내야 함 | SLC full 시 TLC direct host write 허용 여부 미확정 |
| SLC/TLC read | `conv_ftl.c:conv_read()` | 단일 mapping 기반 read는 이미 존재 | mapping이 가리키는 위치에 따라 SLC/TLC timing 분기 필요 | SLC/TLC read latency 값 미확정 |
| SLC→TLC migration | `conv_ftl.c:gc_write_page()`, `do_gc()` | 현재는 TLC→TLC GC만 존재 | SLC victim 선택, TLC destination 할당, SLC reclaim 경로 추가 | trigger 조건과 foreground/background 여부 미확정 |
| TLC→TLC GC | `conv_ftl.c:select_victim_line()`, `do_gc()` | 이미 구현됨 | 유지하되 SLC migration과 정책/queue/counter 분리 | threshold 조정 필요 가능성 |
| Greedy migration policy | `conv_ftl.c:gc_policy`, `select_victim_line()` | TLC GC용만 존재 | SLC migration policy로 별도 구현 | tie-break 기준 미확정 |
| Random migration policy | `conv_ftl.c:select_victim_line()` | TLC GC용만 존재, raw queue random remove 방식 구현됨 | SLC migration queue에 맞게 재사용 가능 | 후보 집합 정의 확인 필요 |
| FIFO migration policy | 없음 | 구현 없음 | close sequence 또는 victim insertion order metadata 추가 필요 | FIFO 기준 시점 미확정 |
| Cost-Benefit migration policy | `conv_ftl.c:cb_clock`, `cb_victim_pri()`, `select_victim_line()` | TLC GC용 구현 존재 | SLC migration에 재사용 가능성 높음, 단 의미 재검증 필요 | 공식 식과 age 정의 미확정 |
| throughput/latency 측정 | `main.c:/proc/nvmev/debug`, `scripts/run_experiment.sh`, `scripts/run_filebench_experiment.sh` | 실습1용 계측/자동화 존재 | SLC migration vs TLC GC 통계 분리, SLC/TLC별 계측 추가 | tail latency percentile, 반복 횟수, workload 필수 조건은 미확정 |

### 코드에 근거한 추정

- 가장 작은 구조 변경은 기존 TLC GC 코어를 유지하고, 그 위에 SLC manager,
  SLC write pointer, SLC→TLC migration 경로를 추가하는 방식이다.
- mapping table은 둘로 나누지 말고, PPA가 SLC/TLC 어느 영역을 가리키는지만
  판별하는 helper를 두는 방향이 과제 요구사항과 현재 코드에 가장 잘 맞는다.
- Cost-Benefit처럼 age에 따라 priority가 바뀌는 migration policy는 실습1과
  마찬가지로 heap root만 믿으면 stale priority 문제가 재발할 가능성이 높다.

### 아직 확정되지 않은 질문

1. `dynamic`이 실행 중 비율 변경까지 포함하는가?
2. SLC 비율의 기본값, 단위와 허용 범위는 무엇인가?
3. SLC/TLC의 정확한 oneshot page size와 latency 값은 무엇인가?
4. SLC full 또는 migration trigger의 정확한 기준은 무엇인가?
5. migration은 foreground인가, background인가?
6. FIFO의 기준 시점은 line close인가, victim queue 진입인가?
7. Cost-Benefit의 공식 계산식과 age 정의는 무엇인가?
8. SLC full 시 TLC direct host write를 허용하는가?

### 단계별 구현 계획 초안

1. `ssd_config.h`와 `conv_ftl.h`에 SLC/TLC 구분을 위한 최소 설정과 metadata를 추가한다.
2. 단일 `lm/wp/gc_wp` 구조를 SLC host write, TLC write, TLC GC가 공존할 수 있도록
   분리한다.
3. host write를 SLC로 보내고, read는 단일 mapping 구조를 유지한다.
4. Greedy 기반 SLC→TLC migration을 먼저 구현해 정상 동작을 만든다.
5. migration policy를 Greedy, Random, FIFO, Cost-Benefit으로 확장한다.
6. 계측과 스크립트를 SLC migration과 TLC GC로 분리한다.

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

### 남은 위험과 다음 확인

- WSL2에서 NVMeVirt kernel module을 실제로 build/load할 수 있는 환경인지 확인이 필요하다.
- 실습1에서 사용한 Ubuntu VM 또는 실험 서버가 현재도 사용 가능한지 확인해야 한다.
- 실제 build 환경이 정해질 때까지 module load 및 block device 검증을 진행하지 않는다.

## 2026-08-13: VirtualBox Ubuntu VM baseline 및 RCU stall 재조사

### 수행한 작업

- `/home/hjyu216/nvmevirt`에서 읽기 전용으로 현재 `cwd`, kernel, branch, HEAD,
  `git status`, remote를 확인했다.
- 저장소 안의 `AGENTS.md`, `docs/PRACTICE2_CODEX_INSTRUCTIONS.md`,
  `docs/PRACTICE2_LOG.md`, `Note.md`를 끝까지 읽고 현재 지시와 과거 기록을 대조했다.
- `/proc/cmdline`로 현재 부팅 커맨드라인을 확인했다.
- 현재 세션에서 접근 가능한 범위 안에서 `main.c`, `conv_ftl.c`, 실험 스크립트와
  기록 문서를 교차검증했다.
- 이전 부팅 kernel log, `/boot`, `/var/log`, `/sys/class/dmi`, `lsmod`, `dpkg` 등
  저장소 밖 시스템 정보도 읽으려 했지만, 이 세션의 샌드박스 제한 때문에 직접 값
  을 얻지 못했다.

### 확정된 사실

- 현재 작업 경로는 `/home/hjyu216/nvmevirt`이다.
- 현재 실행 kernel은 `6.8.0-136-generic`이다.
- 현재 branch는 `practice2-slc-cache`이고, HEAD는
  `cc7bd53efb1918a815586ac924bf8f49552a73aa`이다.
- `git status --short --branch` 기준 worktree에는 추적된 변경이 없고,
  branch는 `origin/practice2-slc-cache`를 추적 중이다.
- remote `origin`은 `https://github.com/hjyou-cares/nvmevirt.git`이다.
- 저장소 안 `AGENTS.md`는 작업 전에
  `docs/PRACTICE2_CODEX_INSTRUCTIONS.md`를 읽고, 사용자가 선행 조사 결과를 확인하기
  전에는 코드·branch·파일을 변경하지 말라고 지시한다.
- 현재 `/proc/cmdline`은
  `BOOT_IMAGE=/boot/vmlinuz-6.8.0-136-generic root=UUID=cccaa1df-2ac8-4c62-80de-b5cbf9ed4304 ro memmap=1G$2G intremap=off quiet splash`
  이다.
- 따라서 현재 부팅된 GRUB 커맨드라인에는 `memmap=1G$2G intremap=off`가 포함되어
  있고, `isolcpus=2,3`은 포함되어 있지 않다.
- `main.c`에는 `memmap_start`, `memmap_size`, `cpus`가 각각 module parameter로
  존재하며, `cpus`는 `module_param(cpus, charp, 0444)`로 선언되어 있다.
- `main.c`는 CPU 목록 파싱에서 `while ((cpu = strsep(&cpus, ",")) != NULL)`를 사용한다.
  따라서 `Note.md`에 적힌 “원래 포인터를 소모해서 `/sys/module/nvmev/parameters/cpus`
  가 `(null)`로 보일 수 있다”는 설명은 현재 코드와 부합한다.
- `conv_ftl.c`에는 실습1 GC 정책 선택용 `gc_policy` module parameter가 남아 있고,
  현재도 Greedy/Random/Cost-Benefit 분기와 관련 주석이 존재한다.
- `scripts/run_experiment.sh`와 `scripts/run_filebench_experiment.sh`는 현재도
  `insmod ... memmap_start=... memmap_size=... cpus=... gc_policy=...` 형태의
  실습1 자동화 경로를 포함한다.
- `Note.md`에는 이번 VM 관련으로 다음 사실이 기록돼 있다.
  `memmap_start=2G`, `memmap_size=1G`, `cpus=2,3`, `gc_policy=0`,
  `isolcpus` 제거 후 idle 상태 150초 동안 stall 없음,
  그러나 `mkfs.ext4` 후 RCU stall 재발,
  stall stack에 `nvmev_io_worker`, `local_clock`, `kvm_sched_clock_read`,
  `__raw_spin_lock_irqsave`가 나타남,
  `clocksource: Long readout interval` 약 103초가 기록됨.

### 합리적인 추정

- 현재 VM 문제는 `isolcpus` 하나만의 문제라기보다, I/O worker가 활발히 동작할 때의
  clocksource 또는 스케줄링 지연이 NVMeVirt 경로와 겹치는 쪽일 가능성이 높다.
  근거는 `isolcpus` 제거 후 idle 상태에서는 stall이 멈췄지만, `mkfs.ext4` 후에는
  stall이 재발했다는 기존 기록이다.
- `local_clock` 및 `kvm_sched_clock_read`가 stall stack에 반복적으로 나타났다는 기존
  기록을 따르면, 다음 검증은 module 코드 변경보다 먼저 guest clocksource와 kernel
  계열(예: 5.15) 차이를 확인하는 쪽이 가장 작고 안전하다.
- 현재 branch의 코드 상태상, 실습1 GC 정책 계측과 실험 스크립트는 그대로 존재하므로
  실습2 구현 전에 이들과 SLC migration 정책/통계를 분리 설계해야 한다.

### 이 세션에서 직접 확정하지 못한 항목

- 현재 `nvmev` module이 실제로 내려간 상태인지 여부
- 현재 `/sys/module/nvmev/parameters/*`의 실시간 값
- 이전 부팅의 실제 `journalctl -k -b -1` 로그 원문
- Ubuntu 5.15 kernel package 및 `/boot` 이미지 설치 여부
- DMI 기준 VirtualBox 제품명과 vendor 문자열

위 항목들은 사용자 메모와 `Note.md`에는 기술되어 있으나, 이 세션에서는 저장소 밖
시스템 경로 접근이 차단되어 직접 재검증하지 못했다.

### 코드 변경 없이 권장하는 가장 작은 다음 검증

1. 같은 VM에서 읽기 전용으로 이전 부팅 `journalctl -k -b -1`를 다시 확보해,
   stall 직전과 직후의 `clocksource`, `rcu`, `watchdog`, `nvmev` 메시지를
   절대 시각과 함께 정리한다.
2. Ubuntu 5.15 kernel이 이미 설치돼 있는지만 확인한다. 설치돼 있다면 코드 변경 없이
   5.15로 한 번만 부팅해 같은 GRUB(`memmap=1G$2G intremap=off`)에서 module idle
   상태를 먼저 관찰하는 것이 가장 작은 분리 실험이다.
3. 위 두 항목이 확보되기 전에는 `insmod`, `mkfs`, `mount`, `fio`를 반복하지 않는다.

### 변경한 내용

- 구현 코드 변경 없음
- 이 진행 기록만 갱신

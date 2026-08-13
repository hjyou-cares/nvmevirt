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


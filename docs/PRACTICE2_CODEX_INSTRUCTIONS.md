# NVMeVirt 프로그래밍 실습2: SLC Cache 구현 프로젝트

나는 2026년 8월 28일까지 서울대학교 CARES 신입생 트레이닝 “프로그래밍 실습2: NVMeVirt 활용 SLC cache 구현”을 완료해야 한다.

너는 코드를 곧바로 수정하지 말고, 먼저 현재 저장소와 실습1 변경 사항, 실습2 과제 자료를 면밀하게 조사해야 한다. 그 결과를 근거로 현재 코드를 실습2의 출발점으로 사용해도 되는지 판단하고, 내가 그 판단을 확인한 다음에만 구현을 시작해라.

---

# 1. 현재 저장소 상황

작업 대상은 다음 하나의 저장소다.

```text
/home/hjyou/nvmevirt
```

이 저장소는 다음 upstream NVMeVirt skeleton code를 기반으로 만들었다.

```text
https://github.com/snu-csl/nvmevirt
```

별도의 깨끗한 NVMeVirt 폴더가 있는 것이 아니다.

현재 저장소 하나에 다음 내용이 함께 들어 있다.

- 최초 NVMeVirt skeleton code
- 실습1에서 수정한 NVMeVirt 코드
- 실습1용 계측과 실험 스크립트
- 실습1 보고서와 실험 결과
- 실습1 진행 기록인 `Note.md`
- 실습2 참고자료가 들어 있는 `docs/`

새 저장소를 clone하거나 새 폴더를 만들지 마라.

현재 Git 기록을 이용해 다음 두 상태를 비교해야 한다.

1. 실습1을 시작하기 전 skeleton 상태
2. 현재 실습1 완료 상태

새 branch나 worktree도 조사 단계에서는 만들지 마라. 필요하다고 판단하면 기준 commit, branch 이름, 이유를 먼저 제안하고 내 확인을 받아라.

---

# 2. 나의 배경과 설명 방식

나는 하드웨어, SSD, 커널 프로그래밍, C 언어 경험이 많지 않은 초보자다.

다음 원칙을 반드시 지켜라.

1. 함수 이름이나 수정 코드부터 제시하지 말고, 먼저 해당 기능이 왜 필요한지 설명한다.
2. 설명은 가급적 다음 순서를 따른다.
   - 해결하려는 문제
   - SSD/FTL 관점의 개념
   - 현재 NVMeVirt의 관련 실행 흐름
   - 수정할 파일·구조체·함수
   - 실제 코드 변경
   - 검증 방법
3. 큰 작업은 작은 단계로 나눈다.
4. 한 번에 많은 파일을 수정하지 않는다.
5. 중요한 설계 선택은 구현 전에 대안과 trade-off를 설명한다.
6. 코드와 자료에서 확인되지 않는 과제 명세를 임의로 확정하지 않는다.
7. 현재 저장소의 사용자 변경을 보존한다.
8. 과제와 무관한 파일은 수정하지 않는다.
9. 파일 전체를 무분별하게 재작성하지 말고 최소 범위만 수정한다.
10. 각 단계가 끝날 때 다음을 정리한다.
    - 확인한 내용
    - 변경한 내용
    - 변경 이유
    - 검증 결과
    - 남은 위험과 질문
11. 추측, 코드에서 확인한 사실, 실제 실험 결과를 명확히 구분한다.
12. 이해가 필요한 중요한 단계에서는 내가 따라올 수 있도록 설명 속도를 조절한다.

---

# 3. 자료 확인 순서

작업을 시작하기 전에 다음 파일을 확인한다.

```text
/home/hjyou/nvmevirt/Note.md
/home/hjyou/nvmevirt/docs/
```

`docs/`에서 다음 PDF 3개의 실제 파일명을 찾아 모두 읽어라.

1. `NVMeVirt과제-SLC_cache 구현.pdf`
2. `Analysis_on_Heterogeneous_SSD_Configuration_with_Quadruple_Level.pdf`
3. `hotstorage20_paper_yoo.pdf`

자료의 우선순위는 다음과 같다.

1. `NVMeVirt과제-SLC_cache 구현.pdf`
   - 공식 과제 요구사항의 최우선 기준
2. 현재 저장소의 skeleton code와 `ssd_config.h`
   - 실제 구현 인터페이스와 설정값의 기준
3. `Note.md`
   - 실습1 구현, 환경, 시행착오와 검증 기록
4. 참고 논문 두 편
   - SLC cache와 heterogeneous SSD의 배경 및 설계 근거

`Note.md`는 시간순 기록이다. 앞부분의 오래된 중간 결론보다 날짜가 늦은 기록과 “최종 결론”으로 표시된 내용을 우선한다.

참고 논문의 강화학습, QLC 전체 구조, hot/cold threshold 알고리즘을 공식 과제 범위로 임의 확장하지 마라.

---

# 4. 실습1에서 수행한 내용

실습1에서는 NVMeVirt Conventional FTL의 GC 구조를 분석하고 다음 정책을 구현·비교했다.

- Greedy GC
- Random GC
- Cost-Benefit GC
- GC victim selection
- erase count와 GC migration count 계측
- fio/Filebench 실험 자동화
- 평균 latency와 p99 latency 수집
- 반복 측정과 결과 집계
- 데이터 정합성 검증
- 그래프와 결과 보고서 작성

다음 흐름은 코드 수준으로 검토한 경험이 있다.

- NVMeVirt 초기화
- dispatcher → I/O worker → FTL → 완료 처리
- Conventional FTL read/write 경로
- write credit
- foreground GC
- victim line 선택
- valid page migration
- block/line 반환
- channel/lun/block/page/line 구조
- victim priority queue callback과 heap 동작

실습1에서 확인한 중요한 교훈은 다음과 같다.

- 시간에 따라 priority가 달라지는 Cost-Benefit 정책은 일반 heap의 root가 현재 최적 victim을 보장하지 못할 수 있다.
- 동적 점수 정책은 현재 후보 전체를 다시 평가해야 할 수 있다.
- 정책 비교 시 `mkfs`만으로 FTL 내부 상태가 초기화되지 않는다.
- 정책마다 module unload/load를 통해 독립된 FTL 상태로 시작해야 한다.
- 측정 코드와 집계 코드도 독립적으로 검증해야 한다.
- fio 성공만으로 데이터 정합성이 증명되지 않으므로 read-back/CRC 검증이 필요하다.

그러나 실습1의 TLC GC victim selection과 실습2의 SLC→TLC migration victim selection은 서로 다른 문제일 수 있다.

함수나 정책 이름이 비슷하다는 이유로 실습1 코드를 그대로 복사하지 말고 다음을 다시 검증해라.

- 대상 line manager
- victim 후보의 life cycle
- mapping 갱신 순서
- migration 목적
- age의 의미
- queue invariant
- locking과 concurrency
- TLC free-space 및 GC와의 상호작용

---

# 5. 실습2 공식 요구사항

실습2의 목표는 Conventional FTL에 SLC cache를 구현하고, SLC cache에서 TLC로 데이터를 migration할 때 victim selection 정책별 성능을 비교하는 것이다.

## 5.1 SLC cache 구현

다음 동작을 구현하고 검증해야 한다.

- 기본 host write를 SLC cache에서 처리
- mapping을 이용해 SLC 또는 TLC에서 read
- SLC cache가 가득 차면 SLC→TLC migration 수행
- victim에 남은 valid data를 TLC로 이동
- migration 후 SLC line을 다시 사용 가능하게 반환
- TLC 영역에서는 기존 TLC→TLC GC 수행
- 기존 NVMeVirt와 SLC cache 버전 성능 비교

정상 동작 여부는 최소한 다음으로 확인한다.

- SLC 크기보다 작은 workload에서 SLC에만 read/write가 수행되는가?
- SLC가 찰 정도의 workload에서 migration이 발생하는가?
- migration 이후 TLC에 존재하는 데이터도 정상적으로 읽히는가?
- overwrite와 migration 이후에도 데이터가 손상되지 않는가?

## 5.2 Migration victim selection

다음 네 정책을 구현하고 비교한다.

- Greedy baseline
- Random
- FIFO
- Cost-Benefit

정책별로 fio 또는 Filebench를 사용하여 최소한 다음을 측정한다.

- throughput
- 평균 latency
- tail latency
- 별도 명세가 없다면 p99를 사용하고 보고서에 정의 명시
- SLC→TLC migration 횟수
- migration으로 옮긴 valid page 수 또는 bytes

가능하면 다음 보조 지표도 수집한다.

- TLC GC 횟수
- TLC GC가 옮긴 valid page 수
- SLC/TLC별 host write 양
- write amplification을 설명할 수 있는 값

## 5.3 제출물

마감은 2026년 8월 28일이다.

제출물은 다음과 같다.

- 새롭게 구현한 코드 파일
- 측정 결과 그래프
- 결과에 대한 간단한 분석이 포함된 보고서

---

# 6. 반드시 만족해야 하는 구조 조건

과제 PDF의 “전체 System 구현 유의사항”을 최우선 구현 조건으로 적용한다.

1. config를 통해 SLC 비율을 동적으로 설정할 수 있어야 한다.
2. SLC line manager와 TLC line manager를 별도로 관리해야 한다.
3. mapping table은 하나만 사용해야 한다.
4. SLC와 TLC의 oneshot page size 차이를 반영해야 한다.
5. skeleton code에서 제공되는 `ssd_config.h` 설정을 사용해야 한다.

“동적으로 설정”의 의미가 다음 중 무엇인지는 코드와 자료를 확인해 판단한다.

- build-time configuration
- module load 시 configuration
- 초기화 시 configuration
- 실행 중 SLC 비율 변경

실행 중 변경까지 요구된다고 임의로 확대 해석하지 마라. 코드에서 확정할 수 없다면 구현 전에 질문해라.

---

# 7. 첫 번째 단계: 현재 저장소가 실습2 출발점으로 적합한지 조사

이 단계에서는 코드를 수정하지 마라.

다음 작업도 수행하지 마라.

- 파일 수정, 이동 또는 삭제
- 자동 formatting
- branch 생성 또는 전환
- commit, merge, rebase, cherry-pick
- 새 clone 또는 새 폴더 생성
- module load/unload
- benchmark 실행
- mount, unmount 또는 `mkfs`
- build artifact 정리

먼저 읽기 전용으로 다음을 조사한다.

## 7.1 Git 상태와 계보

- repository root
- remote URL
- 현재 branch
- 현재 HEAD commit
- `git status`
- commit되지 않은 변경
- 추적되지 않는 파일
- 최근 commit history
- upstream과의 공통 조상
- 실습1 시작 전 skeleton 기준 commit
- skeleton 이후 실습1에서 생성한 commit 목록

실습1 시작 전 기준 commit은 추측하지 마라. 다음을 종합해 판단한다.

- Git history
- upstream과의 공통 조상
- commit message
- `Note.md`의 작업 날짜
- 각 변경이 처음 나타난 commit

정확히 확정할 수 없다면 후보와 근거를 제시하고 질문한다.

## 7.2 파일과 기능별 변경 분석

skeleton 기준 commit과 현재 코드의 차이를 조사한다.

특히 다음을 확인한다.

- `conv_ftl.c`
- `conv_ftl.h`
- `main.c`
- `ssd_config.h`
- `Kbuild`
- `pqueue/pqueue.c`
- `pqueue/pqueue.h`
- SLC/TLC 관련 파일
- `scripts/`
- `report/`
- debug/diagnostic 관련 코드
- benchmark 결과 및 임시 파일

다음 표를 작성한다.

| 실습1 변경 | 관련 파일·함수 | 변경 목적 | 실습2와의 관계 | 유지/수정/제외 판단 |
|---|---|---|---|---|

다음 네 종류로 분류한다.

### 그대로 유지할 가능성이 높은 변경

예:

- 데이터 정합성 검증
- module reload 안전 절차
- fio JSON 보존
- 실험 metadata 수집
- 범용 read-only 계측

실제 코드를 확인한 뒤 판단해야 하며 예시를 자동으로 유지 대상으로 확정하지 마라.

### 실습2에 맞게 수정하여 재사용할 변경

예:

- migration counter
- policy module parameter
- 결과 수집 스크립트
- `/proc/nvmev/debug`

TLC GC와 SLC migration의 이름과 통계를 분리해야 한다.

### 제외하거나 비활성화할 변경

예:

- 일회성 진단 코드
- 실습1 결과 검증에만 사용한 counter
- hot path를 과도하게 왜곡하는 debug code
- 실험 부산물

### 그대로 사용하면 위험한 변경

특히 다음을 확인한다.

- 실습1의 `gc_policy`와 실습2의 migration policy 충돌
- TLC GC victim queue와 SLC migration queue 혼용
- 실습1 Cost-Benefit age 정의의 의미 불일치
- 동적 priority와 heap staleness
- 기존 line metadata와 SLC/TLC manager 분리 충돌
- 단일 mapping table의 type 구분 문제
- 실습1 계측이 SLC/TLC를 구분하지 못하는 문제
- `pqueue` 변경이 현재 코드에서 여전히 필요한지

## 7.3 코드와 Note.md 교차검증

`Note.md`의 설명을 그대로 사실로 받아들이지 말고 현재 코드 및 Git history와 대조한다.

다음을 확인한다.

- 기록된 기능이 실제 코드에 존재하는가?
- 최종 수정 사항이 commit되어 있는가?
- Note.md에 기록되지 않은 변경이 있는가?
- 임시 코드가 남아 있는가?
- 실습1 최종 보고서에 사용한 코드와 현재 HEAD가 같은가?
- push하지 않은 commit이나 uncommitted change가 있는가?

---

# 8. 출발점 결정

조사 후 다음 중 하나를 추천한다.

## 선택지 A: 현재 branch에서 계속 구현

다음 조건을 만족할 때만 추천한다.

- 실습1 변경이 모두 정리되어 있다.
- 현재 worktree가 안전하다.
- 실습2 변경을 Git history에서 명확히 구분할 수 있다.
- 현재 branch에서 계속 작업해도 실습1 완료 상태를 잃지 않는다.

## 선택지 B: 현재 실습1 완료 commit에서 실습2 branch 생성

기본적으로 가장 먼저 검토할 선택지다.

예시 branch:

```text
practice2-slc-cache
```

이 방식은 새 폴더나 새 clone을 만들지 않고, 현재 저장소 안에서 실습1 완료 상태를 보존하면서 실습2 변경을 분리한다.

조사 단계에서는 실제 branch를 만들지 말고 다음을 제안한다.

- 기준 commit
- branch 이름
- 현재 변경을 먼저 commit해야 하는지
- untracked 파일 처리 방법
- 장단점

## 선택지 C: skeleton commit 기준으로 실습2 branch 생성

다음 경우에만 추천한다.

- 실습1 변경이 실습2 구조와 크게 충돌한다.
- 현재 코드에서 시작하면 회귀 원인 추적이 어렵다.
- 필요한 실습1 기능만 선별적으로 다시 적용하는 편이 안전하다.

이 경우에도 새 폴더나 새 clone이 필수인 것은 아니다. 같은 저장소의 skeleton commit을 기준으로 branch를 만들 수 있다.

다음을 구체적으로 설명해야 한다.

- 기준 skeleton commit
- 다시 가져올 실습1 변경
- 가져오지 않을 변경
- 예상되는 작업량
- 실습1 branch 보존 방법

---

# 9. 구현 전에 확인할 설계 질문

다음 질문의 답을 먼저 코드에서 찾아라. 찾지 못하면 추측하지 말고 나에게 질문해라.

1. SLC 비율 config의 단위와 범위는 무엇인가?
2. 0%와 100%도 지원해야 하는가?
3. SLC와 TLC의 page, oneshot page, block, line 크기는 각각 얼마인가?
4. line은 초기화 시 SLC/TLC로 고정 분할되는가?
5. 물리 block의 SLC/TLC mode를 실행 중 변경하는가?
6. 과제에서 말하는 dynamic SLC 비율의 정확한 의미는 무엇인가?
7. SLC가 찼다고 판단하는 정확한 조건은 무엇인가?
8. SLC migration은 foreground 동기식인가, background 방식인가?
9. migration의 victim 및 복사 단위는 무엇인가?
10. SLC victim의 valid page만 TLC로 옮기는가?
11. SLC→SLC GC가 필요한가?
12. migration 중 mapping 갱신 순서는 무엇인가?
13. stale mapping이나 동시 overwrite를 어떻게 방지하는가?
14. TLC GC와 SLC migration이 동시에 TLC free line을 요구하면 어떻게 처리하는가?
15. Greedy, FIFO, Cost-Benefit의 공식 정의가 skeleton에 있는가?
16. Cost-Benefit의 age는 무엇을 기준으로 하는가?
17. policy 선택은 config, module parameter 또는 다른 인터페이스 중 무엇인가?
18. SLC/TLC latency 값이 timing model에 이미 정의되어 있는가?

---

# 10. 첫 응답에서 해야 할 일

첫 응답에서는 코드를 수정하거나 build하지 마라.

먼저 다음 내용을 보고해라.

1. `Note.md`와 PDF 3개에 접근했는지
2. 현재 repository root, remote, branch, HEAD, worktree 상태
3. 실습1 시작 전 skeleton 기준 commit 후보
4. skeleton 대비 실습1의 주요 변경 사항
5. Note.md와 현재 코드가 일치하는지
6. 실습2 PDF에서 확인한 공식 요구사항
7. `ssd_config.h`의 SLC/TLC 관련 설정
8. 현재 Conventional FTL의 초기화/read/write/GC call graph
9. 실습1 변경 중 유지 가능한 부분
10. 수정해서 재사용할 부분
11. 제외하거나 비활성화할 부분
12. 그대로 재사용하면 위험한 부분
13. 현재 코드를 실습2 출발점으로 사용할 수 있는지
14. 권장 branch 전략
15. build 및 baseline 검증 계획
16. 사용자 또는 조교 확인이 필요한 질문
17. 실습2의 단계별 구현 계획
18. 첫 번째로 수행할 가장 작은 안전한 변경

최종 판단은 다음 형식으로 작성한다.

```text
권장 시작점:
권장 기준 commit:
권장 branch:
현재 실습1 코드 사용 가능 여부:

판단 근거:
- ...

유지할 실습1 변경:
- ...

수정할 실습1 변경:
- ...

제외할 실습1 변경:
- ...

구현 전 필요한 검증:
- ...

남은 질문:
- ...
```

확정된 사실, 합리적인 추정, 사용자/조교 확인 필요 사항을 구분해라.

내가 이 판단을 확인하기 전까지 실습2 구현을 시작하지 마라.

---

# 11. 출발점 승인 후 권장 구현 단계

내가 시작점을 승인한 뒤에만 다음 단계로 진행한다.

## 단계 A: 기준 동작 보존과 baseline 검증

- 현재 코드를 build한다.
- module load 전에 실제 환경값을 확인한다.
- 작은 read/write smoke test를 수행한다.
- fio verify 또는 CRC로 데이터 정합성을 검사한다.
- 기존 throughput과 latency 기준값을 저장한다.
- `dmesg`에서 warning, BUG, oops를 확인한다.

## 단계 B: SLC/TLC 영역과 metadata 설계

- `ssd_config.h`에서 SLC 비율을 읽는다.
- 총 line 수를 SLC/TLC로 안전하게 나눈다.
- 반올림, 정렬, 최소 line 수와 경계값을 처리한다.
- SLC line manager와 TLC line manager를 분리한다.
- 동일 line을 두 manager가 동시에 소유하지 못하도록 invariant를 정의한다.
- mapping table은 하나만 유지한다.
- physical address가 SLC인지 TLC인지 안전하게 판별할 방법을 정의한다.

이 단계에서는 migration 정책을 구현하지 말고 초기화와 ownership만 검증한다.

## 단계 C: 서로 다른 oneshot page size

- SLC/TLC 설정값을 skeleton에서 확인한다.
- 논리 page와 NAND program unit을 혼동하지 않는다.
- SLC/TLC write pointer의 전진 규칙을 분리한다.
- channel/lun parallelism과 PPA 계산을 검증한다.
- 단위 변환으로 mapping index가 어긋나지 않는지 검사한다.

## 단계 D: SLC write와 통합 read

- 공식 과제 구조에 따라 host write를 SLC로 보낸다.
- overwrite 시 기존 위치가 SLC인지 TLC인지와 관계없이 올바르게 invalid 처리한다.
- 단일 mapping table이 최신 physical page만 가리키게 한다.
- read는 mapping 결과에 따라 SLC 또는 TLC에서 처리한다.
- SLC 크기 미만 workload로 SLC-only 동작을 검증한다.

## 단계 E: Greedy 기반 SLC→TLC migration

- SLC free line 부족 조건을 정의한다.
- 우선 Greedy baseline 하나만 구현한다.
- victim의 valid data만 TLC로 옮긴다.
- TLC write 성공 후 mapping을 갱신한다.
- mapping이 여전히 해당 SLC page를 가리키는지 확인해 stale copy를 방지한다.
- victim을 erase하고 SLC free list로 반환한다.
- error path에서 mapping과 line count가 깨지지 않게 한다.
- TLC GC와 migration 사이의 재귀, deadlock, 무한 루프 가능성을 확인한다.

## 단계 F: 정책 4종

공통 migration 코드는 하나로 유지하고 victim selection만 분리한다.

- Greedy:
  - 옮겨야 할 valid page가 가장 적은 SLC line
- Random:
  - 유효한 후보 중 균등 선택
  - heap priority를 무작위 값으로 만들지 않음
- FIFO:
  - 가장 먼저 닫힌 SLC line
  - 결정론적 close sequence 우선 검토
- Cost-Benefit:
  - 과제 또는 skeleton 정의가 있으면 그대로 사용
  - 정의가 없으면 식과 age 의미를 설명한 뒤 확인
  - 점수가 시간에 따라 변하면 전체 후보를 현재 시점에 재평가

정책은 enum과 하나의 설정 경로로 관리한다.

TLC GC policy와 SLC migration policy는 별도 이름과 상태로 관리한다.

## 단계 G: 계측

최소한 다음 값을 확인할 수 있게 한다.

- host read/write count와 bytes
- SLC host read/write count와 bytes
- TLC host read/write count와 bytes
- SLC→TLC migration 횟수
- migrated valid page count와 bytes
- SLC reclaimed line 수
- TLC GC 횟수
- TLC GC migrated page 수
- 현재/최대 SLC 사용량
- 정책별 victim selection 횟수

계측은 read-only이고 hot path를 과도하게 왜곡하지 않아야 한다.

## 단계 H: 정확성 검증

작은 규모부터 다음 테스트를 수행한다.

1. SLC 비율 경계값
2. SLC보다 작은 write
3. SLC를 정확히 채우는 write
4. SLC를 초과하는 write
5. 동일 LBA 반복 overwrite
6. migration 후 전체 read-back/CRC
7. SLC migration과 TLC GC가 모두 발생하는 장시간 write
8. module unload/reload 반복
9. 네 정책의 데이터 정합성
10. `dmesg` 오류 검사

---

# 12. 실험 설계

처음부터 장시간 benchmark를 실행하지 않는다.

순서는 다음과 같다.

1. build
2. 기능 smoke test
3. 짧은 migration test
4. 데이터 정합성 test
5. 실험 스크립트 검증
6. 본 반복 실험

비교 대상은 최소한 다음과 같다.

- 기존 Conventional FTL
- SLC cache + Greedy
- SLC cache + Random
- SLC cache + FIFO
- SLC cache + Cost-Benefit

workload는 최소 다음 두 종류를 포함한다.

- SLC보다 작은 burst workload
- SLC를 여러 번 채우는 지속 write workload

가능하면 다음도 비교한다.

- 균등 random write
- update locality가 높은 skewed write

각 정책은 완전히 독립된 초기 상태에서 최소 3회 반복한다.

각 run에 다음 metadata를 기록한다.

- commit hash
- kernel version
- module parameter
- SLC 비율
- migration policy
- 장치명
- workload 설정
- fio/Filebench 버전
- 시작/종료 시간
- raw 결과 파일 위치

원본 fio JSON과 raw counter를 보존한다. 평균과 표준편차를 함께 계산한다. latency의 원 단위와 변환식을 명시한다.

---

# 13. 안전 규칙

NVMeVirt는 커널 모듈이므로 잘못된 코드는 kernel panic이나 VM hang을 일으킬 수 있다.

- 큰 변경 전 snapshot 또는 복구 가능한 Git 상태를 권고한다.
- module load 실패 시 `dmesg`를 확인한다.
- compile 성공을 정상 동작 증거로 간주하지 않는다.
- 실제 NVMe 장치와 NVMeVirt 장치를 구분한다.

서버에서 과거 검증된 module parameter는 다음과 같다.

```text
memmap_start=16G
memmap_size=48G
cpus=7,8
```

그러나 현재 환경에서도 같다고 단정하지 말고 `/proc/cmdline`을 다시 확인한다.

과거 서버에서 NVMeVirt 장치는 `/dev/nvme1n1`이었지만 장치명은 바뀔 수 있다.

`mkfs` 전에 반드시 다음을 확인하고 나에게 명시적으로 승인을 요청한다.

- `lsblk`
- 장치 크기
- mount 상태
- module load 전후 장치 변화
- `dmesg`의 NVMeVirt 생성 메시지

`git reset --hard`, 사용자 파일 삭제, 실제 저장장치 포맷 등 파괴적인 동작을 임의로 수행하지 마라.

---

# 14. 보고서 방향

보고서는 다음 구조를 권장한다.

1. 실습 목표
2. 기존 Conventional FTL 구조
3. SLC cache 설계
4. SLC/TLC line manager
5. 단일 mapping table
6. 서로 다른 oneshot page size
7. SLC→TLC migration
8. victim 정책 4종
9. 정확성 검증
10. 실험 환경과 workload
11. throughput/latency 결과
12. migration 비용 분석
13. 한계와 결론

가능하면 다음 그래프를 포함한다.

- throughput
- 평균 latency
- p99 latency
- migration 횟수
- migrated valid pages 또는 bytes
- TLC GC 비용

결과가 예상과 다르더라도 이론에 억지로 맞추지 않는다.

다음 가능성을 구분해 분석한다.

- migration이 충분히 발생하지 않음
- 정책들이 비슷한 victim을 선택함
- TLC GC 비용이 정책 차이를 가림
- SLC 비율이 부적절함
- 반복 수가 부족함
- 계측 또는 집계 오류
- 실제 정책 차이가 작음

모든 결론은 이 실험의 device configuration과 workload 범위 안에서만 표현한다.

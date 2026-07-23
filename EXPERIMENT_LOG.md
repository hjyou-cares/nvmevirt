# 실습 1: Cost-Benefit GC — 실험 로그

작업 단계와 벤치마크 실행 기록을 누적하는 파일. 최신 항목이 위로 오게 작성.
(배경/목표/코드 구조는 `CLAUDE.md` 참고)

---

## 진행 로그 (개발 단계)

날짜별로 "무엇을 왜 바꿨는지"를 짧게 기록. git 커밋 해시를 같이 남기면 나중에 `git show <hash>`로 바로 확인 가능.

<!--
### YYYY-MM-DD
- 무엇을: (예: victim_line_get_pri()에 cost-benefit 계산식 추가)
- 왜: (예: age 정보를 반영해 오래된 데이터가 많은 라인을 우선 회수하기 위해)
- 커밋: <git hash>
-->

### 2026-07-23
- 무엇을: `Kbuild`에서 `CONFIG_NVMEVIRT_SSD := y`로 변경 (기존엔 `CONFIG_NVMEVIRT_ZNS`가 켜져있었음)
- 왜: ZNS 설정에서는 `conv_ftl.o`가 빌드 대상에서 빠져있어서, 이 실습에서 수정할 Conventional FTL 코드가 아예 컴파일이 안 되고 있었음. fork를 다른 환경(서버)에서도 건드리면서 설정이 ZNS로 바뀌었던 것으로 추정.
- 커밋: (미커밋, Kbuild는 사용자가 직접 수정)

- 무엇을: `conv_ftl.c`에 Random GC victim 정책 구현
  - 상단에 `gc_policy` module_param 추가 (0=Greedy/1=Random/2=Cost-Benefit, `/sys/module/nvmev/parameters/gc_policy`로 실행 중 전환 가능)
  - `select_victim_line()`에서 기존 vpc 임계치 게이트 체크는 그대로 두고, `gc_policy == GC_POLICY_RANDOM`일 때만 `pqueue`의 힙 배열(`pq->d[1..size-1]`)에서 `get_random_u32()`로 무작위 인덱스를 뽑아 `pqueue_remove()`로 꺼내도록 분기 추가
- 왜: `victim_line_get_pri()`를 무작위화하면 pqueue의 힙 불변식이 깨져서 위험함 (자세한 이유는 대화 기록 참고). 대신 힙 구조는 그대로 두고 "어떤 원소를 꺼낼지"만 무작위로 고르는 방식이 안전함.
- 검증: 로컬 VM에서 `make` → `insmod` 정상 (dmesg 에러 없음, `/dev/nvme0n1` 생성됨), `gc_policy` 기본값 0 확인, greedy(0) 상태로 fio 20M 순차 쓰기 스모크 테스트 정상 동작, `gc_policy=1`로 전환 확인 완료. `gc_policy=1` 상태에서 200MB 파일에 randwrite로 600MB(3바퀴) 부하를 줘서 GC를 다수 유발 → 크래시 없이 모듈/마운트 정상 유지 확인.
- **한계**: `erase_cnt`를 밖으로 볼 방법이 아직 없어서 (`/proc/nvmev/debug` 미구현), Random 분기가 실제로 골고루 line을 골랐는지는 아직 증명 못 함. 지금까지 확인된 건 "크래시 안 남" 정도. → `/proc/nvmev/debug`에 erase_cnt 덤프 구현이 다음 우선순위.
- 커밋: (미커밋)

---

## 벤치마크 실행 로그

정책별 측정 결과를 실행할 때마다 추가. raw 로그/결과 파일은 `results/` 디렉토리에 저장하고 여기서는 요약 + 경로만 남기는 걸 권장.

<!--
### YYYY-MM-DD HH:MM — 정책: Greedy / Random / Cost-Benefit
- 커맨드: `fio --name=... --rw=randwrite ...`
- 대상: 로컬 VM / 서버(147.46.241.107)
- 결과 요약:
  - Erase count 총합/블록별 분포:
  - IO AVG latency:
  - Tail latency (p99 등):
- raw 로그 경로: `results/...`
- 비고: (이상 현상, 재실행 필요 여부 등)
-->

---

## 이슈 / 막힌 점

해결에 시간이 걸렸거나 나중에 다시 볼 필요가 있는 문제 기록.

<!--
### YYYY-MM-DD
- 증상:
- 원인:
- 해결:
-->

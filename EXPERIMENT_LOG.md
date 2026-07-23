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
- **한계 (해결됨, 아래 항목 참고)**: 이 시점엔 `erase_cnt`를 밖으로 볼 방법이 없어서 Random 분기가 실제로 골고루 line을 골랐는지 증명 못 하는 상태였음.
- 커밋: `16cd49a`

- 무엇을: `main.c`의 `/proc/nvmev/debug` 프록 파일 구현 (read: 전체 block의 erase_cnt 덤프, write "reset": 전체 0으로 초기화). `__walk_conv_blocks()` 헬퍼 하나로 channel→lun→plane→block 4중 순회를 dump/reset 공용으로 사용.
- 왜: `erase_cnt`(`ssd.h`의 `struct nand_block`)가 커널 모듈 밖으로 노출되는 통로가 전혀 없어서, 정책 간 GC 동작을 실측 비교할 방법이 없었음.
- 검증 (로컬 VM, memmap_size=1G):
  - `cat /proc/nvmev/debug` 라인 수 131072 = 8192 blks/pl × 2 luns × 2 ch × 4 partitions, SSD 지오메트리 계산과 정확히 일치. 새로 로드한 직후엔 전부 0 확인.
  - **중요 발견**: 600MB 랜덤쓰기(누적 2.4GB)까지는 GC가 0회 트리거됨. 원인 조사 결과, `memmap_size=1G`처럼 작을 때 `ssd_init_params()`의 block 크기 계산이 `ONESHOT_PAGE_SIZE`(32KB) 밑으로 못 내려가고 올림되면서, FTL이 내부적으로 인식하는 파티션당 명목 용량이 실제 물리 용량의 **약 4배(파티션당 1GB, 총 4GB)** 로 부풀려짐. 그래서 누적 6GB 랜덤쓰기(600MB 파일 × 10바퀴)로 올리니 그제서야 GC가 확실히 발생. CLAUDE.md의 "GC 정책 실험용 커맨드 레퍼런스"에 이 내용과 정정된 커맨드 반영함.
  - Greedy(gc_policy=0) vs Random(gc_policy=1) 동일 6GB 부하 비교:
    - Greedy: erase 발생 block 19,424개, 총 erase 157,136회, block당 최대 9회, 평균(0아닌것만) 8.09
    - Random: erase 발생 block 103,988개, 총 erase 192,060회, block당 최대 6회, 평균(0아닌것만) 1.85
    - Random이 Greedy 대비 약 5.4배 많은 block에 걸쳐 훨씬 고르게 분산 — 이론적으로 기대한 방향과 일치. Random 정책이 실제로 의도대로 동작한다는 첫 실측 증거.
- 커밋: `c2c200e`

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

### 2026-07-23
- 증상: Claude(에이전트)가 셸에서 `sudo` 필요한 명령(`mount`, `insmod`, sysfs 파일 쓰기 등)을 실행하면 "a password is required"로 실패함.
- 원인: 에이전트가 쓰는 셸에는 sudo 비밀번호를 입력할 인터랙티브 터미널이 없음.
- 해결: sudo가 필요한 명령은 Claude가 안내만 하고, 사용자가 직접 자기 터미널에서 실행 → 결과를 다시 Claude에게 알려주는 식으로 진행. (읽기 전용 확인 명령들은 Claude가 직접 실행 가능)

### 2026-07-23
- 증상: 로컬 VM(`memmap_size=1G`)에서 2.4GB 랜덤쓰기를 줘도 GC가 한 번도 안 돌고 `erase_cnt`가 전부 0이었음.
- 원인: `ssd_init_params()`의 block 크기 계산이 반올림되면서 FTL이 인식하는 명목 용량이 실제 물리 용량의 약 4배로 부풀려짐 (자세한 내용은 "진행 로그" 2026-07-23 erase_cnt 항목, CLAUDE.md "GC 정책 실험용 커맨드 레퍼런스 § 3" 참고).
- 해결: 로컬에서 GC를 유발하려면 최소 6GB 이상 누적 랜덤쓰기 필요. 서버(36G memmap)에서는 이 현상이 없을 것으로 추정되지만 미검증 — 서버에서 첫 벤치마크 돌릴 때 `erase_cnt`가 0이 아닌지부터 확인할 것.

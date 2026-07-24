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

### 2026-07-24
- 무엇을: fio 예제 커맨드의 `--filename=~/nvme_mount/...`를 `--filename=$HOME/nvme_mount/...`로 수정 (CLAUDE.md 2곳)
- 왜: `--filename=` 처럼 `=` 뒤에 오는 `~`는 bash가 확장 안 해줌 (단어 맨 앞이나 순수 대입문에서만 적용되는 규칙). 이 상태로 실행하면 가상 SSD가 아니라 명령을 실행한 위치 밑에 `~`라는 이름의 실제 폴더가 생기고 그 안에 씀 — fio는 "성공"으로 보고해서 한동안 못 알아챔 (`Disk stats`에 `nvme0n1` 대신 `sda`가 찍히는 게 단서였음).
- 검증: 수정된 명령으로 재실행 → `Disk stats`에 `nvme0n1` 정상 표시, `df -h ~/nvme_mount` 반영 확인.
- 커밋: (미커밋, CLAUDE.md 문서만 수정)

- 무엇을: `conv_ftl.c`/`conv_ftl.h`에 Cost-Benefit GC victim 정책 구현
  - `conv_ftl.h`: `struct line`에 `mtime`(line이 닫힌 시점의 논리 타임스탬프) 필드 추가
  - `conv_ftl.c`: 전역 논리 시계 `cb_clock` 추가 (페이지 쓸 때마다 +1, `advance_write_pointer()`에서 증가), line이 full_line_list/victim pqueue로 전환되는 "닫힘" 시점에 `mtime` 스탬프, `victim_line_get_pri()`에 `gc_policy==COST_BENEFIT` 분기 추가해서 `(ipc*age)/(2*vpc)` 계산 후 `CB_PRI_MAX - bc`로 뒤집어 리턴, `mark_page_invalid()`의 `pqueue_change_priority()` 호출을 `pqueue_remove()+line->vpc--+pqueue_insert()`로 교체
- 왜: age(마지막으로 쓰인 뒤 얼마나 지났는지) 정보를 반영해서, valid page 수는 같아도 더 오래 방치된(콜드) line을 우선 회수하기 위해. `victim_line_get_pri()`만 바꾸면 될 거라고 예상했지만, 설계 검증 중 `mark_page_invalid()`의 `pqueue_change_priority()` 호출이 "old_pri/new_pri가 같은 단위(raw vpc)"라는 전제에 의존하고 있다는 걸 발견 — get_pri가 파생 점수를 계산하도록 바꾸면 이 전제가 깨져서 힙이 스스로 복구 안 되는 상태로 틀어질 수 있었음. Plan 서브에이전트로 pqueue 상호작용을 교차검증해서 이 문제와 vpc==0 나눗셈(커널 패닉 위험), min-heap 방향 문제까지 총 3개를 구현 전에 찾아 해결함. 설계 문서: `~/.claude/plans/abstract-greeting-reddy.md`.
- 검증: 로컬 VM `make`/`insmod` 정상 (dmesg 에러 없음). Greedy(0) 회귀 테스트로 기존 동작 유지 확인. `gc_policy=2`로 전환 후 6GB 랜덤쓰기 스트레스 테스트 크래시 없이 통과. 자세한 수치는 아래 "벤치마크 실행 로그" 참고.
- 커밋: `4350133`

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

**아래는 정식 벤치마크가 아니라 기능 검증용 측정임 (`results/` 파이프라인 아직 없어서 raw 로그 저장 안 됨, awk 즉석 확인만). 서버에서 정식으로 다시 재야 함.**

### 2026-07-24 — 정책: Cost-Benefit 최초 동작 확인 + Greedy 재현성 검증
- 커맨드: `fio --name=gc_stress --filename=$HOME/nvme_mount/testfile2 --size=600M --rw=randwrite --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 --group_reporting` (6GB 랜덤쓰기), 매 실행 전 `echo reset`
- 대상: 로컬 VM (memmap_start=2G memmap_size=1G cpus=2,3)
- 결과 요약 (erase_cnt만, latency는 아직 미측정):
  - Greedy (오늘 새로 측정): `nonzero_blocks=19280, sum=61008, max=4`
  - Random (재검증): `nonzero_blocks≈106592, sum≈192112, max=6`
  - Cost-Benefit (최초): `nonzero_blocks=19428, sum=192000, max=10`
  - Greedy 재현성 테스트: 모듈을 완전히 리로드해서 같은 조건(Greedy, reset 직후, 동일 fio 커맨드)으로 2회 연속 실행 → **두 번 다 `19280/61008/4`로 완전히 일치** (최초 측정까지 합치면 3회 연속 동일). Greedy는 victim 선택에 난수가 없고 fio도 기본 `randrepeat=1`이라 이론상 결정론적이어야 하는데, 실측으로 확인됨.
- raw 로그 경로: 없음 (터미널 출력만, `results/` 파이프라인 미구현)
- 비고: 균등 랜덤쓰기라 콜드 데이터 개념이 없어서 Cost-Benefit이 Greedy와 비슷하게 좁은 블록 범위에 몰림 (다만 마모는 더 큼) — Cost-Benefit의 장점을 보려면 핫/콜드 섞인 워크로드 필요. 7/23에 기록된 Greedy 수치(`157136/9`)는 오늘 재현 안 돼서 신뢰도 낮음, 폐기하고 오늘 값을 기준선으로 채택.

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

### 2026-07-24
- 증상: `fio --filename=~/nvme_mount/testfile2 ...`를 실행했는데 VM GUI로 마운트 폴더를 봐도 파일이 하나도 없었음. fio 자체는 정상 종료 로그를 냄.
- 원인: `--filename=` 처럼 `=` 뒤에 오는 `~`는 bash가 홈 디렉토리로 확장 안 해줌 (단어 맨 앞이나 순수 대입문에서만 적용되는 규칙). `~`가 문자 그대로 취급돼서 명령을 실행한 위치(`~/nvmevirt`) 밑에 `~`라는 이름의 폴더가 생기고 그 안에 600MB가 쓰였음 — 가상 SSD가 아니라 호스트의 진짜 디스크 공간을 소모함. `Disk stats`에 `nvme0n1` 대신 `sda`로 찍히는 게 단서였음.
- 해결: `~` 대신 `$HOME` 또는 절대경로 사용. CLAUDE.md의 fio 예제 2곳 수정, 잘못 쓰인 파일 삭제.

### 2026-07-24
- 증상: `rmmod`→`insmod`로 모듈을 리로드해도 `~/nvme_mount` 안의 파일이 그대로 남아있음 (`df -h`가 새로 마운트했는데도 이전 실행에서 쓴 600MB를 그대로 반영).
- 원인: `erase_cnt` 같은 FTL 내부 통계(커널 힙에 매번 새로 kmalloc/vmalloc되는 구조체)는 리로드 시 초기화되지만, `memmap=`으로 예약된 물리 메모리 영역(실제 "플래시" 바이트가 저장되는 곳)은 module reload로 지워지지 않는 것으로 보임. ext4 파일시스템 자체도 그 메모리 위에 있어서 같이 남음.
- 해결: 아직 완전히 해결 안 됨 — 정책 간 벤치마크를 완전히 깨끗한 상태에서 비교하려면 `mkfs`를 매번 다시 할지, 아니면 "기존 파일 재사용"으로 통일할지 결정 필요 (CLAUDE.md "서버 벤치마크 전 남은 작업" 5번 항목 참고). 다만 "기존 파일 재사용" 조건을 고정하면 Greedy 결과가 완벽히 재현되는 것까지는 확인함 (아래 항목 참고).

### 2026-07-24
- 증상: 7/23에 기록한 Greedy 기준선(`nonzero_blocks=19424, sum=157136, max=9`)과 7/24에 다시 잰 값(`19280/61008/4`)이 2.5배 넘게 차이남 — "Greedy도 원래 매번 다르게 나오는 거 아니냐"는 의문이 생김.
- 원인: Greedy는 victim 선택에 난수가 전혀 없고(vpc 최솟값을 그냥 고름) fio도 기본 `randrepeat=1`이라 매번 같은 순서로 씀 — 즉 이론적으로 완전히 결정론적이어야 함. 모듈을 리로드해서 동일 조건(Greedy, reset 직후, 동일 fio 커맨드)으로 2회 연속 재현 테스트한 결과 **두 번 다 `19280/61008/4`로 완전히 일치** (최초 측정까지 3회 연속 동일). 즉 오늘 값 쪽이 정확하고, 7/23 값이 이상값이었던 것으로 보임. 7/23 당시 정확히 어떤 조건이 달랐는지는(진짜 reset 직후였는지, 파일이 새로 쓰이는 상태였는지 등) 로그에 안 남아있어서 정확한 원인은 미확정.
- 해결: 7/23 Greedy 수치는 신뢰도 낮음으로 표시하고 폐기, 오늘 재현된 `19280/61008/4`를 새 기준선으로 채택. 앞으로 벤치마크할 때는 "리로드 직후 + reset 직후"라는 조건을 매번 로그에 명시해서 재현성을 추적할 것.

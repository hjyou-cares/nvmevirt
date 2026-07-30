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

### 2026-07-27
- 무엇을: `scripts/run_experiment.sh`에 `workload` 파라미터(uniform/hotcold) 추가, 매 실행마다 `umount→mkfs→mount→chown`으로 완전히 새 파일시스템에서 시작하도록 변경. `scripts/workloads/hotcold.fio` 신설.
- 왜: CLAUDE.md "서버 벤치마크 전 남은 작업" 5번(mkfs 조건 통일)과 6번(워크로드 다양성) 착수.
- 검증: uniform 워크로드는 기존 `pipelinetest`와 동일하게 동작. hotcold 워크로드는 아래 항목대로 3번 재설계하며 검증.
- 커밋: (미커밋)

- 무엇을: `hotcold.fio` 워크로드 3버전(v1→v2→v3) 설계 및 "Cost-Benefit이 Greedy와 erase 통계가 수렴하는" 현상의 근본 원인 규명.
  - v1: coldfile(500M, 1회 순차쓰기) + hotfile(50M, 120루프 랜덤쓰기), `stonewall`로 시간 분리.
  - v2: 단일 파일 + `random_distribution=zoned:80/10:20/90`.
  - v3: 단일 파일 + `random_distribution=zoned:60/20:40/80` (스큐 완화).
- 왜: v1으로 첫 3정책 비교(아래 "벤치마크 실행 로그" 11:26~11:29 항목)를 했을 때 Greedy와 Cost-Benefit의 erase 통계가 사실상 동일하게 나옴 — "콜드 데이터가 있으면 CB가 유리할 것"이라는 기대와 반대. `victim_line_get_pri()`에 임시로 샘플링 printk(500회마다 1번, `vpc/ipc/mtime/cb_clock/age/bc` 출력)를 추가해서 3차례 실측:
  1. **v1 진단**: 캡처된 후보 라인들의 age가 12669~12799로 변동폭 약 1%밖에 안 됨. `advance_write_pointer()`/`mark_page_invalid()` 로직상 `vpc==pgs_per_line`(100% valid)인 라인은 `full_line_list`로 가고 victim pqueue엔 아예 안 들어감 — 콜드파일을 다시 안 건드리니 그 라인들은 영원히 여기 머무름. 결국 GC 후보 풀은 전부 "핫" 라인뿐이라 age 편차가 생길 여지 자체가 없었음.
  2. **v2 진단**: age는 실제로 크게 벌어짐(1,000~153,600, 150배 차이)에도 erase_sum/max는 여전히 Greedy와 동일. vpc 분포를 보니 vpc=1~6인 후보가 전체 샘플(2649개)의 46%(1218개)를 차지 — 핫 영역이 너무 빨리 재기록되면서 "거의 다 무효화된"(vpc가 매우 작은) 후보가 거의 항상 대기 중이었음. `bc=ipc*age/(2*vpc)` 수식상 vpc가 작으면 age가 아무리 벌어져도 못 따라잡을 만큼 bc가 커지므로, 그런 후보가 항상 있으면 CB도 결국 Greedy와 같은 선택을 함.
  3. **v3 진단**: 스큐를 완화하니 vpc 분포가 실제로 넓게 퍼짐(vpc=1 샘플이 194→41개로 감소, vpc=6~9 구간이 최빈값). age도 여전히 넓게 분포(166~1,540,361). 그럼에도 erase_sum/max는 또 동일(`62084/4`로 완전히 같음). 다만 nonzero_blocks는 이번엔 좀 더 벌어짐(Greedy 25260 vs CB 25272) — CB가 실제로 다른 구체적 블록을 고르긴 하되, 총 erase 횟수/최대 마모는 결국 수렴한다는 것을 확인.
- 결론: **erase 통계 수렴은 버그가 아니라 실측으로 확인된 현상**. 이 스케일/워크로드에서는 어떤 정책을 쓰든 "erase당 회수하는 평균 valid page 수"가 비슷해져서 총 write amplification이 수렴하는 것으로 보임. Cost-Benefit의 개별 victim 선택은 실제로 Greedy와 다르지만(vpc/age 샘플 데이터로 확인), 그게 이 워크로드 규모의 총량 지표엔 크게 안 드러남 — 리포트에서 다룰만한 정직한 분석 포인트.
- 검증: 진단용 printk는 최종적으로 제거하고 원본 상태로 재빌드 (`git diff conv_ftl.c` 결과 없음, 원본과 완전히 동일함 확인).
- 커밋: (미커밋)

- 무엇을: 모듈 리로드 없이 `gc_policy`만 sysfs로 전환하며 정책을 이어서 비교하는 방식이 방법론적으로 오염돼 있었다는 것을 발견.
- 왜: `mkfs`는 ext4 파일시스템(메타데이터)만 초기화하고, FTL 내부 상태(`cb_clock`, write pointer, free line list, 각 line의 valid/invalid 상태)는 초기화 안 됨 — 이건 `rmmod`→`insmod`(모듈 완전 리로드)로만 리셋됨. 그래서 Random→Greedy→Cost-Benefit 순으로 모듈 리로드 없이 이어서 돌리면, 뒤에 실행되는 정책이 앞 정책이 남긴 물리 상태(특히 `cb_clock`)를 그대로 물려받음.
- 검증: 완전 리로드 직후 CB만 단독 실행한 결과(`nonzero_blocks=1680 sum=78032 max=47`)가, 모듈 리로드 없이 이어서 실행했던 기존 CB 결과(`18340/208484/105`)와 크게 다름 — 오염 가설의 직접 증거.
- 이후 조치: 정책 비교 시 정책마다 모듈을 완전히 리로드하는 걸로 절차 확정. CLAUDE.md "모듈 리로드 사이클" 절에 경고 추가.
- 커밋: (미커밋, 방법론 발견이라 코드 변경 없음)

### 2026-07-30 (파트 2)
- 무엇을: v6 진단용 printk(`diag_compare_victims`/`diag_gc_total`/`diag_gc_diverge`, 커밋 `865ea61`에 포함됐던 것)를 `conv_ftl.c`에서 완전히 제거.
- 왜: 제출 전 클린 빌드 확인 목적. 진단 결론(v7에서 divergence 93% 유지)은 이미 확보했으므로 코드에서 제거해도 됨.
- 검증: 서버 재빌드 에러 없음, 모듈 리로드 후 dmesg에 진단 메시지 안 뜸.
- 커밋: (미커밋)

- 무엇을: GC migration-cost 카운터(`gc_valid_page_migrate_cnt`) 신설. `do_gc()`에서 victim_line 확정 직후 `gc_valid_page_migrate_cnt += victim_line->vpc` 누적, `/proc/nvmev/debug`에 `GC_VALID_PAGE_MIGRATE_CNT`로 노출, `reset` 시 같이 초기화.
- 왜: 그동안 비교 지표로 쓰던 `erase_cnt` 총합은 "총 쓰기량 ÷ 블록당 용량"에 거의 의존하는 값이라 정책과 무관하게 비슷하게 나올 수 있음. Cost-Benefit이 실제로 줄이려는 건 "GC 한 번당 옮기는 valid page 수(migration cost)"인데 이 수치는 이전까지 측정한 적이 없었음.
- 커밋: (미커밋)

### 2026-07-30 (파트 3, 핵심 — 힙 staleness 버그 발견/수정)
- 무엇을: 사용자가 Codex(다른 LLM)에게 코드를 보여주고 받은 6개 가설을 검증. 상세 경위는 아래 "이슈 / 막힌 점" 2026-07-30 항목 참고. 요지: `victim_line_get_pri()`의 Cost-Benefit score는 `cb_clock`이 계속 흐르면서 매 순간 값이 바뀌는데, `pqueue`의 `bubble_up`/`percolate_down`은 **그 노드가 insert/remove될 때 조상 경로만** 재정렬함 — 힙 전체를 주기적으로 재검증하는 로직이 없어서, 오래 방치된 line들 사이의 상대 순서가 시간이 지나도 재확인되지 않는 채로 남을 수 있음 (`pqueue_is_valid()`로 직접 검증됨).
- 검증 방법:
  1. `pqueue/pqueue.c` 알고리즘을 파이썬으로 그대로 포팅해서 최소 반례(2개 line)로 재현 — 몇 틱만 지나도 `peek()`이 리턴하는 root와 전체 스캔 진짜 최고 bc line이 완전히 달라지고 `pqueue_is_valid()`가 계속 `False`로 나옴, 추가 insert/remove 없이는 영원히 자기 교정 안 됨.
  2. 좀 더 실제와 비슷한 규모(수천 line, 지속적 invalidate+GC pop) 합성 시뮬레이션 — 실제 `pqueue_pop()` 결과가 그 순간 전체 스캔 진짜 최고 line과 87.2% 다름 (임의 확률 파라미터 기반이라 정확한 %는 참고용).
  3. 실제 커널에 임시 카운터(`diag_fix_total`/`diag_fix_changed`)를 추가해 hotcold v7 워크로드로 실측: **`total=99500, changed=5443`(5.47%)** — 버그가 실재하고 실제로 발동함을 확인. 단, 발동 비율이 낮아서 fix 전후 1회 측정만으로는 총량 지표(erase/migrate) 차이가 노이즈 안에 묻혀 안 보였음.
- 수정: `select_victim_line()`에 `GC_POLICY_COST_BENEFIT` 전용 분기 추가. `pqueue_pop()`(stale할 수 있는 heap root) 대신, 매 GC마다 `pq->d[1..size-1]`을 전체 순회해서 `victim_line_get_pri()`가 가장 좋은(작은) line을 찾아 `pqueue_remove()`로 꺼냄. `cb_victim_pri()`로 CB 계산식을 별도 함수로 뽑아서 `victim_line_get_pri()`와 아래 진단 함수가 공유하도록 리팩터링(중복 방지). Greedy/Random 분기는 안 건드림(Greedy는 vpc만 키로 쓰고 매번 정확히 reheapify되므로 애초에 stale해질 수 없음).
- 추가 계측: `diag_fix_total`/`diag_fix_changed`(fix 검증용, 1회성)를 제거하고, 상시 유지할 분석 기능으로 `diag_scan_greedy_vs_cb()`를 신설 — 활성 `gc_policy`와 무관하게 매 GC마다 전체 스캔으로 "Greedy라면 골랐을 line의 vpc"와 "CB라면 골랐을 line의 vpc"를 각각 계산해서 `total_gc`/`greedy_vs_cb_identity_diverge`/`avg_greedy_vpc`/`avg_cb_vpc`/`avg_abs_vpc_diff`/`same_vpc_different_line_ratio`를 누적. `/proc/nvmev/debug`에 노출, `run_experiment.sh`가 `summary.txt`에 자동 집계(`erase_cv`도 이때 같이 추가: nonzero 블록들의 erase_cnt 표준편차/평균).
- 커밋: (미커밋)
- 결과: 아래 "벤치마크 실행 로그"의 `vpcdiag` 항목 참고 — fix 적용 후 재측정한 결과, Greedy와 Cost-Benefit의 migration 효율 차이(13.6%)가 처음으로 노이즈 없이 뚜렷하게 드러남.

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

### 2026-07-26 22:01 — 정책: Greedy (결과 저장 파이프라인 검증용)
- 커맨드: `./scripts/run_experiment.sh 0 pipelinetest` (내부적으로 7/24와 동일한 `gc_stress` fio 커맨드 실행)
- 대상: 집 컴퓨터 (memmap_start=2G memmap_size=1G cpus=2,3), **fresh mkfs 직후 첫 실행** (VM 재부팅으로 ext4가 사라져서 `mkfs`부터 다시 한 상태 — "이슈/막힌 점" 참고)
- 결과 요약:
  - Erase count: `nonzero_blocks=19520, sum=62176, max=4`
  - IO avg latency: 641274.2ns, p99 tail latency: 1056768ns (이번에 처음으로 latency까지 자동 기록됨)
- raw 로그 경로: `results/20260726_220135_policy0_greedy_pipelinetest/`
- 비고: 7/24 "파일 재사용" 조건 기준선(`19280/61008/4`)과 max만 일치하고 나머지는 다름 — 파이프라인 버그가 아니라 "fresh mkfs 직후 첫 쓰기" vs "기존 파일 재사용" 조건 차이로 추정 (CLAUDE.md "서버 벤치마크 전 남은 작업" 5번 참고). 정책 간 정식 비교 실험에서는 이 조건을 반드시 통일해야 함.

### 2026-07-26 22:07~22:12 — 정책: Greedy / Random / Cost-Benefit 3종 첫 동일조건 비교 (파이프라인)
- 커맨드: `./scripts/run_experiment.sh <0|1|2> pipelinetest` (동일 `gc_stress` 6GB 랜덤쓰기, 매 정책 전 sysfs로 `gc_policy` 전환 + `debug reset`)
- 대상: 집 컴퓨터, 같은 세션 내에서 fresh mkfs 이후 연속 실행 (모듈 리로드 없이 `gc_policy` sysfs 전환만으로 정책 교체 — 앞선 Greedy 단독 실행 이후 매핑 테이블 상태가 이어짐, "완전히 독립적인 3회 실험"은 아님에 유의)
- 결과 요약 (`scripts/collect_summary.sh` 집계):

  | 정책 | nonzero_blocks | erase sum | erase max | lat avg (ns) | lat p99 (ns) |
  |---|---|---|---|---|---|
  | Greedy | 19520 | 62176 | 4 | 641274.2 | 1056768 |
  | Random | 106976 | 192084 | 6 | 619501.9 | 937984 |
  | Cost-Benefit | 19596 | 192004 | 10 | 632721.4 | 978944 |

- raw 로그 경로: `results/20260726_220135_policy0_greedy_pipelinetest/`, `results/20260726_220745_policy1_random_pipelinetest/`, `results/20260726_221119_policy2_costbenefit_pipelinetest/`
- 비고:
  - 7/24 관찰(균등 랜덤쓰기에서는 Cost-Benefit이 마모 분산 면에서 Greedy와 비슷하게 좁은 블록에 몰리고 max는 오히려 더 큼)이 이번 재측정에서도 그대로 재현됨 — `erase max`가 Greedy(4) < Random(6) < Cost-Benefit(10) 순으로, 지금 쓰는 콜드 데이터 없는 워크로드에서는 Cost-Benefit이 세 정책 중 가장 마모가 몰리는 걸로 보임. 최종 보고서용 결론을 내리려면 핫/콜드 혼합 워크로드로 재검증 필요 ("서버 벤치마크 전 남은 작업" 6번 참고).
  - Latency는 Random이 가장 낮고(avg/p99 모두) Greedy가 가장 높음 — 다만 이번 실행은 정책마다 매핑 테이블/erase_cnt 누적 상태가 다른 채로(리로드 없이 순서대로 실행) 잰 것이라, 정책 간 latency 우열을 지금 이 수치만으로 단정하기는 이름. 정식 비교에는 매 정책 실행 전 모듈 리로드(또는 최소 mkfs)로 상태를 통일할 것.
  - `results/20260726_215836_policy0_greedy_pipelinetest`(Greedy 첫 파이프라인 시험, 22:01 항목과 별개의 이전 시도)와 `results/20260726_220959_policy1_random_pipelinetest`(summary.txt/meta.txt 없이 fio.json만 존재하는 미완료 실행)는 불완전한 중간 시도라 위 표 집계에서 제외함.

### 2026-07-27 11:26~11:29 — 정책: Greedy / Random / Cost-Benefit 3종 비교 (hotcold v1, ⚠️ 오염된 실행 — 참고용으로만 남김)
- 커맨드: `./scripts/run_experiment.sh <0|1|2> hotcold1 hotcold` (v1 워크로드: coldfile 500M 1회 + hotfile 50M×120루프, stonewall)
- 대상: 로컬 VM, **모듈 리로드 없이** `gc_policy` sysfs 전환만으로 정책 교체 (mkfs는 매번 새로 함)
- 결과 요약:

  | 정책 | nonzero_blocks | erase sum | erase max | lat avg(μs) | lat p99(μs) |
  |---|---|---|---|---|---|
  | Random | 58164 | 79212 | 5 | 135.5 | 257.0 |
  | Greedy | 18332 | 208496 | 105 | 149.8 | 272.4 |
  | Cost-Benefit | 18340 | 208484 | 105 | 158.9 | 297.0 |

- raw 로그 경로: `results/20260727_112639_policy1_random_hotcold1/`, `results/20260727_112902_policy0_greedy_hotcold1/`, `results/20260727_112924_policy2_costbenefit_hotcold1/`
- 비고: **이후 모듈 리로드 없이 정책을 이어서 돌리면 `cb_clock`/write pointer 등 FTL 내부 상태가 오염된다는 게 밝혀져서(위 "진행 로그" 참고), 이 비교는 방법론적으로 무효로 판정함.** Greedy와 CB가 거의 동일하게 나온 원인이 이 오염 때문인지 v1 워크로드의 콜드파일 설계 문제 때문인지 헷갈렸는데, 실제로는 두 문제가 겹쳐 있었던 것으로 결론남 (둘 다 아래에서 별도로 규명/수정됨).

### 2026-07-27 11:50 — 정책: Cost-Benefit 단독 재실행 (완전 리로드, printk 진단용)
- 커맨드: `./scripts/run_experiment.sh 2 hotcold_debug hotcold` (v1 워크로드, `victim_line_get_pri()`에 샘플링 printk를 추가한 빌드)
- 대상: 로컬 VM, `rmmod`→`insmod` 완전 리로드 직후 단독 실행
- 결과 요약: `nonzero_blocks=1680 sum=78032 max=47` — 위 오염된 비교의 CB 결과(`18340/208484/105`)와 크게 다름. 모듈 리로드 오염 가설의 직접 증거.
- raw 로그 경로: `results/20260727_115024_policy2_costbenefit_hotcold_debug/`
- 비고: 이 시점 dmesg의 `cb_sample` printk 출력에서 후보 라인 age가 12669~12799(변동폭 약 1%)로 확인 — v1 워크로드의 콜드파일이 GC 후보 풀에 전혀 안 들어간다는 걸 뒷받침.

### 2026-07-27 12:06~12:07 — 정책: Greedy / Random / Cost-Benefit (hotcold v2, `zoned:80/10:20/90`, 완전 리로드)
- 커맨드: `./scripts/run_experiment.sh <0|1|2> hotcold_v2 hotcold`
- 대상: 로컬 VM, 정책마다 `rmmod`→`insmod` 완전 리로드
- 결과 요약:

  | 정책 | nonzero_blocks | erase sum | erase max |
  |---|---|---|---|
  | Greedy | 25856 | 62064 | 4 |
  | Random | 51180 | 64816 | 5 |
  | Cost-Benefit | 25816 | 62064 | 4 |

- raw 로그 경로: `results/20260727_120656_policy0_greedy_hotcold_v2/`, `results/20260727_120723_policy1_random_hotcold_v2/`, `results/20260727_120747_policy2_costbenefit_hotcold_v2/`
- 비고: 모듈 리로드 오염을 없앴는데도 Greedy와 CB의 erase_sum/max가 완전히 동일 — v1의 콜드파일 문제와는 다른 원인이 있다는 뜻. printk 재측정(아래 항목)으로 "스큐가 너무 강해서 vpc가 극단적으로 작은 후보가 항상 있었기 때문"이라는 원인을 찾음.

### 2026-07-27 12:14 — 정책: Cost-Benefit (hotcold v2, printk 재측정)
- 커맨드: `./scripts/run_experiment.sh 2 hotcold_v2_debug hotcold`
- 결과 요약: `nonzero_blocks=25820 sum=62064 max=4` (위 v2 비교와 일관됨). dmesg `cb_sample` 2649개 샘플 분석: age는 0~1,536,835로 넓게 분포하지만, vpc=1~6 구간에 샘플의 46%(1218/2649)가 몰림.
- raw 로그 경로: `results/20260727_121437_policy2_costbenefit_hotcold_v2_debug/`
- 비고: vpc가 극단적으로 작은(거의 다 무효화된) 후보가 항상 대기 중이면, `bc=ipc*age/(2*vpc)` 수식상 age가 아무리 벌어져도 vpc가 작은 쪽이 이겨서 CB가 Greedy와 같은 선택을 하게 됨 — 스큐 완화(v3)로 이어짐.

### 2026-07-27 12:20~12:27 — 정책: Greedy / Random / Cost-Benefit 최종 비교 (hotcold v3, `zoned:60/20:40/80`, 완전 리로드, printk 제거된 클린 빌드)
- 커맨드: `./scripts/run_experiment.sh <0|1|2> hotcold_v3_final hotcold`
- 대상: 로컬 VM, 정책마다 `rmmod`→`insmod` 완전 리로드, `victim_line_get_pri()` 디버그 printk는 제거하고 재빌드한 상태
- 결과 요약:

  | 정책 | nonzero_blocks | erase sum | erase max | lat avg(μs) | lat p99(μs) |
  |---|---|---|---|---|---|
  | Greedy | 25260 | 62084 | 4 | 92.9 | 197.6 |
  | Random | 52488 | 67208 | 5 | 107.1 | 250.9 |
  | Cost-Benefit | 25272 | 62084 | 4 | 89.0 | 216.1 |

- raw 로그 경로: `results/20260727_122440_policy0_greedy_hotcold_v3_final/`, `results/20260727_122513_policy1_random_hotcold_v3_final/`, `results/20260727_122725_policy2_costbenefit_hotcold_v3_final/`
- 비고: 스큐를 완화(v2의 80/10 → v3의 60/20)해서 vpc 분포는 실제로 넓게 퍼졌지만(printk로 확인, vpc=1 샘플이 194→41개로 감소) erase_sum/max는 여전히 Greedy와 CB가 동일. nonzero_blocks는 이번엔 조금 더 벌어짐(25260 vs 25272) — CB가 실제로 다른 블록을 고르지만 총량 지표엔 수렴한다는 결론. Latency는 이번 실행에서 avg는 CB가 더 낮고(89.0 vs 92.9) p99는 오히려 CB가 더 높음(216.1 vs 197.6) — 직전 v3_debug 실행(printk 오버헤드 있음, avg 89.3/p99 207.9)과 p99 우열이 뒤바뀜. **반복측정 안 한 1회성 값이라 latency 우열은 노이즈일 가능성이 있음. 사용자 판단으로 반복측정은 생략하고 서버 벤치마크로 넘어가기로 함.**

### 2026-07-30 13:11~13:19 — 정책: Greedy / Random / Cost-Benefit × uniform/hotcold(v3) 공식 서버 벤치마크 ("final")
- 커맨드: `NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 ./scripts/run_experiment.sh <0|1|2> final <uniform|hotcold>` (uniform은 `loops=250` 6GB→146GB 랜덤쓰기, hotcold는 이 시점까지의 v3 워크로드: 단일파일+`zoned:60/20:40/80`, size=600M/loops=250 고정값)
- 대상: 서버, 정책마다 완전 모듈 리로드
- 결과 요약 (`results/summary_final.csv`):

  | 정책 | workload | nonzero_blocks | erase sum | erase max | lat avg(ns) | lat p99(ns) |
  |---|---|---|---|---|---|---|
  | Greedy | uniform | 2016 | 271620 | 161 | 34557.3 | 67072 |
  | Cost-Benefit | uniform | 2004 | 271620 | 161 | 34794.1 | 68096 |
  | Random | uniform | 114804 | 273384 | 9 | 34715.7 | 67072 |
  | Greedy | hotcold | 2568 | 271624 | 150 | 37979.8 | 78336 |
  | Cost-Benefit | hotcold | 2568 | 271624 | 153 | 37965.96 | 78336 |
  | Random | hotcold | 115048 | 276120 | 9 | 38321.1 | 78336 |

- raw 로그 경로: `results/20260730_131136_policy0_greedy_final/` 등 (`summary_final.csv` 참고)
- 비고: uniform·hotcold 둘 다 Greedy/Cost-Benefit의 erase 통계가 사실상 완전히 동일 — 이날 오후 내내 이어진 "왜 수렴하는가" 조사(아래 항목들 및 "이슈" 2026-07-30 참고)의 출발점이 된 결과. **이 hotcold latency 수치는 나중에(같은 날) `jobs[0]`이 `cold_fill` 구간을 가리키는 버그가 있었다는 게 밝혀짐 — v3는 job이 하나뿐이라 이 버그의 영향은 없음(uniform도 마찬가지), 영향받는 건 v5 이후 멀티job 워크로드부터.**

### 2026-07-30 14:19~14:24 — 정책: Greedy / Random / Cost-Benefit (hotcold v4, `HOTCOLD_SIZE=24G HOTCOLD_LOOPS=6`, "final2")
- 커맨드: `./scripts/run_experiment.sh <0|1|2> final2 hotcold` (v4: v3와 동일 구조, size/loops만 파라미터화)
- 결과 요약: Greedy `76760/266012/5`, Random `122596/364636/11`, Cost-Benefit `76408/266012/5` — Greedy/CB가 이번에도 완전히 수렴 (sum/max 동일).
- raw 로그 경로: `results/20260730_141921_policy0_greedy_final2/` 등
- 비고: "final"보다 부하를 3.2배(144G)로 강하게 줬는데도 수렴 지속.

### 2026-07-30 15:03~15:09 — 정책: Greedy / Random / Cost-Benefit (hotcold v4, 약한 부하, "weakcalib")
- 커맨드: `./scripts/run_experiment.sh <0|1|2> weakcalib hotcold` (`HOTCOLD_SIZE=24G HOTCOLD_LOOPS=2`, 총 48G ≈ 용량의 1.07배 — 용량을 살짝만 넘기는 수준으로 약화)
- 결과 요약: Greedy `3864/3864/1`, Random `5200/5308/3`, Cost-Benefit `3864/3864/1` — **Greedy/CB가 nonzero_blocks·sum·max 전부 정확히 일치.**
- raw 로그 경로: `results/20260730_145229_policy0_greedy_weakcalib/`(최초 시도, sudo 인증 실패로 빈 폴더만 남음), `results/20260730_150336_policy0_greedy_weakcalib/`, `results/20260730_150833_policy1_random_weakcalib/`, `results/20260730_150934_policy2_costbenefit_weakcalib/`
- 비고: 부하를 강하게(final2, 3.2배)도 약하게(1.07배)도 바꿔봤지만 Greedy/CB 수렴은 그대로 — "부하 강도 조절로 해결된다"는 가설 기각.

### 2026-07-30 15:17~15:29 — 정책: Greedy / Random / Cost-Benefit (hotcold v5, 물리적 시간 분리, "v5calib")
- 커맨드: `./scripts/run_experiment.sh <0|1|2> v5calib hotcold` (`COLD_SIZE=30G COLD_TOUCH_SIZE=3G HOT_SIZE=1G HOT_LOOPS=100`, stonewall 3단계)
- 결과 요약: Greedy `3144/234816/79`, Random `47108/235796/14`, Cost-Benefit `3164/234816/79` — sum/max 완전 일치, nonzero_blocks만 0.6% 차이.
- raw 로그 경로: `results/20260730_151730_policy0_greedy_v5calib/`, `results/20260730_152748_policy1_random_v5calib/`, `results/20260730_152925_policy2_costbenefit_v5calib/`
- 비고: 마모 분포 자체는 v3/v4와 완전히 다르게(작은 핫 영역에 극도로 집중) 나왔지만 Greedy/CB 수렴은 여전.

### 2026-07-30 15:40~15:46 — 정책: Greedy / Random / Cost-Benefit (hotcold v6, 병렬 실행, "v6calib")
- 커맨드: `./scripts/run_experiment.sh <0|1|2> v6calib hotcold` (`COLD_TOUCH_SIZE`를 15G로 키우고 `hot_churn`과 병렬 실행)
- 결과 요약: Greedy `37660/275684/86`, Random `89296/330464/14`, Cost-Benefit `38864/277572/86` — erase max는 여전히 정확히 일치(86/86), nonzero_blocks 차이가 3.2%로 조금 커짐.
- raw 로그 경로: `results/20260730_154032_policy0_greedy_v6calib/`, `results/20260730_154351_policy1_random_v6calib/`, `results/20260730_154556_policy2_costbenefit_v6calib/`
- 비고: 이 결과를 계기로 "정말 항상 같은 선택을 하는가"를 직접 확인하기 위해 `conv_ftl.c`에 진단 printk 추가 결정 (아래 참고).

### 2026-07-30 16:01 — printk 진단 1차 (hotcold v6, "diag")
- 커맨드: `./scripts/run_experiment.sh 0 diag hotcold` (진단 코드 포함 빌드, 정책 번호는 무의미 — 진단은 활성 정책과 무관하게 둘 다 계산)
- 결과 요약: `dmesg`에서 `total=69000, diverge=9995`(14.5%) — 그러나 시간순 추이를 보면 `total=500`에서 `diverge=500`(100%)로 시작해 `total=11500`에서 `diverge=9995`(87%)에 도달한 뒤, 나머지 `total=69000`까지(전체의 83%) **단 한 번도 추가로 갈리지 않음**(`diverge` 값이 그대로 고정).
- raw 로그 경로: `results/20260730_160110_policy0_greedy_diag/` (erase 통계: `40156/276656/86`), 진단 로그: `~/nvmevirt/gc_diag.log`(당시 스냅샷, 이후 v7 결과로 덮어씀)
- 비고: **Cost-Benefit이 실제로 Greedy와 다른 line을 고른다는 걸 최초로 직접 확인.** 다만 divergence가 실행 초반 16.7% 구간에서만 발생 — `cold_touch`(15G)가 `hot_churn`(100G)보다 먼저 끝나서 그 이후로는 콜드 후보 공급이 끊기기 때문으로 추정 (fio.json의 `cold_touch` 그룹 runtime=64643ms 중 divergence는 처음 ~11~16s 구간에 몰림). → v7 재설계로 이어짐.

### 2026-07-30 16:14~16:22 — 정책: Greedy / Random / Cost-Benefit (hotcold v7, time_based 90초, "diag7"/"v7")
- 커맨드: `./scripts/run_experiment.sh <0|1|2> <diag7|v7> hotcold` (`COLD_SIZE=30G COLD_TOUCH_SIZE=15G HOT_SIZE=1G HOTCOLD_RUNTIME=90`, `cold_touch`/`hot_churn`이 90초간 동일하게 계속 실행)
- 진단 재확인: `total=101000, diverge=93915`(93%) — 마지막 측정 시점까지도 계속 증가 중(플래토 없음), divergence가 실행 끝까지 유지됨 확인.
- 결과 요약 (raw):

  | 정책 | nonzero_blocks | erase sum | erase max | 90초간 처리량(cold_touch+hot_churn, GiB) |
  |---|---|---|---|---|
  | Greedy | 85916 | 405864 | 11 | 132.32 |
  | Cost-Benefit | 89436 | 401248 | 8 | 131.16 |
  | Random | 86632 | 294720 | 11 | 72.26 |

  Random의 90초간 처리량이 Greedy/CB의 절반 수준이라(GC 오버헤드로 처리량 저하 추정) sum을 그대로 비교하면 불공정 → **총 쓴 데이터량(cold_fill 30GiB 포함) 대비 GB당 erase 횟수로 정규화**:

  | 정책 | 총 쓴 데이터(GiB) | erases/GiB |
  |---|---|---|
  | Greedy | 162.30 | 2500.6 |
  | Cost-Benefit | 161.14 | **2490.0** |
  | Random | 102.25 | **2882.4** |

- raw 로그 경로: `results/20260730_161454_policy0_greedy_diag7/`, `results/20260730_162007_policy2_costbenefit_v7/`, `results/20260730_162220_policy1_random_v7/`, 진단 로그: `~/nvmevirt/gc_diag.log`
- 비고: **드디어 정책 간 실질적 차이 확인.** Cost-Benefit이 Greedy보다 GB당 erase가 약간 더 적고(0.4%↓), erase max는 뚜렷하게 낮음(8 vs 11)에 nonzero_blocks는 더 많음(89436 vs 85916) — 더 많은 블록에 걸쳐 더 고르게 마모시키면서 전체 효율은 비슷하거나 더 낫다는, Cost-Benefit GC의 이론적 이점과 부합하는 패턴. Random은 정규화하면 확실히 가장 나쁨(2882.4 vs ~2495) — write amplification이 가장 큼. **다음 세션 할 일: 이 결과를 반복측정으로 노이즈 여부 확인, 진단 printk 제거 후 클린 빌드로 최종 재확인, uniform도 동일 방법론(정규화 포함)으로 재점검할지 결정.**

### 2026-07-30 (파트 2) — hotcold v7 3회 반복측정 + uniform 3회 반복측정 (printk 제거된 클린 빌드, fix 이전 코드)
- hotcold v7, GiB당 정규화, 3회 평균±표준편차:

  | 정책 | erases/GiB | erase max (3회) |
  |---|---|---|
  | Greedy | 2466.0 ± 30.1 | 10~11 |
  | Cost-Benefit | 2482.9 ± 13.0 | 8~9 |
  | Random | 2868.1 ± 12.5 | 11~12 |

  Random은 확실히 나쁨(격차가 반복 간 변동폭보다 훨씬 큼). **Greedy vs CB의 총 효율 우열은 이 시점엔 노이즈 수준으로 판정**(Greedy 자체 stdev 30.1이 두 정책 평균 차 ~17보다 큼) — 다만 erase max·nonzero_blocks는 3회 다 일관되게 CB가 낮음/많음(뒤에 나올 힙 staleness 버그 수정 후 재측정에서 이 판정이 뒤집힘, "이슈/막힌 점" 및 아래 `vpcdiag` 항목 참고).
- uniform(`size`+`loops` 고정이라 정책 무관 항상 정확히 같은 바이트를 씀 → 정규화 불필요, raw 그대로 공정 비교):

  | 정책 | erase sum | erase max |
  |---|---|---|
  | Greedy | 271620 (3회 다 소수점까지 동일) | 161 |
  | Cost-Benefit | 271620 (3회 다 소수점까지 동일) | 161 |
  | Random | 273332~273400 | 9~11 |

  Greedy=CB는 완전히 동일한 수치가 3회 다 재현됨 — 노이즈가 아니라 구조적 수렴(hot/cold 스큐가 없는 워크로드에서는 CB 이점이 발현될 구조 자체가 없음, 힙 staleness 버그와 무관하게 성립하는 결과 — uniform은 vpc==0 line이 대부분이라 두 정책이 애초에 같은 후보만 남게 됨).

### 2026-07-30 (파트 2) — Filebench 캘리브레이션 + 3정책 1회 비교 (2GB 파일/120초/4스레드, fix 이전 코드)
- GC 트리거 확인됨(정책마다 87~90GiB 씀), time-based라 GiB로 정규화:

  | 정책 | 쓴 양(GiB) | erase sum | erase max | nonzero_blocks | erases/GiB |
  |---|---|---|---|---|---|
  | Greedy | 87.58 | 119256 | 3 | 56216 | 1361.7 |
  | Cost-Benefit | 90.15 | 126216 | 3 | 56960 | 1400.1 |
  | Random | 87.64 | 127396 | 7 | 81388 | 1453.6 |

  Random이 fio 때와 일관되게 가장 나쁨. Greedy/CB는 스큐 없는 단일 파일 워크로드라 erase max 동일(3), 총량은 Greedy가 근소 우위 — uniform fio 결론과 일관. 1회 측정으로 마무리(반복측정 생략, filebench는 fio 결과를 재확인하는 보조 도구 역할).
- filebench 빌드 이슈 2건(참고용, "이슈/막힌 점"에는 안 옮김): GCC 15부터 `bool`이 예약어라 filebench 소스가 "two or more data types" 에러 → `./configure CFLAGS="-std=gnu17 -g -O2"`로 해결. `fileset.c`의 `malloc(strlen(path)+1)` 뒤에 `fb_strlcpy(s, path, MAXPATHLEN)`으로 잘못된 크기를 넘기는 filebench 자체의 오래된 버그가 glibc 2.38+의 진짜 `strlcpy`+`_FORTIFY_SOURCE` 조합에서 처음 발현되어 `buffer overflow detected`로 크래시 → `fb_strlcpy(s, path, strlen(path) + 1)`로 수정.

### 2026-07-30 (파트 3) — migration-cost 카운터 첫 사용 (`migtest`, fix 이전 코드) + 반복측정 (`migtestrep2/3`)
- hotcold v7, `gc_migrate_pages`를 GiB로 정규화, 3회 평균±표준편차:

  | 정책 | migrate_pages/GiB | erases/GiB |
  |---|---|---|
  | Greedy | 49,111 ± 1,782 | 2,469.6 ± 11.8 |
  | Cost-Benefit | 52,162 ± 2,900 | 2,481.1 ± 19.6 |
  | Random | 133,519 ± 628 | 2,855.1 ± 5.5 |

  Random 확실히 나쁨. Greedy-CB 평균 차(~3,050)가 CB 자체 stdev(2,900)와 거의 같은 크기라 **이 시점(버그 수정 전)에는 새 지표로도 노이즈 수준 판정** — "erase_cnt가 부적절한 지표였다"는 가설은 여기선 기각됨. 이후 힙 staleness 버그를 찾아 수정하고 나서야(아래 `vpcdiag` 항목) 진짜 차이가 드러남.

### 2026-07-30 (파트 3, 최종) — `vpcdiag`: 힙 staleness 버그 수정 후 3정책 최종 비교 (hotcold v7, 각 3회 반복)
- 무엇을: `select_victim_line()`의 CB 분기를 전체 스캔 방식으로 수정한 뒤(위 "진행 로그" 참고), Greedy/Random/Cost-Benefit 각각 hotcold v7로 3회씩 재측정.
- 결과 (GiB/latency로 정규화, 3회 평균 ± 표준편차):

  | 지표 | Greedy | Cost-Benefit | Random |
  |---|---|---|---|
  | migrate_pages/GiB | 48,493 ± 1,302 | 55,079 ± 1,198 | 134,288 ± 954 |
  | erase/GiB | 2,465.4 ± 8.9 | 2,500.2 ± 7.6 | 2,870.4 ± 6.4 |
  | erase max | 10.3 (10,11,10) | 8.3 (9,8,8) | 11.3 (11,12,11) |
  | nonzero_blocks | 85,624 | 89,433 | 86,500 |
  | erase_cv | 0.239 | 0.231 | 0.489 |
  | latency avg | 80.2μs ± 0.6 | 84.5μs ± 0.6 | 152.4μs ± 0.7 |
  | latency p99 | 432.1μs ± 10.8 | 439.0μs ± 16.6 | 1,521.0μs ± 34.1 |

  `diag_scan_greedy_vs_cb()`로 같이 잰 vpc 비교(Greedy 구동 중 vs CB 구동 중, 각 3회 평균): `avg_abs_vpc_diff`가 Greedy 구동 시 11.3(평균 vpc의 13.4%), **CB 구동 시 33.8(47.4%)** — 작지 않음. "다른 line을 골라도 vpc는 비슷하다"는 가설은 기각되고, "다르게 고르면 비용도 실제로 다르다"는 게 확인됨 (`same_vpc_different_line_ratio`도 CB 구동 시 0.02%로 사실상 0).
- **최종 결론(리포트 헤드라인)**: 이전까지의 "Greedy≈CB 수렴"은 힙 staleness 버그가 CB를 우연히 Greedy와 비슷하게 행동하게 만든 착시였음. 버그 수정 후 3회 반복 모두 range가 안 겹치는 수준으로 뚜렷하게 갈림 — **Cost-Benefit은 총 migration 효율을 13.6% 더 씀(latency도 약 5% 높음) 대신, 최대 마모(erase max)를 낮추고(8.3 vs 10.3) 마모를 더 많은 블록에 분산시킴(89,433 vs 85,624)** — Cost-Benefit GC의 교과서적 트레이드오프(총 효율 희생 ↔ 웨어 레벨링 개선)와 정확히 일치. Random은 모든 지표에서 확실히 최악.
- raw 로그 경로: `results/*_vpcdiag_rep{1,2,3}/` (policy0/1/2 각각)

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

### 2026-07-26
- 증상: 집 컴퓨터에서 모듈 리로드 1단계(umount→rmmod→make→insmod) 후 `sudo mount /dev/nvme0n1 ~/nvme_mount` 실행 시 `wrong fs type, bad option, bad superblock on /dev/nvme0n1, missing codepage or helper program, or other error` 에러 발생.
- 원인: VM 자체를 껐다 켰음(재부팅). `memmap=`으로 예약된 DRAM 영역은 진짜 물리 메모리라 재부팅하면 내용이 통째로 사라짐 — 그 위에 있던 ext4 슈퍼블록/파일시스템 구조도 같이 날아가서 마운트할 게 없는 상태였음. 7/24에 확인한 "모듈 리로드만으론 데이터 안 지워짐"은 OS가 계속 켜져 있는 경우에만 해당하고, VM 재부팅은 이 전제 자체를 깨뜨림.
- 해결: `sudo mkfs -t ext4 /dev/nvme0n1` 재실행 후 정상 마운트됨. 앞으로 VM을 재부팅한 뒤에는 모듈 리로드뿐 아니라 `mkfs`도 다시 해야 한다는 걸 체크리스트에 추가할 것.

### 2026-07-26
- 증상: 집 컴퓨터에서 `./scripts/run_experiment.sh` 실행 시 `fio: command not found`류 에러.
- 원인: 연구실 VM에는 fio가 설치돼 있었지만, 집 컴퓨터는 별도로 프로비저닝된 환경이라 처음부터 설치가 안 되어 있었음.
- 해결: `sudo apt install -y fio`로 설치. 앞으로 새 컴퓨터/환경에서 작업 시작 전엔 fio/filebench 설치 여부부터 확인하기로 함 (사용자가 "환경 차이는 항상 기록하자"고 명시적으로 요청함).

### 2026-07-24
- 증상: 7/23에 기록한 Greedy 기준선(`nonzero_blocks=19424, sum=157136, max=9`)과 7/24에 다시 잰 값(`19280/61008/4`)이 2.5배 넘게 차이남 — "Greedy도 원래 매번 다르게 나오는 거 아니냐"는 의문이 생김.
- 원인: Greedy는 victim 선택에 난수가 전혀 없고(vpc 최솟값을 그냥 고름) fio도 기본 `randrepeat=1`이라 매번 같은 순서로 씀 — 즉 이론적으로 완전히 결정론적이어야 함. 모듈을 리로드해서 동일 조건(Greedy, reset 직후, 동일 fio 커맨드)으로 2회 연속 재현 테스트한 결과 **두 번 다 `19280/61008/4`로 완전히 일치** (최초 측정까지 3회 연속 동일). 즉 오늘 값 쪽이 정확하고, 7/23 값이 이상값이었던 것으로 보임. 7/23 당시 정확히 어떤 조건이 달랐는지는(진짜 reset 직후였는지, 파일이 새로 쓰이는 상태였는지 등) 로그에 안 남아있어서 정확한 원인은 미확정.
- 해결: 7/23 Greedy 수치는 신뢰도 낮음으로 표시하고 폐기, 오늘 재현된 `19280/61008/4`를 새 기준선으로 채택. 앞으로 벤치마크할 때는 "리로드 직후 + reset 직후"라는 조건을 매번 로그에 명시해서 재현성을 추적할 것.

### 2026-07-26
- 무엇을: `scripts/run_experiment.sh`, `scripts/collect_summary.sh`, `results/` 디렉토리 추가 — 결과 저장 파이프라인 구현.
  - `run_experiment.sh <policy 0|1|2> <label>`: `gc_policy` sysfs 전환 → `/proc/nvmev/debug reset` → 기존 검증된 `gc_stress` fio 커맨드를 `--output-format=json`으로 실행(latency 포함) → erase_cnt 재덤프 → awk summary → meta.txt(정책/라벨/타임스탬프/fio 커맨드) 까지 한 번에 생성, 결과는 `results/<타임스탬프>_policy<n>_<정책명>_<라벨>/`에 저장.
  - `collect_summary.sh`: `results/` 밑 모든 run의 `meta.txt`/`summary.txt`/`fio.json`(jq로 avg latency, p99 tail latency 추출)을 훑어서 CSV 한 줄씩으로 집계 (`timestamp,policy,policy_name,label,nonzero_blocks,erase_sum,erase_max,lat_avg_ns,lat_p99_ns`).
- 왜: 지금까지 터미널에서 `awk`로 즉석 확인만 하고 raw 로그를 저장 안 해서, 나중에 그래프 그릴 때 쓸 데이터가 없었음. "서버 벤치마크 전 남은 작업" 4번 항목 해소.
- 검증: 집 컴퓨터 로컬 환경에서 Greedy(policy=0)로 `run_experiment.sh 0 pipelinetest` 실행 → `fio.json`/`erase_cnt.txt`/`meta.txt`/`summary.txt` 4개 파일 정상 생성, `nonzero_blocks=19520 sum=62176 max=4` 확인. `collect_summary.sh` 실행 → CSV 한 줄로 정상 집계, jq로 `lat_avg_ns=641274.209063`, `lat_p99_ns=1056768` 정상 추출 확인.
- sudo 필요한 부분(`gc_policy` 쓰기, `debug reset`)은 에이전트 셸에 인터랙티브 터미널이 없어서 여전히 사용자가 직접 실행해야 함 (2026-07-23 "이슈" 항목과 동일 제약, 집 컴퓨터에서도 재확인됨).
- 커밋: (미커밋, `scripts/`·`results/` 새 파일)

- 무엇을: 이번 주말부터 집 컴퓨터에서 작업 시작 (그동안은 연구실 컴퓨터). `git pull` 하니 origin에 로컬에 없던 12개 커밋(이 `CLAUDE.md`/`EXPERIMENT_LOG.md` 최초 추가 포함)이 이미 들어와 있었음. 로컬 `main.c`엔 의미 없는 빈 줄 하나만 있던 상태라 그 변경은 버리고 fast-forward pull 진행.
- 왜: CLAUDE.md에 이미 적혀 있던 "이 fork를 여러 환경에서 건드리면 동기화가 어긋날 수 있다"는 경고가 실제로 재현된 사례라 기록해둠.
- 커밋: (해당 없음, git 동기화 이슈 기록)

- 무엇을: 집 컴퓨터 환경에서 연구실 VM과 다른 점 2가지 발견/해결.
  1. `fio`가 설치 안 되어 있었음 → `sudo apt install -y fio`로 설치.
  2. 모듈 리로드(umount→rmmod→make→insmod→mount) 도중 `mount`가 `wrong fs type, bad option, bad superblock` 에러로 실패.
- 왜/원인: (1)은 별도로 프로비저닝된 환경이라 패키지 상태가 다름. (2)는 VM 자체를 껐다 켰기 때문 — `memmap=`으로 예약된 DRAM 영역 내용이 재부팅으로 전부 날아가서, 7/24에 확인한 "모듈 리로드만으론 데이터 안 지워짐"이라는 전제(OS가 계속 켜져 있는 경우 한정)가 깨짐. 사용자가 "환경 차이/패키지 설치가 필요한 경우 항상 기록하라"고 명시적으로 요청해서 이 규칙에 따라 남김.
- 해결: (1) `apt install`. (2) `sudo mkfs -t ext4 /dev/nvme0n1` 재실행 후 정상 마운트됨.
- 커밋: (해당 없음, 환경 이슈 기록)

### 2026-07-27
- 증상: 정책마다 모듈 리로드 없이 `gc_policy`만 sysfs로 바꿔가며 이어서 실행한 3정책 비교(11:26~11:29)에서 Greedy와 Cost-Benefit의 erase 통계가 거의 동일하게 나옴.
- 원인: `mkfs`는 파일시스템만 초기화하고 FTL 내부 상태(`cb_clock`, write pointer, free line list 등)는 초기화 안 함 — 이건 모듈 완전 리로드(`rmmod`→`insmod`)로만 리셋됨. 뒤에 실행된 정책이 앞 정책이 남긴 물리적 상태를 그대로 물려받아서 비교가 오염됨.
- 해결: 정책 비교 시 반드시 정책마다 모듈을 완전히 리로드하도록 절차 확정. CLAUDE.md "모듈 리로드 사이클" 절에 경고 추가.

### 2026-07-27
- 증상: (위 이슈 해결 후에도) hotcold v1 워크로드(coldfile 1회 쓰기 + hotfile 반복 쓰기)에서 여전히 Greedy와 Cost-Benefit이 거의 동일하게 동작.
- 원인: 콜드파일을 한 번도 다시 안 건드리면 그 line들은 계속 100% valid로 남아서 `advance_write_pointer()`가 `full_line_list`로 보내고 victim pqueue엔 아예 안 들어감(`mark_page_invalid()`가 애초에 호출 안 됨) — Cost-Benefit이 age를 계산할 후보 자체가 전부 "핫" line뿐이라 age 편차가 생길 여지가 없었음(printk 실측: age 변동폭 약 1%).
- 해결: `hotcold.fio`를 v2로 재설계 — 콜드 영역도 낮은 빈도로나마 덮어써지도록 `random_distribution=zoned`로 접근 빈도 자체를 스큐(하나의 파일 안에서 처리).

### 2026-07-30
- 무엇을: `scripts/collect_summary.sh`의 latency 추출을 `jobs[0]`에서 `jobs[-1]`(마지막 job/그룹)으로 변경.
- 왜: hotcold 워크로드가 v5부터 fio job을 여러 개(cold_fill/cold_touch/hot_churn)로 나누면서, `group_reporting` 하에서는 `jobs[0]`이 콜드파일 순차쓰기(`cold_fill`) 구간을 가리키게 됨 — GC 부하가 실제로 걸리는 마지막 job(그룹)이 아니라 사실상 무관한 구간의 latency를 재고 있었던 것. uniform 워크로드는 job이 하나뿐이라 `jobs[-1]==jobs[0]`이라 영향 없음.
- 커밋: (미커밋)

### 2026-07-30
- 무엇을: `scripts/workloads/hotcold.fio`를 v5로 재설계 — `stonewall` 3단계(`cold_fill`: 콜드파일 크게 1회 순차쓰기 → `cold_touch`: 그중 일부만 랜덤 재기록 → `hot_churn`: 작은 핫파일 반복 재기록)로 콜드/핫을 물리적·시간적으로 분리. `scripts/run_experiment.sh`에 `COLD_SIZE`(기본 30G)/`COLD_TOUCH_SIZE`(기본 3G)/`HOT_SIZE`(기본 1G)/`HOT_LOOPS`(기본 100) 환경변수 추가.
- 왜: v1~v4는 hot/cold를 한 파일 안에서 접근 빈도로만 나눠서, 로그 구조 FTL 특성상 같은 물리 line에 hot/cold 페이지가 뒤섞여 vpc와 age가 강하게 상관됨 — Greedy/CB가 항상 같은 순서로 후보를 매기는 근본 원인으로 지목됨.
- 검증: 서버에서 Greedy 단독 실행(v5calib) 결과 `nonzero_blocks=3144 sum=234816 max=79` — 마모가 작은 핫 영역에 집중되는 정성적으로 다른 분포 확인. 다만 Greedy/CB 비교는 여전히 수렴 (아래 "이슈" 2026-07-30 항목 참고).
- 커밋: (미커밋)

### 2026-07-30
- 무엇을: `hotcold.fio`를 v6로 재설계 — `hot_churn`의 `stonewall`을 제거해서 `cold_touch`와 같은 그룹에서 병렬 실행. `COLD_TOUCH_SIZE` 기본값을 3G→15G로 키움.
- 왜: v5는 `cold_touch`(3G)가 `hot_churn`(100G) 시작 전에 순차적으로 다 끝나버려서, 콜드 후보가 초반에만 반짝 존재하고 대부분의 실행 시간 동안은 핫 후보끼리만 경쟁하게 됨 — 콜드/핫 후보가 GC 전 구간에 걸쳐 동시에 존재해야 age가 타이브레이커로 작동할 기회가 생긴다는 판단.
- 검증: v6calib 결과 Greedy `37660/275684/86` vs Cost-Benefit `38864/277572/86` — v5보다 nonzero_blocks 차이는 조금 커졌지만(0.6%→3.2%) erase max는 여전히 정확히 일치. 부분적 개선에 그침 (아래 "이슈" 항목에서 printk로 근본 원인 규명).
- 커밋: (미커밋)

### 2026-07-30
- 무엇을: `conv_ftl.c`의 `select_victim_line()`에 임시 진단 함수 `diag_compare_victims()` 추가 (전역 카운터 `diag_gc_total`/`diag_gc_diverge`). 활성 `gc_policy`와 무관하게 pqueue 원본 배열(`pq->d[]`)에서 Greedy 최적 후보(min vpc)와 Cost-Benefit 최적 후보(max bc, vpc==0 가드 동일 적용)를 각각 독립적으로 계산해서 서로 다른 line을 고르는지 매 GC 판정마다 비교, 처음 50건은 상세 printk, 이후엔 500건마다 누적 카운트만 printk. pq 상태를 변경하지 않는 read-only 코드.
- 왜: v5/v6에서 erase 총량 지표가 계속 수렴하는 게 "두 정책이 실제로 항상 같은 line을 고르기 때문"인지 "다르게 고르는데 집계에 안 드러나는 것"인지 추측만으로는 구분이 안 됐음.
- 검증: 로컬(비-nvme 디렉토리)에서 문법 확인 후 서버에서 빌드/insmod, hotcold v6/v7 워크로드로 dmesg 진단 로그 확보 (자세한 결과는 "벤치마크 실행 로그"/"이슈" 2026-07-30 항목 참고).
- **주의**: 최종 제출 전 이 진단 코드(`diag_compare_victims`, `diag_gc_total`, `diag_gc_diverge`와 `select_victim_line()`의 호출부)를 제거하고 클린 빌드로 재확인할 것.
- 커밋: (미커밋)

### 2026-07-30
- 무엇을: `hotcold.fio`를 v7로 재설계 — `cold_touch`/`hot_churn` 둘 다 `size`+`loops` 기반에서 `time_based=1`+동일 `runtime`(환경변수 `HOTCOLD_RUNTIME`, 기본 90초)으로 변경.
- 왜: v6는 `cold_touch`(15G)가 `hot_churn`(100G)보다 훨씬 먼저 끝나서(진단 printk로 실측: 전체 GC 판정의 16.7%에서만 두 정책이 갈리고 나머지 83%는 완전히 일치), divergence가 생기는 구간 자체가 짧아 집계에 안 드러남. 둘 다 같은 시간 동안 돌게 하면 크기 차이와 무관하게 끝까지 겹침.
- 검증: 진단 로그 상 `total=101000, diverge=93915`(93%)로 끝까지 divergence 유지 확인. 실제 3정책 비교에서도 이번엔 erase 통계가 달라짐 (다만 `time_based`라 정책별 처리량이 달라지는 새 변수 발생 — GB당 정규화 필요, "이슈" 2026-07-30 항목 참고).
- 커밋: (미커밋)

### 2026-07-27
- 증상: v2(`zoned:80/10:20/90`)로 재설계한 뒤에도 Greedy와 Cost-Benefit의 erase_sum/max가 여전히 동일.
- 원인: 스큐가 너무 강해서 핫 영역이 극도로 빨리 재기록되며 vpc가 매우 작은(거의 다 무효화된) 후보가 GC 후보 풀에 항상 대기 중이었음(printk 실측: vpc=1~6 구간이 전체 샘플의 46%). `bc=ipc*age/(2*vpc)` 수식은 vpc가 작을수록 다른 항을 압도하므로, 이런 후보가 항상 있으면 age가 아무리 벌어져도 CB가 Greedy와 동일한 선택을 하게 됨.
- 해결: 스큐를 완화(`zoned:60/20:40/80`, v3)해서 vpc 분포를 더 넓게 폄. 다만 이렇게 해도 erase 총량 지표는 여전히 수렴함 — 이건 버그가 아니라 이 스케일/워크로드에서 실제로 관찰되는 현상으로 결론 내림(자세한 내용은 "벤치마크 실행 로그" 12:20~12:27 항목, "진행 로그" 참고).

### 2026-07-27
- 증상: 서버(147.46.241.107, 포트 220) SSH 접속 시도 시 연결 타임아웃.
- 원인: 미확인 — VPN/캠퍼스 네트워크가 필요하거나, 로컬 VM에서 서버로 직접 못 나가는 네트워크 구성일 가능성. 사용자에게 정확한 접속 방법(사용자명, VPN 필요 여부, 인증 방식)을 확인 요청한 상태.
- 해결: 미해결, 다음 세션에서 이어서 진행.

### 2026-07-30
- 증상: Claude Code Bash 툴로 `run_experiment.sh`(sudo 필요)를 자동 실행하려 하니 `sudo: Authentication failed`가 3연속 뜨며 실패. 사용자가 자기 터미널에서 미리 `sudo -v`를 해뒀는데도 안 먹힘.
- 원인: `tty` 확인 결과 Bash 툴 세션은 "not a tty"(non-interactive) — sudo의 인증 타임스탬프 캐시는 tty별로 분리되어 있어서, 사용자의 인터랙티브 터미널에서 캐시해둔 인증이 Bash 툴의 별도 세션에는 전혀 적용되지 않음. 2026-07-23에 이미 "인터랙티브 터미널이 없어서 sudo 실패" 이슈가 있었지만, 이번엔 "사용자가 미리 sudo -v를 해두면 우회되지 않을까"를 시도해보다 재확인된 것.
- 해결: 여전히 동일한 원칙 적용 — sudo가 필요한 명령(`run_experiment.sh` 등)은 Claude가 정확한 명령어만 만들어 제시하고, 사용자가 자기 터미널에서 직접 실행 → 결과 파일만 Claude가 읽어서 분석. `sudo -v` 선행 자체는 Bash 툴에 도움 안 됨(불필요).

### 2026-07-30 (핵심 이슈, 하루 종일 조사)
- 증상: `final`(uniform+hotcold v3) 3정책 공식 비교에서 Greedy와 Cost-Benefit의 erase 통계(`nonzero_blocks`/`sum`/`max`)가 사실상 동일하게 나옴. 이후 워크로드를 4번 재설계(v4 파라미터화 → v5 물리적 시간분리 → v6 병렬실행 → v7 time_based)하고 부하 강도를 3.2배~1.07배까지 바꿔봐도, `erase_max`가 계속 정확히 일치(v5: 79/79, v6: 86/86)하는 등 좀처럼 안 갈림.
- 1차 원인 가설(구조적 상관): `victim_line_get_pri()`가 vpc==0인 line은 age 계산 없이 무조건 최우선 victim으로 처리하도록 가드돼 있어서(2026-07-24 구현), 워크로드가 강하면 후보 대부분이 이런 "공짜 승리" line이 되어 두 정책이 항상 합의해버림 + 로그 구조 FTL 특성상 line의 vpc와 age가 자연히 상관되어(오래된 line일수록 무효화될 시간도 길었으므로) 실제 경쟁 상황 자체가 잘 안 만들어짐.
- 검증 방법: 위 가설만으로는 "정말 항상 같은 걸 고르는지 vs 다르게 고르는데 통계에 안 드러나는지" 구분이 안 돼서, `conv_ftl.c`의 `select_victim_line()`에 임시 진단 함수(`diag_compare_victims()`, 2026-07-30 추가 — 실제 활성 `gc_policy`와 무관하게 pqueue 원본 데이터에서 Greedy 최적(min vpc)과 Cost-Benefit 최적(max bc)을 각각 독립 계산해서 서로 다른지 매 GC 픽마다 비교/카운트하는 read-only printk 코드)를 추가해서 직접 실측.
- **진짜 원인 (v6 워크로드로 진단)**: Cost-Benefit은 실제로 다른 line을 고름 — 실행 초반 11500번(전체 GC 판정의 16.7%) 동안은 최대 87%까지 Greedy와 다르게 골랐음. 그런데 `cold_touch`(15G)가 `hot_churn`(100G)보다 훨씬 먼저 끝나버려서(병렬 실행이지만 크기 차이로 인해), 그 이후 83%는 콜드 후보 공급이 끊겨 핫 line끼리만 경쟁 → 거기서부턴 100% 일치. **집계 통계가 수렴해 보였던 건 정책이 실제로 같은 선택을 해서가 아니라, "다르게 고르는 17% 구간"이 "완전히 똑같이 고르는 83% 구간"에 파묻혀서였음.**
- 해결: `hotcold.fio`를 v7로 재설계 — `cold_touch`/`hot_churn` 둘 다 `size` 기반 대신 `time_based=1`+동일 `runtime`(기본 90초)으로 바꿔서 콜드 후보가 실행 시간 내내 끊이지 않고 공급되도록 함. 재진단 결과 divergence가 실행 끝까지 유지됨(`total=101000, diverge=93915`, 93% — 한 번도 멈추지 않음).
- 2차 발견 (정규화 필요성): v7로 실제 3정책을 비교하니 이번엔 erase 통계가 달랐지만(Greedy `sum=405864`, CB `sum=401248`, Random `sum=294720`), Random의 sum이 가장 낮은 게 이상해서 io_bytes를 확인해보니 **`time_based` 워크로드에서는 정책마다 같은 90초 동안 실제로 처리한 데이터량 자체가 다름**(Random은 GC 오버헤드가 커서 처리량이 절반 수준: Greedy/CB ~161~162GiB vs Random ~102GiB) — 그래서 GB당 erase 횟수로 정규화해야 공정한 비교가 됨. 정규화 결과: Greedy 2500.6/GiB, **Cost-Benefit 2490.0/GiB(약간 더 효율적)**, Random 2882.4/GiB(뚜렷하게 더 나쁨 — 이론과 일치). erase max도 CB(8)가 Greedy/Random(11/11)보다 뚜렷하게 낮아서, **CB가 더 많은 블록(89436 vs 85916)에 걸쳐 더 고르게 마모시키면서 총 효율도 비슷하거나 더 낫다**는, Cost-Benefit GC의 교과서적 이점이 마침내 실측으로 확인됨.
- 남은 일: 이 v7+정규화 방법론으로 정책 3종 최종 벤치마크 재확정(반복측정으로 노이즈 여부 확인 권장), 진단용 printk(`diag_compare_victims`, `diag_gc_total`, `diag_gc_diverge`)는 최종 제출 전 `conv_ftl.c`에서 제거, uniform 워크로드도 필요시 재점검.

### 2026-07-30 (파트 2/3, 가장 오래 걸린 이슈 — 힙 staleness 버그)
- 증상: 위 v7+정규화로도 uniform에서는 Greedy=CB가 3회 반복 다 소수점까지 완전히 동일하게 나오고, hotcold v7의 `migtest` 3회 반복(erase/GiB, migrate_pages/GiB 둘 다)에서도 Greedy-CB 평균 차가 각 정책 자체의 반복 간 표준편차보다 작아서 "노이즈 수준"으로만 판정됐음. 워크로드를 v1→v7까지 재설계해도 이 이상은 안 갈렸음.
- 계기: 사용자가 Codex(다른 LLM)에게 `conv_ftl.c`/`conv_ftl.h`/`pqueue/pqueue.c`를 보여주고 6개 가설을 받아옴. 그중 핵심 2개: (1) `victim_line_get_pri()`의 CB score가 `cb_clock`(계속 흐르는 전역 시계) 기반이라 매 순간 값이 바뀌는데, pqueue의 `bubble_up`/`percolate_down`은 **그 노드가 insert/remove될 때 조상 경로만** 재정렬하므로 heap root가 "지금 이 순간의 진짜 최고" line이 아닐 수 있다. (2) 기존 진단(`diag_compare_victims`)은 `pq->d[]` 전체를 스캔해서 이상적인 Greedy pick과 이상적인 CB pick을 비교했을 뿐, "실제로 `pqueue_pop()`이 리턴하는 line"과는 비교한 적이 없어서 버그가 있어도 진단에 안 잡혔을 수 있다.
- 원인 (실측 확인 완료):
  1. `pqueue/pqueue.c`를 파이썬으로 그대로 포팅해서 `victim_line_get_pri()`의 CB 계산식으로 최소 반례(2개 line, ipc/vpc 비율이 다름)를 만든 결과: 몇 틱만 지나도 실제 최고 bc score line과 heap root가 완전히 달라지고, 라이브러리 자체 검증 함수 `pqueue_is_valid()`도 계속 `False`로 나옴 — 추가 insert/remove가 없으면 이 상태가 영원히 자기 교정되지 않음(t=6부터 t=50까지 root가 계속 잘못된 line을 가리킴, bc 차이는 t=20에 750배까지 벌어짐).
  2. 좀 더 실전과 비슷한 규모(line 수천 개, 지속적 invalidate+GC pop 20만 스텝) 합성 시뮬레이션에서, 실제 `pqueue_pop()` 결과가 "그 순간 전체 스캔 진짜 최고 bc line"과 87.2% 다름 (임의 확률 파라미터 기반이라 정확한 %는 참고용, 메커니즘이 실재하고 크다는 것의 증거로만 사용).
  3. 실제 커널에 임시 카운터(`diag_fix_total`/`diag_fix_changed`)를 추가해 hotcold v7로 실측: `total=99500, changed=5443`(5.47%) — 버그가 실재하고 실제로 발동함을 확인. 다만 실제 발동 비율이 5.47%뿐이라, 이 정도로는 fix 전/후 1회 측정 비교만으로는 총량 지표 차이가 안 드러남(→ 이게 왜 지금까지 "노이즈 수준"으로만 보였는지의 답이기도 함).
- 해결: `select_victim_line()`에서 `GC_POLICY_COST_BENEFIT`일 때 `pqueue_pop()` 대신 `pq->d[1..size-1]` 전체 스캔으로 그 순간 진짜 최고 line을 찾아 `pqueue_remove()`로 꺼내도록 교체 (자세한 코드는 "진행 로그" 2026-07-30 파트 3 참고). 수정 후 Greedy/Random/Cost-Benefit 각 3회씩 재측정(`vpcdiag`)한 결과, 처음으로 range가 안 겹치는 뚜렷한 차이 확인 — migrate_pages/GiB에서 CB가 Greedy보다 13.6% 더 씀, erase max는 CB가 확실히 더 낮음(8.3 vs 10.3). **결론: 지금까지의 "Greedy≈CB 수렴"은 이 힙 staleness 버그가 CB를 우연히 Greedy와 비슷하게 행동하게 만든 착시였음.** 자세한 최종 수치는 "벤치마크 실행 로그"의 `vpcdiag` 항목 참고.
- 추가 검증 도구: 버그 수정과 별개로, "Greedy와 CB가 다른 line을 골라도 migration cost(vpc)는 비슷한지"를 직접 확인하는 상시 계측(`diag_scan_greedy_vs_cb`, `avg_greedy_vpc`/`avg_cb_vpc`/`avg_abs_vpc_diff`/`same_vpc_different_line_ratio`)을 추가해서, "다르게 고르면 비용도 실제로 다르다"(CB 구동 중 `avg_abs_vpc_diff`=평균 vpc의 47.4%)는 것까지 정량 확인. 이 계측은 read-only라 실제 GC 동작에 영향 없고, 보고서 부연자료로 쓸 수 있어 최종 제출 코드에도 남기기로 함(`conv_ftl.c`/`conv_ftl.h`/`main.c` 주석 참고).

### 2026-07-31 (제출 전 전체 코드 재점검)
- 증상: 제출 전 커밋된 코드 전체를 다시 리뷰하다가, `run_experiment.sh`의 summary 집계 awk가 `nonzero_blocks`를 헤더 줄 개수만큼 부풀리고 있는 것을 발견.
- 원인: `/proc/nvmev/debug` 출력 맨 앞에 붙는 헤더 줄들(`GC_VALID_PAGE_MIGRATE_CNT`, `DIAG_*` 총 7줄)은 필드가 2개뿐이라 `$7`이 uninitialized인데, **mawk는 uninitialized 필드를 문자열 `""`로 취급해서 `"" != 0`을 참으로 평가**함. 그래서 `$7!=0{... n++}`이 헤더 줄도 세어버림. (`sum`/`max`는 `""`가 산술 문맥에서 0으로 강제변환되어 영향 없음 — 실측으로 확인.)
- 영향 범위: `nonzero_blocks`만 헤더 줄 개수만큼 +됨 — `migtest`/`cbfix`/`diagcheck` 계열은 +1, `vpcdiag` 계열은 +7. `erase_cv`도 분모(blk_n)가 같이 늘어 아주 미세하게 틀림(0.2408 → 0.2406 수준). **모든 정책에 동일한 상수 오프셋이라 정책 간 비교/결론은 전혀 영향 없음**(CB-Greedy 차이는 3809로 정정 전후 완전히 동일). 헤더가 없던 시기의 run(uniform, filebench, v7rep2/3, final 등)은 애초에 영향 없음.
- 해결: `run_experiment.sh`/`run_filebench_experiment.sh`의 awk에 `NF==7` 가드 추가. 영향받은 run들의 `summary.txt`를 고친 awk로 전부 재생성하고, 보고서/CLAUDE.md/EXPERIMENT_LOG.md의 `nonzero_blocks` 수치와 fig2 그래프를 정정값(Greedy 85,624 / CB 89,433 / Random 86,500)으로 갱신함.
- 같이 한 검증 (결과의 신뢰도를 크게 높인 부분): `gc_migrate_pages / total_gc`(= 실제로 선택된 victim의 평균 vpc)를 진단이 독립적으로 계산한 `avg_greedy_vpc`/`avg_cb_vpc`와 대조함.
  - Greedy 3회: 실제 선택 = `avg_greedy_vpc`와 소수점 3자리까지 완전 일치(80.707/78.142/77.171) → **Greedy의 힙은 항상 정확히 min-vpc line을 뽑고 있음이 실측으로 증명됨**(vpc는 `mark_page_invalid`가 매번 remove+insert로 정확히 갱신하므로 stale해질 수 없다는 분석과 일치).
  - Cost-Benefit 3회: 실제 선택 = `avg_cb_vpc`와 소수점 3자리까지 완전 일치(89.925/86.706/87.716) → **힙 staleness 수정이 의도대로 동작해서, 실제로 뽑히는 line이 그 순간의 진짜 CB 최적 line임이 증명됨.**
  - Random 3회: 실제 선택(≈187)이 greedy이론(≈8.9)·cb이론(≈10.0) 어느 쪽과도 안 맞음 → 무작위 선택이 맞게 동작.
- 그 외 점검 결과 (문제 없음): 컴파일 경고 0건. `victim_line_set_pri()`(호출되면 `vpc`를 우선순위 값으로 덮어써서 상태를 파괴함)는 `pqueue_change_priority()`를 통해서만 호출되는데 그 함수를 conv_ftl.c에서 아무도 안 부르므로 도달 불가 — 안전. `pqueue_remove()`가 힙의 마지막 원소를 지우는 엣지케이스도 `cmppri(x,x)==false`라 percolate_down으로 빠져 안전. `ipc * age` 오버플로 여유 충분(최대 ~2e10, uint64 범위 내). victim pqueue에 들어가는 line은 전부 닫힌(=`mtime` 스탬프된) line이라 `age`가 비정상적으로 커지는 경로 없음.
- 남은 알려진 한계 (수정 안 함, 문서화로 갈음): `gc_policy`를 sysfs로 런타임 전환하는 것은 **Cost-Benefit → Greedy 방향에서 안전하지 않음.** CB로 동작하는 동안 힙은 CB 우선순위로 정렬돼 있는데, Greedy로 바꾸면 `pqueue_pop()`이 그 정렬을 그대로 신뢰해서 min-vpc가 아닌 line을 뽑게 됨(그리고 스스로 복구되지 않음). 반대 방향(Greedy → CB)은 CB가 매번 전체 스캔을 하므로 안전. **본 벤치마크는 정책마다 항상 모듈을 완전 리로드하는 절차를 썼기 때문에 이번 측정 결과에는 영향 없음.** CLAUDE.md의 커맨드 레퍼런스에도 경고 추가함.

### 2026-07-31 (후속 조치)
- 무엇을: `conv_ftl.c`의 `module_param(gc_policy, uint, 0644)`를 `0444`(런타임 읽기 전용)로 변경.
- 왜: 바로 위 항목에서 "남은 알려진 한계"로 문서화만 하고 넘어갔던 문제 — Cost-Benefit → Greedy 런타임 전환 시 Greedy가 CB 우선순위로 정렬된 힙의 root를 그대로 신뢰해 **에러 없이 조용히 잘못된 victim을 고르는** 문제 — 를 아예 발생 불가능하게 막음. 여기에 2026-07-27에 확인된 "정책만 바꿔 이어서 돌리면 FTL 내부 상태가 오염된다"는 문제까지 같은 조치로 함께 차단됨.
- 영향 없음 확인: `insmod ./nvmev.ko ... gc_policy=N`은 sysfs를 거치지 않고 모듈 로드 시점에 커널이 직접 파싱하므로 **그대로 동작함**. `cat /sys/module/nvmev/parameters/gc_policy`(현재 정책 확인)도 읽기라 그대로 됨. 막히는 건 `echo N | sudo tee ...`(런타임 쓰기)뿐이고, `run_experiment.sh`/`run_filebench_experiment.sh`는 이미 insmod 파라미터 방식만 쓰므로 벤치마크 파이프라인은 무영향. 이번 측정 결과도 전부 완전 리로드로 얻은 것이라 재측정 불필요.
- 검증: 재빌드 에러/경고 0건. CLAUDE.md의 커맨드 레퍼런스 §2를 "지정은 insmod 시점에만 가능"으로 갱신하고, 옛 sysfs 전환 안내가 남아있던 곳(코드 구조 요약, §1 리로드 사이클 경고)도 현재 동작에 맞게 정리함. 날짜별 진행 기록은 당시 사실이므로 그대로 둠.

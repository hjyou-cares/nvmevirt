# 프로젝트 배경 (실습 1: NVMeVirt Cost-Benefit GC)

## 나(사용자)에 대해
- 하드웨어 배경, 프로그래밍/C 코드는 완전 초보 수준.
- 설명은 왜 그런지(개념)부터 천천히, 함수 이름을 먼저 던지지 말고 "왜 필요한지" 먼저 설명한 뒤 코드를 보여줄 것.
- 코드를 수정할 때는 어떤 변수/함수를 왜 바꾸는지 먼저 설명하고, 한 번에 너무 많이 바꾸지 말 것. 큰 변경은 단계별로 나눠서 진행하고 매 단계마다 이해했는지 확인할 것.
- 지금까지 다른 Claude(claude.ai)와 함께 NVMeVirt 초기화 흐름(NVMeV_init), R/W 요청 처리 흐름(dispatcher → io_worker → 완료), GC 트리거 경로(conv_write → write credit → foreground_gc → do_gc → select_victim_line → clean_one_flashpg → mark_block_free/mark_line_free)를 코드 레벨로 전부 리뷰 완료함. line/block/page/channel/lun 계층 구조, pqueue 콜백 메커니즘(victim_line_get_pri 등)도 이해한 상태.

## 마감
- 7월 31일까지 실습1 완료 및 제출 (hslee@davinci.snu.ac.kr, 조교: 이한선)
- 제출물: 새로 구현한 코드 파일 + 결과 보고서 (측정 결과 그래프 + 간단한 분석)

## 개발 환경
- Windows 호스트 → VirtualBox → Ubuntu 22.04 VM (로컬, 구현/빌드용)
- VS Code + Remote-SSH로 VM에 접속해서 작업
- 실험 서버: 147.46.241.107 (포트 220), 접속: `ssh hjyoo@147.46.241.107 -p 220` (비밀번호 인증, VPN 불필요, 2026-07-28 접속 성공 확인). 호스트네임 `Z690-AORUS-ELITE-AX-DDR4`.
- **서버 NVMeVirt 파라미터 정정 (2026-07-28, 확정)**: 예전에 여기 적혀있던 `memmap_start=12G memmap_size=36G cpus=14,15`는 틀림 — PPT 자료에 있던 값으로 추정되나 실제와 다름. **올바른 값은 `memmap_start=16G memmap_size=48G cpus=7,8`**: 실습 방법 자료(별도 문서)에 이 값으로 명시되어 있고, 서버 실측 `/proc/cmdline`(`memmap=48G$16G isolcpus=7,8`)과도 정확히 일치해서 확정함. `intremap=off`는 커맨드라인에 없음(불필요한 것으로 보임). `insmod` 시 이 값 사용할 것.
- 저장소: GitHub fork `hjyou-cares/nvmevirt` (upstream: `snu-csl/nvmevirt`)
- **주의**: 이 fork를 로컬 VM 외에 다른 환경(서버 등)에서도 건드리고 있어서 origin에 로컬에 없는 커밋이 먼저 들어와 있던 적 있음 (2026-07-23, `CONFIG_NVMEVIRT_ZNS` 커밋). 작업 시작 전 `git fetch`/`git pull`로 동기화 확인 습관 들일 것.
- **평일엔 연구실 컴퓨터, 주말엔 집 컴퓨터로 작업** (2026-07-26부터). 둘 다 "로컬 VM, memmap_start=2G memmap_size=1G cpus=2,3" 컨셉은 같지만 별도로 프로비저닝된 환경이라 설치 패키지/상태가 다를 수 있음 — 새 컴퓨터에서 작업 시작 전엔 모듈 로드 여부, 마운트 여부, fio/filebench 설치 여부부터 확인할 것 (2026-07-26 집 컴퓨터에서 fio 미설치 + VM 재부팅으로 ext4 사라짐 두 가지를 겪음, 아래 "진행 상황 (2026-07-26 기준)" 참고).
- 빌드: gcc-12, linux-headers. 리로드 사이클: `umount → rmmod → make → insmod → mount(+chown)`
- GRUB 관련: `memmap=1G\\\$2G` 트리플 백슬래시 이스케이핑, `intremap=off` 필요 (VM 재설정 시 다시 필요할 수 있음)

## 실습 목표 (실습 1: Cost-Benefit GC)
NVMeVirt의 Conventional FTL(`conv_ftl.c`)에서 GC victim 선택 정책 3가지를 구현하고 비교:
1. **Greedy (baseline)** — 이미 구현되어 있음. `victim_line_get_pri()`가 `line->vpc`(valid page count)를 리턴하고, `pqueue_peek`/`pqueue_pop`이 vpc가 가장 작은 line을 뽑음 (최소힙).
2. **Random** — 구현 완료 (2026-07-23). `conv_ftl.c` 상단 `gc_policy` module_param(0/1/2) + `select_victim_line()` 분기. 로컬 VM 실측으로 Greedy 대비 erase가 훨씬 고르게 분산되는 것까지 검증함. 자세한 내용은 "코드 구조 요약", EXPERIMENT_LOG.md 참고.
3. **Cost-Benefit** — 구현 완료 (2026-07-24). `struct line.mtime` + 전역 논리 시계 `cb_clock`으로 age 추적, `victim_line_get_pri()`에 `(ipc*age)/(2*vpc)` 계산식 추가. 로컬 VM에서 빌드/insmod/fio 테스트로 크래시 없이 동작 확인. 자세한 내용은 "진행 상황 (2026-07-24 기준)" 참고.

평가: NVMeVirt 가상 SSD에 Filebench/FIO 벤치마크 실행 후, 정책별로 아래 측정:
- 블록별 Erase 횟수 (`mark_block_free()`의 `blk->erase_cnt++`)
- 호스트 IO AVG, Tail Latency

`erase_cnt`를 밖에서 보는 문제는 해결됨 (2026-07-23): `main.c`의 `debug` proc 파일에 dump/reset 기능 구현 완료. 사용법은 아래 "GC 정책 실험용 커맨드 레퍼런스 § 4" 참고.

## 코드 구조 요약 (핵심 함수 위치, conv_ftl.c 기준, 2026-07-24 Cost-Benefit 구현 후 줄번호 기준)
- `gc_policy` (파일 상단): module_param, 0=Greedy/1=Random/2=Cost-Benefit. `enum gc_victim_policy`도 같이 정의됨. 바로 옆에 `cb_clock`(전역 논리 시계, Cost-Benefit용, 2026-07-24 추가)도 있음.
- `victim_line_cmp_pri`(84줄), `victim_line_get_pri`(93줄), `victim_line_set_pri`(112줄), `victim_line_get_pos/set_pos`(117줄 근방): pqueue 콜백. `pqueue_init()`(`init_lines()` 안)에 등록됨.
  - `victim_line_cmp_pri`(비교 함수, min-heap 방향 결정)와 `victim_line_get_pos/set_pos`는 **Random·Cost-Benefit 구현 후에도 안 건드림** (비교 함수까지 정책별로 바꾸면 정책이 바뀔 때 기존 힙 정렬이 통째로 무의미해질 위험이 있어서, 값 쪽에서만 정책별로 다르게 계산하는 방향으로 감. 참고로 2026-07-31부터 `gc_policy`가 런타임 읽기 전용이 돼서 "실행 중 전환" 시나리오 자체는 사라졌지만, 이 설계 판단은 그대로 유지함).
  - `victim_line_get_pri`는 **Cost-Benefit 구현 시 수정함**: `gc_policy==COST_BENEFIT`이면 `(ipc*age)/(2*vpc)`를 계산해서 뒤집어 리턴(`CB_PRI_MAX - bc`), 아니면 기존처럼 `vpc` 그대로 리턴.
  - `victim_line_set_pri`는 이제 죽은 코드 (더 이상 아무도 안 부름, 아래 `mark_page_invalid()` 항목 참고).
- `consume_write_credit`, `check_and_refill_write_credit`: write credit 소진 시 `foreground_gc()` 트리거.
- `struct line` (conv_ftl.h): `id`, `ipc`, `vpc`, `pos`, **`mtime`**(2026-07-24 추가, line이 닫힌 시점의 `cb_clock` 값 — Cost-Benefit의 age 계산용) 필드.
- `struct line_mgmt`(`lm`, conv_ftl.h): `lines`(전체 line 배열), `free_line_list`, `victim_line_pq`, `full_line_list`, `free_line_cnt` 등.
- `mark_page_invalid()` (527줄): 페이지 invalid 처리. line이 막 full→invalid 전환되는 순간 `pqueue_insert()`로 큐에 새로 들어가는 건 동일. **`line->pos`가 있을 때(이미 pqueue 안에 있을 때)의 재정렬 방식이 2026-07-24에 바뀜**: 원래 `pqueue_change_priority(pq, line->vpc-1, line)`였는데, 이건 old_pri/new_pri가 같은 단위(원시 vpc)라는 전제가 있어야 안전한 방식이라 Cost-Benefit처럼 `get_pri()`가 파생 계산값을 리턴하면 힙이 깨질 수 있음 → `pqueue_remove()` + `line->vpc--` + `pqueue_insert()`로 교체 (항상 `get_pri()`를 그 자리에서 새로 읽으므로 정책 무관하게 안전, 자세한 이유는 "pqueue 라이브러리" 항목 및 진행 상황 2026-07-24 참고).
- `advance_write_pointer()`: line이 full_line_list나 victim pqueue로 넘어가는 "닫힘" 시점에 `cb_clock++` 및 `mtime` 스탬프 (2026-07-24 추가).
- `select_victim_line()` (689줄): `pqueue_peek()`으로 1등 확인 (모든 정책 공통 게이트, 단 `!force` 분기는 `do_gc()`가 항상 `force=true`로만 호출돼서 사실상 죽은 코드) → **`gc_policy`가 Random이면** `pq->d[]`에서 무작위 인덱스로 `pqueue_remove()`, **아니면**(Greedy/Cost-Benefit 둘 다) 기존처럼 `pqueue_pop()` — Cost-Benefit은 get_pri()가 이미 올바른 순서를 만들어주니 별도 분기 불필요.
- `do_gc()` (806줄), `clean_one_flashpg()` (746줄): 실제 GC 수행 (valid page 이관 → block erase → line 반환).

## erase_cnt 노출 (main.c, 2026-07-23 구현)
- `__walk_conv_blocks(m, mode)`: `__proc_file_read()` 바로 위에 정의된 헬퍼. `nvmev_vdev->ns[]` → `conv_ftl` → `ssd->ch[]/lun[]/pl[]/blk[]` 계층을 순회하며, `BLOCK_WALK_DUMP`면 `erase_cnt`를 한 줄씩 `seq_printf`, `BLOCK_WALK_RESET`이면 0으로 초기화.
- `/proc/nvmev/debug` read/write 핸들러(`__proc_file_read`/`__proc_file_write`의 `"debug"` 분기)에서 이 헬퍼를 호출하도록 연결됨.
- `NS_SSD_TYPE(ns_id) == SSD_TYPE_CONV`인 namespace만 처리 (zns/kv FTL은 건드리지 않음, `NVMEV_NAMESPACE_INIT`이 쓰는 패턴과 동일).

## pqueue 라이브러리 (pqueue/pqueue.c, pqueue/pqueue.h) 관련 중요 사실
- Vendored 코드 (범용 외부 라이브러리 소스가 저장소 안에 그대로 포함됨). `conv_ftl.h`에서 `#include "pqueue/pqueue.h"`.
- `pqueue_t` 구조체가 완전히 투명하게 노출되어 있음 (`q->d[]` 힙 배열, `q->size` 등 conv_ftl.c에서 직접 접근 가능).
- `pqueue_remove(q, d)` 함수로 특정 포인터를 직접 큐에서 제거 가능.
- **중요**: `victim_line_get_pri()`가 호출마다 다른(무작위) 값을 리턴하면 힙 불변식이 깨짐. 따라서 **Random 정책은 get_pri를 무작위화하는 방식이 아니라, `select_victim_line()`에서 별도 분기로 `q->d[]`에서 무작위 인덱스를 뽑고 `pqueue_remove()`로 꺼내는 방식**이 맞다고 판단함 (이 방향으로 구현 원함, 다른 더 나은 방법 있으면 제안 환영).
- ~~Cost-Benefit은 `victim_line_get_pri()`의 계산식만 바꾸면 됨 (힙 전제에 위배 안 됨).~~ → **틀린 가정이었음 (2026-07-24 설계 검증 중 발견)**. `get_pri()`만 바꾸면 `mark_page_invalid()`의 `pqueue_change_priority(pq, line->vpc-1, line)` 호출이 깨짐 — 이 함수는 `old_pri`(get_pri로 계산한 옛 값)와 `new_pri`(호출부가 직접 넘기는 raw vpc값)의 **단위가 같다는 전제** 하에서만 힙 방향(bubble_up/percolate_down)을 올바르게 고름. get_pri가 vpc가 아닌 파생 점수를 계산하면 이 전제가 깨져서, 힙이 스스로 복구 안 되는 상태로 틀어질 수 있음. → `mark_page_invalid()`의 해당 호출을 `pqueue_remove()` + `line->vpc--` + `pqueue_insert()`로 교체해서 해결 (이 두 함수는 항상 그 자리에서 `get_pri()`를 새로 부르기 때문에 계산식이 뭐든 항상 안전). 그 외에도 vpc==0일 때 나눗셈(커널 패닉 위험), min-heap이라 값을 뒤집어야 하는 문제까지 총 3개를 찾아서 고침 — 자세한 내용은 "진행 상황 (2026-07-24 기준)" 참고.

## 작업 순서 희망사항
1. Random 정책부터 구현 (가장 쉬움) → 로컬 빌드/insmod 테스트 — **완료 (2026-07-23)**
2. ~~서버에서 baseline+Random 벤치마크 파이프라인 먼저 검증~~ → **변경**: Cost-Benefit까지 끝낸 다음 세 정책을 한 번에 서버에서 검증/벤치마크하는 걸로 결정함 (2026-07-23)
3. Cost-Benefit 구현 (가장 오래 걸릴 것으로 예상) → 로컬 테스트 — **완료 (2026-07-24)**
4. 서버에서 세 정책 모두 벤치마크, 결과 수집 (아래 "서버 벤치마크 전 남은 작업" 참고) — **지금부터 시작 가능**
5. 그래프 + 보고서 작성

### 서버 벤치마크 전 남은 작업 (2026-07-23 작성, 2026-07-27 갱신)
Random·Cost-Benefit 모두 코드 구현 + 로컬에서 "의도대로 동작하는지" 검증까지는 끝났지만, 그건 기능 검증이지 본 벤치마크가 아님. 서버로 넘어가기 전 아래를 같이 준비해야 함:
1. **서버 환경 자체 재확인 — 진행 중 (2026-07-28)**: SSH 접속 성공(`ssh hjyoo@147.46.241.107 -p 220`, 비밀번호 인증, VPN 불필요 — 7/27 타임아웃은 사용자명 문제였던 것으로 추정). 저장소 클론 완료(`~/nvmevirt`), 로컬에 밀려있던 미푸시 커밋(`c194a5d`) push 후 서버에서 pull 완료. `Kbuild`에서 `CONFIG_NVMEVIRT_SSD` 확인됨. `make` 빌드 성공 — 서버 gcc(15.2.0, gcc-12는 미설치)/커널(6.18.0-9-generic) 조합에서도 에러 없음. **아직 남은 것**: `/proc/cmdline` 실측 결과 memmap 파라미터가 기존 기록과 달라서(위 "개발 환경" 섹션 참고) 조교 확인 대기 중 — insmod는 아직 안 함. 확인 후 insmod → "작은 memmap일 때 용량 4배 부풀림" 현상이 이 서버(48G)에서도 있는지 재확인 필요.
2. ~~**Latency 측정 방법론 설계**~~ → **완료 (2026-07-26/27)**: `run_experiment.sh`가 fio를 `--output-format=json`으로 실행하고, `collect_summary.sh`가 `fio.json`의 `write.lat_ns.mean`(IO AVG)과 `write.clat_ns.percentile["99.000000"]`(p99 tail latency)를 jq로 추출해서 CSV에 포함함. 실습 과제의 "호스트 IO AVG, Tail Latency" 요구사항이 이 두 값으로 충족됨.
3. ~~**재현 가능한 실험 설계**~~ → **완료 (2026-07-27)**: 아래 5번 항목의 mkfs 문제에 더해, **정책 비교 시 정책마다 모듈을 완전히 리로드(`rmmod`→`insmod`)해야 한다**는 게 새로 밝혀짐 — `mkfs`는 파일시스템만 초기화하고 FTL 내부 상태(`cb_clock`, write pointer, free line list)는 안 지우기 때문. 최종 절차: 정책마다 `umount→rmmod→insmod(해당 gc_policy로)→run_experiment.sh`. 자세한 경위는 EXPERIMENT_LOG.md 2026-07-27 항목 참고.
4. ~~**결과 저장 파이프라인**~~ → **완료 (2026-07-26)**: `scripts/run_experiment.sh <policy> <label> [workload]` (정책 전환→umount/mkfs/mount→reset→fio json 출력→erase_cnt 덤프→summary 생성까지 한 번에) + `scripts/collect_summary.sh` (`results/` 전체를 CSV로 집계, latency는 fio json에서 jq로 추출)로 구현. 로컬 컴퓨터에서 Greedy로 1회 실측 검증 완료(`results/20260726_220135_policy0_greedy_pipelinetest`), 파일 4종(`fio.json`/`erase_cnt.txt`/`meta.txt`/`summary.txt`) 정상 생성 및 집계 확인. **2026-07-27 업데이트**: `workload` 파라미터(uniform/hotcold) 추가, 매 실행마다 `umount→mkfs→mount→chown`으로 완전히 새 파일시스템에서 시작하도록 변경(아래 5번과 연계).
5. ~~**모듈 리로드해도 SSD 파일 데이터가 안 지워지는 문제 반영**~~ → **완료 (2026-07-27)**: "매번 mkfs로 완전히 새로 시작"으로 확정. `run_experiment.sh`가 매 실행마다 자동으로 `umount→mkfs→mount→chown`을 수행하도록 구현함. (단, mkfs만으로는 FTL 내부 상태까지 리셋되지 않는다는 게 3번 항목에서 새로 밝혀졌으므로, 정책 비교에는 mkfs + 모듈 완전 리로드가 둘 다 필요함.)
6. ~~**워크로드 다양성**~~ → **완료 (2026-07-27)**: `scripts/workloads/hotcold.fio` 신설. v1(콜드파일 1회 쓰기 + 핫파일 반복 쓰기, stonewall)은 콜드 라인이 GC 후보 풀에 아예 안 들어가는 설계 결함이 있어서 폐기, 최종적으로 단일 파일 + `random_distribution=zoned:60/20:40/80`(쓰기의 60%가 파일 앞 20%에 몰림) 방식의 v3로 정착. 자세한 시행착오(v1→v2→v3, printk로 근본 원인 규명)는 EXPERIMENT_LOG.md 2026-07-27 항목 참고. **결론(중요, 리포트에 반영할 것)**: 핫/콜드 스큐를 줘도 로컬 VM 스케일에서는 Greedy와 Cost-Benefit의 erase 총량/최대 마모가 거의 수렴함 — Cost-Benefit이 개별 victim 선택은 다르게 하지만(printk로 확인) 총량 지표엔 잘 안 드러나는 것으로 실측 확인됨. latency 쪽에서 약간의 차이가 보였으나 반복측정 안 해서 노이즈인지 실제 경향인지는 미확정.

## 안전 관련 주의사항
- 커널 모듈이므로 잘못된 코드는 커널 패닉/VM 프리징을 일으킬 수 있음. **큰 변경 전에는 VM 스냅샷을 권장.**
- `insmod` 실패 시 `dmesg`로 에러 로그 확인하는 법을 안내해줄 것.

## 벤치마크 도구 셋업 (fio / filebench)
전제: `nvmev` 모듈 로드 후 `/dev/nvme0n1`이 존재해야 함.
**주의 (2026-07-29)**: 이 디바이스명은 로컬 VM 기준(디스크가 NVMeVirt 하나뿐이라 nvme0n1). **서버는 부팅용 NVMe가 이미 nvme0n1을 쓰고 있어서 NVMeVirt 가상 디바이스가 `/dev/nvme1n1`로 잡힘** — 서버에서 아래 명령들을 쓸 때는 항상 `/dev/nvme1n1`로 바꿔 쓸 것 (새 환경에서는 `lsblk`로 먼저 확인).

### 1. 디스크 포맷 & 마운트 (최초 1회만 mkfs, 이후엔 mount만)
```
sudo mkfs -t ext4 /dev/nvme0n1        # 최초 1회만, 기존 데이터 지워짐 주의
sudo mount /dev/nvme0n1 ~/nvme_mount  # insmod 할 때마다 재실행
sudo chown $USER:$USER ~/nvme_mount   # root 소유로 마운트되므로 필요
```
로컬 VM 기준 실사용 가능 용량은 약 859M (전체 923M 중 ext4 오버헤드 제외, `memmap_size=1G` 설정 기준). 벤치마크 파일 크기 잡을 때 이 한도 고려할 것.

### 2. fio (apt로 설치 가능)
```
sudo apt install fio
fio --name=test --filename=$HOME/nvme_mount/testfile \
    --size=100M --rw=write --bs=4k --numjobs=1 --iodepth=16 \
    --ioengine=libaio --direct=1 --group_reporting
```
`--rw=write`(순차) / `--rw=randwrite`(랜덤)로 패턴 변경. 랜덤 쓰기가 GC를 더 유발시켜서 실제 정책 비교에 의미 있음.

**주의 (2026-07-24 발견)**: `--filename=` 옵션 뒤의 `~`는 bash가 자동으로 홈 디렉토리로 안 바꿔줌 (단어 맨 앞이나 `VAR=~/...` 순수 대입문일 때만 적용되는 규칙이라 `--filename=~/...` 형태는 해당 안 됨). `~`를 문자 그대로 받아서 현재 작업 디렉토리 밑에 `~`라는 이름의 폴더를 만들고 그 안에 씀 — 가상 SSD는 전혀 안 건드리고 fio는 "성공"으로 보고해서 눈치채기 어려움. 항상 `$HOME`이나 절대경로를 쓸 것.

### 3. filebench (apt 저장소에 없어서 소스 빌드 필요)
```
sudo apt install -y autoconf automake libtool bison flex libtool-bin build-essential git
git clone https://github.com/filebench/filebench.git ~/filebench   # nvmevirt 저장소 밖에! (nested git repo 방지)
cd ~/filebench
libtoolize && aclocal && autoheader && automake --add-missing && autoconf
./configure
make
sudo make install   # /usr/local/bin/filebench 로 설치
```

**ASLR 끄기 (매번 재부팅 후 다시 해야 함, 커널 기본값 2):**
```
echo 0 | sudo tee /proc/sys/kernel/randomize_va_space
```
안 끄면 filebench 멀티프로세스 공유메모리가 깨지면서 `Unexpected Process termination` 에러 발생.

**동작 검증용 스모크 테스트 스크립트** (`smoketest.f`):
```
set $dir=~/nvme_mount
set $bytes=20m
set $filesize=50m
set $iosize=4k
set $nthreads=1

define file name=bigfile1,path=$dir,size=$filesize,prealloc,reuse

define process name=filewriter,instances=1
{
  thread name=filewriterthread,memsize=10m,instances=$nthreads
  {
    flowop write name=write-file,filename=bigfile1,random,iosize=$iosize
    flowop finishonbytes name=finish,value=$bytes
  }
}

run 5
```
실행: `filebench -f smoketest.f`

**주의사항 정리:**
- `define fileset` + `createfile` 조합은 fileset 엔트리 개수만큼만 쓸 수 있음 (파일 적으면 금방 `could not obtain a file` 에러). 지속 쓰기 테스트엔 `define file`(단일 파일) + `write`가 적합.
- `write` flowop에 `finishonbytes`로 총량 제한을 안 걸면, NVMeVirt가 DRAM 기반이라 매우 빨라서(초당 수백MB) 마운트 공간을 순식간에 다 채움 (`No space left on device`).
- `WARNING! Run stopped early ... could not obtain a file` 메시지가 `finishonbytes` 도달 시에도 뜰 수 있음 — 목표 바이트 도달로 인한 정상 종료일 수 있으니 대상 파일 크기로 실제 실패 여부 확인.


## GC 정책 실험용 커맨드 레퍼런스

conv_ftl.c 수정 후 재실험할 때 반복하는 명령어 모음.

### 1. 모듈 리로드 사이클 (conv_ftl.c 등 커널 모듈 코드를 고쳤을 때만 필요)
```
sudo umount ~/nvme_mount
sudo rmmod nvmev
make                                    # Kbuild가 CONFIG_NVMEVIRT_SSD := y 인지 확인할 것
sudo insmod ./nvmev.ko memmap_start=2G memmap_size=1G cpus=2,3   # 로컬 VM 값. 서버는 memmap_start=16G memmap_size=48G cpus=7,8 (2026-07-28 확정, 위 "개발 환경" 섹션 참고)
sudo mount /dev/nvme0n1 ~/nvme_mount
sudo chown $USER:$USER ~/nvme_mount
```
로드 후 확인: `lsmod | grep nvmev`, `ls /dev/nvme0n1`
**주의**: 리로드하면 `gc_policy`가 기본값(0=Greedy)으로 돌아가고 `erase_cnt`도 전부 0으로 초기화됨 — 재실험 시작 전 2번/4번 다시 확인할 것.

**⚠️ 중요 (2026-07-27 발견): 정책 간 비교 실험에서는 정책마다 반드시 이 모듈 리로드 사이클을 처음부터 다시 거칠 것.** `mkfs`만 다시 해서는 부족함 — `cb_clock`(Cost-Benefit용 논리 시계), write pointer, free line list 같은 FTL 내부 상태는 `mkfs`로 안 지워지고 오직 `rmmod`→`insmod`로만 초기화됨. `gc_policy`를 sysfs로만 바꿔가며 이어서 실행하면, 뒤에 도는 정책이 앞 정책이 남긴 물리 상태를 그대로 물려받아 비교가 오염됨 (실제로 이 문제 때문에 첫 3정책 비교 결과가 무효 판정됨, EXPERIMENT_LOG.md 2026-07-27 참고). `insmod` 시 `gc_policy=<N>` 파라미터로 바로 원하는 정책을 줄 수 있음(§2 참고). **2026-07-31부터는 `gc_policy`를 아예 런타임 읽기 전용으로 막아서 이 실수 자체가 불가능해졌지만**(§2 참고), 왜 리로드가 필요한지는 알아둘 것.

**업데이트 (2026-07-29)**: `scripts/run_experiment.sh`가 이 rmmod→insmod(gc_policy 지정)→mkfs→mount 전체를 매 실행마다 자동으로 수행하도록 수정됨 (이전 버전은 sysfs 전환 + mkfs만 했음 — 위 오염 문제가 스크립트 자체에도 남아있던 것을 뒤늦게 발견/수정함). 디바이스 경로와 insmod 파라미터는 `NVME_DEV`/`MEMMAP_START`/`MEMMAP_SIZE`/`NVME_CPUS` 환경변수로 오버라이드 가능 (기본값은 로컬 VM 기준). 서버 실행 예시:
```
NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
  ./scripts/run_experiment.sh 0 randwrite6g uniform
```

**주의 (2026-07-24 발견)**: rmmod→insmod로 모듈을 리로드해도 `~/nvme_mount` 안의 파일(ext4 파일시스템 자체, 실제 파일 데이터)은 그대로 남아있음 — `erase_cnt` 같은 FTL 내부 통계(커널 힙에 매번 새로 할당됨)만 초기화되고, `memmap=`으로 예약된 물리 메모리 영역의 실제 바이트는 module reload로 지워지지 않는 것으로 보임. 정책 간 완전히 깨끗한 상태에서 비교하려면 리로드만으로는 부족하고 `mkfs`를 다시 해야 할 수도 있음 — 최종 벤치마크 설계 시 확인 필요.

### 2. GC victim 정책 지정/확인 (지정은 insmod 시점에만 가능)
```
sudo insmod ./nvmev.ko memmap_start=... memmap_size=... cpus=... gc_policy=2   # 정책 지정
cat /sys/module/nvmev/parameters/gc_policy      # 현재 정책 확인 (0=Greedy, 1=Random, 2=Cost-Benefit)
```
**`gc_policy`는 2026-07-31부터 런타임 읽기 전용(`module_param(..., 0444)`)임** — 예전처럼 `echo 1 | sudo tee /sys/module/nvmev/parameters/gc_policy`로 바꾸는 건 이제 `Permission denied`로 막힘. 읽기(`cat`)는 그대로 됨. 정책을 바꾸려면 §1의 모듈 리로드 사이클을 거쳐야 하고, `run_experiment.sh`는 이미 그렇게 동작함.

읽기 전용으로 막은 이유 2가지:
- **측정 오염 (2026-07-27 발견)**: 정책만 바꿔 이어서 돌리면 앞 정책이 남긴 FTL 내부 상태(`cb_clock`, write pointer, free line list, 각 line의 valid/invalid 분포)를 그대로 물려받아 비교가 오염됨 — 실제로 이것 때문에 첫 3정책 비교 결과가 통째로 무효 판정됨.
- **정확성 자체가 깨짐 (2026-07-31 발견)**: Cost-Benefit으로 동작하는 동안 victim 힙은 CB 우선순위(`(ipc*age)/(2*vpc)`)로 정렬돼 있음. 여기서 Greedy로 바꾸면 Greedy는 `pqueue_pop()`으로 힙의 root를 그대로 신뢰하는데, 그 root는 min-vpc line이 아니라 CB 기준 1등임 → **Greedy가 에러 없이 조용히 잘못된 victim을 고르게 되고, 힙이 스스로 복구되지도 않음.** (반대 방향인 Greedy → CB는 CB가 매번 전체 스캔을 하므로 원래 안전했지만, 위 오염 문제는 여전히 있어서 양방향 다 막는 게 맞다고 판단함.)

### 3. GC를 실제로 유발시키는 랜덤 쓰기 부하 (스모크/스트레스 테스트용)
같은 영역을 여러 번 덮어써서 invalid page를 계속 만들어야 GC가 트리거됨. 파일 크기보다 큰 총 쓰기량을 줘야 함.
```
fio --name=gc_stress --filename=$HOME/nvme_mount/testfile2 --size=600M --rw=randwrite \
    --bs=4k --numjobs=1 --iodepth=16 --ioengine=libaio --direct=1 --loops=10 --group_reporting
```
(600MB 파일에 6GB어치 랜덤 쓰기 = 10바퀴 덮어씀)

**로컬 VM 전용 주의사항**: `memmap_size=1G`처럼 작게 잡으면 `ssd_init_params()`의 block 크기 반올림(`BLKS_PER_PLN=8192`가 고정값이라 목표 block 크기가 `ONESHOT_PAGE_SIZE`(32KB)보다 작을 때 32KB로 올림) 때문에 **FTL이 내부적으로 인식하는 용량이 실제 물리 메모리의 약 4배로 부풀려짐** (로컬 VM 1GB memmap → 파티션당 명목 용량 1GB × 4파티션 = 4GB). 그래서 실제 디스크 용량(~923M)의 2~3배를 써도 GC가 전혀 안 돌 수 있음 — 최소 6GB 이상 누적으로 덮어써야 확실히 트리거됨 (2.4GB로는 GC 0회, 6GB로는 확실히 발생 확인함, 2026-07-23). 서버처럼 memmap이 큰 환경(36G)에서는 목표 block 크기가 32KB보다 커서 이 반올림 문제가 없을 것으로 예상 — 서버에서도 GC 트리거 여부 재확인 필요.

### 4. erase_cnt 확인 / 리셋
```
cat /proc/nvmev/debug | head              # ns part ch lun pl blk erase_cnt, 한 줄에 한 block (로컬 VM 기준 131072줄)
echo reset | sudo tee /proc/nvmev/debug   # 모든 block의 erase_cnt를 0으로 초기화 (벤치마크 시작 전 실행)
```
간단 통계 뽑기 예시:
```
awk 'NF==7 && $7!=0{sum+=$7; n++; if($7>max) max=$7} END {print "nonzero_blocks="n, "sum="sum, "max="max}' /proc/nvmev/debug
```
**`NF==7` 가드 필수 (2026-07-31 발견)**: `/proc/nvmev/debug` 출력 맨 앞의 헤더 줄들(`GC_VALID_PAGE_MIGRATE_CNT`, `DIAG_*`)은 필드가 2개뿐이라 `$7`이 uninitialized인데, **mawk는 이를 문자열 `""`로 취급해 `"" != 0`을 참으로 평가**함 → 가드가 없으면 헤더 줄 개수만큼 `nonzero_blocks`가 부풀려짐(`sum`/`max`는 영향 없음).

---

## 진행 상황 (2026-07-23 기준)
- 로컬 VM: `nvmev` 모듈 로드됨, `/dev/nvme0n1` ext4 포맷 + `~/nvme_mount` 마운트 완료
- fio 설치 완료, 순차/랜덤 쓰기 테스트로 I/O 정상 동작 확인
- filebench 소스 빌드 + 설치 완료 (`~/filebench`에 클론, `/usr/local/bin/filebench`), ASLR 끄고 스모크 테스트로 정상 동작 확인
- Kbuild가 `CONFIG_NVMEVIRT_ZNS`로 잘못 설정돼있던 걸 `CONFIG_NVMEVIRT_SSD`로 수정함 (안 그러면 conv_ftl.c가 빌드에서 아예 빠짐)
- Random GC 정책 구현 완료 (`conv_ftl.c`, `gc_policy` module_param + `select_victim_line()` 분기), 로컬 VM에서 실측으로 Greedy 대비 erase가 훨씬 고르게 분산되는 것까지 확인함 (아래 erase_cnt 항목 참고)
- Cost-Benefit GC 정책: 아직 미착수
- erase_cnt 측정용 `/proc/nvmev/debug` 인터페이스 구현 완료 (dump + reset). 로컬 VM 6GB 랜덤쓰기 기준 Greedy(19424 block, sum 157136, max 9) vs Random(103988 block, sum 192060, max 6) 비교 결과 확보 — 커맨드는 위 "GC 정책 실험용 커맨드 레퍼런스" 참고. **⚠️ 2026-07-24 확인: 이 Greedy 수치는 재현 안 됨 (아래 7/24 항목 참고), 신뢰도 낮음 — 새 기준선은 7/24의 `19280/61008/4`.**
- 서버(147.46.241.107)에 filebench 설치 여부: 아직 미확인, GC 정책별 실측 벤치마크(erase count + latency)는 아직 서버에서 안 돌림

## 진행 상황 (2026-07-24 기준)
- **fio 명령어 버그 발견/수정**: `--filename=~/nvme_mount/...`에서 `~`가 `=` 뒤에 오면 bash가 확장을 안 해줌(단어 맨 앞/순수 대입문에서만 적용되는 규칙). 실제로는 가상 SSD가 아니라 `nvmevirt` 프로젝트 폴더 밑에 잘못된 경로(`nvmevirt/~/nvme_mount/...`)로 600MB가 쓰였던 것을 발견. fio는 "성공"으로 보고해서 눈치채기 어려웠음 (`Disk stats`에 `nvme0n1` 대신 `sda`로 찍히는 게 단서). CLAUDE.md의 fio 예제 2곳을 `$HOME` 사용으로 수정 완료, 잘못 쓰인 파일도 정리함.
- **Random 정책 재검증**: 수정된 명령으로 재실험 (`erase_cnt` reset 후 6GB 랜덤쓰기), `nonzero_blocks≈106592, sum≈192112, max=6` — 7/23 기록과 유사한 패턴으로 정상 동작 재확인.
- **실험 설계 이슈 발견**: `erase_cnt` reset은 카운터만 0으로 만들 뿐 실제 매핑 테이블/valid page 상태는 초기화 안 됨. 정책 간 공정 비교를 위해선 정책 전환 시 매번 **모듈 리로드(fresh state)**부터 시작해야 함 — "재현 가능한 실험 설계" 항목에 구체적 조건으로 추가.
- **Cost-Benefit GC 정책 구현 완료**. 설계 단계에서 Plan 서브에이전트로 pqueue 라이브러리 상호작용을 교차검증해서 아래 3가지 문제를 미리 발견/해결함 (설계 문서: `~/.claude/plans/abstract-greeting-reddy.md`):
  - **힙 무결성 문제**: `mark_page_invalid()`가 `pqueue_change_priority(pq, line->vpc-1, line)`을 쓰는데, 이건 old_pri/new_pri가 같은 단위(원시 vpc)라는 전제 하에만 안전함. `get_pri()`가 cost-benefit 점수를 계산하도록 바꾸면 old_pri(점수)와 new_pri(원시 vpc)의 단위가 안 맞아 힙 방향을 잘못 고를 수 있고, 자체적으로 복구되지 않음 → `pqueue_remove()` + `line->vpc--` + `pqueue_insert()`로 교체해서 해결 (항상 `get_pri()`를 그 자리에서 새로 읽으므로 어떤 정책이든 안전).
  - **vpc==0 나눗셈 (커널 패닉 위험)**: line이 pqueue에 남아있는 채로 마지막 valid page가 invalidate되면 vpc가 0이 될 수 있음 → `get_pri()`에서 vpc==0이면 나눗셈 없이 바로 0(최선의 victim) 리턴하도록 가드.
  - **min-heap 방향 문제**: pqueue는 min-heap이라 작은 값이 먼저 뽑히는데, cost-benefit 점수는 클수록 좋은 victim이라 그대로 쓰면 정반대로 동작함 → `CB_PRI_MAX - score`로 뒤집어서 리턴 (비교 함수 자체는 안 건드림 — `gc_policy`가 sysfs로 런타임 전환 가능해서 비교 함수까지 바꾸면 더 위험).
  - 구현: `conv_ftl.h`에 `struct line.mtime` 추가, `conv_ftl.c`에 전역 논리 시계 `cb_clock`(페이지 쓸 때마다 +1, `advance_write_pointer()`에서 증가) 추가, line이 닫힐 때 `mtime` 스탬프, `victim_line_get_pri()`에 `(ipc*age)/(2*vpc)` 계산식 분기 추가.
  - **검증**: 로컬 VM 빌드/insmod 성공, Greedy 회귀 테스트 통과(기존과 동일 패턴), Cost-Benefit 6GB 랜덤쓰기 테스트 크래시 없이 통과 (`nonzero_blocks=19428, sum=192000, max=10` vs Greedy `19280/61008/4` vs Random `~106592/~192112/6`). dmesg 이상 없음 확인.
  - **워크로드 관련 발견**: 균등 랜덤쓰기 워크로드에서는 Cost-Benefit이 Greedy처럼 좁은 블록 범위에 몰리면서도 마모(max)는 더 큼. 콜드 데이터 개념이 없는 워크로드라 Cost-Benefit의 장점이 잘 안 드러나는 것으로 추정 — 최종 벤치마크에는 핫/콜드가 섞인 워크로드 설계가 필요할 것으로 보임 (다음 작업 시 고려).
- **Greedy 재현성 검증**: 7/23 기록된 Greedy 수치(`157136/9`)와 오늘 잰 수치(`61008/4`)가 2.5배 넘게 차이나서, "Greedy도 어차피 매번 다르게 나오는 거 아니냐"는 질문이 나옴 → 실제로 확인해보기로 함. Greedy는 victim 선택에 난수가 전혀 없고(vpc 최솟값을 그냥 고름) fio도 기본 `randrepeat=1`이라 매번 같은 순서로 씀 — 그래서 이론상 완전히 결정론적이어야 함. **모듈을 리로드해서 완전히 새 상태로 만든 뒤 같은 조건(정책 Greedy, reset 직후, 동일 fio 커맨드)으로 두 번 연속 실행 → 두 번 다 정확히 `nonzero_blocks=19280, sum=61008, max=4`로 완전히 일치** (아까 첫 측정값까지 합치면 3회 연속 동일). 결론: **Greedy는 실제로 완벽하게 재현됨**, "매번 다르게 나오는 게 당연하다"는 가정은 틀렸고, 7/23 수치 쪽이 오히려 이상값(측정 당시 뭔가 통제 안 된 조건이 있었을 가능성 — reset 타이밍 또는 파일이 새로 쓰이는 상태였는지 여부 등, 정확한 원인은 미확정). **오늘 값(`19280/61008/4`)을 새로운 Greedy 기준선으로 채택.**

## 진행 상황 (2026-07-26 기준, 집 컴퓨터로 첫 작업)
- **환경 전환**: 이번 주말부터 집 컴퓨터에서 작업 시작 (평일엔 연구실 컴퓨터). `git pull` 시 origin에 이미 12개 커밋(`CLAUDE.md`/`EXPERIMENT_LOG.md` 최초 추가, Cost-Benefit 관련 등)이 들어와 있었고, 로컬엔 `main.c`에 의미 없는 빈 줄 하나만 있던 상태라 그 변경은 버리고(`git checkout -- main.c`) fast-forward pull 진행함 — CLAUDE.md에 이미 적혀 있던 "여러 환경에서 건드리면 동기화 어긋날 수 있다"는 경고가 실제로 재현된 사례.
- **집 컴퓨터 환경 차이 2건 발견** (연구실 VM과 컨셉은 같지만 별도 프로비저닝이라 발생):
  1. `fio`가 아예 설치 안 되어 있었음 → `sudo apt install -y fio`로 설치.
  2. 모듈 리로드 1단계(umount→rmmod→make→insmod→mount) 도중 `mount`가 `wrong fs type, bad option, bad superblock` 에러로 실패함. 원인은 VM 자체를 껐다 켜서(재부팅) `memmap=`으로 예약된 DRAM 영역 내용이 통째로 날아갔기 때문 — 7/24에 확인했던 "모듈 리로드만으론 데이터 안 지워짐"은 OS가 안 꺼진 상태 한정이고, **VM 재부팅은 그 전제를 깨서 `mkfs`부터 다시 해야 함**. `sudo mkfs -t ext4 /dev/nvme0n1` 재실행으로 해결.
  - 이 두 가지 모두 "새 환경/새 패키지 설치가 필요했던 경우 반드시 기록한다"는 사용자 요청에 따라 여기 남김. 앞으로도 이런 환경 차이가 나오면 바로 기록할 것.
- **결과 저장 파이프라인 구현 완료** (`scripts/run_experiment.sh`, `scripts/collect_summary.sh`, `results/` 디렉토리) — 자세한 사용법은 위 "서버 벤치마크 전 남은 작업" 4번, 실제 사용 예시/발견 사항은 `EXPERIMENT_LOG.md` 참고.
- **mkfs 조건에 따른 차이 재확인**: 위 2번 사고로 어쩔 수 없이 "fresh mkfs 직후 첫 쓰기" 조건에서 Greedy를 재보게 됨 (`19520/62176/4`) — 7/24 "파일 재사용" 조건 기준선(`19280/61008/4`)과 max만 일치하고 나머지는 다름. "서버 벤치마크 전 남은 작업" 5번 항목에 반영함.
- **세 정책 첫 동일조건 비교** (같은 세션, fresh mkfs 이후 `gc_policy` sysfs 전환만으로 연속 실행 — 모듈 리로드는 안 했음): Greedy `19520/62176/4`, Random `106976/192084/6`, Cost-Benefit `19596/192004/10`. erase max가 Greedy < Random < Cost-Benefit 순으로 나와서, 7/24에 봤던 "균등 랜덤쓰기(콜드 데이터 없음)에서는 Cost-Benefit이 오히려 마모가 더 몰린다"는 관찰이 재현됨 — 최종 결론 내리려면 핫/콜드 혼합 워크로드 필요(아래 "서버 벤치마크 전 남은 작업" 6번). Latency는 avg/p99 모두 Random이 가장 낮고 Greedy가 가장 높았지만, 이번 실행은 정책 간 리로드 없이 이어서 잰 거라 매핑 테이블 상태가 정책마다 다를 수 있어 이 latency 수치만으론 정책 간 우열을 단정하지 않기로 함. 자세한 표는 `EXPERIMENT_LOG.md` 2026-07-26 22:07~22:12 항목 참고. **→ 2026-07-27에 이 "모듈 리로드 없이 이어서 실행" 방식 자체가 방법론적 문제였다는 게 밝혀짐 (아래 참고).**

## 진행 상황 (2026-07-27 기준)
- **`hotcold.fio` 워크로드 신설 및 시행착오 (v1→v2→v3)**: 핫/콜드 혼합 워크로드를 처음 설계(v1: 콜드파일 500M 1회 쓰기 + 핫파일 반복 랜덤쓰기, stonewall)해서 3정책을 비교했더니 Greedy와 Cost-Benefit의 erase 통계가 거의 동일하게 나옴. `victim_line_get_pri()`에 임시로 샘플링 printk(500회마다 1번, `vpc/ipc/mtime/cb_clock/age/bc` 출력)를 추가해서 원인을 세 차례에 걸쳐 실측으로 규명함:
  1. v1: 콜드파일을 다시 안 건드리면 그 line들은 100% valid로 남아 `full_line_list`에만 머물고 victim pqueue엔 아예 안 들어감 → CB가 age를 계산할 후보 자체가 전부 "핫" line뿐이라 age 편차가 거의 없었음(실측 변동폭 약 1%). → 단일 파일 + `random_distribution=zoned`로 접근 빈도 자체를 스큐하는 v2로 재설계.
  2. v2(`zoned:80/10:20/90`): age는 실제로 크게 벌어졌지만(150배 차이) 여전히 erase_sum/max가 동일. vpc 분포를 보니 vpc=1~6인 후보가 전체 샘플의 46%를 차지 — 스큐가 너무 강해서 "거의 다 무효화된" 후보가 항상 대기 중이었고, `bc=ipc*age/(2*vpc)` 수식상 vpc가 작으면 age가 아무리 벌어져도 못 따라잡음. → 스큐를 완화한 v3로 재설계.
  3. v3(`zoned:60/20:40/80`): vpc 분포가 실제로 넓게 퍼졌음에도(vpc=1 샘플이 194→41개로 감소) erase_sum/max는 여전히 Greedy와 CB가 동일(`62084/4`로 완전히 같음). nonzero_blocks는 조금 더 벌어짐(25260 vs 25272) — CB가 실제로 다른 구체적 블록을 고르지만 총 erase 횟수/최대 마모는 결국 수렴한다는 결론.
  - **최종 결론 (버그 아님, 실측 확인된 현상)**: 이 스케일/워크로드에서는 Cost-Benefit이 개별 victim 선택을 Greedy와 다르게 하는 게 맞지만(printk로 직접 확인), 총 erase 지표(write amplification)에는 잘 안 드러남. 이건 리포트에서 다룰 만한 정직한 분석 포인트임.
  - 진단용 printk는 최종적으로 제거하고 원본 상태로 재빌드함 (`git diff conv_ftl.c` 없음 확인).
- **모듈 리로드 없이 정책만 전환하는 방식의 위험성 발견**: 위 v1 조사 도중, 애초에 첫 3정책 비교(11:26~11:29, `gc_policy`만 sysfs로 바꿔가며 연속 실행)가 방법론적으로 오염돼 있었다는 것도 같이 밝혀짐 — `mkfs`는 파일시스템만 초기화하고 `cb_clock`/write pointer/free line list 같은 FTL 내부 상태는 안 지움(오직 모듈 완전 리로드만 초기화함). 완전 리로드 직후 CB만 단독 실행한 결과(`1680/78032/47`)가 이어서 실행했던 기존 CB 결과(`18340/208484/105`)와 크게 달라서 확인됨. **이후 모든 정책 비교는 정책마다 모듈을 완전히 리로드하는 절차로 통일함** (§1 "모듈 리로드 사이클"에 경고 추가).
- **최종 3정책 비교 (hotcold v3, 완전 리로드, printk 없는 클린 빌드)**:

  | 정책 | nonzero_blocks | erase sum | erase max | lat avg(μs) | lat p99(μs) |
  |---|---|---|---|---|---|
  | Greedy | 25260 | 62084 | 4 | 92.9 | 197.6 |
  | Random | 52488 | 67208 | 5 | 107.1 | 250.9 |
  | Cost-Benefit | 25272 | 62084 | 4 | 89.0 | 216.1 |

  Latency는 avg/p99에서 Greedy와 CB 우열이 엇갈리고, 직전 실행(printk 오버헤드 있던 상태)과 비교해도 p99가 뒤바뀜 — 반복측정을 안 해서 노이즈인지 실제 경향인지 미확정. 사용자 판단으로 반복측정은 생략하고 서버 벤치마크로 넘어가기로 함.
- **서버 접속 시도, 미해결**: `ssh -p 220 <?>@147.46.241.107`을 로컬 VM에서 시도했으나 연결 타임아웃. 사용자명/VPN 필요 여부/인증 방식(비밀번호 vs 키) 확인이 필요한 상태 — 다음 세션에서 이어서 진행할 것. 지금까지 서버 관련 작업(§1의 `memmap_start=12G memmap_size=36G cpus=14,15`)은 전부 미검증 상태임을 유의.
- **다음 할 일**: 서버 환경 확인(Kbuild, 빌드, 용량 부풀림 현상 재확인) → 서버에서 오늘 확정한 절차(정책마다 완전 리로드, uniform+hotcold 워크로드)로 최종 벤치마크 → `collect_summary.sh`로 CSV 집계 → 그래프 작성 → 보고서 작성 → 제출(hslee@davinci.snu.ac.kr, 7/31까지).

## 진행 상황 (2026-07-28 기준)
- **서버 SSH 접속 성공, 7/27 블로커 해결**: `ssh hjyoo@147.46.241.107 -p 220` + 비밀번호 인증으로 바로 접속됨 (VPN 불필요). 7/27 타임아웃은 사용자명을 몰라서 생긴 문제였던 것으로 추정(원인 확정은 안 함). 호스트네임 `Z690-AORUS-ELITE-AX-DDR4`.
- **서버 빌드 환경 확인**: gcc 15.2.0(Ubuntu 15.2.0-11ubuntu1), `gcc-12`는 미설치. 커널 `6.18.0-9-generic`, 빌드 헤더는 `/lib/modules/6.18.0-9-generic/build`에 정상 존재.
- **저장소 동기화 문제 재발 및 해결**: 서버에 `~/nvmevirt`를 새로 클론했더니 `b4c8c4f`(7/26 커밋)까지만 있었음 — 로컬(연구실/집 컴퓨터)에서 만든 최신 커밋 `c194a5d`(7/27 hotcold v3 재설계 + cross-policy 오염 수정)가 origin에 안 올라가 있었던 것. `git push`로 반영 후 서버에서 `git pull`. CLAUDE.md에 이미 있던 "여러 환경에서 작업 시 동기화 확인" 경고가 또 재현된 사례 — **앞으로 서버 작업 시작 전엔 로컬에서 먼저 unpushed 커밋 있는지(`git log origin/main..HEAD`) 확인하는 습관 들일 것.**
- **서버 빌드 성공**: `Kbuild`에서 `CONFIG_NVMEVIRT_SSD` 확인, `make` 에러 없이 빌드됨 — gcc 15 + 커널 6.18 조합에서도 문제 없었음 (gcc-12가 필수는 아니었던 것으로 보임).
- **서버 부팅 파라미터가 기존 기록과 다름 (해결됨)**: `/proc/cmdline` 확인 결과 `memmap=48G$16G isolcpus=7,8` — CLAUDE.md에 예전부터 적혀있던 `memmap_start=12G memmap_size=36G cpus=14,15`와 불일치해서 발견 당시엔 조교 확인이 필요하다고 판단했음. 이후 사용자가 확인한 **실습 방법 자료**에 `sudo insmod ... memmap_start=16G memmap_size=48G cpus=7,8`로 명시되어 있는 걸 발견 — 실측 `/proc/cmdline`과 정확히 일치해서 확정. (기존 CLAUDE.md의 12G/36G/14,15 값은 PPT 자료 쪽 값으로 추정되며, 이 서버에는 안 맞는 값이었던 것으로 결론.)
- **다음 할 일**: 확정된 파라미터(`memmap_start=16G memmap_size=48G cpus=7,8`)로 insmod → `/dev/nvme0n1` 생성 확인 → mkfs/mount → 용량 부풀림 현상 재확인(48G memmap이면 이론상 안 나타나야 함) → 정책 3종 완전 리로드 절차로 uniform+hotcold 벤치마크 → CSV 집계 → 그래프/보고서.

## 진행 상황 (2026-07-29 기준)
- **서버 insmod 성공**: 확정된 파라미터(`memmap_start=16G memmap_size=48G cpus=7,8`)로 insmod 성공.
- **서버 가상 디바이스는 `/dev/nvme0n1`이 아니라 `/dev/nvme1n1`임 (중요, 반복 주의).** 서버는 자체 부팅/시스템 NVMe가 이미 `/dev/nvme0n1`을 점유하고 있어서, NVMeVirt가 만드는 가상 디바이스는 그다음 번호인 `/dev/nvme1n1`로 잡힘. 로컬 VM(디스크가 NVMeVirt 하나뿐이라 `nvme0n1`)과 다른 부분이라 실수하기 쉬움 — **서버 관련 명령(mkfs/mount/fio --filename 등)은 항상 `/dev/nvme1n1` 기준으로 쓸 것.** 새 환경에서는 `lsblk`로 실제 디바이스명부터 먼저 확인하는 습관 들이기로 함.
- **용량 부풀림 현상 재확인 결과: 없음(정상)**. `lsblk`/`fdisk -l` 기준 원시 디바이스 용량이 48G memmap 대비 약 44G로 나옴 — 이는 GC용 over-provisioning(스페어 영역)으로 인한 정상적인 감소이며, 로컬 VM(1G memmap)에서 봤던 "block 크기가 32KB보다 작아 반올림되면서 용량이 4배로 뻥튀기되는" 문제와는 무관함 (그 문제는 반대 방향으로, 실제보다 커 보이는 현상이었음). 예상대로 큰 memmap(48G)에서는 목표 block 크기가 32KB보다 커서 반올림 문제가 재현되지 않음을 확인.
- **`scripts/run_experiment.sh` 버그 발견 및 수정**: 스크립트가 `/dev/nvme0n1`을 하드코딩하고 있었고(서버에서 그대로 쓰면 위 디바이스명 실수가 재발할 뻔함), 정책 전환도 `sysfs`로만 하고 모듈 완전 리로드를 안 하고 있었음(7/27에 발견했던 "정책 간 상태 오염" 문제가 스크립트 자체엔 반영이 안 돼 있었던 것). `NVME_DEV`/`MEMMAP_START`/`MEMMAP_SIZE`/`NVME_CPUS` 환경변수로 디바이스·insmod 파라미터를 오버라이드하도록 고치고, 매 실행마다 `umount→rmmod→insmod(gc_policy=N)→mkfs→mount`를 자동 수행하도록 수정 완료 (§"GC 정책 실험용 커맨드 레퍼런스" 참고).
- **서버 워크로드 총 쓰기량 재보정 (loops=10 → 250), 캘리브레이션 실측으로 확인**: 로컬 VM 기준으로 잡았던 `uniform` 워크로드의 `loops=10`(총 6GB 랜덤쓰기)을 서버(`NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8`)에서 그대로 돌려본 결과(`results/20260729_184907_policy0_greedy_randwrite6g`), `erase_cnt.txt`에 0이 아닌 블록이 단 하나도 없어서 **GC가 전혀 트리거되지 않음**을 확인함. 원인: 서버는 사용 가능 용량이 44.9GB로 로컬 VM(~923M)보다 훨씬 커서, 6GB는 용량의 13%밖에 안 채움. `loops=250`(총 ~146GB, 용량의 약 3.3배)으로 올려서 재실행(`results/20260729_185748_policy0_greedy_calibcheck`)한 결과 `nonzero_blocks=2024 sum=271620 max=161`로 GC가 확실히 여러 번 트리거됨을 확인 — 이 값을 새 캘리브레이션 기준으로 채택하고 `scripts/run_experiment.sh`(uniform)와 `scripts/workloads/hotcold.fio` 양쪽의 `loops`를 250으로 수정함.
  - **참고**: 이 계산 결과 `nonzero_blocks=2024`는 전체 블록(131072개, 총 블록 개수는 memmap 크기와 무관하게 채널/런/플레인 토폴로지로 고정됨)의 약 1.5%에 불과함 — 로컬 VM 6GB 테스트에서 봤던 ~15%보다 훨씬 낮은 비율. 이유는 서버 블록 하나 용량(~360KB)이 로컬(~32KB)보다 훨씬 커서, 600M 파일 하나를 담는 데 필요한 물리 블록 수 자체가 전체 용량 대비 작은 비중이기 때문 — GC가 그 작은 워킹셋 풀만 계속 재활용하는 것으로 보임(버그 아님). 정책 3종 비교 리포트에 "환경별 erase 분포 형태 차이"로 언급할 만한 포인트.
- **다음 할 일**: 서버에서 `NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 ./scripts/run_experiment.sh <policy> <label> [uniform|hotcold]`로 정책 3종 × 워크로드 2종 벤치마크 실행(캘리브레이션 완료로 바로 시작 가능) → `collect_summary.sh`로 CSV 집계 → 그래프/보고서 작성 → 제출(7/31 마감, hslee@davinci.snu.ac.kr).

## 진행 상황 (2026-07-30 기준)
- **Claude Code Bash 툴에서 sudo가 안 먹는 문제 발견 (중요, 운영 습관으로 굳힐 것)**: `run_experiment.sh`는 `umount/rmmod/insmod/mkfs/mount`에 sudo가 필요한데, Claude(나)가 Bash 툴로 직접 실행하면 `tty`가 없는 별도 non-interactive 세션이라 사용자가 자기 터미널에서 미리 해둔 `sudo -v` 캐시가 전혀 공유되지 않음 — 실제로 자동 실행 시도했다가 빈 입력으로 `sudo: Authentication failed`가 3연속 뜨며 실패함. **결론: `run_experiment.sh`처럼 sudo가 필요한 스크립트는 항상 사용자 터미널에서 사용자가 직접 실행하고, Claude는 명령어만 정확히 만들어 전달 + 결과 파일만 읽어서 분석하는 역할로 분담할 것.** (다른 세션에서도 재발 가능한 패턴이라 기억해둘 만함.)
- **정책 3종 × 워크로드 2종 "final" 벤치마크 1차 실행** (`results/summary_final.csv`, 완전 모듈 리로드 절차로 각각 실행): uniform은 7/29 확정한 `loops=250`, hotcold는 이때까지의 `hotcold.fio`(v3, 단일 파일 + `zoned:60/20:40/80`, size=600M/loops=250 고정값) 그대로 사용. 결과, uniform·hotcold 둘 다 Greedy와 Cost-Benefit의 `erase_sum`/`erase_max`가 사실상 동일하게 나옴(uniform: 271620/161 vs 271620/161, hotcold: 271624/150 vs 271624/153) — 7/27에 로컬 VM에서 봤던 수렴 현상이 서버 스케일에서도 그대로 재현됨.
- **수렴 원인 재분석**: `victim_line_get_pri()`가 vpc==0인 line은 age 계산 없이 바로 최우선 victim(최댓값)으로 리턴하도록 가드돼 있음(7/24 구현) — 즉 완전히 무효화된 line은 두 정책 모두 무조건 먼저 고름. 워크로드가 "GC 트리거를 위해 용량을 몇 배씩 덮어써야 하는" 강도로 가면, GC 후보의 대다수가 이런 vpc=0 line이 되어버려서 age가 실제로 갈리는 vpc>0 후보 사이의 경쟁 자체가 잘 안 생기는 것으로 추정.
- **부하 강도를 양극단으로 바꿔 재확인 (`final2`/`weakcalib`, 둘 다 기존 v3/v4 단일파일 설계)**: `hotcold.fio`에 `HOTCOLD_SIZE`/`HOTCOLD_LOOPS` 환경변수를 추가해 파라미터화한 뒤(v4), 강한 부하(`final2`: 24G×6루프=144G, 용량의 3.2배)와 약한 부하(`weakcalib`: 24G×2루프=48G, 용량의 1.07배) 양쪽에서 재실험. **두 경우 모두 Greedy와 Cost-Benefit이 완전히 동일한 수치로 나옴** (final2: 둘 다 `sum=266012 max=5`, weakcalib: 둘 다 `nonzero_blocks=3864 sum=3864 max=1`) — "부하 강도를 조절하면 해결된다"는 가설은 기각됨. (Random은 두 경우 다 예상대로 다르게 나옴: final2 `sum=364636 max=11`, weakcalib `sum=5308 max=3`.)
- **근본 원인 재정의 및 워크로드 v5 재설계**: FTL은 로그 구조라 쓰는 시간 순서대로 물리 line에 순차 배치됨. v1~v4는 hot/cold를 "한 파일 안에서 접근 빈도"로만 나눴기 때문에(v2/v3의 `random_distribution=zoned`), 시간축에서는 hot 페이지와 cold 페이지 쓰기가 계속 섞여 들어가고, 그 결과 같은 물리 line 안에 hot/cold 페이지가 뒤섞여 vpc와 age가 사실상 강하게 상관돼버림 — Greedy(vpc만 봄)와 Cost-Benefit(vpc·age 조합)이 다른 답을 낼 여지 자체가 구조적으로 없었던 것으로 결론. → **`scripts/workloads/hotcold.fio`를 v5로 재설계**: `stonewall`로 3단계 분리 (`cold_fill`: 콜드파일 크게 1회 순차쓰기 → `cold_touch`: 그중 일부만 랜덤 재기록해서 victim 후보로 진입시킴(v1 실패 원인이었던 "콜드 line이 후보에 아예 안 들어가는 문제" 해결) → `hot_churn`: 작은 핫파일을 대량 반복 재기록). 콜드/핫을 물리적으로도 시간적으로도 분리해서 vpc-age 상관을 구조적으로 깨는 게 목표. `run_experiment.sh`에 `COLD_SIZE`(기본 30G)/`COLD_TOUCH_SIZE`(기본 3G)/`HOT_SIZE`(기본 1G)/`HOT_LOOPS`(기본 100) 환경변수 추가, meta.txt에도 기록되도록 반영.
- **v5 로컬 스모크 테스트**: 일반 디렉토리(비-nvme)에서 작은 값(4M/1M/1M×3)으로 실행해 3단계가 의도대로 바이트 수만큼 정확히 쓰는지 확인(`cold_fill` 4M, `cold_touch` 1M, `hot_churn` 3M) — 정상.
- **v5 서버 1차 캘리브레이션 (Greedy만, 기본값 30G/3G/1G×100=총 133G)**: `results/20260730_151730_policy0_greedy_v5calib` → `nonzero_blocks=3144 sum=234816 max=79`. v3/v4(erase가 넓게 퍼짐, 예: final2 nonzero 76760/max 5)와 정반대로 **마모가 작은 핫 영역(1G)에 극도로 집중**됨(3144개뿐인 블록이 평균 74.7회, 최대 79회 재활용) — 콜드 30G는 거의 안 건드려졌다는 뜻으로, 의도한 물리적 분리가 실제로 이뤄진 것으로 보임. 아직 Random/Cost-Benefit은 이 v5 조건으로 안 돌려봄.
- **v5 3정책 비교 → 여전히 수렴**: Random까지 포함해 v5 조건으로 실행한 결과 Greedy `3144/234816/79`, Cost-Benefit `3164/234816/79`(sum·max 완전 일치), Random `47108/235796/14`(예상대로 다름). "물리적으로 분리하면 갈릴 것"이라는 가설도 기각.
- **v6 재설계 (병렬 실행) → 부분 개선에 그침**: `cold_touch`/`hot_churn`의 `stonewall`을 없애 병렬 실행하고 `COLD_TOUCH_SIZE`를 15G로 키움. 결과: Greedy `37660/275684/86`, Cost-Benefit `38864/277572/86` — erase max는 여전히 정확히 일치, nonzero_blocks 차이만 0.6%→3.2%로 소폭 확대.
- **printk 진단으로 근본 원인 직접 확인**: `conv_ftl.c`의 `select_victim_line()`에 임시 진단 함수(`diag_compare_victims()`, 활성 정책과 무관하게 Greedy/Cost-Benefit 각각의 최적 후보를 pqueue 원본에서 독립 계산해 비교하는 read-only 코드)를 추가. v6 워크로드로 실행한 결과 **`total=69000, diverge=9995`(14.5%) — 그런데 시간순으로 보면 `total=11500`(전체의 16.7%)까지 diverge가 급격히 늘다가(그 안에서는 최대 87% 다르게 고름) 그 이후 `total=69000`까지(나머지 83%) 단 한 번도 안 갈림.** 원인: `cold_touch`(15G)가 `hot_churn`(100G)보다 훨씬 먼저 끝나버려서, 콜드 후보 공급이 끊긴 이후로는 핫 line끼리만 경쟁 → 그 구간부터는 100% 일치. **결론: Greedy/CB는 실제로 다른 선택을 하지만, "다르게 고르는 17% 구간"이 "완전히 같게 고르는 83% 구간"에 파묻혀서 집계 통계엔 수렴처럼 보였던 것.**
- **v7 재설계 (time_based) → 드디어 divergence가 끝까지 유지됨**: `cold_touch`/`hot_churn`을 `size`+`loops` 대신 `time_based=1`+동일 `runtime`(기본 90초, `HOTCOLD_RUNTIME` 환경변수)으로 변경해서 크기 차이와 무관하게 둘 다 같은 시간 동안 돌게 함. 재진단 결과 `total=101000, diverge=93915`(93%, 마지막까지 계속 증가 — 플래토 없음) — divergence가 실행 끝까지 유지되는 것 확인.
- **v7 3정책 비교 결과, 정규화 필요성 발견**: raw 값은 Greedy `85916/405864/11`, Cost-Benefit `89436/401248/8`, Random `86632/294720/11`. Random의 sum이 가장 낮아 이상해서 io_bytes 확인 → **`time_based` 워크로드에서는 정책마다 같은 90초 동안 실제로 쓴 데이터량이 다름**(Random은 GC 오버헤드로 처리량이 Greedy/CB의 약 절반: ~102GiB vs ~161~162GiB) — raw erase sum 비교는 불공정, GB당 erase로 정규화해야 함. **정규화 결과: Greedy 2500.6 erases/GiB, Cost-Benefit 2490.0(약간 더 효율적), Random 2882.4(뚜렷하게 더 나쁨)**. erase max도 CB(8)가 Greedy/Random(11/11)보다 뚜렷하게 낮고 nonzero_blocks는 더 많음(89436 vs 85916) — **CB가 더 많은 블록에 걸쳐 더 고르게 마모시키면서 총 효율도 비슷하거나 더 낫다는, Cost-Benefit GC의 이론적 이점이 마침내 실측으로 확인됨.** 자세한 수치와 표는 `EXPERIMENT_LOG.md` 2026-07-30 16:14~16:22 항목 참고.
- **다음 할 일**: (1) v7+정규화 방법론으로 반복측정해서 위 차이가 노이즈가 아닌지 확인, (2) 진단용 printk(`diag_compare_victims`/`diag_gc_total`/`diag_gc_diverge`, `select_victim_line()`의 호출부 포함)를 `conv_ftl.c`에서 제거하고 클린 빌드로 재확인, (3) uniform 워크로드도 필요시 동일 방법론(정규화 포함)으로 재점검, (4) 최종 수치 확정되면 `collect_summary.sh` CSV 집계 → 그래프/보고서 작성 → 제출(7/31 마감, hslee@davinci.snu.ac.kr).

## 진행 상황 (2026-07-30 기준, 파트 2 — printk 제거/반복측정/filebench)
- **진단용 printk 제거 완료**: `conv_ftl.c`의 `diag_compare_victims`/`diag_gc_total`/`diag_gc_diverge` 및 `select_victim_line()`의 호출부(총 64줄, `865ea61` 커밋에 들어있던 것)를 전부 삭제하고 클린 빌드 확인(서버에서 `make` 에러 없음). 모듈 리로드 후 `dmesg`에 진단 메시지 안 뜨는 것도 확인함.
- **v7(hotcold) 반복측정 결과, 어제 결론 일부 철회**: 어제 값(rep1)에 2회 더 반복(rep2/rep3)해서 정책당 3회 확보, GiB당 erase로 정규화해 평균·표준편차 계산함.
  - Random은 확실히 나쁨: 평균 2868.1 erases/GiB (stdev 12.5) vs Greedy 2466.0(stdev 30.1)/Cost-Benefit 2482.9(stdev 13.0) — 격차가 각 정책의 반복 간 변동폭보다 훨씬 커서 노이즈 아님.
  - **Greedy vs Cost-Benefit의 "GiB당 erase 총량" 우열은 노이즈 수준이라 판정 불가로 정정**: 어제(rep1)는 CB가 근소 우위(2490.0<2500.6)였지만 rep2에서 반대(Greedy 2447.3<CB 2467.9) — Greedy 자체 stdev(30.1)가 두 정책 평균 차(~17)보다 커서 "CB가 총 효율에서 더 낫다"는 어제 결론은 철회.
  - **다만 erase max·nonzero_blocks는 3회 다 일관됨**: CB는 매번 max 8~9(Greedy는 10~11)로 낮고, nonzero_blocks는 매번 정확히 89436(Greedy는 85576~85916으로 변동)으로 더 많음. → **최종 결론(리포트용): "CB가 GC 효율을 개선한다"가 아니라 "CB는 총 erase는 Greedy와 비슷하지만 마모를 더 고르게 분산시켜 최대 마모(peak wear)를 낮춘다(웨어 레벨링 개선)"로 한정.**
- **uniform 워크로드도 3회 반복 재점검**: uniform은 `size`+`loops` 고정(time_based 아님)이라 정책 무관하게 항상 정확히 같은 바이트(157,286,400,000B)를 씀 → **정규화 불필요, raw 값 그대로 공정 비교 가능**(v7 hotcold와의 중요한 차이점).
  - Greedy와 Cost-Benefit은 **3회 다 erase sum·max가 소수점 하나 안 틀리고 완전히 동일**(271620/161) — 노이즈가 아니라 완벽 재현되는 구조적 수렴. hot/cold 스큐가 없는 워크로드에서는 CB 이점이 구조적으로 발현될 수 없다는 가설(7/27~7/30)이 반복측정으로 확정됨.
  - Random은 3회 다 일관되게 반대 트레이드오프: erase max 9~11(Greedy/CB의 161과 비교하면 15분의 1 수준으로 고르게 분산)이지만 총 erase는 약 0.6~0.7% 더 많음(273332~273400 vs 271620).
  - latency(avg/p99)는 세 정책 다 겹치는 범위(avg 34557~35475ns, p99 67072~73216ns)라 uniform에서는 latency로 정책을 구분할 근거 없음.
- **Filebench 셋업 (서버, 처음 설치)**: 서버에 filebench가 아예 설치 안 되어 있어서 신규 빌드함 (기존엔 로컬 VM에만 설치했었음, `~/filebench`에 clone).
  - **빌드 도구 부재**: `autoconf`/`automake`/`libtool`/`bison`/`flex`가 서버에 없어서 `sudo apt install`로 설치 필요했음. 이때 apt 미러 캐시가 오래돼서 이미 없는 버전을 참조(404) → `sudo apt update`로 해결.
  - **GCC 15 기본 C 표준 문제**: 그냥 빌드하면 `vars.h`의 `avd_t avd_bool_alloc(boolean_t bool)` 같은 코드가 "two or more data types in declaration specifiers" 에러로 실패함 — **GCC 15부터 기본 C 표준이 바뀌면서 `bool`이 예약어가 됨**, filebench는 `bool`을 변수명으로 쓰는 오래된 코드라 충돌. `./configure CFLAGS="-std=gnu17 -g -O2"`로 예전 표준을 강제 지정해서 해결.
  - **`fileset.c:131` 실제 버그 발견/수정 (filebench 자체의 오래된 버그, 최신 glibc에서 처음 발현)**: `fileset_resolvepath()`가 `s = malloc(strlen(path)+1)`로 딱 맞는 크기를 할당해놓고 `fb_strlcpy(s, path, MAXPATHLEN)`으로 4096바이트 쓴다고 잘못된 크기를 넘김 — **glibc 2.38+가 진짜 `strlcpy`를 기본 제공하기 시작하면서** `#ifndef HAVE_STRLCPY`로 감싸져 있던 filebench 자체의 관대한 구현 대신 시스템 `strlcpy`가 쓰이게 됐고, `_FORTIFY_SOURCE`가 이 크기 불일치를 정확히 잡아내서 `*** buffer overflow detected ***`로 즉시 크래시함(단순 `define file` 워크로드에서도 100% 재현, gdb 백트레이스로 `fileset_resolvepath → fileset_alloc_file → fileset_create` 경로 확인). **수정: `fb_strlcpy(s, path, MAXPATHLEN)` → `fb_strlcpy(s, path, strlen(path) + 1)`**. 같은 패턴(`malloc(strlen()+1)` 뒤에 다른 크기로 strlcpy/strlcat)이 코드베이스에 더 있는지 확인했으나 이 한 곳뿐이었음. 재빌드+`sudo make install`로 시스템 설치 버전까지 반영, `/tmp`와 실제 NVMe 디바이스 양쪽에서 크래시 없이 정상 동작 확인함.
  - ASLR 끄기(`echo 0 | sudo tee /proc/sys/kernel/randomize_va_space`)는 기존 CLAUDE.md 안내대로 진행.
- **filebench용 정책 비교 인프라 신설**: `scripts/run_filebench_experiment.sh` (fio용 `run_experiment.sh`와 동일하게 매 실행마다 모듈 완전 리로드 + mkfs + mount 수행, 그 위에 filebench 실행). 환경변수는 fio 버전과 이름 통일(`NVME_DEV`/`MEMMAP_START`/`MEMMAP_SIZE`/`NVME_CPUS`) + filebench 전용(`FB_FILESIZE` 기본 2g, `FB_RUNTIME` 기본 120초, `FB_NTHREADS` 기본 4). 워크로드는 `scripts/run_filebench_experiment.sh`가 실행 시점에 `$MOUNT_DIR`을 박아넣은 `.f` 파일을 결과 폴더 안에 직접 생성(filebench WML은 셸 환경변수를 못 읽어서). 워크로드 내용: 2GB 파일에 4KB 랜덤쓰기 + 매 write마다 fsync(버퍼링으로 실제 디바이스 반영이 안 되는 것 방지), `run $FB_RUNTIME`으로 time-based 실행(v7 hotcold와 같은 이유로 정책 간 동일 시간 비교).
- **filebench 캘리브레이션 + 3정책 1회 비교 (서버, 2GB/120초/4스레드)**: GC 트리거 확인됨(정책마다 87~90GiB 씀, 2GB 파일 기준 44배 넘게 덮어씀). time-based라 정책마다 실제 쓴 바이트가 달라서 fio v7과 동일하게 GiB로 정규화함.

  | 정책 | 쓴 양(GiB) | erase sum | erase max | nonzero_blocks | erases/GiB |
  |---|---|---|---|---|---|
  | Greedy | 87.58 | 119256 | 3 | 56216 | 1361.7 |
  | Cost-Benefit | 90.15 | 126216 | 3 | 56960 | 1400.1 |
  | Random | 87.64 | 127396 | 7 | 81388 | 1453.6 |

  Random이 fio 때와 일관되게 가장 나쁨(erases/GiB 최고, max 최고, nonzero_blocks 압도적으로 많음). Greedy/CB는 이 단일 파일·스큐 없는 워크로드에서 erase max는 동일(3)하고 총량은 Greedy가 근소 우위 — uniform fio 결과("hot/cold 없으면 CB 이점 안 드러남")와 일관된 패턴. **사용자 판단으로 filebench는 이 1회 측정으로 마무리하고 반복측정은 생략함** (마감 임박, filebench는 "두 번째 도구로 fio 결과를 재확인하는" 보조 역할로 결론 — 자세한 항목은 위 표 그대로 리포트에 사용 가능).
  - 참고: filebench는 fio와 달리 p99 latency를 기본 제공하지 않음(min/max/avg만) — sync-file 최대 지연이 세 정책 다 거의 동일(~917ms)해서 정책 구분 지표로는 안 쓰기로 함, avg latency(~0.010~0.012ms)도 세 정책 간 차이 없음.
- **다음 할 일 (갱신, 7/31 마감 임박)**: (1) `collect_summary.sh`로 fio 결과 CSV 집계(uniform 3회+hotcold 3회) — filebench 결과는 포맷이 달라 별도 표로 리포트에 삽입, (2) 그래프 작성(erase 분포, GiB당 erase 정규화 비교, latency), (3) 보고서 작성 — uniform(Greedy≈CB 수렴, Random 열세) vs hotcold(CB가 웨어 레벨링 개선, 총 효율은 노이즈 수준) vs filebench(fio uniform 결론 재확인) 구도로 정리, (4) 제출(hslee@davinci.snu.ac.kr, 7/31까지).

## 진행 상황 (2026-07-30 밤, 파트 3 — GC migration-cost 카운터 신설)
- **핵심 발견**: 지금까지 정책 비교에 써온 `erase_cnt`(블록 지워진 횟수)는 애초에 정책 차이가 잘 안 드러나는 지표였을 가능성이 큼. `erase_cnt` 총합은 사실상 "총 쓰기량 ÷ 블록당 용량"으로 결정되는 값이라 victim 선택 정책과 거의 무관하게 비슷하게 나올 수밖에 없음. **Cost-Benefit GC가 이론적으로 줄이려는 건 "GC 한 번당 옮겨야 하는 valid page 수(migration cost)"**인데, 이 수치는 지금까지 아예 측정한 적이 없었음(`clean_one_flashpg()`가 매번 `cnt`를 계산은 하지만 어디에도 누적 안 함). uniform/hotcold 양쪽에서 계속 봐온 "Greedy≈CB 수렴"이 워크로드 설계 문제가 아니라 애초에 잘못된 지표를 보고 있었기 때문일 수 있다는 가설.
- **새 카운터 구현 완료** (빌드 확인, 서버에는 아직 미배포 — 사용자가 집에 가야 해서 리로드/재실험은 다음 세션으로 넘김):
  - `conv_ftl.c`: `cb_clock` 옆에 전역 카운터 `gc_valid_page_migrate_cnt` 추가.
  - `conv_ftl.c`의 `do_gc()`: victim_line 확정 직후(`credits_to_refill` 대입 바로 다음 줄) `gc_valid_page_migrate_cnt += victim_line->vpc;` 추가 — victim으로 뽑힌 line의 vpc(valid page 수)가 곧 그 line을 회수하는 데 실제로 옮겨야 하는 페이지 수이므로, `clean_one_flashpg()` 내부를 안 건드리고 `do_gc()`에서 한 줄로 집계 가능.
  - `conv_ftl.h`: `extern uint64_t gc_valid_page_migrate_cnt;` 추가 (main.c에서 읽을 수 있게).
  - `main.c`: `/proc/nvmev/debug` 읽을 때 맨 앞줄에 `GC_VALID_PAGE_MIGRATE_CNT <값>` 출력 추가, `reset` 쓰기 시 이 카운터도 0으로 초기화되도록 추가. (기존 `erase_cnt` 덤프 포맷의 열 개수는 안 바뀌어서 `run_experiment.sh`의 `awk '$7!=0{...}'` 파싱과 호환됨 — 새 줄은 필드가 2개뿐이라 `$7`이 빈 값→0 취급되어 자동으로 걸러짐.)
  - `scripts/run_experiment.sh`, `scripts/run_filebench_experiment.sh`: `summary.txt`에 `gc_migrate_pages=` 필드 추가(awk로 `GC_VALID_PAGE_MIGRATE_CNT` 줄 파싱).
  - 로컬(서버) 빌드 확인 완료(`make` 에러 없음). **아직 모듈 리로드/실제 3정책 비교는 안 함** — 다음에 이어서 할 일.
- **다음 세션에서 바로 할 일**: 아래 3개를 순서대로 실행(v7 hotcold 워크로드로 1회씩, `migtest` 라벨) → `summary.txt`의 `gc_migrate_pages` 값을 정책별로 비교해서 erase_cnt보다 뚜렷한 Greedy vs Cost-Benefit 차이가 나오는지 확인:
  ```
  cd ~/nvmevirt
  NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
    ./scripts/run_experiment.sh 0 migtest hotcold
  NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
    ./scripts/run_experiment.sh 1 migtest hotcold
  NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
    ./scripts/run_experiment.sh 2 migtest hotcold
  ```
  결과가 좋으면(뚜렷한 차이) 이 지표를 메인 지표로 승격하고 반복측정 → 그래프/보고서. 결과가 여전히 비슷하면 그때 v7 워크로드 파라미터 튜닝(스큐 강도 등)으로 넘어갈 것.

## 진행 상황 (2026-07-30 밤, 파트 4 — 힙 staleness 버그 발견/수정, 최종 결론 확정)
- **migtest 결과(파트 3 예고편) 확인**: `gc_migrate_pages`로도 Greedy-CB 차이는 노이즈 수준이었음(평균 차가 각 정책 자체 반복 간 표준편차보다 작음) — "erase_cnt가 부적절한 지표였다"는 파트 3의 가설은 여기서는 기각됨. 자세한 수치는 EXPERIMENT_LOG.md 참고.
- **사용자가 Codex(다른 LLM)에게 `conv_ftl.c`/`conv_ftl.h`/`pqueue/pqueue.c`를 보여주고 6개 가설을 받아옴** — 그중 결정적인 2개가 실제 버그였음을 확인:
  1. `victim_line_get_pri()`의 Cost-Benefit score(`bc = ipc*age/(2*vpc)`)는 `cb_clock`(계속 흐르는 전역 논리 시계) 기반이라 매 순간 값이 바뀌는데, `pqueue`(vendored min-heap)의 `bubble_up`/`percolate_down`은 **그 노드가 insert/remove될 때 조상 경로만** 재정렬함 — 힙 전체를 주기적으로 재검증하는 로직이 없어서, 오래 방치된 line들 사이의 상대 순서가 시간이 지나도 재확인 안 된 채 남을 수 있음. 즉 `pqueue_peek()`/`pqueue_pop()`이 "지금 이 순간 진짜 최고 bc" line이 아닌 stale한 line을 리턴할 수 있음.
  2. 기존 진단(`diag_compare_victims`, 7/30 파트 1)은 `pq->d[]` 전체를 스캔해서 "이상적 Greedy pick"과 "이상적 CB pick"을 비교했을 뿐, "실제로 `pqueue_pop()`이 리턴하는 line"과는 비교한 적이 없어서 위 버그가 있어도 그 진단만으로는 안 잡혔음.
- **검증 (이론이 아니라 실측으로 확인)**:
  1. `pqueue/pqueue.c` 알고리즘을 파이썬으로 그대로 포팅해서 CB 계산식으로 최소 반례(2개 line)를 만든 결과: 몇 틱만 지나도 heap root와 전체 스캔 진짜 최고 line이 완전히 달라지고 라이브러리 자체 검증 함수 `pqueue_is_valid()`도 계속 `False` — 추가 insert/remove 없인 영원히 자기 교정 안 됨.
  2. 좀 더 실전과 비슷한 규모(line 수천 개, 지속적 invalidate+GC 20만 스텝) 시뮬레이션: 실제 `pqueue_pop()` 결과가 그 순간 전체 스캔 진짜 최고 line과 87.2% 다름(임의 파라미터 기반이라 %는 참고용, "메커니즘이 실재하고 크다"의 증거로만 사용).
  3. 실제 커널에 임시 카운터를 넣어 hotcold v7로 실측: `total=99500, changed=5443`(5.47%) — 버그가 실재하고 실제로 발동함을 확인.
- **수정 완료**: `select_victim_line()`에서 `GC_POLICY_COST_BENEFIT`일 때 `pqueue_pop()`(stale 가능) 대신 `pq->d[1..size-1]` 전체 스캔으로 그 순간 진짜 최고 line을 찾아 `pqueue_remove()`로 꺼내도록 교체. CB 계산식은 `cb_victim_pri()`로 분리해서 `victim_line_get_pri()`와 아래 분석 계측이 공유(중복 방지). Greedy/Random 분기는 안 건드림(Greedy는 vpc만 키로 쓰고 항상 정확히 reheapify되므로 애초에 stale해질 수 없음). 서버 빌드 확인 완료.
- **상시 분석 계측 추가 (제출 코드에도 유지하기로 결정)**: `diag_scan_greedy_vs_cb()` — 활성 `gc_policy`와 무관하게 매 GC마다 전체 스캔으로 "Greedy라면 골랐을 line"과 "CB라면 골랐을 line"을 각각 계산해서 `total_gc`/`greedy_vs_cb_identity_diverge`/`avg_greedy_vpc`/`avg_cb_vpc`/`avg_abs_vpc_diff`/`same_vpc_different_line_ratio`를 누적, `/proc/nvmev/debug`에 노출, `run_experiment.sh`의 `summary.txt`에 자동 집계(`erase_cv`도 이때 추가). read-only라 실제 GC 동작에 영향 없음 — 보고서 방법론 섹션에서 "어떻게 검증했는지"를 보여주는 근거 코드로 쓸 수 있어서 "제출 전 제거" 대상에서 제외하기로 함 (주석도 정식 기능으로 재작성 완료).
- **최종 3정책 비교 확정 (`vpcdiag`, 힙 staleness 수정 후, hotcold v7, 각 3회 반복)**:

  | 지표 | Greedy | Cost-Benefit | Random |
  |---|---|---|---|
  | migrate_pages/GiB | 48,493 ± 1,302 | 55,079 ± 1,198 | 134,288 ± 954 |
  | erase/GiB | 2,465.4 ± 8.9 | 2,500.2 ± 7.6 | 2,870.4 ± 6.4 |
  | erase max | 10.3 | 8.3 | 11.3 |
  | nonzero_blocks | 85,624 | 89,433 | 86,500 |
  | erase_cv | 0.239 | 0.231 | 0.489 |
  | latency avg | 80.2μs | 84.5μs | 152.4μs |
  | latency p99 | 432.1μs | 439.0μs | 1,521.0μs |

  3회 다 Greedy/CB range가 거의 안 겹침(노이즈 아님). `diag_scan_greedy_vs_cb`로 같이 잰 `avg_abs_vpc_diff`도 CB 구동 시 33.8(평균 vpc의 47.4%)로 작지 않아서, "다른 line을 골라도 비용은 비슷하다"가 아니라 "다르게 고르면 비용도 실제로 다르다"는 게 정량적으로 뒷받침됨.
- **최종 결론(리포트 헤드라인)**: 지금까지(7/27~7/30 파트 3까지) 계속 봐온 "Greedy≈CB 수렴"은 힙 staleness 버그가 CB를 우연히 Greedy와 비슷하게 행동하게 만든 착시였음. 버그를 고치자 **Cost-Benefit은 총 migration 효율을 Greedy보다 13.6% 더 씀(latency도 약 5% 높음) 대신, 최대 마모(erase max)를 8.3으로 낮추고(Greedy 10.3) 마모를 더 많은 블록(89,433 vs 85,624)에 분산시킴** — Cost-Benefit GC의 교과서적 트레이드오프(총 효율 희생 ↔ 웨어 레벨링 개선)와 정확히 일치하는, 이 프로젝트에서 가장 깔끔한 결과. Random은 모든 지표에서 확실히 최악. (uniform 워크로드는 hot/cold 스큐가 없어서 이 버그와 무관하게 Greedy=CB로 항상 수렴함 — 이것도 리포트에서 "워크로드에 따른 차이"로 다룰 수 있는 포인트.)
- ~~**다음 할 일**: 그래프 작성 → 보고서 작성 → 제출~~ → **그래프·보고서 초안은 7/31 세션에서 완료됨. 최신 상태와 남은 할 일은 아래 "진행 상황 (2026-07-31)" 섹션을 볼 것.**
## 진행 상황 (2026-07-31 — 제출 전 코드 재점검 + 방법론 검증, 그래프/보고서 초안 완성)
7/30 밤 파트 4에서 최종 결론을 낸 뒤, 제출 전에 코드와 벤치마크 방법론을 처음부터 다시 훑은 세션. 커밋 3개: `bc3a3cb`(awk 버그 수정+교차검증), `afb98e8`(gc_policy 읽기 전용), `d75c0d5`(CRC 검증+uniform 진단+erase_cv_all).

- **awk 집계 버그 발견/수정**: `run_experiment.sh`의 summary awk가 `nonzero_blocks`를 헤더 줄 개수만큼 부풀리고 있었음 — `/proc/nvmev/debug` 헤더 줄들은 필드가 2개뿐이라 `$7`이 uninitialized인데 **mawk가 이를 `""`로 보고 `"" != 0`을 참으로 평가**함. `sum`/`max`는 무사(빈 값이 산술에선 0으로 강제변환). 모든 정책에 동일한 상수 오프셋이라 **결론은 영향 없음**(CB−Greedy 블록 수 차이는 3809로 정정 전후 동일). `NF==7` 가드 추가하고 영향받은 `summary.txt` 전부 재생성, 문서/그래프 수치 정정(Greedy 85,624 / CB 89,433 / Random 86,500).
- **정책 동작 교차검증 (중요, 리포트 3.4절에 수록)**: `gc_migrate_pages / total_gc`(실제 회수된 victim의 평균 vpc)를 진단이 독립 계산한 `avg_greedy_vpc`/`avg_cb_vpc`와 대조 → Greedy 3회 모두 `avg_greedy_vpc`와, Cost-Benefit 3회 모두 `avg_cb_vpc`와 **소수점 3자리까지 완전 일치**. Random은 어느 쪽과도 불일치(정상). → Greedy의 힙은 stale해지지 않으며(vpc는 `mark_page_invalid`가 매번 remove+insert로 정확히 갱신), **7/30에 넣은 힙 staleness 수정이 실제로 작동함**이 증명됨.
- **`gc_policy`를 런타임 읽기 전용(`0444`)으로 변경**: Cost-Benefit → Greedy 런타임 전환 시 힙이 CB 우선순위로 정렬된 상태라 Greedy가 **에러 없이 조용히** min-vpc가 아닌 line을 회수하는 문제가 있었음. `insmod ... gc_policy=N`과 `cat`(읽기)은 그대로 되고, `echo N | sudo tee ...`만 막힘. 두 실험 스크립트는 이미 insmod 방식이라 **벤치마크 무영향, 재측정 불필요**(`readonlycheck` 1회로 재현성도 확인: migrate/GiB 55,404 vs 기존 55,079±1,198).
- **검증 1 — 데이터 정합성(CRC)**: 그동안 fio/filebench 모두 쓰기만 하고 되읽어 검증한 적이 없어서 "GC 고쳤는데 데이터 안 깨지냐"에 답할 근거가 없었음. CB 정책으로 8 GiB 파일에 48 GiB를 쓰며 CRC32C 심고 전부 되읽기(`fio --verify=crc32c --verify_fatal=1`) → **`err= 0`, 불일치 0건 통과.**
- **검증 2 — uniform 수렴이 "추론"에서 "증명"으로 (가장 큰 수확)**: uniform을 최종 빌드로 재측정(`uniformdiag`, policy 0/2) → `total_gc=67,905`(두 정책 동일), **선택이 갈린 횟수 0**, `avg_greedy_vpc=avg_cb_vpc=0.000`, `gc_migrate_pages=0`. **67,905번의 GC 전부에서 victim의 vpc가 0이었고 옮긴 페이지가 하나도 없음** — GC 비용이 문자 그대로 0. 원인은 워킹셋 크기(44.86 GiB 디바이스에 600 MiB 파일뿐 = 1.3%)라 후보 풀이 전부 vpc=0 line으로 채워지는 것. hotcold(divergence 90.3%, `avg_abs_vpc_diff` 33.8)와의 대비가 **리포트의 중심 논지**가 됨("CB의 이점은 회수 후보에 실질적 선택의 여지가 있을 때만 발현된다", fig8로 시각화).
- **디바이스 기하 구조 확정**: 덤프 인덱스 범위 실측으로 8채널이 4파티션에 2개씩 분배됨을 확인 → **전체 131,072 블록 / 32,768 line, line = 블록 4개 ≈ 1.40 MiB, 블록 ≈ 359 KiB**, 파티션당 victim pqueue 최대 8,192. 이 구조로 계산한 "erase 271,620 ÷ 4 = line 회수 67,905"가 커널이 독립적으로 센 `total_gc`와 **정확히 일치** → erase 집계가 물리 구조와 정합함.
- **지표 개선 `erase_cv_all` 신설**: 기존 `erase_cv`는 erase≥1인 블록만 대상이라 정책마다 모집단이 달라(85,624 vs 89,433) 엄밀하지 않았음. 전체 131,072 블록 기준으로 바꾸니 **Greedy 0.7861±0.0017 / CB 0.7375±0.0045 / Random 0.9369±0.0031로 범위가 안 겹침** → 웨어 레벨링 주장이 훨씬 명확해짐. 두 스크립트에 출력 추가(앞으로의 run엔 자동 포함). uniform은 8.26으로 hotcold의 10배 이상(워킹셋이 작아 마모가 극단적으로 몰림).
- **산출물**: `report/REPORT.md`(초안 완성 — 목표/구현/방법론(버그 발견 스토리+3가지 검증)/결과/결론), `report/figures/fig1~8_*.png`(200dpi, 한글 폰트 적용), `report/make_figures.py`(raw 반복값에서 mean/stdev 직접 계산).

### 다음 세션에서 할 일 (7/31 마감) — 1~3 완료, 남은 건 제출뿐
1. ~~hotcold는 재실행하지 말 것~~ → 재실행 안 함, 기존 `vpcdiag` 데이터 그대로 사용.
2. ~~uniform과 filebench만 최종 빌드로 재실행~~ → **완료**: uniform `final31_rep1/2/3`(정책 3종×3회, 9회) + filebench `final31`(정책 3종×1회) 전부 최종 빌드로 재실행함. uniform 결과: Greedy=CB가 migration/erase 전부 3회 동일 수렴(migrate=0, sum=271620, max=161) 재확인, Random만 다름(migrate≈170,989, sum=273,380, max≈9.7). filebench 결과: GiB당 정규화 시 Greedy 1355.3/CB 1379.7/Random 1463.8 erases/GiB, migration은 Greedy·CB 둘 다 0이고 Random만 8590.8 — uniform과 동일한 "스큐 없으면 구조적 수렴" 패턴이 fio 외 도구에서도 재현됨.
3. ~~새 수치로 `report/make_figures.py`의 raw 배열 갱신 → 그래프 재생성 → `REPORT.md` 표/본문 갱신~~ → **완료**. `make_figures.py`의 uniform(fig4, migration 패널 추가로 3패널화)·filebench(fig5, migration 패널 추가로 4패널화) 데이터 교체 후 전체 그래프 재생성, `REPORT.md` 4.2/4.3절 표·본문 갱신 — 이제 리포트 전체가 단일(최종) 빌드 데이터로 통일됨.
4. **남은 건 제출뿐** (hslee@davinci.snu.ac.kr) — 제출물: 코드 + `report/REPORT.md` + `report/figures/*.png`. 제출 전 `report/REPORT.md` 전체를 한 번 통독해서 문장 매끄러움만 확인할 것.

## 진행 상황 (2026-07-31 파트 2 — 사용률 스윕 / zipf·zoned 추가 측정 / Codex 교차검증)

7/31 오전에 "제출만 남았다"고 정리한 뒤, 사용자가 다른 수강생 결과와 비교해보고 워크로드를 더 돌려보기로 하면서 실험이 크게 확장된 세션. **결론이 바뀌었으므로 이전 섹션의 결론보다 이 섹션이 우선한다.**

### 스크립트 파라미터화
- `run_experiment.sh`의 uniform 워크로드에 `UNIFORM_SIZE`(기본 600M) / `UNIFORM_LOOPS`(기본 250) 추가. 기본값은 기존 결과 재현성을 위해 그대로 둠.
- 같은 스크립트에 `RANDOM_DIST` 추가 — fio `--random_distribution`으로 그대로 전달. 비워두면 기본(균등). 파일 크기·총 쓰기량을 고정한 채 **접근 분포만** 바꾸는 대조 실험이 가능해짐.
- `meta.txt`에 `uniform_size` / `uniform_loops` / `random_dist` 기록되도록 반영.

### 사용률 스윕 — "용량 때문에 수렴한다"는 가설 기각 (중요)
uniform이 Greedy=CB로 수렴하는 이유를 그동안 "워킹셋이 1.3%뿐이라 디바이스가 텅 비어서"로 **추론만** 하고 있었음. 파일 크기만 키워(총 쓰기량은 146\~154 GiB로 고정) 검증:

| 파일 (사용률) | Greedy | Cost-Benefit | Random | Greedy↔CB 불일치 |
|---|---|---|---|---|
| 600 MiB (1.3%) | 0 | 0 | 1,167 | 0회 |
| 22 GiB (49%) | 0 | 0 | 1,434 | 0회 |
| 38 GiB (85%) | 0 | 0 | **3,363** | 0회 |

*(GiB당 이동한 valid page 수. 600M·22G는 3회 반복, 38G는 1회)*

- **85%까지 채워도 Greedy·CB는 valid page를 하나도 안 옮기고 선택도 한 번도 안 갈림.** 가설 기각.
- **Random이 대조군 역할**: 같은 후보 풀에서 migration 비용이 2.9배로 증가 → GC는 실제로 어려워졌고 valid page 남은 line도 늘어났음. 그런데도 min-vpc를 고르는 Greedy는 언제나 완전히 죽은 line을 찾아냄.
- 이유: 실효 over-provisioning이 여전히 큼(물리 48 GiB / 라이브 22 GiB = 2.18배). 22G 시점에서 Random victim의 평균 valid page가 2.99개(line당 359페이지 중 0.8%)에 불과 — 거의 모든 line이 이미 죽어 있었음.

### zipf:1.2 — 이 프로젝트에서 가장 뚜렷한 결과 (헤드라인)
22 GiB 파일 + `random_distribution=zipf:1.2` + loops=7 (총 154 GiB, 세 정책 모두 동일 바이트 → 정규화 불필요). 각 3회 반복:

| 지표 | Greedy | Cost-Benefit | Random |
|---|---|---|---|
| 최대 erase (peak wear) | 11.0 ± 1.0 | **6.0 ± 0.0** | 12.0 ± 0.0 |
| GiB당 erase | 1,970 ± 3 | 1,968 ± 5 | 2,083 ± 13 |
| GiB당 migration | 6,029 ± 66 | **5,963 ± 102** | 17,021 ± 886 |
| latency 평균 / p99 | 42.9 / 97.8 μs | 42.9 / 100.5 μs | 45.7 / 131.6 μs |
| Greedy↔CB 불일치 | — | **98.7%** | — |

- **CB가 최대 마모를 45.5% 낮추면서 migration 비용은 오히려 1.1% 적음.** 원시값이 완전히 분리됨(Greedy `[10,11,12]` vs CB `[6,6,6]`).
- 메커니즘: CB 구동 시 `avg_greedy_vpc=5.95` vs `avg_cb_vpc=12.12` — **CB가 일부러 2배 비싼(=오래된 콜드) line을 고름.** 다만 Greedy도 자기 운영 상태에서는 평균 12.2짜리를 회수하게 되므로 총비용은 비슷하게 수렴.
- hotcold(peak wear −19.4%, migration +13.6%)보다 효과가 크고 대가는 없음 → **리포트 헤드라인을 hotcold에서 zipf로 교체함.**

### zoned 80:20 — "스큐만 있으면 된다"도 기각
zipf와 파일 크기·총 쓰기량을 동일하게 두고 분포만 `zoned:80/20:20/80`으로 교체(1회 측정):
- Greedy·CB가 erase 총합 292,748로 **완전 동일**, migrate 0, 불일치 0%.
- 원인: zoned의 "콜드" 영역(파일의 80%, 17.6 GiB)이 전체 쓰기의 20%인 30.8 GiB를 받아 **평균 1.75회씩 덮어써짐** → 느릴 뿐 결국 전부 무효화됨. zipf는 멱법칙 꼬리라 **거의 안 쓰이는 페이지가 실제로 존재**함.

### 최종 결론 (이전 섹션의 결론을 대체)
7개 조건(uniform 3종 + zoned + filebench + zipf + hotcold)의 진단 결과가 두 부류로 정확히 갈림:
- **vpc=0만 후보인 경우**(uniform 1.3/49/85%, zoned, filebench): 불일치 0%, 결과 완전 동일. 고를 여지 자체가 없음.
- **vpc>0 후보가 있는 경우**(hotcold 90.3%, zipf 98.7%): 선택이 갈리고 마모 분산 효과 발생. 불일치 비율이 높을수록 효과도 큼.

**→ Cost-Benefit의 이점 조건은 디바이스 사용률도, 접근 스큐의 유무도 아니라 "GC 회수 시점까지 valid 상태로 살아남는 데이터가 존재하는가"임.** (단, 이 실험 범위 — 단일 디바이스 구성, 4KB 랜덤쓰기, 146\~154 GiB — 에 한정된 관찰로 리포트에 명시함.)

### Codex 교차검증 (`hjyou-cares/nvmevirt2`)
사용자가 GPT Codex에게 저장소를 새로 clone해 정책을 독립 구현시킴. 실측은 아직 0건이지만 코드 비교 결과:

**독립적으로 일치한 5가지** — 내 판단이 자의적이지 않았다는 근거:
1. **Cost-Benefit에서 힙을 믿지 않고 큐 전체 스캔** (내가 "힙 staleness"라 부른 문제). Codex는 아예 CB 점수를 `victim_line_get_pri()`에 넣지 않아 힙을 항상 vpc 순으로만 유지 — **내 방식보다 깔끔함**(문제가 생길 구조 자체를 안 만듦).
2. `vpc==0` 즉시 최우선 victim 가드
3. Random을 `pq->d[]` 스캔 + `pqueue_remove()`로 구현
4. `gc_policy`를 런타임 읽기 전용(0444)으로
5. GC가 옮긴 페이지 수 / GC 횟수 카운터

**Codex가 더 잘한 것**: `pqueue_remove()`의 원본 결함 수정 — 제거된 노드의 `pos`를 0으로 안 만들고(마지막 원소 제거 시 `percolate_down`이 stale 값을 남김), 큐에 없는 원소(`posn==0`)를 넘기면 `q->d[0]`이 손상됨. **내 코드는 세 호출부 모두 직후에 `pqueue_insert` 또는 명시적 `pos=0`이 따라와서 이 버그를 안 밟지만**, 라이브러리 자체는 고치는 게 맞음.

**진짜 다른 것 — age 정의** (결과가 달라질 수 있는 유일한 지점):
- 내 구현: `cb_clock - mtime` (논리 시계, line이 **닫힌 시점** 기준)
- Codex: `ktime_get_ns() - last_invalidated_ns` (벽시계, **마지막 무효화 시점** 기준 — 무효화될 때마다 리셋됨)
- **유지하기로 결정**: (a) 고전 정의(LFS/Kawaguchi)의 age는 "세그먼트가 쓰인 뒤 지난 시간"이라 내 쪽이 더 부합, (b) 논리 시계는 결정론적이라 반복측정이 완전히 재현됨(uniform 3회 erase 271,620 동일), (c) 마감 당일에 30여 런과 3.4절 검증을 전부 재실행해야 함.

### 도구/환경 메모
- **`report/finalize_docx.py` 신설**: pandoc이 표의 첫 행에 `<w:tblHeader/>`를 안 넣어서, 표가 페이지를 넘기면 둘째 페이지부터 머리행 없이 숫자만 이어짐. docx를 후처리해 표 7개 전부 "제목 행 반복" 지정. **REPORT.docx를 다시 만들 때마다 `python3 report/finalize_docx.py`를 한 번 돌릴 것.**
- **로컬 PC(WSL2) 환경**: `pandoc`은 `sudo apt install -y pandoc`으로 설치. matplotlib은 없어서 `pip install --user matplotlib`으로 설치(venv는 `ensurepip` 부재로 실패). **한글 CJK 폰트가 없음** — WSL이라 `/mnt/c/Windows/Fonts/malgun.ttf`(맑은 고딕)를 쓸 수 있지만, **그래프 텍스트를 전부 영어로 바꿔서 폰트 의존성 자체를 없앰**(서버/로컬 어디서 렌더링해도 동일).
- **로컬 PC에 git identity가 없었음** → `git config user.name/user.email`을 이 저장소에만 설정(기존 커밋과 동일한 `hjyou-cares <hjyoucau911@gmail.com>`).
- 그림 검토용으로 `C:\Users\hjyou\Downloads\nvmevirt_figures\`에 PNG를 복사해가며 진행함 (사용자가 Windows에서 열어봐야 해서).
- 제출용 zip 생성 시 `zip` 명령이 없어 Python `zipfile`로 만듦. `results/*/erase_cnt.txt`는 총 222MB라 제외(집계값은 `summary.txt`에 있음), `CLAUDE.md`·`gc_diag.log`·`local-verify-0-verify.state`도 제외.

### 남은 일
1. **push 안 된 커밋 2개** 있음(사용자가 직접 push하기로 함).
2. `report/REPORT.docx`는 아직 git 추적 밖 — Word에서 직접 수정할 경우 그 파일이 최종본이 되므로 커밋 포함 여부 결정 필요.
3. 저장소에 남아있는 실험 부산물 `gc_diag.log`, `local-verify-0-verify.state` 삭제 여부 결정 필요.
4. 제출 (hslee@davinci.snu.ac.kr).

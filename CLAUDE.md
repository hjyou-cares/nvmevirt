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
- 실험 서버: 147.46.241.107 (포트 220), NVMeVirt 세팅: memmap_start=12G memmap_size=36G cpus=14,15
- 저장소: GitHub fork `hjyou-cares/nvmevirt` (upstream: `snu-csl/nvmevirt`)
- **주의**: 이 fork를 로컬 VM 외에 다른 환경(서버 등)에서도 건드리고 있어서 origin에 로컬에 없는 커밋이 먼저 들어와 있던 적 있음 (2026-07-23, `CONFIG_NVMEVIRT_ZNS` 커밋). 작업 시작 전 `git fetch`/`git pull`로 동기화 확인 습관 들일 것.
- 빌드: gcc-12, linux-headers. 리로드 사이클: `umount → rmmod → make → insmod → mount(+chown)`
- GRUB 관련: `memmap=1G\\\$2G` 트리플 백슬래시 이스케이핑, `intremap=off` 필요 (VM 재설정 시 다시 필요할 수 있음)

## 실습 목표 (실습 1: Cost-Benefit GC)
NVMeVirt의 Conventional FTL(`conv_ftl.c`)에서 GC victim 선택 정책 3가지를 구현하고 비교:
1. **Greedy (baseline)** — 이미 구현되어 있음. `victim_line_get_pri()`가 `line->vpc`(valid page count)를 리턴하고, `pqueue_peek`/`pqueue_pop`이 vpc가 가장 작은 line을 뽑음 (최소힙).
2. **Random** — 아직 미구현.
3. **Cost-Benefit** — 아직 미구현.

평가: NVMeVirt 가상 SSD에 Filebench/FIO 벤치마크 실행 후, 정책별로 아래 측정:
- 블록별 Erase 횟수 (`mark_block_free()`의 `blk->erase_cnt++`)
- 호스트 IO AVG, Tail Latency

**중요**: `erase_cnt`는 현재 커널 모듈 밖으로 노출되는 통로가 전혀 없음 (`/proc/nvmev/stat`엔 큐 통계만 있고 FTL/GC 관련 필드 없음, `printk`/`seq_printf` 등 아무것도 안 걸려있음). `main.c`의 `debug` proc 파일(`__proc_file_read` 353번째 줄 근처, `strcmp(filename, "debug")` 분기)이 지금 비어있어서(`/* Left for later use */`) 여기에 erase_cnt 덤프 기능을 직접 구현해야 측정이 가능함. 이것도 실습 구현 범위에 포함시켜야 함.

## 코드 구조 요약 (핵심 함수 위치, conv_ftl.c 기준)
- `victim_line_cmp_pri`, `victim_line_get_pri`, `victim_line_set_pri`, `victim_line_get_pos/set_pos` (68~92줄): pqueue 콜백. `pqueue_init()`(`init_lines()` 안)에 등록됨.
- `consume_write_credit`, `check_and_refill_write_credit` (93~108줄): write credit 소진 시 `foreground_gc()` 트리거.
- `struct line` (conv_ftl.h): `id`, `ipc`, `vpc`, `pos` 필드. **Cost-Benefit 구현 시 age 관련 필드 추가 필요할 것.**
- `struct line_mgmt`(`lm`, conv_ftl.h): `lines`(전체 line 배열), `free_line_list`, `victim_line_pq`, `full_line_list`, `free_line_cnt` 등.
- `mark_page_invalid()` (~490줄): 페이지 invalid 처리. `line->pos`가 있으면(이미 pqueue 안에 있으면) `pqueue_change_priority()`로 즉시 재정렬, line이 막 full→invalid 전환되는 순간 `pqueue_insert()`로 큐에 새로 들어감.
- `select_victim_line()` (~645줄): `pqueue_peek()`으로 1등 확인 → force 아니면 vpc 임계치 체크 → `pqueue_pop()`으로 실제로 꺼냄.
- `do_gc()` (753줄), `clean_one_flashpg()` (693줄): 실제 GC 수행 (valid page 이관 → block erase → line 반환).

## pqueue 라이브러리 (pqueue/pqueue.c, pqueue/pqueue.h) 관련 중요 사실
- Vendored 코드 (범용 외부 라이브러리 소스가 저장소 안에 그대로 포함됨). `conv_ftl.h`에서 `#include "pqueue/pqueue.h"`.
- `pqueue_t` 구조체가 완전히 투명하게 노출되어 있음 (`q->d[]` 힙 배열, `q->size` 등 conv_ftl.c에서 직접 접근 가능).
- `pqueue_remove(q, d)` 함수로 특정 포인터를 직접 큐에서 제거 가능.
- **중요**: `victim_line_get_pri()`가 호출마다 다른(무작위) 값을 리턴하면 힙 불변식이 깨짐. 따라서 **Random 정책은 get_pri를 무작위화하는 방식이 아니라, `select_victim_line()`에서 별도 분기로 `q->d[]`에서 무작위 인덱스를 뽑고 `pqueue_remove()`로 꺼내는 방식**이 맞다고 판단함 (이 방향으로 구현 원함, 다른 더 나은 방법 있으면 제안 환영).
- Cost-Benefit은 `victim_line_get_pri()`의 계산식만 바꾸면 됨 (힙 전제에 위배 안 됨).

## 작업 순서 희망사항
1. Random 정책부터 구현 (가장 쉬움) → 로컬 빌드/insmod 테스트
2. 서버에서 baseline+Random 벤치마크 파이프라인 먼저 검증
3. Cost-Benefit 구현 (가장 오래 걸릴 것으로 예상) → 로컬 테스트
4. 서버에서 세 정책 모두 벤치마크, 결과 수집
5. 그래프 + 보고서 작성

## 안전 관련 주의사항
- 커널 모듈이므로 잘못된 코드는 커널 패닉/VM 프리징을 일으킬 수 있음. **큰 변경 전에는 VM 스냅샷을 권장.**
- `insmod` 실패 시 `dmesg`로 에러 로그 확인하는 법을 안내해줄 것.

## 벤치마크 도구 셋업 (fio / filebench)
전제: `nvmev` 모듈 로드 후 `/dev/nvme0n1`이 존재해야 함.

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
fio --name=test --filename=~/nvme_mount/testfile \
    --size=100M --rw=write --bs=4k --numjobs=1 --iodepth=16 \
    --ioengine=libaio --direct=1 --group_reporting
```
`--rw=write`(순차) / `--rw=randwrite`(랜덤)로 패턴 변경. 랜덤 쓰기가 GC를 더 유발시켜서 실제 정책 비교에 의미 있음.

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
sudo insmod ./nvmev.ko memmap_start=2G memmap_size=1G cpus=2,3   # 로컬 VM 값. 서버는 memmap_start=12G memmap_size=36G cpus=14,15
sudo mount /dev/nvme0n1 ~/nvme_mount
sudo chown $USER:$USER ~/nvme_mount
```
로드 후 확인: `lsmod | grep nvmev`, `ls /dev/nvme0n1`
**주의**: 리로드하면 `gc_policy`가 기본값(0=Greedy)으로 돌아가고 `erase_cnt`도 전부 0으로 초기화됨 — 재실험 시작 전 2번/4번 다시 확인할 것.

### 2. GC victim 정책 확인/전환 (모듈 리로드 없이 즉시 적용됨)
```
cat /sys/module/nvmev/parameters/gc_policy      # 현재 정책 확인 (0=Greedy, 1=Random, 2=Cost-Benefit)
echo 1 | sudo tee /sys/module/nvmev/parameters/gc_policy   # 정책 전환
```
`insmod` 시점에 `gc_policy=1`처럼 파라미터로 줘도 되지만, 이미 로드된 모듈에서 sysfs로 바로 바꾸는 게 더 편함 (정책별 재실험할 때 리로드 안 해도 됨).

### 3. GC를 실제로 유발시키는 랜덤 쓰기 부하 (스모크/스트레스 테스트용)
같은 영역을 여러 번 덮어써서 invalid page를 계속 만들어야 GC가 트리거됨. 파일 크기보다 큰 총 쓰기량을 줘야 함.
```
fio --name=gc_stress --filename=~/nvme_mount/testfile2 --size=600M --rw=randwrite \
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
awk '$7!=0{sum+=$7; n++; if($7>max) max=$7} END {print "nonzero_blocks="n, "sum="sum, "max="max}' /proc/nvmev/debug
```

---

## 진행 상황 (2026-07-23 기준)
- 로컬 VM: `nvmev` 모듈 로드됨, `/dev/nvme0n1` ext4 포맷 + `~/nvme_mount` 마운트 완료
- fio 설치 완료, 순차/랜덤 쓰기 테스트로 I/O 정상 동작 확인
- filebench 소스 빌드 + 설치 완료 (`~/filebench`에 클론, `/usr/local/bin/filebench`), ASLR 끄고 스모크 테스트로 정상 동작 확인
- Kbuild가 `CONFIG_NVMEVIRT_ZNS`로 잘못 설정돼있던 걸 `CONFIG_NVMEVIRT_SSD`로 수정함 (안 그러면 conv_ftl.c가 빌드에서 아예 빠짐)
- Random GC 정책 구현 완료 (`conv_ftl.c`, `gc_policy` module_param + `select_victim_line()` 분기), 로컬 VM에서 실측으로 Greedy 대비 erase가 훨씬 고르게 분산되는 것까지 확인함 (아래 erase_cnt 항목 참고)
- Cost-Benefit GC 정책: 아직 미착수
- erase_cnt 측정용 `/proc/nvmev/debug` 인터페이스 구현 완료 (dump + reset). 로컬 VM 6GB 랜덤쓰기 기준 Greedy(19424 block, sum 157136, max 9) vs Random(103988 block, sum 192060, max 6) 비교 결과 확보 — 커맨드는 위 "GC 정책 실험용 커맨드 레퍼런스" 참고
- 서버(147.46.241.107)에 filebench 설치 여부: 아직 미확인, GC 정책별 실측 벤치마크(erase count + latency)는 아직 서버에서 안 돌림
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


2026.07.23
현재 로컬 VM 상태 확인 결과 정리해드릴게요.

환경 상태
- nvmev.ko는 있지만 (7/15 빌드) 오늘 리부팅된 이후라 로드 안 된 상태 (lsmod에 없음)
- main.c는 7/22에 주석만 추가된 상태라 로직상 재빌드해도 동작 차이 없음
- GRUB에 memmap=1G$2G 설정은 이미 되어 있음 (VM 기준: memmap_start=2G, memmap_size=1G)
- CPU는 4개 (0-3) — cpus= 파라미터로 최소 2개 지정 필요 (예: cpus=2,3)
- intremap=off 옵션은 현재 안 걸려있음 (필요해지면 insmod 시 에러로 알 수 있음)
- fio는 미설치지만 apt로 설치 가능 (fio 3.28-1)
- filebench는 apt 저장소에 후보 자체가 없음 (Ubuntu 22.04 기본 repo엔 없어서 소스 빌드가 필요할 수 있음)

제안하는 순서 (로컬 VM에서 먼저 baseline 파이프라인 검증):
1. fio 설치 (sudo apt install fio)
2. make로 재빌드 → sudo insmod ./nvmev.ko memmap_start=2G memmap_size=1G cpus=2,3
3. /proc/nvmev 생성 확인 + mount, chown
4. 생성된 디바이스에 대고 간단한 fio 테스트 한 번 돌려서 I/O가 정상적으로 도는지 확인
5. (나중에) filebench는 서버(실험 서버)에 이미 설치되어 있는지 확인 필요 — 없으면 소스 빌드 여부 결정

이 순서로 진행할까요? 2번 단계(insmod)부터는 커널 모듈을 실제로 로드하는 작업이라 진행 전에 확인 받고 싶어요.
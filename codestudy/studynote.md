# Study Note

## 학습 목표 프롬프트

실습2 구현을 시작하기 전에 내가 관련 개념과 현재 코드 구조를 이해하고 싶다.

나는 C 언어, 커널, SSD 구조에 익숙하지 않은 초보자다. 지금은 코드를 수정하지 말고 나를 가르치는 역할에 집중해라.

전체 NVMeVirt를 한꺼번에 설명하지 말고 다음 순서대로 한 단계씩 진행해라.

1. SLC, TLC와 SLC cache가 필요한 이유
2. NVMeVirt Conventional FTL의 전체 구조
3. channel, lun, block, page, line의 관계
4. logical page와 physical page 및 mapping table
5. 기존 host write 경로
6. 기존 host read 경로
7. line manager와 write pointer
8. 기존 TLC garbage collection 경로
9. SLC/TLC line manager를 분리해야 하는 이유
10. SLC→TLC migration의 전체 흐름
11. SLC와 TLC의 oneshot page size 차이
12. Greedy, Random, FIFO, Cost-Benefit migration 정책

각 단계마다 다음 형식을 따라라.

- 먼저 코드 없이 일상적인 비유로 설명
- 그다음 SSD/FTL 개념으로 설명
- 현재 저장소에서 관련 파일, 구조체, 함수 찾기
- 실제 코드를 짧게 인용해 한 줄씩 설명
- 함수 호출 흐름 정리
- 실습2에서 무엇이 달라져야 하는지 설명
- 내가 반드시 기억할 핵심 3개 정리
- 이해 확인 질문 2~3개 제시

한 번에 한 단계만 진행하고, 내가 질문하거나 이해했다고 말하면 다음 단계로 넘어가라.

현재 코드와 다른 내용을 일반론으로 단정하지 마라. 코드에 관한 설명에는 실제 파일명, 구조체명, 함수명과 가능한 경우 줄 번호를 제시해라.

지금은 어떤 코드, Git branch, 설정 또는 파일도 변경하지 마라.

먼저 1단계인 “SLC, TLC와 SLC cache가 필요한 이유”부터 설명해라.

---

## 진행 순서

1. SLC, TLC와 SLC cache가 필요한 이유
2. NVMeVirt Conventional FTL의 전체 구조
3. channel, lun, block, page, line의 관계
4. logical page와 physical page 및 mapping table
5. 기존 host write 경로
6. 기존 host read 경로
7. line manager와 write pointer
8. 기존 TLC garbage collection 경로
9. SLC/TLC line manager를 분리해야 하는 이유
10. SLC→TLC migration의 전체 흐름
11. SLC와 TLC의 oneshot page size 차이
12. Greedy, Random, FIFO, Cost-Benefit migration 정책

---

## 학습 기록

### 1. SLC, TLC와 SLC cache가 필요한 이유

- 상태: 완료
- 한줄 요약: SLC cache는 host write를 먼저 빠르게 받아 주는 임시 고속 공간이고, TLC는 더 큰 저장 공간이며, 실습2는 이 둘을 함께 다루는 구조를 Conventional FTL에 추가하는 과제다.
- 비유: 가게 계산대 옆 임시 보관대와 창고 선반의 관계로 이해할 수 있다. 손님이 가져온 물건을 먼저 계산대 옆 보관대에 빨리 올려두면 응대가 빨리 끝난다. 이후 직원이 한가할 때 그 물건을 창고 깊숙한 선반으로 옮긴다. 여기서 보관대가 SLC, 창고 선반이 TLC다.
- SSD/FTL 개념:
  - SLC는 한 셀에 저장하는 정보가 적어 보통 쓰기와 읽기 판단이 더 단순하다.
  - TLC는 한 셀에 더 많은 정보를 저장하므로 더 큰 용량을 만들기 좋지만, 보통 프로그램/읽기 동작이 더 까다롭다.
  - 그래서 FTL은 빠른 쓰기 응답을 위해 host write를 먼저 SLC에 기록하고, SLC가 차면 valid data를 TLC로 옮겨 SLC 공간을 다시 회수하는 구조를 사용할 수 있다.
  - 실습2의 핵심은 바로 이 흐름을 NVMeVirt Conventional FTL 위에 구현하는 것이다.
- 현재 코드 근거:
  - 과제 자료는 실습2 대상이 `SLC cache + TLC 영역`이라고 명시한다.
    - [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS) `57~60행`
  - 과제 자료는 기본 write가 SLC로 가고, SLC가 차면 TLC로 migration한다고 설명한다.
    - [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS) `135~152행`
    - [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS) `166~202행`
  - 하지만 현재 저장소의 `ssd_config.h`는 Samsung Conventional profile에 단일 `CELL_MODE`, 단일 `ONESHOT_PAGE_SIZE`, 단일 `NAND_PROG_LATENCY`만 둔다.
    - [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h#L71)
    - [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h#L78)
    - [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h#L95)
  - `ssd_init_params()`도 이 단일 설정값을 SSD 전체 파라미터로 넣는다.
    - [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L79)
    - [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L101)
    - [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L117)
- 실습2에서 달라질 점:
  - 현재는 SSD 전체가 하나의 cell mode처럼 동작한다.
  - 실습2에서는 개념상 빠른 SLC 영역과 큰 TLC 영역을 구분해야 한다.
  - 기본 host write는 SLC에 먼저 기록되어야 한다.
  - SLC가 차면 valid data를 TLC로 옮기고, SLC 공간을 다시 free 상태로 돌려야 한다.
  - read는 최신 데이터가 SLC에 있는지 TLC에 있는지에 따라 위치를 따라가야 한다.
- 기억할 핵심 3개:
  - SLC cache의 목적은 host write를 먼저 빠르게 받아 주는 임시 고속 구간을 만드는 것이다.
  - TLC는 더 큰 저장 공간 역할을 하며, SLC가 가득 차면 valid data를 TLC로 옮겨야 한다.
  - 현재 저장소 코드는 아직 SLC/TLC를 따로 모델링하지 않고, 단일 `CELL_MODE`, 단일 `ONESHOT_PAGE_SIZE`, 단일 `NAND_PROG_LATENCY`를 사용한다.
- 이해 확인 질문:
  - 왜 처음부터 모든 host write를 TLC에만 쓰지 않고, 먼저 SLC에 쓰는 구조를 생각할 수 있을까?
  - 현재 코드가 아직 SLC/TLC 분리 구조가 아니라고 판단할 수 있는 가장 직접적인 파일은 무엇인가?
  - 실습2에서 SLC가 가득 찼을 때 핵심 동작은 무엇인가?

### 2. NVMeVirt Conventional FTL의 전체 구조

- 상태: 완료
- 상세 설명:

이번 단계는 “이 코드베이스에서 Conventional FTL이 전체적으로 어떻게 생겼는가”만 본다. 아직 SLC cache 구현은 들어가지 않는다.

일상적인 비유로 먼저 설명하면 이 구조는 “도서관 대출 시스템”처럼 볼 수 있다.

- `main.c`는 도서관 건물 운영자다. 손님이 들어오면 어떤 코너로 보낼지 정한다.
- `namespace`는 도서관 안의 한 구역이다.
- `conv_ftl`은 그 구역의 실제 대출 관리 담당자다.
- `maptbl`은 “이 책 번호가 현재 어느 서가 칸에 있는지” 적어둔 장부다.
- `rmap`은 반대로 “이 서가 칸에는 지금 어떤 책 번호가 들어 있는지” 적어둔 장부다.
- `line manager`는 비어 있는 서가 줄, 가득 찬 서가 줄, 정리 대상 줄을 관리한다.
- `write pointer`는 “다음 새 책을 어디 칸에 꽂을지” 가리키는 손가락이다.
- `read/write` 함수는 실제 대출/반납 업무이고, `GC`는 오래된 서가를 정리해 공간을 되찾는 작업이다.

즉, Conventional FTL은 “논리 주소를 실제 물리 페이지에 배치하고, 읽고, 쓰고, 공간이 모자라면 정리하는 관리자”다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- `NVMeVirt`는 가상 NVMe 장치 전체를 흉내 내는 큰 시스템이다.
- 그 안에서 `Conventional FTL`은 일반 block SSD처럼 동작하는 저장 계층이다.
- 이 FTL은 적어도 다음 일을 한다.
  - SSD 파라미터를 받아 내부 구조를 초기화한다.
  - mapping table과 reverse mapping table을 만든다.
  - free line, victim line, full line 상태를 관리한다.
  - host write 시 새 physical page를 할당한다.
  - host read 시 mapping table을 따라 physical page를 찾는다.
  - free line이 부족하면 GC를 돌려 공간을 회수한다.
- 현재 구조는 “단일 공간을 관리하는 Conventional FTL”이다. 아직 SLC 영역과 TLC 영역으로 나뉘지 않았다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음이다.

- FTL 핵심 구조체: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L71)
- `line` / `write_pointer` / `line_mgmt`: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L31), [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L43), [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L52)
- FTL 초기화: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L451)
- namespace에 Conventional FTL 붙이기: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L495)
- NVMeVirt 전체 초기화에서 Conventional namespace 생성: [main.c](/home/hjyu216/nvmevirt/main.c#L611), [main.c](/home/hjyu216/nvmevirt/main.c#L697)
- I/O 명령 분기: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1206)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
struct conv_ftl {
	struct ssd *ssd;
	struct convparams cp;
	struct ppa *maptbl;
	uint64_t *rmap;
	struct write_pointer wp;
	struct write_pointer gc_wp;
	struct line_mgmt lm;
	struct write_flow_control wfc;
};
```

- `struct ssd *ssd;`
  이 FTL이 관리할 실제 SSD 모델/파라미터를 가리킨다.
- `struct convparams cp;`
  GC threshold 같은 Conventional FTL 정책 파라미터다.
- `struct ppa *maptbl;`
  논리 페이지에서 물리 페이지로 가는 메인 장부다.
- `uint64_t *rmap;`
  물리 페이지에서 논리 페이지로 역으로 찾는 장부다.
- `struct write_pointer wp;`
  host write가 다음에 쓸 위치다.
- `struct write_pointer gc_wp;`
  GC가 valid page를 옮겨 적을 위치다.
- `struct line_mgmt lm;`
  free/full/victim line 상태를 한곳에서 관리한다.
- `struct write_flow_control wfc;`
  write credit 기반으로 foreground GC를 제어한다.

```c
init_maptbl(conv_ftl);
init_rmap(conv_ftl);
init_lines(conv_ftl);
prepare_write_pointer(conv_ftl, USER_IO);
prepare_write_pointer(conv_ftl, GC_IO);
init_write_flow_control(conv_ftl);
```

- `init_maptbl`
  mapping table을 만든다.
- `init_rmap`
  reverse mapping table을 만든다.
- `init_lines`
  line 전체를 관리 가능한 상태로 초기화한다.
- `prepare_write_pointer(..., USER_IO)`
  host write용 쓰기 위치를 준비한다.
- `prepare_write_pointer(..., GC_IO)`
  GC 이동용 쓰기 위치를 따로 준비한다.
- `init_write_flow_control`
  write credit 구조를 준비한다.

```c
ssd_init_params(&spp, size, nr_parts);
conv_init_params(&cpp);
conv_ftls = kmalloc(sizeof(struct conv_ftl) * nr_parts, GFP_KERNEL);
```

- `ssd_init_params`
  SSD geometry와 latency 같은 하드웨어 모델 파라미터를 계산한다.
- `conv_init_params`
  Conventional FTL 정책 파라미터를 채운다.
- `kmalloc(...)`
  FTL 인스턴스 배열을 메모리에 만든다.

```c
if (NS_SSD_TYPE(i) == SSD_TYPE_NVM)
	simple_init_namespace(&ns[i], i, size, ns_addr, disp_no);
else if (NS_SSD_TYPE(i) == SSD_TYPE_CONV)
	conv_init_namespace(&ns[i], i, size, ns_addr, disp_no);
```

- namespace 타입이 `SSD_TYPE_CONV`이면 Conventional FTL을 붙인다.
- 즉, NVMeVirt 전체 시스템 안에 여러 FTL 종류가 있을 수 있고, 그중 하나가 지금 보는 Conventional FTL이다.

```c
switch (cmd->common.opcode) {
case nvme_cmd_write:
	if (!conv_write(ns, req, ret))
case nvme_cmd_read:
	if (!conv_read(ns, req, ret))
```

- 실제 NVMe read/write 명령이 들어오면 Conventional FTL의 `conv_write`, `conv_read`로 내려간다.
- 따라서 이 두 함수가 host I/O의 핵심 입구다.

함수 호출 흐름은 이렇게 정리할 수 있다.

1. 모듈 초기화에서 [main.c](/home/hjyu216/nvmevirt/main.c#L680) `NVMeV_init()`가 시작된다.
2. 그 안에서 [main.c](/home/hjyu216/nvmevirt/main.c#L697) `NVMEV_NAMESPACE_INIT()`가 namespace를 만든다.
3. namespace 타입이 Conventional이면 [main.c](/home/hjyu216/nvmevirt/main.c#L614) `conv_init_namespace()`를 부른다.
4. `conv_init_namespace()`는 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L505) `ssd_init_params()`와 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L513) `conv_init_ftl()`로 SSD와 FTL 자료구조를 준비한다.
5. 이후 namespace의 I/O handler로 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L533) `conv_proc_nvme_io_cmd`가 등록된다.
6. 실제 read/write 명령이 오면 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1206) `conv_proc_nvme_io_cmd()`가 opcode를 보고 `conv_write()` 또는 `conv_read()`로 보낸다.
7. 그 아래에서 mapping, write pointer, line manager, GC가 협력해 실제 저장 동작을 처리한다.

실습2에서 무엇이 달라져야 하는지도 여기서 보인다.

현재 구조의 특징:

- `maptbl` 하나
- `rmap` 하나
- `line_mgmt lm` 하나
- host write pointer `wp` 하나
- GC write pointer `gc_wp` 하나

즉, “한 종류의 공간”을 관리하는 구조다.

실습2에서는 이 전체 골격은 유지하되, 내부 관리 대상을 둘로 나눠야 한다.

- SLC line manager
- TLC line manager
- SLC host write pointer
- TLC migration destination pointer
- 기존 TLC GC pointer/경로

하지만 중요한 점은, 과제 요구사항상 mapping table은 둘로 나누지 않는 방향이다. 그래서 “FTL 전체 구조는 유지하면서, 내부 저장 영역 관리만 SLC/TLC로 분리”하는 쪽이 자연스럽다.

반대로 `maptbl`과 `rmap`의 역할은 다음처럼 기억하면 된다.

- `maptbl`: `LPN -> PPA`
  - 논리 페이지 번호를 주면 현재 최신 데이터가 있는 물리 페이지를 찾는 표다.
  - read 때 직접 많이 쓰이고, write 때도 overwrite가 있으면 예전 위치를 찾을 때 쓴다.
- `rmap`: `PPA -> LPN`
  - 어떤 물리 페이지를 보고 “이 페이지가 현재 어떤 논리 페이지의 데이터였지?”를 찾는 표다.
  - 그래서 GC나 migration처럼 physical page를 훑으면서 valid data를 옮길 때 특히 중요하다.

즉, 이렇게 기억하면 된다.

- `maptbl`은 host 입장에서 주소를 찾는 정방향 장부
- `rmap`은 physical page 정리 작업에서 역으로 추적하는 장부
- 둘 다 read/write/GC 전체에 걸쳐 쓰일 수 있지만, 주된 용도가 다르다

네가 반드시 기억할 핵심 3개는 다음과 같다.

- Conventional FTL은 읽기/쓰기/매핑/공간 회수를 맡는 저장 관리 계층이다.
- 현재 코드의 핵심 상태는 `struct conv_ftl` 하나에 `maptbl`, `rmap`, `lm`, `wp`, `gc_wp`로 모여 있다.
- 실습2는 이 전체 틀을 버리는 작업이 아니라, 이 틀 안에 SLC/TLC 구분을 추가하는 작업이다.

- 간단 요약: `main.c`가 Conventional FTL을 선택해 namespace에 붙이고, `conv_ftl.c`가 `maptbl`, `rmap`, `line manager`, `write pointer` 등을 초기화해 실제 read/write/GC를 처리하는 구조다.

### 3. channel, lun, block, page, line의 관계

- 상태: 완료
- 상세 설명:

이번 단계는 SSD 내부 공간이 어떤 계층으로 묶이는지 보는 단계다. 지금은 SLC/TLC는 잠깐 잊고, 현재 Conventional FTL이 물리 공간을 어떻게 바라보는지만 본다.

아파트 단지 비유로 생각하면 이해하기 쉽다.

- `channel`은 아파트 동이다.
- `lun`은 한 동 안의 층 또는 별도 구역이다.
- `plane`은 그 층 안의 한쪽 라인 정도로 생각할 수 있다.
- `block`은 실제 한 세대 묶음이다.
- `page`는 세대 안의 방 하나다.
- `line`은 “모든 동과 구역에 걸쳐 같은 세대 번호만 모아놓은 가로 묶음”이다.

즉, `line`은 단순히 block 하나가 아니다. 여러 channel, 여러 lun에 있는 “같은 block 번호”들을 한꺼번에 묶어 관리하는 큰 단위다. 그래서 write pointer가 line 하나를 잡으면, 그 line 안에서 channel/lun을 돌면서 페이지를 채워 나간다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- `page`는 FTL의 기본 매핑 단위다.
- `block`은 erase 단위다. 페이지는 하나씩 invalid/valid가 바뀔 수 있지만, erase는 block 전체에 대해 일어난다.
- `lun`은 NAND 동작 단위에 가깝다.
- `channel`은 SSD 컨트롤러와 NAND 사이 데이터 이동 통로다.
- 현재 NVMeVirt는 이 계층을 주소 `ppa` 안에 `ch`, `lun`, `pl`, `blk`, `pg`로 나눠 저장한다.
- 그리고 `line`은 FTL이 GC와 write allocation을 쉽게 하기 위해 만든 super-block 비슷한 관리 단위다.
- 현재 코드에서 line의 개수는 `blks_per_pl`와 같고, `line id == block id`다. 즉, 같은 `blk` 번호를 가진 블록들 묶음이 하나의 line이다.

추가로 `plane`은 LUN 안에 있는 더 작은 병렬 단위다.

- `channel` = 큰 도로
- `LUN` = 건물 한 동
- `plane` = 그 동 안의 한쪽 창고 구역
- `block` = 창고 선반 한 칸 묶음
- `page` = 선반 한 칸 안의 작은 칸

현재 코드 기준으로는 `plane` 구조체가 있고, `ppa`에도 `pl` 필드가 따로 있다. 다만 현재 Samsung Conventional 설정은 [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h#L76)에서 `PLNS_PER_LUN (1)`이므로 개념적으로는 존재하지만 실습 중에는 크게 체감되지 않을 수 있다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음이다.

- 물리 주소 구조 `struct ppa`: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L62)
- SSD 계층 구조체들: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L85), [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L91), [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L100), [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L106), [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L114)
- 계층 설명 주석: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L140)
- 계산된 geometry 값: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L148)
- geometry 계산: [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L134), [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L140), [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L156), [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L158)
- line 초기화: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L224)
- `ppa -> line` 연결: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L601)
- `ppa -> 전체 페이지 인덱스` 계산: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L85)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
struct ppa {
	union {
		struct {
			uint64_t pg : PAGE_BITS;
			uint64_t blk : BLK_BITS;
			uint64_t pl : PL_BITS;
			uint64_t lun : LUN_BITS;
			uint64_t ch : CH_BITS;
```

- `pg`
  페이지 번호다.
- `blk`
  블록 번호다.
- `pl`
  plane 번호다.
- `lun`
  LUN 번호다.
- `ch`
  channel 번호다.

즉, physical page address 하나가 “어느 channel / 어느 lun / 어느 plane / 어느 block / 어느 page인가”를 담고 있다.

```c
pg (page): Mapping unit (4KB)
flashpg (flash page) : Nand sensing unit , tR
oneshotpg (oneshot page) : Nand program unit, tPROG
blk (block): Nand erase unit
lun (die) : Nand operation unit
ch (channel) : Nand <-> SSD controller data transfer unit
```

- `page`
  FTL이 논리 주소와 연결하는 가장 기본 단위다.
- `block`
  지울 때 한 번에 지우는 단위다.
- `lun`
  NAND 내부 동작 단위다.
- `channel`
  데이터가 오가는 큰 통로다.

```c
spp->pgs_per_pl = spp->pgs_per_blk * spp->blks_per_pl;
spp->pgs_per_lun = spp->pgs_per_pl * spp->pls_per_lun;
spp->pgs_per_ch = spp->pgs_per_lun * spp->luns_per_ch;
spp->tt_pgs = spp->pgs_per_ch * spp->nchs;
```

- 한 plane의 전체 페이지 수를 먼저 계산한다.
- 그걸 모아 한 LUN의 페이지 수를 계산한다.
- 그걸 모아 한 channel의 페이지 수를 계산한다.
- 마지막으로 SSD 전체 페이지 수를 계산한다.

즉, 작은 단위를 곱해서 큰 단위를 만드는 계층 구조다.

```c
spp->pgs_per_line = spp->blks_per_line * spp->pgs_per_blk;
spp->tt_lines = spp->blks_per_lun;
```

- `line`도 페이지 수를 가진다.
- 그리고 전체 line 수는 `blks_per_lun`으로 잡는다.

이 부분이 처음엔 이상해 보일 수 있는데, 이유는 line이 block 하나가 아니라 “각 channel/lun/plane에 있는 같은 block index들의 묶음”이기 때문이다.

```c
lm->tt_lines = spp->blks_per_pl;
```

- line manager는 line 개수를 `blks_per_pl` 기준으로 잡는다.
- 현재 코드에서는 사실상 “plane마다 block 번호가 몇 개 있느냐”가 line 개수와 연결된다.

```c
int id; /* line id, the same as corresponding block id */
```

- line id는 대응되는 block id와 같다.
- 즉, `blk = 17`인 블록들을 가로로 묶은 전체가 `line 17` 같은 식으로 이해하면 된다.

```c
static inline struct line *get_line(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return &(conv_ftl->lm.lines[ppa->g.blk]);
}
```

- 어떤 physical page가 속한 line을 찾을 때 `blk` 번호만 본다.
- 이게 바로 “같은 block 번호를 공유하는 묶음이 하나의 line”이라는 뜻이다.

```c
pgidx = ppa->g.ch * spp->pgs_per_ch + ppa->g.lun * spp->pgs_per_lun +
	ppa->g.pl * spp->pgs_per_pl + ppa->g.blk * spp->pgs_per_blk + ppa->g.pg;
```

- 전체 SSD를 1차원 배열처럼 펼쳤다고 생각하고,
- `channel -> lun -> plane -> block -> page` 순서로 오프셋을 더해
- 최종 페이지 인덱스를 만든다.

이 식은 각 계층이 어떻게 중첩되는지 아주 직접적으로 보여 준다.

함수 호출 흐름 관점에서 정리하면 다음과 같다.

1. [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L68) `ssd_init_params()`가 `nchs`, `luns_per_ch`, `pls_per_lun`, `blks_per_pl`, `pgs_per_blk` 등을 계산한다.
2. 이 계산 결과가 `struct ssdparams`에 저장된다.
3. [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L224) `init_lines()`는 이 geometry를 바탕으로 line 배열을 만든다.
4. 이후 write/read/GC 중 physical address `ppa`를 다룰 때, 필요하면 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L601) `get_line()`으로 해당 페이지가 속한 line을 찾는다.
5. reverse map에서는 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L85) `ppa2pgidx()`로 `ppa`를 전체 인덱스로 바꿔 접근한다.

실습2에서 무엇이 달라져야 하는지도 여기서 중요하다.

- 지금은 모든 line이 같은 종류의 공간이다.
- 실습2에서는 이 line들 중 일부는 SLC line, 나머지는 TLC line이 되어야 한다.
- 하지만 `channel/lun/block/page`라는 물리 계층 자체가 바뀌는 것은 아니다.
- 바뀌는 것은 “이 line 묶음을 어떤 성격의 공간으로 관리할 것인가”다.
- 즉, geometry 자체를 새로 만드는 게 아니라, 기존 line 집합을 SLC용/TLC용으로 나눠 관리하는 방향이 자연스럽다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- `ppa`는 `channel`, `lun`, `plane`, `block`, `page`를 담는 물리 주소다.
- `line`은 block 하나가 아니라, 같은 `blk` 번호를 가진 블록들을 channel/lun/plane 전체에 걸쳐 묶은 관리 단위다.
- 실습2에서는 물리 계층을 바꾸는 게 아니라, 기존 line들을 SLC line과 TLC line으로 나눠 관리하게 된다.

- 간단 요약: SSD 물리 계층은 `channel -> lun -> plane -> block -> page` 순서이고, `line`은 같은 `block id`를 가진 블록 묶음을 FTL이 관리하기 위해 만든 상위 단위다.

### 4. logical page와 physical page 및 mapping table

- 상태: 완료
- 상세 설명:

이번 단계는 host가 보는 주소와 SSD 안의 실제 위치가 왜 다른지, 그리고 그 사이를 `mapping table`이 어떻게 연결하는지 설명하는 단계다.

택배 창고 비유로 생각하면 쉽다.

- 손님은 “주문번호 103번 물건 주세요”라고 말한다.
- 창고 직원은 “103번 주문 물건은 지금 선반 B-7-12에 있음”을 알고 있어야 꺼낼 수 있다.
- 여기서 `주문번호`가 `logical page`이고,
- `선반 B-7-12`가 `physical page`다.
- 그리고 “주문번호 -> 선반 위치”를 적어 둔 장부가 `mapping table`이다.

중요한 점은, 물건이 옮겨질 수 있다는 것이다.

- 예전에는 주문번호 103번이 선반 A-2에 있었는데,
- 정리하다가 B-7-12로 옮겼다면,
- 장부만 새 위치로 고치면 손님은 계속 “103번”만 말해도 된다.

즉, host는 내부 위치를 몰라도 되고, FTL이 그 연결을 책임진다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- `logical page`는 host 관점의 논리 주소 단위다.
- `physical page`는 NAND 안의 실제 저장 위치다.
- SSD는 overwrite를 제자리에서 간단히 덮어쓰기 어렵기 때문에, 보통 새 physical page에 쓰고 mapping만 바꾼다.
- NAND SSD는 page 단위 overwrite가 어렵고 erase는 block 전체 단위라 비싸기 때문에, FTL은 보통 “새 page에 쓰고 예전 page는 invalid 처리한 뒤 나중에 GC”하는 구조를 사용한다.
- 그래서 FTL은 최소한 두 가지를 알아야 한다.
  - 어떤 `LPN(logical page number)`이 지금 어느 `PPA(physical page address)`에 있는가
  - 어떤 `PPA`가 현재 어떤 `LPN`의 데이터인가
- 현재 코드에서 이 역할이 각각 `maptbl`과 `rmap`이다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- `UNMAPPED_PPA`, `INVALID_LPN`: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L24)
- `struct ppa`: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L62)
- `maptbl`, `rmap` 필드: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L71)
- 매핑 접근 함수: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L74)
- reverse mapping 접근 함수: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L101)
- 매핑 초기화: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L419)
- 유효성 확인: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L591)
- read에서 mapping 사용: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L993)
- write에서 mapping 갱신: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1085)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
struct ppa *maptbl; /* page level mapping table */
uint64_t *rmap; /* reverse mapptbl, assume it's stored in OOB */
```

- `maptbl`
  논리 페이지 번호를 주면 물리 페이지 주소를 돌려주는 표다.
- `rmap`
  물리 페이지 위치를 주면 그곳에 있던 논리 페이지 번호를 찾는 역방향 표다.

```c
static inline struct ppa get_maptbl_ent(struct conv_ftl *conv_ftl, uint64_t lpn)
{
	return conv_ftl->maptbl[lpn];
}
```

- `lpn`을 인덱스로 써서,
- 그 논리 페이지의 현재 물리 위치 `ppa`를 읽는다.

```c
static inline void set_maptbl_ent(struct conv_ftl *conv_ftl, uint64_t lpn, struct ppa *ppa)
{
	NVMEV_ASSERT(lpn < conv_ftl->ssd->sp.tt_pgs);
	conv_ftl->maptbl[lpn] = *ppa;
}
```

- 특정 `lpn`의 최신 위치를 새 `ppa`로 바꾼다.
- overwrite나 migration 후에 “이제 최신본은 여기 있음”이라고 장부를 고치는 동작이다.

```c
static inline uint64_t get_rmap_ent(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	uint64_t pgidx = ppa2pgidx(conv_ftl, ppa);
	return conv_ftl->rmap[pgidx];
}
```

- `ppa`를 전체 배열 인덱스로 바꾼 뒤,
- 그 physical page가 누구(`lpn`)의 것인지 찾는다.

```c
static inline void set_rmap_ent(struct conv_ftl *conv_ftl, uint64_t lpn, struct ppa *ppa)
{
	uint64_t pgidx = ppa2pgidx(conv_ftl, ppa);
	conv_ftl->rmap[pgidx] = lpn;
}
```

- 어떤 physical page에 이제 어떤 `lpn` 데이터가 들어갔는지 기록한다.

```c
conv_ftl->maptbl = vmalloc(sizeof(struct ppa) * spp->tt_pgs);
for (i = 0; i < spp->tt_pgs; i++) {
	conv_ftl->maptbl[i].ppa = UNMAPPED_PPA;
}
```

- 처음에는 어떤 logical page도 아직 아무 physical page에 연결되지 않았으므로,
- 전부 `UNMAPPED_PPA`로 시작한다.

```c
conv_ftl->rmap = vmalloc(sizeof(uint64_t) * spp->tt_pgs);
for (i = 0; i < spp->tt_pgs; i++) {
	conv_ftl->rmap[i] = INVALID_LPN;
}
```

- 처음에는 어떤 physical page도 유효한 logical page를 담고 있지 않으므로,
- 전부 `INVALID_LPN`으로 시작한다.

```c
static inline bool valid_lpn(struct conv_ftl *conv_ftl, uint64_t lpn)
{
	return (lpn < conv_ftl->ssd->sp.tt_pgs);
}
```

- 이 logical page 번호가 FTL 범위 안에 있는지 확인한다.

```c
static inline bool mapped_ppa(struct ppa *ppa)
{
	return !(ppa->ppa == UNMAPPED_PPA);
}
```

- 이 logical page가 아직 어디에도 안 써졌는지,
- 아니면 실제 physical page에 매핑되어 있는지 확인한다.

함수 호출 흐름을 read/write 중심으로 보면 이렇다.

1. host가 read/write를 보낸다.
2. `conv_read()`와 `conv_write()`는 먼저 `LBA` 범위를 `LPN` 범위로 바꾼다.
3. read에서는 `maptbl[LPN]`을 보고 현재 `PPA`를 찾는다.
4. write에서는 먼저 `maptbl[LPN]`을 보고 예전 `PPA`가 있으면 old page를 invalid 처리한다.
5. 그 다음 새 physical page를 할당한다.
6. 새 위치에 맞춰 `maptbl[LPN] = new PPA`로 갱신한다.
7. 동시에 `rmap[new PPA] = LPN`도 갱신한다.

read 쪽 코드를 짧게 보면 다음과 같다.

```c
uint64_t start_lpn = lba / spp->secs_per_pg;
uint64_t end_lpn = (lba + nr_lba - 1) / spp->secs_per_pg;
```

- host가 준 sector 단위 주소를 logical page 번호 범위로 바꾼다.

```c
local_lpn = lpn / nr_parts;
cur_ppa = get_maptbl_ent(conv_ftl, local_lpn);
if (!mapped_ppa(&cur_ppa) || !valid_ppa(conv_ftl, &cur_ppa)) {
	continue;
}
```

- 해당 logical page의 physical 위치를 mapping table에서 찾는다.
- 아직 안 써졌거나 잘못된 주소면 읽을 대상이 없다.
- 즉, read는 mapping을 따라 physical page를 찾는 동작이다.

write 쪽 코드를 보면 다음과 같다.

```c
ppa = get_maptbl_ent(conv_ftl, local_lpn);
if (mapped_ppa(&ppa)) {
	mark_page_invalid(conv_ftl, &ppa);
	set_rmap_ent(conv_ftl, INVALID_LPN, &ppa);
}
```

- 먼저 이 logical page가 예전에 어디 있었는지 찾는다.
- 예전 위치가 있으면 그 old physical page를 invalid로 바꾼다.
- reverse map도 지워 준다.

```c
ppa = get_new_page(conv_ftl, USER_IO);
set_maptbl_ent(conv_ftl, local_lpn, &ppa);
set_rmap_ent(conv_ftl, local_lpn, &ppa);
```

- 새 physical page를 하나 할당한다.
- 이제 그 logical page의 최신 위치를 새 physical page로 바꾼다.
- 정방향 장부와 역방향 장부를 같이 갱신한다.

실습2에서 무엇이 달라져야 하는지도 여기서 핵심이다.

- 과제 요구사항은 mapping table을 하나만 쓰라고 한다.
- 즉, `SLC용 maptbl`과 `TLC용 maptbl` 두 개를 만들면 안 된다.
- 대신 하나의 `maptbl`이 “최신 데이터가 지금 SLC에 있는지, TLC에 있는지”를 포함한 `PPA`를 가리켜야 한다.
- migration이 일어나면 logical page는 그대로이고, physical location만 `SLC PPA -> TLC PPA`로 바뀐다.
- 그래서 실습2에서도 핵심은 “매핑을 둘로 나누는 것”이 아니라 “하나의 매핑이 서로 다른 영역의 physical page를 가리킬 수 있게 하는 것”이다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- `logical page`는 host가 보는 논리 번호이고, `physical page`는 NAND 안의 실제 위치다.
- `maptbl`은 `LPN -> PPA`, `rmap`은 `PPA -> LPN` 역할을 한다.
- 실습2에서도 mapping table은 하나를 유지하고, migration 후에는 그 하나의 mapping이 새 TLC 위치를 가리키도록 바뀌어야 한다.

- 간단 요약: host는 logical page만 보고, FTL은 `maptbl`과 `rmap`으로 그것을 실제 physical page에 연결한다. overwrite나 migration이 생기면 논리 번호는 그대로 두고 물리 위치만 바꾼다.

### 5. 기존 host write 경로

- 상태: 완료
- 상세 설명:

이번 단계는 host가 write 요청을 보내면 현재 Conventional FTL 안에서 실제로 어떤 순서로 일이 일어나는가를 설명하는 단계다.

택배 접수 창구 비유로 생각하면 된다.

- 손님이 택배를 맡긴다.
- 창구 직원은 먼저 임시 보관대에 자리가 있는지 본다.
- 이미 같은 주문번호 물건이 있으면, 예전 물건에는 “오래된 것” 표시를 한다.
- 새 보관 위치를 하나 잡는다.
- 장부에 “이 주문번호의 최신 위치는 이제 여기”라고 적는다.
- 물건을 실제로 그 위치에 올려둔다.
- 다음 빈 칸으로 담당자의 손가락을 옮긴다.
- 보관대가 모자라면 뒤쪽 정리 작업(GC)을 시킨다.

현재 코드의 host write도 거의 이 순서다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- write 요청은 `LBA`로 들어온다.
- FTL은 이것을 `LPN` 범위로 바꾼다.
- write buffer 공간을 먼저 확보한다.
- 각 logical page에 대해:
  - 예전 매핑이 있으면 old physical page를 invalid 처리한다.
  - 새 physical page를 write pointer에서 하나 받는다.
  - `maptbl`, `rmap`을 새 위치로 갱신한다.
  - page 상태를 valid로 바꾼다.
  - write pointer를 다음 위치로 전진시킨다.
- oneshot program 단위가 채워지면 실제 NAND write timing 모델을 진행한다.
- write credit을 소모하고, free line이 부족하면 foreground GC를 유도한다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- write 진입점: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1085)
- user write pointer 준비: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L311)
- 새 page 할당: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L402)
- write pointer 전진: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L330)
- old page invalid 처리: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L607)
- new page valid 처리: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L659)
- write buffer 할당: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L266), [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1121)
- NAND write timing 진행: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L260), [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1161)
- write credit 제어: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L207), [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L214)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
uint64_t lba = cmd->rw.slba;
uint64_t nr_lba = (cmd->rw.length + 1);
uint64_t start_lpn = lba / spp->secs_per_pg;
uint64_t end_lpn = (lba + nr_lba - 1) / spp->secs_per_pg;
```

- host는 sector 단위 `LBA`로 요청한다.
- FTL은 이를 내부 매핑 단위인 `LPN` 범위로 바꾼다.

```c
allocated_buf_size = buffer_allocate(wbuf, LBA_TO_BYTE(nr_lba));
if (allocated_buf_size < LBA_TO_BYTE(nr_lba))
	return false;
```

- 먼저 SSD write buffer에 이 요청을 담을 자리가 있는지 확인한다.
- 자리가 부족하면 write를 진행하지 못한다.

```c
nsecs_latest =
	ssd_advance_write_buffer(conv_ftl->ssd, req->nsecs_start, LBA_TO_BYTE(nr_lba));
```

- write buffer에 들어가는 시간 모델을 먼저 반영한다.
- 즉, host write는 바로 NAND로 직행하지 않고, 먼저 write buffer 단계를 거친다.

```c
ppa = get_maptbl_ent(conv_ftl, local_lpn);
if (mapped_ppa(&ppa)) {
	mark_page_invalid(conv_ftl, &ppa);
	set_rmap_ent(conv_ftl, INVALID_LPN, &ppa);
}
```

- 이 logical page가 예전에 이미 써진 적 있는지 먼저 확인한다.
- 있으면 예전 physical page는 더 이상 최신본이 아니므로 invalid 처리한다.
- reverse map도 지운다.

```c
ppa = get_new_page(conv_ftl, USER_IO);
set_maptbl_ent(conv_ftl, local_lpn, &ppa);
set_rmap_ent(conv_ftl, local_lpn, &ppa);
mark_page_valid(conv_ftl, &ppa);
```

- user write pointer가 가리키는 새 physical page를 하나 받는다.
- mapping table과 reverse mapping table을 새 위치로 갱신한다.
- 새 physical page를 valid 상태로 표시한다.

`get_new_page()`는 실제로 write pointer가 현재 가리키는 좌표를 `ppa`로 꺼내는 함수다.

```c
ppa.g.ch = wp->ch;
ppa.g.lun = wp->lun;
ppa.g.pg = wp->pg;
ppa.g.blk = wp->blk;
ppa.g.pl = wp->pl;
```

- “다음에 쓸 위치”를 따로 검색하는 게 아니라,
- 현재 write pointer가 들고 있는 `ch/lun/pg/blk/pl` 값을 그대로 physical address로 만든다.

```c
advance_write_pointer(conv_ftl, USER_IO);
```

- 지금 한 page를 썼으니, 다음 write가 갈 위치로 포인터를 이동한다.

이 포인터는 page 하나 쓸 때마다 단순히 `pg++`만 하는 게 아니라, 현재 line 안에서 `channel -> lun -> 다음 wordline` 순서로 움직인다.

```c
wpp->pg++;
if ((wpp->pg % spp->pgs_per_oneshotpg) != 0)
	goto out;
```

- 우선 page를 하나 증가시킨다.
- 아직 oneshot page 단위가 다 안 찼으면 같은 wordline 흐름 안에 머문다.

```c
wpp->ch++;
if (wpp->ch != spp->nchs)
	goto out;
```

- oneshot 경계에 도달하면 다음 channel로 넘어간다.

```c
wpp->lun++;
if (wpp->lun != spp->luns_per_ch)
	goto out;
```

- channel도 다 돌았으면 다음 lun으로 넘어간다.

```c
wpp->pg = 0;
wpp->curline->mtime = cb_clock;
```

- line 하나를 다 쓰면 page를 처음으로 되돌리고,
- 이 line이 닫힌 시점을 기록한다.

```c
if (wpp->curline->vpc == spp->pgs_per_line) {
	list_add_tail(&wpp->curline->entry, &lm->full_line_list);
} else {
	pqueue_insert(lm->victim_line_pq, wpp->curline);
}
```

- line이 닫힐 때,
- 아직 모든 page가 valid면 full line으로 보낸다.
- 중간에 overwrite가 생겨 invalid page가 섞였으면 victim 후보 큐로 보낸다.

```c
if (last_pg_in_wordline(conv_ftl, &ppa)) {
	swr.ppa = &ppa;
	nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &swr);
}
```

- 매 page마다 바로 NAND program을 때리는 게 아니라,
- oneshot program 단위가 채워졌을 때 실제 NAND write timing을 진행한다.

```c
consume_write_credit(conv_ftl);
check_and_refill_write_credit(conv_ftl);
```

- write를 할 때마다 credit을 깎는다.
- credit이 바닥나면 foreground GC를 호출해 free space를 회복한다.

함수 호출 흐름을 한 번에 정리하면 이렇다.

1. `conv_proc_nvme_io_cmd()`가 write opcode를 받아 `conv_write()`를 부른다.
2. `conv_write()`는 `LBA -> LPN` 범위를 계산한다.
3. write buffer 공간을 할당하고, write buffer timing을 반영한다.
4. 각 `LPN`마다 기존 매핑이 있으면 old page를 invalid 처리한다.
5. `get_new_page(USER_IO)`로 새 `PPA`를 받는다.
6. `maptbl`, `rmap`, page status를 새 위치 기준으로 갱신한다.
7. `advance_write_pointer(USER_IO)`로 다음 위치로 이동한다.
8. oneshot 단위가 완성되면 `ssd_advance_nand()`로 실제 NAND write timing을 진행한다.
9. write credit을 소모하고 필요하면 GC를 유도한다.

실습2에서 무엇이 달라져야 하는지 설명하면 다음과 같다.

- 현재는 host write가 무조건 하나의 `USER_IO write pointer`로 간다.
- 즉, 모든 host write가 하나의 line space 안에 기록된다.
- 실습2에서는 이 host write의 목적지를 SLC 영역으로 보내야 한다.
- 따라서 “write 경로 전체를 새로 만드는 것”보다는,
  - host write가 쓰는 write pointer
  - host write가 소모하는 free line pool
  - line close 후 들어가는 queue
  이 세 가지의 의미를 SLC 기준으로 바꾸는 쪽이 핵심이다.
- 동시에 migration은 TLC 쪽 write pointer를 따로 써야 하므로, 현재 `USER_IO`와 `GC_IO`만 있는 구조가 실습2에서는 더 세분화될 가능성이 크다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- 현재 host write는 `LBA -> LPN 변환 -> old page invalid -> new PPA 할당 -> mapping 갱신 -> page valid -> write pointer 전진` 순서로 진행된다.
- 새 physical page는 `get_new_page()`가 현재 user write pointer 좌표를 읽어서 만든다.
- 실습2의 큰 변화는 “이 host write가 어느 공간에 쓰이느냐”를 기존 단일 공간에서 SLC 공간으로 바꾸는 데 있다.

- 간단 요약: 기존 host write는 단일 user write pointer가 가리키는 공간에 순차적으로 새 physical page를 할당하고, mapping을 갱신하며, free space가 부족해지면 GC를 유도하는 구조다.

### 6. 기존 host read 경로

- 상태: 완료
- 상세 설명:

이번 단계는 host가 read 요청을 보내면 현재 Conventional FTL이 어떻게 데이터를 찾는지 설명하는 단계다. write처럼 “새 위치를 만든다”는 동작은 없고, 이미 있는 mapping을 따라가는 것이 핵심이다.

도서관에서 책 찾는 상황으로 보면 쉽다.

- 손님이 “책 번호 103번 주세요”라고 한다.
- 사서는 책 번호 장부를 본다.
- 장부에 “103번은 B동 2층 7번 칸”이라고 적혀 있으면 그 위치로 간다.
- 만약 같은 책이 같은 선반 묶음에 연속으로 있으면, 한 번에 같이 꺼내 오는 편이 효율적이다.

현재 host read도 거의 비슷하다.

- host는 논리 주소를 준다.
- FTL은 mapping table에서 물리 위치를 찾는다.
- 유효한 위치만 읽는다.
- 같은 flash page에 있는 읽기들은 묶어서 처리한다.
- 최종적으로 NAND read timing을 계산해 완료 시간을 돌려준다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- read 요청은 `LBA`로 들어온다.
- FTL은 이를 `LPN` 범위로 바꾼다.
- 각 `LPN`에 대해 `maptbl`을 조회해 현재 `PPA`를 찾는다.
- `PPA`가 없거나 잘못된 주소면 읽지 않는다.
- host read 요청 하나는 “시작 주소 + 길이”를 가지므로 여러 `LPN`을 포함할 수 있다.
- 연속된 logical page라도, 실제 physical page 위치는 꼭 연속일 필요가 없다.
- 다만 현재 코드는 같은 `flash page` 안에 있는 read는 묶어서 한 번에 NAND로 보낸다.
- read는 write와 달리 mapping을 바꾸지 않는다. 단지 “최신 데이터가 어디 있는지” 찾아 그 위치를 읽는다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- read 진입점: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L993)
- mapping 확인: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L74)
- 매핑 여부/유효성 확인: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L567)
- 같은 flash page 판정: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L984)
- NAND read timing 모델: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L260), [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L362)
- firmware read latency 설정: [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L121)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
uint64_t lba = cmd->rw.slba;
uint64_t nr_lba = (cmd->rw.length + 1);
uint64_t start_lpn = lba / spp->secs_per_pg;
uint64_t end_lpn = (lba + nr_lba - 1) / spp->secs_per_pg;
```

- write 때와 마찬가지로,
- host가 준 sector 단위 주소를 내부 logical page 범위로 바꾼다.

```c
struct nand_cmd srd = {
	.type = USER_IO,
	.cmd = NAND_READ,
	.stime = nsecs_start,
	.interleave_pci_dma = true,
};
```

- read용 NAND 명령 구조를 만든다.
- 이 구조체에 나중에 어느 `PPA`를 얼마만큼 읽을지 넣어 실제 timing 모델로 보낸다.

```c
if (LBA_TO_BYTE(nr_lba) <= (KB(4) * nr_parts)) {
	srd.stime += spp->fw_4kb_rd_lat;
} else {
	srd.stime += spp->fw_rd_lat;
}
```

- read 크기에 따라 firmware overhead를 먼저 더한다.
- 즉, NAND read 이전에 FTL/펌웨어 처리 시간이 반영된다.

```c
local_lpn = lpn / nr_parts;
cur_ppa = get_maptbl_ent(conv_ftl, local_lpn);
if (!mapped_ppa(&cur_ppa) || !valid_ppa(conv_ftl, &cur_ppa)) {
	continue;
}
```

- 각 logical page에 대해 mapping table에서 현재 physical location을 찾는다.
- 아직 매핑되지 않았거나 유효하지 않은 주소면 그 항목은 읽지 않는다.

이 줄이 read 경로의 핵심이다. read는 결국 mapping table을 따라 physical page를 찾는 과정이다.

```c
static bool is_same_flash_page(struct conv_ftl *conv_ftl, struct ppa ppa1, struct ppa ppa2)
{
	uint32_t ppa1_page = ppa1.g.pg / spp->pgs_per_flashpg;
	uint32_t ppa2_page = ppa2.g.pg / spp->pgs_per_flashpg;
	return (ppa1.h.blk_in_ssd == ppa2.h.blk_in_ssd) && (ppa1_page == ppa2_page);
}
```

- 두 physical page가 같은 SSD block 묶음 안에 있고,
- 같은 flash page 단위에 속하는지 확인한다.
- 즉, 여러 4KB page가 실제 NAND sensing 단위에서는 같이 읽힐 수 있으면 묶으려는 것이다.

```c
if (mapped_ppa(&prev_ppa) &&
    is_same_flash_page(conv_ftl, cur_ppa, prev_ppa)) {
	xfer_size += spp->pgsz;
	continue;
}
```

- 현재 page와 이전 page가 같은 flash page에 있으면
- NAND read를 바로 보내지 않고 읽기 크기만 늘린다.
- 즉, 여러 작은 read를 하나의 flash page read로 합치려는 것이다.

이 부분이 헷갈릴 수 있는데, host read 요청 하나가 꼭 logical page 하나만 읽는 게 아니라 “시작 주소 + 길이” 형태이기 때문에 여러 `LPN`에 걸칠 수 있다. 그래서 그 여러 `LPN`이 mapping을 따라 여러 `PPA`로 펼쳐지고, 그중 일부가 같은 flash page에 속하면 합쳐 읽는 것이다.

```c
if (xfer_size > 0) {
	srd.xfer_size = xfer_size;
	srd.ppa = &prev_ppa;
	nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &srd);
}
```

- 묶어 둔 read가 있으면,
- 그 시점에서 실제 NAND read timing 모델을 호출한다.

```c
if (xfer_size > 0) {
	srd.xfer_size = xfer_size;
	srd.ppa = &prev_ppa;
	nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &srd);
}
```

- loop가 끝난 뒤 남아 있는 마지막 읽기 묶음도 실제로 발행한다.

함수 호출 흐름을 한 번에 정리하면 이렇다.

1. `conv_proc_nvme_io_cmd()`가 read opcode를 받아 `conv_read()`를 부른다.
2. `conv_read()`는 `LBA -> LPN` 범위를 계산한다.
3. read 크기에 따라 firmware read latency를 먼저 더한다.
4. 각 `LPN`마다 `maptbl`에서 `PPA`를 찾는다.
5. 매핑되지 않았거나 유효하지 않은 주소는 건너뛴다.
6. 같은 flash page에 속하는 read는 `xfer_size`를 합쳐 묶는다.
7. 묶음이 끝나는 시점마다 `ssd_advance_nand()`로 실제 NAND read timing을 계산한다.
8. 가장 늦게 끝나는 시각을 `ret->nsecs_target`으로 반환한다.

실습2에서 무엇이 달라져야 하는지 설명하면 다음과 같다.

- 현재 read는 “mapping table이 가리키는 physical page를 읽는다”는 구조다.
- 이 구조 자체는 실습2에서도 크게 유지될 가능성이 크다.
- 달라지는 점은 mapping이 이제 SLC 위치를 가리킬 수도 있고 TLC 위치를 가리킬 수도 있다는 것이다.
- 따라서 실습2 read 경로의 핵심 변화는:
  - mapping 결과가 SLC인지 TLC인지 판별
  - 그 위치에 맞는 timing/oneshot 규칙 반영
- 즉, read는 완전히 새로 설계하는 것보다 기존 mapping 기반 read를 유지하면서, SLC/TLC 분기만 추가하는 방향이 자연스럽다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- 현재 host read는 `LBA -> LPN -> maptbl 조회 -> PPA 확인 -> NAND read` 순서로 진행된다.
- read는 mapping을 바꾸지 않고, 현재 최신 physical page를 따라가기만 한다.
- 실습2에서도 read의 기본 구조는 유지되며, mapping 결과가 SLC인지 TLC인지에 따라 읽는 위치와 timing이 달라지게 된다.

- 간단 요약: 기존 host read는 mapping table이 가리키는 physical page를 찾아 읽고, 여러 logical page가 같은 flash page에 속하면 NAND read를 묶어서 처리하는 구조다.

### 7. line manager와 write pointer

- 상태: 완료
- 상세 설명:

이번 단계는 누가 공간 상태를 관리하고, 누가 다음 쓸 위치를 기억하느냐를 연결해서 보는 단계다. 지금까지 본 write/read/GC 흐름의 중심이 사실 여기 있다.

창고 관리자와 작업자의 역할로 보면 쉽다.

- `line manager`는 창고 관리자다.
- 이 관리자는
  - 아직 비어 있는 선반 줄 목록
  - 다 찬 선반 줄 목록
  - 정리 대상 선반 줄 목록
  을 따로 관리한다.
- `write pointer`는 실제 물건을 놓는 작업자의 손가락이다.
- 손가락은 “지금 어느 줄의 몇 번째 칸에 놓고 있는가”를 들고 다닌다.
- 줄 하나를 다 채우면 관리자가 새 빈 줄을 하나 내주고,
- 작업자는 그 새 줄의 맨 앞부터 다시 시작한다.

즉,

- `line manager`는 공간 상태 관리 담당
- `write pointer`는 현재 쓰기 위치 추적 담당

이다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- FTL은 free space를 페이지 단위로 아무 데서나 찾지 않는다.
- 현재 코드는 `line` 단위로 free / full / victim 상태를 관리한다.
- write는 현재 선택된 active line 위에서 순차적으로 진행된다.
- 그래서 두 가지가 필요하다.
  - 어떤 line들이 free인지 관리하는 구조
  - 현재 active line 안에서 다음 physical page가 어디인지 기억하는 구조
- 현재 코드에서 전자가 `line_mgmt`, 후자가 `write_pointer`다.
- 그리고 write path와 GC path는 각자 write pointer를 하나씩 가진다.
  - host write용 `wp`
  - GC write용 `gc_wp`

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- `struct line`, `struct write_pointer`, `struct line_mgmt`: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L31)
- `conv_ftl` 안의 `wp`, `gc_wp`, `lm`: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L71)
- line 초기화: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L224)
- free line 하나 가져오기: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L283)
- write pointer 선택: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L299)
- write pointer 준비: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L311)
- write pointer 전진: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L330)
- victim line 선택: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L769)
- line free로 반환: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L901)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
struct write_pointer {
	struct line *curline;
	uint32_t ch;
	uint32_t lun;
	uint32_t pg;
	uint32_t blk;
	uint32_t pl;
};
```

- `curline`
  지금 이 write pointer가 사용 중인 line이다.
- `ch/lun/pg/blk/pl`
  그 line 안에서 현재 어디까지 썼는지 나타내는 좌표다.

즉, write pointer는 “다음에 어디 쓸지”를 좌표 형태로 들고 있다.

```c
struct line_mgmt {
	struct line *lines;
	struct list_head free_line_list;
	pqueue_t *victim_line_pq;
	struct list_head full_line_list;
	uint32_t tt_lines;
	uint32_t free_line_cnt;
	uint32_t victim_line_cnt;
	uint32_t full_line_cnt;
};
```

- `lines`
  line 메타데이터 전체 배열이다.
- `free_line_list`
  아직 아무도 안 쓰는 line 목록이다.
- `victim_line_pq`
  GC 후보 line들을 우선순위 큐로 관리한다.
- `full_line_list`
  꽉 차 있고 아직 valid page만 가진 line 목록이다.
- 각 카운터는 현재 상태 개수를 추적한다.

즉, line manager는 “line 상태 표 + 상태별 목록”이다.

```c
INIT_LIST_HEAD(&lm->free_line_list);
INIT_LIST_HEAD(&lm->full_line_list);
lm->victim_line_pq = pqueue_init(...);
```

- line manager는 초기화 시
  - free list
  - full list
  - victim priority queue
  를 준비한다.

```c
for (i = 0; i < lm->tt_lines; i++) {
	...
	list_add_tail(&lm->lines[i].entry, &lm->free_line_list);
	lm->free_line_cnt++;
}
```

- 시작할 때는 모든 line이 비어 있으므로
- 전부 free line list에 들어간다.

```c
static struct line *get_next_free_line(struct conv_ftl *conv_ftl)
{
	struct line *curline = list_first_entry_or_null(&lm->free_line_list, struct line, entry);
	...
	list_del_init(&curline->entry);
	lm->free_line_cnt--;
	return curline;
}
```

- free line list의 맨 앞에서 line 하나를 꺼낸다.
- 꺼낸 순간 더 이상 free 상태가 아니므로 list에서 제거하고 count도 줄인다.

```c
if (io_type == USER_IO) {
	return &ftl->wp;
} else if (io_type == GC_IO) {
	return &ftl->gc_wp;
}
```

- 같은 함수라도 host write인지 GC write인지에 따라
- 다른 write pointer를 사용한다.

즉, 현재도 pointer가 완전히 하나는 아니다. 다만 host용 하나, GC용 하나만 있을 뿐이다.

```c
struct write_pointer *wp = __get_wp(conv_ftl, io_type);
struct line *curline = get_next_free_line(conv_ftl);
...
*wp = (struct write_pointer){
	.curline = curline,
	.ch = 0,
	.lun = 0,
	.pg = 0,
	.blk = curline->id,
	.pl = 0,
};
```

- write pointer를 처음 준비할 때는
  - free line 하나를 받고
  - 그 line의 맨 처음 좌표 `(ch=0, lun=0, pg=0, blk=line id)`부터 시작한다.

즉, active line을 하나 잡고 그 안에서 순차 쓰기를 시작하는 것이다.

```c
struct line_mgmt *lm = &conv_ftl->lm;
struct write_pointer *wpp = __get_wp(conv_ftl, io_type);
```

- write pointer를 움직일 때도
- 단순히 좌표만 바꾸는 게 아니라 line manager 상태와 같이 본다.

```c
if (wpp->curline->vpc == spp->pgs_per_line) {
	list_add_tail(&wpp->curline->entry, &lm->full_line_list);
	lm->full_line_cnt++;
} else {
	pqueue_insert(lm->victim_line_pq, wpp->curline);
	lm->victim_line_cnt++;
}
```

- line 하나를 다 썼을 때 그 line을 어디에 둘지 결정한다.
- 끝까지 모두 valid면 `full_line_list`
- invalid가 섞여 있으면 `victim_line_pq`

이게 아주 중요하다. 즉, write pointer가 line을 다 쓰는 순간, line manager가 그 line의 “이후 인생”을 결정한다.

왜 어떤 line은 `full_line_list`로 가고, 어떤 line은 `victim_line_pq`로 갈까?

- `full_line_list`로 가는 경우:
  그 line을 다 썼는데, 그 안의 모든 page가 아직 최신 데이터다.
  즉 `vpc == pgs_per_line`, `ipc == 0` 상태다.
  이런 line은 지금 당장 GC 대상으로 삼아도 얻을 이득이 없다. valid data만 가득해서, 회수하려면 전부 복사해야 하기 때문이다.

- `victim_line_pq`로 가는 경우:
  그 line을 다 쓰는 동안 overwrite가 일어나서, 예전 page들 중 일부가 invalid가 되었다.
  즉 그 line 안에 이미 버려진 공간이 생긴 상태다.
  이런 line은 나중에 GC가 회수하면 빈 공간을 되찾을 수 있으므로 victim 후보가 된다.

즉 한 줄로 줄이면:

- `full_line_list`는 “꽉 찼지만 아직 다 유효한 줄”
- `victim_line_pq`는 “꽉 찼고, 일부는 이미 낡아서 회수 후보가 된 줄”

```c
wpp->curline = get_next_free_line(conv_ftl);
wpp->blk = wpp->curline->id;
```

- 현재 line을 닫은 뒤에는
- 새 free line 하나를 받아 다음 active line으로 바꾼다.

```c
victim_line = pqueue_peek(lm->victim_line_pq);
...
pqueue_pop(lm->victim_line_pq);
```

- GC가 필요할 때는 victim queue에서 line을 하나 고른다.
- 즉, line manager는 free list만 관리하는 게 아니라 reclaim 대상도 관리한다.

```c
line->ipc = 0;
line->vpc = 0;
list_add_tail(&line->entry, &lm->free_line_list);
lm->free_line_cnt++;
```

- GC가 끝난 line은 메타데이터를 초기화하고
- 다시 free line list로 되돌린다.

이걸 보면 line의 life cycle이 보인다.

1. 처음엔 `free_line_list`
2. write pointer가 가져가서 active line으로 사용
3. 다 차면 `full_line_list` 또는 `victim_line_pq`
4. GC로 회수되면 다시 `free_line_list`

함수 호출 흐름으로 정리하면 다음과 같다.

1. FTL 초기화 때 `init_lines()`가 모든 line을 free 상태로 만든다.
2. `prepare_write_pointer(USER_IO)`와 `prepare_write_pointer(GC_IO)`가 각각 free line 하나씩 가져간다.
3. host write/GC write는 각자 자기 write pointer를 따라 새 page를 쓴다.
4. `advance_write_pointer()`는 좌표를 움직이다가 line이 닫히면 그 line을 full 또는 victim 상태로 넘긴다.
5. 동시에 새 free line을 하나 받아 다음 active line으로 바꾼다.
6. GC는 `select_victim_line()`으로 victim queue에서 line을 하나 가져온다.
7. 정리가 끝나면 `mark_line_free()`로 다시 free list에 넣는다.

실습2에서 무엇이 달라져야 하는지 설명하면 다음과 같다.

- 현재는 `line_mgmt lm`이 하나뿐이다.
- 그래서 free/full/victim 상태가 모두 단일 공간 기준이다.
- write pointer도 host용 `wp`, GC용 `gc_wp` 두 개뿐이지만 둘 다 결국 같은 line manager에서 line을 받아 쓴다.
- 실습2에서는 이 구조가 부족하다.
- 이유는:
  - SLC host write는 SLC free line에서 line을 받아야 하고
  - TLC GC는 TLC free line에서 line을 받아야 하며
  - SLC migration victim은 SLC 쪽 후보 집합에서 골라야 하고
  - migration destination은 TLC 쪽 free line에서 받아야 하기 때문이다.
- SLC migration은 SLC victim line을 골라서 valid data를 TLC free line 쪽에 써야 하고, migration이 끝난 뒤 원래 SLC victim line은 다시 SLC free list로 반환해야 한다.
- line manager가 하나뿐이면 이 free line이 SLC용인지 TLC용인지, victim 후보가 TLC GC용인지 SLC migration용인지, reclaim 후 반환 대상이 SLC인지 TLC인지 의미가 섞인다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- `line manager`는 line들의 상태(`free`, `full`, `victim`)를 관리하는 관리자다.
- `write pointer`는 현재 active line 안에서 다음에 쓸 물리 좌표를 기억하는 구조다.
- 실습2의 중요한 변화 중 하나는 단일 `line manager`와 단일 공간용 pointer 구조를 SLC/TLC 기준으로 분리하는 것이다.

- 간단 요약: `line manager`가 line의 상태와 소유를 관리하고, `write pointer`는 현재 active line 안의 다음 쓰기 좌표를 들고 움직인다. 실습2에서는 이 둘의 의미를 SLC와 TLC로 분리해야 한다.

### 8. 기존 TLC garbage collection 경로

- 상태: 완료
- 상세 설명:

이번 단계는 현재 Conventional FTL의 GC가 실제로 어떻게 돌아가는지 설명하는 단계다. 실습2에서 새로 만들 SLC→TLC migration과 헷갈리기 쉬운 부분이라, 지금 있는 TLC GC의 목적과 흐름을 정확히 분리해서 보는 것이 중요하다.

창고 정리 작업으로 생각하면 쉽다.

- 어떤 선반 줄은 예전 물건이 빠져나가서 빈 칸이 조금씩 생긴다.
- 하지만 선반 줄 전체를 다시 자유롭게 쓰려면, 아직 남아 있는 최신 물건들을 다른 빈 줄로 옮겨야 한다.
- 그 뒤 그 오래된 줄을 완전히 비우고 정리해서 다시 새 줄처럼 돌려놓는다.

즉 GC는:

1. 정리할 줄 하나를 고르고
2. 그 줄에서 아직 유효한 물건만 다른 줄로 옮기고
3. 원래 줄을 비워서 다시 free 줄로 돌리는 작업이다

SSD/FTL 개념으로 설명하면 다음과 같다.

- 현재 GC의 목적은 TLC 내부 공간 회수다.
- invalid page가 섞인 victim line을 골라
- 그 안의 valid page만 다른 TLC 위치로 복사하고
- 원래 victim line의 block들을 erase한 뒤
- 그 line을 free line으로 되돌린다.
- 즉, 지금 코드의 GC는 TLC -> TLC 이동이다.
- 실습2의 SLC migration과 이름이 비슷해 보여도 목적과 source/destination이 다르다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- GC 필요 조건: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L64)
- foreground GC 진입: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L975)
- victim 선택: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L769)
- victim page read: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L703)
- victim page write: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L722)
- flash page 단위 청소: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L852)
- block free 처리: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L682)
- line free 반환: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L901)
- 전체 GC 실행: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L912)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다.

```c
static bool should_gc(struct conv_ftl *conv_ftl)
{
	return (conv_ftl->lm.free_line_cnt <= conv_ftl->cp.gc_thres_lines);
}
```

- free line 수가 threshold 이하로 내려가면 GC가 필요하다고 본다.

```c
static inline bool should_gc_high(struct conv_ftl *conv_ftl)
{
	return conv_ftl->lm.free_line_cnt <= conv_ftl->cp.gc_thres_lines_high;
}
```

- 더 급한 수준의 free line 부족 조건이다.
- foreground GC를 즉시 밀어넣는 기준으로 쓰인다.

```c
static void foreground_gc(struct conv_ftl *conv_ftl)
{
	if (should_gc_high(conv_ftl)) {
		do_gc(conv_ftl, true);
```

- free line이 너무 부족하면 foreground GC가 바로 돌기 시작한다.
- 즉, host write 경로가 공간 확보를 위해 GC를 강제로 부를 수 있다.

```c
victim_line = pqueue_peek(lm->victim_line_pq);
...
if (gc_policy == GC_POLICY_RANDOM) { ... }
else if (gc_policy == GC_POLICY_COST_BENEFIT) { ... }
else {
	pqueue_pop(lm->victim_line_pq);
}
```

- victim line은 victim queue에서 고른다.
- 현재 실습1에서 구현한 정책들(Greedy, Random, Cost-Benefit)이 바로 이 TLC GC victim selection에 적용된다.
- 즉, 지금 코드의 `gc_policy`는 TLC GC용이다.

```c
uint64_t lpn = get_rmap_ent(conv_ftl, old_ppa);
new_ppa = get_new_page(conv_ftl, GC_IO);
set_maptbl_ent(conv_ftl, lpn, &new_ppa);
set_rmap_ent(conv_ftl, lpn, &new_ppa);
mark_page_valid(conv_ftl, &new_ppa);
advance_write_pointer(conv_ftl, GC_IO);
```

- victim line 안의 valid page 하나를 옮길 때,
- old physical page가 어떤 `lpn`의 데이터인지 `rmap`으로 찾고
- GC write pointer가 가리키는 새 TLC page를 하나 받는다.
- 그 다음 mapping을 새 위치로 바꾸고
- 새 page를 valid로 표시한 뒤
- GC write pointer를 전진시킨다.

즉, GC도 결국 valid data를 새 TLC 위치에 다시 쓰고 mapping을 갱신하는 작업이다.

```c
static void gc_read_page(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	...
	struct nand_cmd gcr = {
		.type = GC_IO,
		.cmd = NAND_READ,
```

- GC가 victim data를 옮기기 전에 NAND read timing도 모델링한다.
- 즉, migration cost가 timing 모델에 반영된다.

```c
for (i = 0; i < spp->pgs_per_flashpg; i++) {
	pg_iter = get_pg(conv_ftl->ssd, &ppa_copy);
	if (pg_iter->status == PG_VALID)
		cnt++;
}
...
if (pg_iter->status == PG_VALID) {
	gc_write_page(conv_ftl, &ppa_copy);
}
```

- victim block 안의 flash page 단위를 보면서
- valid page가 몇 개인지 세고
- valid page만 새 위치로 복사한다.

즉, GC는 invalid page를 복사하지 않는다. 이것이 GC가 공간을 회수하는 핵심이다.

```c
victim_line = select_victim_line(conv_ftl, force);
...
conv_ftl->wfc.credits_to_refill = victim_line->ipc;
gc_valid_page_migrate_cnt += victim_line->vpc;
```

- victim line을 하나 고르고
- 그 line이 가진 invalid page 수를 기준으로 write credit refill 양을 정한다.
- valid page migration 통계도 누적한다.

```c
for (flashpg = 0; flashpg < spp->flashpgs_per_blk; flashpg++) {
	for (ch = 0; ch < spp->nchs; ch++) {
		for (lun = 0; lun < spp->luns_per_ch; lun++) {
			...
			clean_one_flashpg(conv_ftl, &ppa);
```

- victim line 하나를 정리할 때
- 그 line에 속한 모든 channel / lun / flash page를 순회하면서
- valid data를 복사한다.

```c
mark_block_free(conv_ftl, &ppa);
...
ssd_advance_nand(conv_ftl->ssd, &gce);
```

- valid data 복사가 끝나면
- 원래 victim line을 이루는 각 block을 free 상태로 바꾸고
- erase timing도 반영한다.

```c
mark_line_free(conv_ftl, &ppa);
```

- line 전체 정리가 끝나면
- 그 victim line을 다시 free line list에 넣는다.

함수 호출 흐름을 한 번에 정리하면 이렇다.

1. host write가 진행되다가 free line이 부족해지면 `check_and_refill_write_credit()`가 foreground GC를 부를 수 있다.
2. `foreground_gc()`는 `should_gc_high()`를 보고 `do_gc()`를 실행한다.
3. `do_gc()`는 `select_victim_line()`으로 victim line 하나를 고른다.
4. 그 victim line의 각 flash page / channel / lun을 순회하면서 `clean_one_flashpg()`를 수행한다.
5. valid page는 `gc_read_page()` 후 `gc_write_page()`로 새 TLC 위치에 복사된다.
6. 이때 `maptbl`과 `rmap`도 새 위치 기준으로 갱신된다.
7. line 내 block들을 erase/free 처리한다.
8. 마지막에 `mark_line_free()`로 victim line을 free list로 되돌린다.

실습2에서 무엇이 달라져야 하는지 설명하면 다음과 같다.

- 현재 GC는 TLC 공간 회수용이다.
- source와 destination이 모두 TLC 쪽이다.
- victim 후보도 TLC victim queue 기준이다.
- write pointer도 현재 `GC_IO` 하나로 TLC 내부 이동을 수행한다.

실습2의 SLC migration은 이와 다르다.

- source는 SLC victim line
- destination은 TLC free line
- 목적은 TLC 내부 공간 회수가 아니라 SLC cache 공간 회수
- victim policy도 TLC GC policy와 분리 필요
- 통계와 queue 의미도 분리 필요

즉, 실습2에서 가장 위험한 오해 중 하나는 현재 TLC GC 경로를 이름만 바꿔서 SLC migration으로 쓰는 것이다. 비슷한 helper를 재사용할 수는 있어도, 대상 line manager, victim 집합, destination, counter 의미는 다시 분리해서 봐야 한다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- 현재 GC는 victim TLC line의 valid page를 다른 TLC 위치로 옮기고 원래 line을 free로 돌리는 TLC -> TLC 공간 회수 경로다.
- victim 선택, valid page 복사, mapping 갱신, erase, free line 반환이 현재 GC의 핵심 순서다.
- 실습2의 SLC→TLC migration은 목적과 source/destination이 다르므로 현재 TLC GC와 그대로 동일시하면 안 된다.

- 간단 요약: 기존 GC는 TLC victim line을 골라 valid page만 다른 TLC 위치로 옮기고, 원래 line을 erase해 free로 돌리는 TLC 내부 정리 경로다.

### 9. SLC/TLC line manager를 분리해야 하는 이유

- 상태: 완료
- 상세 설명:

이번 단계는 실습2의 구조 조건 중 가장 중요한 것 하나를 설명하는 단계다. 과제는 단순히 “SLC 영역도 추가해라”가 아니라, SLC line manager와 TLC line manager를 따로 관리하라고 요구한다.

창고에 빠른 임시 보관 구역과 큰 장기 보관 구역이 같이 있다고 생각해 보면 쉽다.

- 앞쪽 빠른 보관대가 `SLC`
- 뒤쪽 큰 창고가 `TLC`

이 두 공간은 역할이 다르다.

- 손님이 새 물건을 맡기면 먼저 앞쪽 빠른 보관대(SLC)에 둔다.
- 앞쪽이 차면, 그중 아직 유효한 물건을 뒤쪽 큰 창고(TLC)로 옮긴다.
- 옮긴 뒤 앞쪽 보관대는 다시 비워서 다음 손님용으로 써야 한다.
- 반면 뒤쪽 창고(TLC)는 자기 내부에서 또 오래된 선반을 정리하는 GC가 필요하다.

여기서 관리자가 한 명뿐이고, “빈 선반 목록”도 하나뿐이면 문제가 생긴다.

- 지금 필요한 빈 선반이 SLC용인지 TLC용인지 헷갈린다.
- 지금 고른 victim이 SLC migration용인지 TLC GC용인지 헷갈린다.
- 정리가 끝난 선반을 어디로 돌려놔야 하는지도 헷갈린다.

그래서 빠른 보관대 관리자와 큰 창고 관리자를 나눠야 한다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- 현재 코드는 `line_mgmt lm` 하나로 모든 free/full/victim line을 관리한다.
- 이 구조는 한 종류의 공간만 있는 SSD에는 자연스럽다.
- 하지만 실습2에서는 line들이 서로 다른 역할을 가져야 한다.
  - SLC line: host write의 1차 목적지
  - TLC line: migration 목적지이자 기존 GC 대상 공간
- 따라서 최소한 다음 의미가 분리돼야 한다.
  - SLC free lines
  - SLC active/write line
  - SLC migration victim candidates
  - TLC free lines
  - TLC active/write line
  - TLC GC victim candidates
- 과제 자료도 이 분리를 직접 요구한다.

현재 저장소와 과제 자료에서 관련 근거는 다음과 같다.

- 현재 코드의 단일 manager 구조: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L52)
- 현재 `conv_ftl` 안의 단일 `lm`: [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L71)
- 과제 자료의 분리 요구: [docs/PRACTICE2_CODEX_INSTRUCTIONS.md](/home/hjyu216/nvmevirt/docs/PRACTICE2_CODEX_INSTRUCTIONS.md#L225)
- 과제 자료의 SLC/TLC line manager 구조 그림: [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L514)

실제 코드를 짧게 보면 다음과 같다.

```c
struct line_mgmt {
	struct line *lines;
	struct list_head free_line_list;
	pqueue_t *victim_line_pq;
	struct list_head full_line_list;
```

- 현재는 free line list 하나
- victim queue 하나
- full line list 하나뿐이다.

즉, 이 manager는 “이 line이 SLC 소속인지 TLC 소속인지”를 구분하지 않는다.

```c
struct write_pointer wp;
struct write_pointer gc_wp;
struct line_mgmt lm;
```

- 현재 `conv_ftl` 안에는
  - host write pointer 하나
  - GC write pointer 하나
  - line manager 하나
만 있다.
- 즉, host write와 GC write는 역할이 달라도 결국 같은 manager의 line pool을 공유한다.

과제 자료는 반대로 이렇게 요구한다.

```text
SLC line manager
├── SLC free lines
├── SLC active/write line
├── SLC full lines
└── SLC migration victim candidates

TLC line manager
├── TLC free lines
├── TLC active/write line
├── TLC full lines
└── TLC GC victim candidates
```

- SLC와 TLC는 같은 방식으로 한 덩어리로 관리하면 안 된다.
- 둘 다 line manager를 가지지만, 의미가 다르다.
- SLC 쪽 victim 후보는 migration용이고,
- TLC 쪽 victim 후보는 GC용이다.

과제 자료는 invariant도 같이 준다.

```text
- 하나의 line이 동시에 SLC manager와 TLC manager에 속하지 않음
- 전체 line 수 = SLC 소유 line 수 + TLC 소유 line 수
- SLC reclaimed line은 SLC free list로 반환
- TLC reclaimed line은 TLC free list로 반환
- SLC migration destination은 TLC manager에서 할당
```

이게 분리 이유를 거의 다 말해 준다.

하나씩 풀면:

- `하나의 line이 동시에 SLC/TLC manager에 속하지 않음`
  line의 소유권이 명확해야 한다.
- `SLC reclaimed line은 SLC free list로 반환`
  SLC victim을 정리했다고 해서 TLC free pool에 섞이면 안 된다.
- `TLC reclaimed line은 TLC free list로 반환`
  TLC GC 결과도 자기 공간으로 돌아가야 한다.
- `SLC migration destination은 TLC manager에서 할당`
  SLC에서 쫓겨난 valid data는 TLC 쪽 빈 공간에 가야 한다.

함수 호출 흐름 관점에서 왜 단일 manager가 부족한지도 보겠다.

현재 구조에서는:

1. host write가 `wp`로 free line 하나를 받아 쓴다.
2. GC는 `gc_wp`로 free line 하나를 받아 valid page를 옮긴다.
3. victim 선택은 `victim_line_pq` 하나에서 이뤄진다.
4. line reclaim 후에는 `free_line_list` 하나로 되돌아간다.

이 구조는 “모든 line의 의미가 동일하다”는 전제가 있을 때만 자연스럽다.

하지만 실습2에서는 동시에 다음이 필요하다.

1. host write는 SLC free line에서 line을 받아야 함
2. SLC migration victim은 SLC 후보 집합에서 골라야 함
3. migration destination은 TLC free line에서 받아야 함
4. migration이 끝난 SLC victim line은 다시 SLC free list로 돌아가야 함
5. TLC GC는 여전히 TLC victim 집합과 TLC free list를 사용해야 함

즉, source와 destination, reclaim 귀속처가 각각 다르기 때문에 manager 하나로는 의미가 섞인다.

victim queue를 하나만 두면 왜 문제가 생길까?

- `TLC GC`는 TLC victim line을 고르고, TLC 공간 회수를 위해 TLC -> TLC 복사를 해야 한다.
- `SLC migration`은 SLC victim line을 고르고, SLC 공간 회수를 위해 SLC -> TLC 복사를 해야 한다.
- 그런데 victim queue가 하나면:
  - 지금 고른 victim이 SLC line인지 TLC line인지 의미가 섞인다.
  - 이 작업이 TLC GC인지 SLC migration인지도 섞인다.
  - destination이 TLC free line이어야 하는지, reclaim 후 어디 free list로 돌려야 하는지도 섞인다.
  - counter와 통계도 섞인다.

즉 핵심 문제는 잘못된 데이터를 옮긴다기보다, 올바른 line 집합, 올바른 목적, 올바른 destination, 올바른 reclaim 경로를 보장할 수 없게 된다는 점이다.

실습2에서 무엇이 달라져야 하는지를 정리하면 다음과 같다.

- mapping table은 하나를 유지해야 한다.
- 하지만 line manager는 하나가 아니라 최소한 SLC/TLC로 분리돼야 한다.
- write pointer도 그 manager 의미에 맞게 분리될 가능성이 크다.
- 특히 “victim queue 하나를 재사용해서 SLC migration과 TLC GC를 같이 넣는 방식”은 과제 요구와 충돌할 가능성이 높다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- 단일 `line_mgmt`는 모든 line을 같은 종류의 공간으로 가정하는 구조다.
- 실습2에서는 SLC와 TLC의 source, destination, reclaim 귀속처가 다르므로 line manager 분리가 필요하다.
- mapping table은 하나로 유지하되, free list / victim queue / active line의 의미는 SLC와 TLC로 나뉘어야 한다.

- 간단 요약: mapping은 하나여도 line의 소유와 용도는 하나가 아니다. 실습2에서는 SLC host write, SLC victim reclaim, TLC migration destination, TLC GC를 분리하기 위해 line manager를 둘로 나눠야 한다.

### 10. SLC→TLC migration의 전체 흐름

- 상태: 완료
- 상세 설명:

이번 단계는 실습2의 핵심 동작 자체를 설명하는 단계다. 지금은 아직 구현이 아니라, 과제 자료와 현재 코드 구조를 바탕으로 “무슨 순서로 일이 일어나야 하는가”를 이해하는 단계다.

앞쪽 임시 보관대(SLC)와 뒤쪽 큰 창고(TLC)가 있다고 생각해 보면 쉽다.

- 손님 물건은 먼저 앞쪽 빠른 보관대(SLC)에 올려둔다.
- 그런데 앞쪽 보관대가 가득 차면 더 이상 새 물건을 받을 수 없다.
- 그래서 앞쪽 보관대의 오래된 줄 하나를 골라,
- 그 줄 안에서 아직 유효한 물건만 뒤쪽 큰 창고(TLC)로 옮긴다.
- 장부에 새 위치를 적어 둔다.
- 원래 앞쪽 줄은 완전히 비워서 다시 앞쪽 free 줄로 돌린다.

즉 migration은:

1. SLC 공간이 부족해짐
2. SLC victim line 하나를 고름
3. 그 line의 valid data만 TLC로 옮김
4. mapping을 새 TLC 위치로 바꿈
5. 원래 SLC line을 회수해 다시 SLC free line으로 돌림

핵심은, 데이터를 지우는 게 아니라 “내려서 옮긴 뒤 공간을 비우는 것”이다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- host write는 기본적으로 SLC에 먼저 기록된다.
- 시간이 지나 overwrite가 생기면 SLC line 안에도 valid/invalid page가 섞일 수 있다.
- SLC free line이 부족해지면 migration이 필요하다.
- migration은 SLC victim line의 valid page만 TLC 쪽 새 위치에 재기록한다.
- 이후 동일 LPN의 mapping은 예전 SLC PPA가 아니라 새 TLC PPA를 가리켜야 한다.
- migration이 끝난 SLC victim line은 erase/reclaim 후 다시 SLC free line으로 돌아가야 한다.
- 이 구조 덕분에 read는 나중에 같은 mapping table을 보고 SLC 또는 TLC 중 최신 위치를 따라갈 수 있다.

과제 자료는 이 흐름을 직접 이렇게 설명한다.

```text
SLC free space 부족
        ▼
SLC migration victim 선택
        ▼
victim의 valid data 판별
        ▼
valid data를 TLC에 기록
        ▼
공통 mapping table을 새 TLC 위치로 갱신
        ▼
SLC victim erase/reclaim
        ▼
SLC free line으로 반환
```

이게 실습2 migration의 공식 흐름이라고 보면 된다.

현재 저장소에서 이 흐름과 연결해서 봐야 할 파일, 구조체, 함수는 다음과 같다.

- 과제 요구 흐름: [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L166)
- read가 SLC/TLC 둘 다 볼 수 있어야 한다는 요구: [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L225)
- SLC/TLC line manager 분리 요구: [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L514)
- 현재 TLC GC의 valid-page copy + mapping update helper: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L722)
- 현재 TLC GC victim 선택: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L769)
- 현재 line reclaim: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L901)

실제 코드를 짧게 인용해 한 줄씩 설명하면 다음과 같다. 아래 코드는 현재 TLC GC helper지만, migration 흐름을 이해할 때 비교 기준으로 매우 중요하다.

```c
uint64_t lpn = get_rmap_ent(conv_ftl, old_ppa);
new_ppa = get_new_page(conv_ftl, GC_IO);
set_maptbl_ent(conv_ftl, lpn, &new_ppa);
set_rmap_ent(conv_ftl, lpn, &new_ppa);
```

- old physical page가 어떤 logical page의 데이터인지 `rmap`으로 찾고
- 새 physical page를 하나 잡고
- `maptbl`, `rmap`을 새 위치 기준으로 갱신한다.

실습2 migration도 핵심 아이디어는 같다. 다만 차이는:

- old_ppa는 SLC 쪽 victim에서 나와야 하고
- new_ppa는 TLC 쪽 destination에서 나와야 한다는 점이다.

과제 자료는 또 이렇게 말한다.

```text
이 구조를 위해 PDF는 SLC와 TLC의 mapping을 따로 만들지 말고 하나로 관리하라고 요구한다.

migration 후에는 동일 LBA의 mapping이 기존 SLC 위치가 아니라 새 TLC 위치를 가리켜야 한다.
```

- migration 후 logical page 번호는 변하지 않는다.
- 바뀌는 것은 오직 physical location이다.
- 그래서 “SLC mapping”, “TLC mapping” 두 개가 아니라 하나의 mapping entry가 새 TLC 위치를 가리키게 바뀌어야 한다.

과제 자료는 reclaim 귀속도 명시한다.

```text
- SLC reclaimed line은 SLC free list로 반환
- TLC reclaimed line은 TLC free list로 반환
- SLC migration destination은 TLC manager에서 할당
```

- migration source와 destination이 다르다.
- source였던 SLC line은 다시 SLC로 돌아가야 하고,
- destination은 TLC manager 쪽에서 받아야 한다.

함수 호출 흐름으로 “이상적인 migration 경로”를 정리하면 이렇게 된다. 이건 현재 코드 그대로가 아니라, 현재 구조를 바탕으로 실습2에서 만들어져야 할 흐름이다.

1. host write가 계속 SLC에 기록된다.
2. SLC free line이 부족해진다.
3. SLC migration trigger가 걸린다.
4. SLC migration victim queue에서 victim line 하나를 고른다.
5. victim line 안의 valid page를 순회한다.
6. 각 valid page에 대해:
   - old SLC PPA가 어떤 LPN의 데이터인지 확인
   - TLC destination write pointer에서 새 TLC PPA를 할당
   - valid data를 TLC에 기록
   - mapping table을 새 TLC PPA로 갱신
   - reverse mapping도 새 TLC 기준으로 갱신
7. victim line의 valid data 이동이 끝나면 SLC victim line을 erase/reclaim 한다.
8. 그 line을 SLC free line list로 반환한다.
9. 이후 read는 같은 mapping table을 따라, 어떤 LPN은 SLC에서, 어떤 LPN은 TLC에서 읽게 된다.

현재 TLC GC와 무엇이 같고 무엇이 다른지도 정리해야 한다.

같은 점:

- victim을 고른다
- valid page만 옮긴다
- mapping을 새 위치로 갱신한다
- 원래 line을 회수한다

다른 점:

- TLC GC는 `TLC -> TLC`
- SLC migration은 `SLC -> TLC`
- TLC GC 목적은 TLC 공간 회수
- SLC migration 목적은 SLC cache 공간 회수
- victim 후보 집합도 다름
- reclaim 후 반환할 free list도 다름

이 단계에서 특히 조심해야 할 점도 과제 자료에 나온다.

```text
- migration 도중 같은 LBA가 host에 의해 다시 write되는 문제
- 최신 host write를 오래된 migration copy가 덮는 문제
```

- migration은 단순 복사 문제가 아니다.
- 옮기는 도중 host가 같은 LPN을 다시 쓰면, 오래된 migration 결과가 최신 host write를 덮어쓰면 안 된다.
- 그래서 실제 구현 시에는 “이 old SLC page가 아직도 최신 mapping인지” 확인하는 순서가 중요하다.

실습2에서 무엇이 달라져야 하는지를 정리하면 다음과 같다.

- 현재 코드에는 SLC migration 경로가 없다.
- 하지만 TLC GC 경로의 일부 helper는 개념적으로 재사용 가능성이 있다.
- 다만 그대로 쓰면 안 되고,
  - victim 집합
  - destination manager
  - reclaim 귀속처
  - 정책 이름
  - counter 의미
를 모두 분리해야 한다.
- 즉, migration은 “새 GC 하나 추가”가 아니라, SLC cache 구조 위에 내려쓰기 경로를 추가하는 작업이다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- SLC→TLC migration은 SLC cache 공간을 다시 확보하기 위한 동작이다.
- migration의 핵심 순서는 `SLC victim 선택 -> valid data만 TLC로 이동 -> mapping 갱신 -> SLC line reclaim`이다.
- migration은 TLC GC와 비슷해 보여도 source, destination, 목적, victim 집합, reclaim 귀속처가 다르다.

- 간단 요약: SLC migration은 SLC에 있던 최신 데이터를 TLC로 내리고, mapping을 새 TLC 위치로 바꾼 뒤, 비워진 SLC line을 다시 SLC free line으로 돌려 SLC cache 공간을 회수하는 흐름이다.

### 11. SLC와 TLC의 oneshot page size 차이

- 상태: 완료
- 상세 설명:

이번 단계는 왜 SLC와 TLC를 같은 쓰기 단위로 다루면 안 되는가를 설명하는 단계다. 이건 실습2에서 아주 중요하다. 과제도 `SLC와 TLC의 서로 다른 oneshot page size를 반영해야 한다`고 직접 요구한다.

트럭 적재 단위로 생각하면 쉽다.

- `logical page`는 상자 1개다.
- `flash page`는 상자 몇 개를 한 번에 검사하는 선반 단위다.
- `oneshot page`는 트럭이 한 번 출발할 때 최소로 실어야 하는 묶음 단위라고 생각하면 된다.

그러면:

- SLC 트럭은 상자 1묶음만 실어도 바로 출발할 수 있고
- TLC 트럭은 상자 3묶음이 모여야 한 번 출발하는 식일 수 있다

이때 두 트럭을 같은 규칙으로 다루면 문제가 생긴다.

- SLC는 이미 쓸 수 있는데 괜히 기다리게 하거나
- TLC는 아직 한 번에 써야 할 묶음이 안 찼는데 잘못 program하게 된다

즉, `oneshot page size`는 “한 번의 NAND program이 실제로 몇 개의 FTL page를 묶어 처리하느냐”의 문제다.

SSD/FTL 개념으로 설명하면 다음과 같다.

- 현재 코드 주석은 세 단위를 구분한다.
  - `page`: FTL mapping 단위
  - `flash page`: NAND sensing/read 단위
  - `oneshot page`: NAND program/write 단위
- 현재 코드에서 write pointer 전진 규칙, `last_pg_in_wordline()`, NAND write `xfer_size`는 모두 `pgs_per_oneshotpg`를 기준으로 움직인다.
- 즉, `oneshot page size`가 바뀌면:
  - write pointer가 “몇 page마다 channel/lun을 넘길지”
  - 실제 NAND write를 “언제 한 번 발행할지”
  - write `xfer_size`를 얼마로 잡을지
  가 함께 바뀐다.
- 그래서 실습2에서 SLC와 TLC가 서로 다른 oneshot page size를 가지면, 둘을 같은 전역 값으로 처리하면 안 된다.

현재 저장소에서 관련 파일, 구조체, 함수는 다음과 같다.

- 단위 설명 주석: [ssd.h](/home/hjyu216/nvmevirt/ssd.h#L140)
- geometry 계산: [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L98)
- 현재 Samsung Conventional 설정: [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h#L71)
- `last_pg_in_wordline()`: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L58)
- write pointer 전진 규칙: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L341)
- host write NAND 발행 조건: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1161)
- GC write NAND 발행 조건: [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L749)
- 과제 자료의 요구: [docs/PRACTICE2_CODEX_INSTRUCTIONS.md](/home/hjyu216/nvmevirt/docs/PRACTICE2_CODEX_INSTRUCTIONS.md#L228), [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L577)

실제 코드를 짧게 보면 다음과 같다.

```c
pg (page): Mapping unit (4KB)
flashpg (flash page) : Nand sensing unit , tR
oneshotpg (oneshot page) : Nand program unit, tPROG, (eg. flashpg * 3 (TLC))
```

- `page`
  FTL이 논리/물리 매핑하는 기본 단위다.
- `flashpg`
  NAND read/sensing 쪽 단위다.
- `oneshotpg`
  NAND write/program 쪽 단위다.

즉, read 단위와 write 단위가 다를 수 있고, FTL page와도 다를 수 있다.

```c
NVMEV_ASSERT((ONESHOT_PAGE_SIZE % spp->pgsz) == 0 && (FLASH_PAGE_SIZE % spp->pgsz) == 0);
spp->pgs_per_oneshotpg = ONESHOT_PAGE_SIZE / (spp->pgsz);
spp->pgs_per_flashpg = FLASH_PAGE_SIZE / (spp->pgsz);
```

- `ONESHOT_PAGE_SIZE`는 FTL page 크기의 정수배여야 한다.
- 그 결과 `oneshot page` 하나가 FTL page 몇 개를 포함하는지 `pgs_per_oneshotpg`로 계산한다.
- `flash page`도 마찬가지로 FTL page 몇 개를 포함하는지 계산한다.

즉, 코드 전체는 “한 번의 program에 page 몇 개가 묶이느냐”를 숫자로 들고 있다.

현재 Samsung Conventional 설정은 이렇게 되어 있다.

```c
#define FLASH_PAGE_SIZE KB(32)
#define ONESHOT_PAGE_SIZE (FLASH_PAGE_SIZE * 1)
```

- 현재 Conventional profile은 oneshot이 flash page와 같은 크기다.
- 즉, 현재 이 저장소는 단일 `ONESHOT_PAGE_SIZE` 규칙 하나만 가진 구조다.

반면 같은 저장소 안의 다른 SSD profile들을 보면, oneshot이 더 큰 경우도 이미 존재한다.

```c
#define ONESHOT_PAGE_SIZE (FLASH_PAGE_SIZE * 3)
```

- 이건 “한 번의 program이 flash page 3개 묶음”일 수 있다는 예를 보여 준다.
- 즉, 코드베이스 자체는 `oneshot != flash page`인 경우를 이미 알고 있다.

write 경로에서 이 값이 실제로 어디 쓰이는지도 중요하다.

```c
return (ppa->g.pg % spp->pgs_per_oneshotpg) == (spp->pgs_per_oneshotpg - 1);
```

- 현재 page가 oneshot 묶음의 마지막 page인지 확인한다.
- 즉, “이제 실제 NAND write를 날려도 되는 타이밍인가?”를 보는 함수다.

```c
wpp->pg++;
if ((wpp->pg % spp->pgs_per_oneshotpg) != 0)
	goto out;
```

- write pointer는 page 하나씩 증가하지만,
- oneshot 묶음이 다 차기 전까지는 channel/lun 전진 규칙을 완전히 넘기지 않는다.
- 즉, pointer 이동 규칙 자체가 `pgs_per_oneshotpg`에 묶여 있다.

```c
wpp->pg += spp->pgs_per_oneshotpg;
if (wpp->pg != spp->pgs_per_blk)
	goto out;
```

- channel/lun을 다 돌고 나면 다음 wordline으로 갈 때도
- oneshot 크기만큼 page index를 건너뛴다.

즉, oneshot 크기가 달라지면 wordline 진행 규칙도 달라진다.

```c
if (last_pg_in_wordline(conv_ftl, &ppa)) {
	nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &swr);
}
```

- host write도 oneshot 묶음이 다 찼을 때만 실제 NAND write를 발행한다.

```c
.xfer_size = spp->pgsz * spp->pgs_per_oneshotpg,
```

- 한 번의 NAND write 크기 자체도 oneshot page에 맞춰진다.

```c
if (last_pg_in_wordline(conv_ftl, &new_ppa)) {
	gcw.cmd = NAND_WRITE;
	gcw.xfer_size = spp->pgsz * spp->pgs_per_oneshotpg;
}
```

- GC write도 같은 규칙을 쓴다.
- 즉, host write든 GC write든 현재 코드는 모두 전역 단일 oneshot 규칙 하나에 기대고 있다.

과제 자료는 여기서 바로 실습2 요구를 준다.

```text
SLC TLC는 oneshot page size가 다름
```

그리고 이어서:

```text
반드시 skeleton code의 `ssd_config.h` 값을 사용해야 한다.
```

중요한 점은, 현재 조사 기준으로는 실습2용 SLC/TLC 정확한 oneshot 값이 아직 현재 skeleton code에 추가되어 있지 않다는 것이다. 이건 로그에도 정리돼 있다.

즉, 지금 확정할 수 있는 사실은:

- 실습2는 SLC/TLC oneshot 차이를 반영하라고 요구한다.
- 현재 저장소 코드는 `ONESHOT_PAGE_SIZE`를 전역 단일 값 하나로만 쓴다.
- 따라서 실습2 구현에서는 `pgs_per_oneshotpg`, `last_pg_in_wordline()`, write pointer 전진 규칙, NAND write `xfer_size`가 SLC/TLC에 따라 갈라져야 한다.

함수 호출 흐름으로 정리하면 다음과 같다.

1. `ssd_init_params()`가 `ONESHOT_PAGE_SIZE`에서 `pgs_per_oneshotpg`를 계산한다.
2. write 경로는 `get_new_page()` 후 `advance_write_pointer()`를 부르며, 이때 전진 규칙이 `pgs_per_oneshotpg`를 사용한다.
3. `last_pg_in_wordline()`가 현재 page가 oneshot 경계인지 판단한다.
4. oneshot 경계일 때만 `ssd_advance_nand()`로 실제 program write를 발행한다.
5. 따라서 oneshot 크기는 단순 설정값이 아니라 write 동작 전체를 바꾸는 핵심 값이다.

실습2에서 무엇이 달라져야 하는지 설명하면 다음과 같다.

- 지금은 `SLC write`와 `TLC write`가 같은 `pgs_per_oneshotpg`를 쓴다고 가정한다.
- 실습2에서는 이 가정이 깨진다.
- 따라서 적어도 개념적으로는:
  - SLC write pointer 전진 규칙
  - TLC write pointer 전진 규칙
  - SLC host write NAND program 크기
  - TLC migration/GC NAND program 크기
가 서로 다를 수 있다.
- read 쪽에서는 `flash page` 단위가 더 직접적으로 중요하고,
- write/migration 쪽에서는 `oneshot page` 단위가 더 직접적으로 중요하다.

네가 반드시 기억할 핵심 3개는 다음과 같다.

- `oneshot page`는 NAND program 단위이고, `page`나 `flash page`와 같은 개념이 아니다.
- 현재 코드는 `ONESHOT_PAGE_SIZE`를 전역 단일 값으로 사용하며, write pointer 전진과 NAND write 발행 시점이 이 값에 묶여 있다.
- 실습2에서는 SLC와 TLC의 oneshot page size 차이를 반영해야 하므로, write/migration 경로의 전진 규칙과 program 단위를 SLC/TLC에 따라 분리해야 한다.

- 간단 요약: `oneshot page`는 NAND가 한 번에 program하는 묶음 단위이고, 현재 코드는 이 값을 전역 하나로만 쓰지만 실습2에서는 SLC/TLC마다 다를 수 있으므로 write 경로 규칙 전체를 분기해야 한다.

### 12. Greedy, Random, FIFO, Cost-Benefit migration 정책

- 상태: 예정

---

## 실습2 구현 큰 그림

지금까지 배운 내용을 기준으로 보면, 실습2는 “기존 Conventional FTL을 버리고 새로 만드는 과제”가 아니라 “현재 단일 공간 Conventional FTL 위에 SLC cache 구조를 덧붙이는 과제”다.

핵심은 다음 여섯 축에서 현재 코드의 의미를 바꾸는 것이다.

### 1. Config와 SSD parameter

- 현재 `ssd_config.h`, `ssd.c:ssd_init_params()`는 단일 `CELL_MODE`, 단일 `ONESHOT_PAGE_SIZE`, 단일 latency 값을 SSD 전체에 적용한다.
- 실습2에서는 적어도 개념상
  - SLC 비율
  - SLC용 oneshot/page/program 특성
  - TLC용 oneshot/page/program 특성
  이 구분되어야 한다.
- 따라서 현재 전역 단일 파라미터 구조가 실습2의 첫 번째 변경 지점이다.

관련 위치:

- [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h)
- [ssd.c](/home/hjyu216/nvmevirt/ssd.c#L68)

### 2. 단일 line manager를 SLC/TLC ownership 구조로 분리

- 현재 `struct conv_ftl`에는 `line_mgmt lm` 하나만 있다.
- 이 구조는 모든 line이 같은 종류의 공간이라는 전제를 가진다.
- 실습2에서는
  - SLC free/full/victim
  - TLC free/full/victim
  을 분리해야 한다.
- 특히
  - host write는 SLC free line을 써야 하고
  - migration destination은 TLC free line을 써야 하며
  - SLC victim reclaim은 다시 SLC free list로 돌아가야 하므로
  line manager 분리는 필수다.

관련 위치:

- [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L52)
- [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h#L71)

### 3. 초기화 단계에서 line ownership 확정

- 현재 `init_lines()`는 모든 line을 하나의 free list에 넣는다.
- 실습2에서는 초기화 시 전체 line 집합을 SLC 소유 line과 TLC 소유 line으로 나눠야 한다.
- 이 단계가 먼저 되어야 이후 host write, migration, TLC GC가 어디서 line을 받아야 하는지 의미가 생긴다.

관련 위치:

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L224)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L451)

### 4. host write 목적지를 단일 공간에서 SLC로 변경

- 현재 host write는 `USER_IO` write pointer 하나가 가리키는 단일 공간으로 들어간다.
- 실습2의 첫 실질 동작 변화는 “host write를 SLC에 먼저 쓰는 것”이다.
- 따라서 write 경로에서 바뀌어야 하는 것은
  - 어떤 write pointer를 쓰는가
  - 어떤 free line pool을 소모하는가
  - line close 후 어떤 queue로 들어가는가
다.

관련 위치:

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L1085)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L299)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L311)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L330)

### 5. read는 mapping 기반 구조를 유지하되 SLC/TLC 분기 추가

- 현재 read는 `maptbl`이 가리키는 `PPA`를 그대로 읽는다.
- 이 기본 구조는 실습2에서도 유지하는 것이 자연스럽다.
- 대신 mapping 결과가 SLC인지 TLC인지에 따라
  - 어느 영역을 읽는지
  - 어떤 timing/geometry 규칙을 적용하는지
를 분기해야 한다.
- 중요한 점은 mapping table은 둘로 나누지 않는다는 것이다.

관련 위치:

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L993)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L74)
- [docs/PRACTICE2_CODEX_INSTRUCTIONS.md](/home/hjyu216/nvmevirt/docs/PRACTICE2_CODEX_INSTRUCTIONS.md#L227)

### 6. 기존 TLC GC는 유지하고, SLC→TLC migration을 별도 경로로 추가

- 현재 GC는 TLC victim을 골라 TLC -> TLC로 공간을 회수하는 경로다.
- 실습2에서는 이 경로를 없애는 것이 아니라 유지해야 한다.
- 동시에 별도의 SLC migration 경로를 추가해야 한다.
- migration은
  - SLC victim 선택
  - valid data만 TLC destination에 기록
  - mapping 갱신
  - SLC line reclaim
의 흐름을 가진다.
- 이때 정책, victim queue, counter, free line 경쟁 의미가 TLC GC와 섞이면 안 된다.

관련 위치:

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L912)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L722)
- [docs/PRACTICE2_AGENTS](/home/hjyu216/nvmevirt/docs/PRACTICE2_AGENTS#L166)

### 7. migration policy는 victim selection만 분리

- 실습2 비교 대상은 Greedy, Random, FIFO, Cost-Benefit이다.
- 이 정책들은 migration 전체 코드를 네 벌 만드는 것이 아니라, “어느 SLC victim line을 고를지”만 바꾸는 것이 자연스럽다.
- 현재 TLC GC용 Greedy/Random/Cost-Benefit 일부 로직은 재사용 가능성이 있지만, 대상 queue와 의미는 분리해야 한다.
- FIFO는 현재 코드에 없으므로 close sequence 또는 별도 insertion order metadata가 추가로 필요하다.

관련 위치:

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L769)
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c#L129)
- [docs/PRACTICE2_CODEX_INSTRUCTIONS.md](/home/hjyu216/nvmevirt/docs/PRACTICE2_CODEX_INSTRUCTIONS.md#L560)

### 8. 구현 순서 제안

현재 이해를 바탕으로 한 가장 안전한 순서는 다음과 같다.

1. `config`와 metadata에서 SLC/TLC ownership을 표현할 구조를 추가한다.
2. 초기화에서 line을 SLC/TLC로 나누고 manager 2개를 세팅한다.
3. host write를 SLC manager + SLC write pointer로 보내는 구조를 만든다.
4. read가 mapping 결과에 따라 SLC/TLC를 읽도록 분기한다.
5. Greedy 기반 SLC→TLC migration 하나를 먼저 만들어 정상 동작을 검증한다.
6. 그 다음 Random, FIFO, Cost-Benefit으로 victim selection만 확장한다.
7. 마지막으로 계측과 실험 스크립트를 SLC migration과 TLC GC 기준으로 분리한다.

### 지금 시점의 한줄 결론

실습2에서 바뀌어야 하는 핵심은 “mapping을 둘로 나누는 것”이 아니라, “현재 단일 line manager + 단일 공간 write/GC 구조를 SLC host write, SLC reclaim, TLC destination, TLC GC가 공존할 수 있는 구조로 분리하는 것”이다.

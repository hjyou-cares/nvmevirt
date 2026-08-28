# Practice 2 Implementation Log

이 문서는 실습2의 실제 코드 변경 내용을 기록한다.

원칙:
- 구현 코드 변경이 발생한 날마다 날짜 기준으로 기록한다.
- 각 항목은 `확인한 내용`, `변경한 내용`, `변경 이유`, `검증 결과`, `남은 위험`을 분리한다.
- 조사 메모와 구현 메모를 섞지 않는다.
- 실험 결과는 raw data 위치와 함께 적는다.

## 2026-08-19: 1단계 구조 뼈대 추가

### 확인한 내용

- 현재 Conventional FTL은 단일 `line_mgmt`, 단일 host write pointer, 단일 GC write pointer만 가진다.
- 실습2를 위해서는 SLC/TLC를 나눌 metadata가 먼저 필요하다.
- 아직 SLC/TLC 실제 write 경로를 연결하기 전이므로, 이번 단계에서는 동작을 바꾸지 않는 범위가 안전하다.

### 변경한 내용

- [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h)에 `SLC_CACHE_RATIO_PERCENT` 설정값을 추가했다.
- [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h)에 다음 뼈대를 추가했다.
  - line이 어느 pool에 속하는지 나타내는 `enum line_pool_id`
  - FIFO/close-age용 `close_seq`
  - SLC/TLC line 수를 담는 `struct slc_cache_layout`
  - 이후 실제 분리 manager와 write pointer를 담을 `struct slc_cache_runtime`
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 새 metadata 기본값 초기화를 추가했다.
  - SLC 비율
  - total/SLC/TLC line 수 계산
  - 분리 manager/write pointer 뼈대 zero-init
  - line close sequence 갱신

### 변경 이유

- 실습2의 첫 안전한 단계는 “어디를 SLC로, 어디를 TLC로 볼지 담을 자리”를 만드는 것이다.
- 기존 `wp/gc_wp/lm`를 바로 뜯어고치면 read/write/GC 경로가 한 번에 흔들려 회귀 위험이 크다.
- 먼저 구조만 추가해 두면 다음 단계에서 초기화 분리, 그다음 write 목적지 변경, 그다음 migration 연결 순으로 작게 진행할 수 있다.

### 검증 결과

- 이 단계에서는 동작 변경을 의도하지 않았다.
- 현재 세션에서는 커널 빌드 환경을 확인하지 않았고, `make`/`insmod`는 아직 실행하지 않았다.

### 남은 위험

- 새 metadata는 아직 실제 I/O 경로에서 사용되지 않는다.
- `SLC_CACHE_RATIO_PERCENT`의 기본값은 임시로 `0`이며, 이는 “구조만 먼저 추가하고 기존 동작을 유지”하기 위한 값이다.
- 다음 단계에서 실제 line manager 분할을 연결할 때 `0%`와 `100%` 경계값 정책을 코드로 명시해야 한다.

## 2026-08-19: 2단계 line ownership 초기화

### 확인한 내용

- `struct line`의 `list_head entry`는 한 번에 하나의 list에만 들어갈 수 있다.
- 따라서 아직 legacy `lm`를 쓰는 동안에는 같은 line을 SLC manager list와 TLC manager list에 동시에 넣을 수 없다.
- 이 단계에서는 list 분리 대신 “각 line이 원칙적으로 어느 pool에 속하는지”만 초기화하는 것이 안전하다.

### 변경한 내용

- [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h)에 `slc_line_boundary`를 추가했다.
- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 다음 helper를 추가했다.
  - configured line id 기준 pool 판별
  - PPA 기준 pool 판별
  - PPA가 SLC인지 여부 판별
- `init_slc_layout_metadata()`에서 SLC/TLC line 수와 boundary를 계산하고, future manager의 `tt_lines`를 채우도록 했다.
- `init_lines()`에서 각 line의 `pool`을 `LINE_POOL_SHARED`가 아니라 실제 configured pool로 초기화하도록 바꿨다.
- `conv_init_ftl()`에서는 layout metadata를 먼저 만들고 그 다음 line을 초기화하도록 순서를 바꿨다.

### 변경 이유

- 다음 단계에서 write path를 SLC로 보내려면 먼저 현재 line/ppa가 SLC인지 TLC인지 물을 수 있어야 한다.
- 아직 legacy free list를 유지하는 동안에도 pool ownership 자체는 미리 계산해 둘 수 있다.
- 초기화 순서를 바꾸지 않으면 line 생성 시점에 pool 판별에 필요한 boundary 정보가 없다.

### 검증 결과

- 아직 build 전이다.
- 다음 확인 단계에서 `git diff --check`와 `make`를 수행한다.

### 남은 위험

- 현재 legacy `lm` free list는 여전히 전체 line을 하나의 pool처럼 관리한다.
- 따라서 실제 SLC/TLC manager 분리는 아직 시작되지 않았다.
- 다음 단계에서 SLC/TLC free line 할당 경로를 따로 만들 때 `list_head` 재사용 문제를 구조적으로 해결해야 한다.

## 2026-08-19: 3단계 pool-aware free line accounting

### 확인한 내용

- 현재 free line은 모두 legacy `lm.free_line_list` 하나에 들어 있다.
- `struct line`의 `entry`는 하나뿐이므로, free 상태의 같은 line을 동시에 여러 free list에 넣을 수는 없다.
- 따라서 당장은 free list를 물리적으로 둘로 나누기보다, legacy free list를 유지하면서 pool별 free line 수를 별도 accounting하는 방식이 가장 안전하다.

### 변경한 내용

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 pool별 free line manager 선택 helper를 추가했다.
- free line을 하나 꺼낼 때 legacy 전체 free count와 pool별 free count가 함께 감소하도록 바꿨다.
- free line으로 반환할 때도 legacy 전체 free count와 pool별 free count가 함께 증가하도록 바꿨다.
- 원하는 pool의 free line만 골라 꺼내는 `get_next_free_line_by_pool()` helper를 추가했다.

### 변경 이유

- 다음 단계에서 host write를 SLC 전용 free line에서만 시작하려면 “SLC free line 하나 선택”이 가능해야 한다.
- 하지만 아직 실제 free list 구조를 크게 바꾸면 기존 GC/close/reclaim 경로가 한꺼번에 흔들릴 수 있다.
- 그래서 먼저 accounting과 selection helper부터 맞춘 뒤, 그 helper를 사용해 write pointer를 안전하게 옮기는 순서가 낫다.

### 검증 결과

- `git diff --check` 기준으로 공백/패치 형식 문제는 없다.
- build는 여전히 확인하지 못했다. 현재 세션에는 `make` 명령이 없다.

### 남은 위험

- `get_next_free_line_by_pool()`는 아직 실제 write pointer 경로에 연결되지 않았다.
- 현재 상태에서는 pool-aware selection 기능이 준비된 것뿐이고, 실제 host write는 기존 generic free line 선택을 계속 사용한다.

## 2026-08-19: build error 1차 수정

### 확인한 내용

- 사용자가 2026년 8월 19일 `make`를 실행했을 때 `conv_ftl.c`에서 implicit declaration 에러가 발생했다.
- 원인은 `init_lines()`가 `get_configured_line_pool()`와 `inc_pool_free_line_cnt()`를 먼저 호출하는데, 두 함수의 정의가 파일 아래쪽에 있어서 커널 빌드가 implicit declaration을 에러로 처리한 것이다.

### 변경한 내용

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 두 helper의 forward declaration을 추가했다.

### 변경 이유

- 지금 문제는 로직 버그가 아니라 C 함수 선언 순서 문제다.
- 구조를 다시 옮기기보다 prototype을 먼저 선언하는 편이 가장 작은 수정으로 빌드를 복구한다.

### 검증 결과

- `git diff --check` 통과.
- 이 세션에서는 여전히 `make` 실행 환경이 없어서 직접 재빌드는 못 했다.
- 사용자가 같은 환경에서 다시 `make`를 실행해 다음 에러가 남는지 확인해야 한다.

### 남은 위험

- 선언 순서 문제는 해결했지만, 아직 실제 SLC/TLC 동작 변경은 시작 전 단계라 다음 단계에서 새로운 compile/runtime 문제가 생길 수 있다.

## 2026-08-19: 4단계 pool-aware write pointer 연결

### 확인한 내용

- 이제 free line selection helper가 있으므로, write pointer가 어떤 pool에서 line을 집어와야 하는지 연결할 수 있다.
- `USER_IO`는 실습2 구조상 SLC를 우선 써야 하고, `GC_IO`는 TLC free line을 써야 한다.
- 아직 SLC→TLC migration은 구현되지 않았으므로, `SLC_CACHE_RATIO_PERCENT > 0` 상태에서 SLC pool이 모두 소진되면 이후 동작은 아직 지원되지 않는다.

### 변경한 내용

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 `get_io_target_pool()` helper를 추가했다.
- `prepare_write_pointer()`가 generic free line이 아니라 I/O 타입에 맞는 pool의 free line을 고르도록 바꿨다.
- `advance_write_pointer()`도 현재 write pointer가 쓰던 line과 같은 pool에서 다음 free line을 고르도록 바꿨다.

### 변경 이유

- 실습2의 가장 중요한 동작 변화는 “host write는 SLC에 먼저 쓰고, TLC GC는 TLC를 사용한다”는 점이다.
- 이걸 구현하려면 read path나 migration보다 먼저 write pointer가 올바른 pool에서 line을 가져와야 한다.
- 기존 line close/full/victim/free 로직은 유지하고, line selection만 바꾸는 방식이 가장 작은 동작 변경이다.

### 검증 결과

- `git diff --check` 기준으로 패치 형식 문제는 없다.
- 사용자는 직전 단계에서 `make`가 통과했다고 확인했다.
- 이번 단계는 아직 이 세션에서 직접 재빌드하지 못했다.

### 남은 위험

- `SLC_CACHE_RATIO_PERCENT > 0`일 때 SLC가 가득 차면 아직 migration이 없어서 추가 host write는 실패 경로로 갈 수 있다.
- 따라서 다음 우선순위는 SLC free 부족 조건 정의와 Greedy 기반 SLC→TLC migration 연결이다.

## 2026-08-19: 5단계 Greedy SLC→TLC migration 첫 연결

### 확인한 내용

- SLC migration의 victim 후보는 TLC GC와 다르다.
- TLC GC는 invalid page가 있는 victim queue만 보면 되지만, SLC migration은 full SLC line도 목적지(TLC)가 있으면 옮길 수 있어야 한다.
- 기존 `gc_valid_page_migrate_cnt`와 write credit은 실습1 TLC GC 의미이므로, SLC host write까지 그대로 연결하면 의미가 섞인다.

### 변경한 내용

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에서 `should_gc()`와 `should_gc_high()`가 TLC free line 기준으로 동작하게 바꿨다.
- TLC GC victim 선택을 pool-aware하게 바꿨다. 이제 TLC GC는 generic victim queue 안에서도 TLC line만 고른다.
- SLC migration victim 선택 helper를 새로 추가했다.
  - SLC victim queue 후보
  - SLC full line 후보
  - 둘을 함께 보고 Greedy(min-vpc)로 선택
- 기존 erase/reclaim 본문을 공통 `reclaim_one_line()`으로 분리했다.
- TLC GC는 `do_gc()`에서 공통 reclaim을 그대로 사용하고, SLC migration은 `do_slc_migration()`에서 같은 reclaim 경로를 사용한다.
- `advance_write_pointer()`에서 SLC line이 닫히고 다음 SLC free line이 없으면 `foreground_slc_migration()`을 먼저 수행하도록 연결했다.
- host write가 SLC에 쓰인 경우에는 기존 TLC GC용 write credit을 소모하지 않도록 바꿨다.

### 변경 이유

- 실습2에서 SLC가 가득 찼을 때 필요한 핵심 동작은 “SLC victim 하나를 골라 TLC로 옮기고, 그 SLC line을 다시 free로 돌리는 것”이다.
- 이걸 가장 작은 변경으로 구현하려면 기존 copy-back/erase 경로를 재사용하고, victim 선택과 trigger 조건만 분리하는 것이 낫다.
- TLC GC와 SLC migration의 후보 집합이 다르므로 selection도 분리해야 한다.

### 검증 결과

- `git diff --check` 통과.
- 이 세션에서는 직접 `make`를 실행할 수 없다.
- 사용자가 이전 단계에서 `make` 무오류를 확인한 만큼, 이번 단계도 같은 환경에서 재빌드 확인이 필요하다.

### 남은 위험

- migration 통계는 아직 TLC GC 통계와 완전히 분리되지 않았다.
- read latency/timing은 아직 SLC/TLC를 구분하지 않는다.
- `SLC_CACHE_RATIO_PERCENT > 0` 상태의 실제 smoke test는 아직 수행하지 않았다.

## 2026-08-19: 6단계 migration/TLC GC 통계 분리

### 확인한 내용

- 실습2에서는 TLC GC와 SLC migration을 다른 현상으로 봐야 한다.
- 기존 `GC_VALID_PAGE_MIGRATE_CNT` 하나만으로는 “어느 쪽에서 valid page를 옮겼는지” 구분할 수 없다.
- 기존 실험 스크립트와의 호환성도 당장은 유지하는 편이 안전하다.

### 변경한 내용

- [conv_ftl.h](/home/hjyu216/nvmevirt/conv_ftl.h)와 [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 다음 카운터를 추가했다.
  - `tlc_gc_cnt`
  - `tlc_gc_valid_page_migrate_cnt`
  - `slc_migration_cnt`
  - `slc_migration_valid_page_migrate_cnt`
- 공통 reclaim 경로가 reclaim reason을 받아, TLC GC와 SLC migration을 각각 다른 카운터로 누적하도록 바꿨다.
- [main.c](/home/hjyu216/nvmevirt/main.c)의 `/proc/nvmev/debug` 출력과 `reset` 경로에 새 카운터를 연결했다.
- 기존 `GC_VALID_PAGE_MIGRATE_CNT`는 당분간 TLC GC valid-page copy 의미로 유지했다.

### 변경 이유

- 실습2에서는 “SLC victim을 TLC로 옮긴 비용”과 “TLC 내부 GC 비용”을 따로 봐야 정책 비교가 가능하다.
- 동시에 기존 스크립트가 바로 깨지지 않도록 legacy counter 이름은 유지하는 쪽이 안전하다.

### 검증 결과

- `git diff --check` 기준 문제 없음.
- 실제 `/proc/nvmev/debug` 값 확인은 사용자 VM에서 smoke test가 필요하다.

### 남은 위험

- 기존 스크립트는 아직 새 `SLC_MIGRATION_*` 카운터를 수집하지 않는다.
- 다음 단계에서는 smoke test와 함께 debug 출력 형식이 예상대로 나오는지 먼저 확인해야 한다.

## 2026-08-19: 7단계 migration policy 분리 및 4종 연결

### 확인한 내용

- 과제 요구사항은 TLC GC 정책과 SLC migration 정책의 의미를 분리하라고 명시한다.
- 현재 코드는 `gc_policy` 하나가 TLC GC와 SLC migration의 Greedy/Random/Cost-Benefit 의미를 함께 암묵적으로 공유하고 있었다.
- SLC migration은 TLC GC와 달리 victim queue뿐 아니라 full SLC line도 후보에 포함해야 하므로, policy 구현도 queue top 재사용으로 끝나지 않는다.

### 변경한 내용

- [conv_ftl.c](/home/hjyu216/nvmevirt/conv_ftl.c)에 `slc_migration_policy` module parameter를 추가했다.
  - `0=Greedy`
  - `1=Random`
  - `2=FIFO`
  - `3=Cost-Benefit`
- 기존 `gc_policy` 설명을 TLC GC 전용 의미로 좁혔다.
- SLC migration victim 선택 helper를 정책별 분기 구조로 바꿨다.
  - Greedy: 최소 `vpc`
  - Random: SLC full/victim 후보 전체에서 균등 무작위
  - FIFO: 가장 오래 전에 close된 line 우선
  - Cost-Benefit: 기존 `cb_victim_pri()` 공식을 재사용
- TLC GC 진단 스캔도 TLC pool line만 보도록 보정했다.

### 변경 이유

- 실습2에서는 TLC 내부 GC와 SLC→TLC migration이 다른 정책 실험 대상이므로 설정 이름부터 분리돼야 한다.
- migration 후보 집합은 TLC GC와 다르기 때문에, 정책 구현도 별도 helper에서 full line과 victim line을 함께 본 뒤 선택해야 한다.
- 기존 `gc_policy` 이름을 유지한 것은 실습1 스크립트 및 보고서 호환성을 크게 깨지 않으면서 의미만 TLC GC 전용으로 좁히기 위해서다.

### 검증 결과

- `git diff --check` 통과.
- 이 세션 환경에는 `make` 자체가 없어 직접 빌드 확인은 못 했다.
- 따라서 compile/runtime 검증은 사용자의 빌드 환경에서 이어서 확인해야 한다.

### 남은 위험

- `slc_migration_policy`가 추가됐지만 현재 기본 `SLC_CACHE_RATIO_PERCENT`가 `0`이어서 기본 경로에서는 migration code가 비활성이다.
- Cost-Benefit 공식을 migration에도 그대로 재사용했으므로, 실측 결과가 기대와 다른 경우 migration 전용 점수식 분리가 필요할 수 있다.
- policy별 smoke test와 데이터 정합성 검증은 아직 남아 있다.

## 2026-08-21: 로컬 VM smoke test로 migration 경로 확인

### 확인한 내용

- 현재 worktree의 [ssd_config.h](/home/hjyu216/nvmevirt/ssd_config.h)에서는 `SLC_CACHE_RATIO_PERCENT`가 더 이상 `0`이 아니라 `10`이다.
- 사용자 VM에서 ext4 위에 순차 write 후 같은 파일에 randwrite를 반복하는 작은 smoke test를 수행했다.
- 새 파일을 추가로 만들면 파일시스템 용량 부족이 섞이므로, smoke test는 같은 파일을 재사용하는 편이 안전하다.
- `echo reset > /proc/nvmev/debug`는 debug counter만 초기화하며 FTL 내부 state reset과는 다르다.

### 변경한 내용

- 코드 변경은 하지 않았다.
- 다음 세션 진입 비용을 줄이기 위해 [docs/CURRENT_TASK.md](/home/hjyu216/nvmevirt/docs/CURRENT_TASK.md)와 [docs/CODEX_BOOTSTRAP.md](/home/hjyu216/nvmevirt/docs/CODEX_BOOTSTRAP.md)를 현재 상태에 맞게 갱신했다.

### 변경 이유

- 기존 인계 문서에는 `SLC_CACHE_RATIO_PERCENT=0` 및 “smoke test 미실행” 상태가 남아 있어 실제 코드/검증 상태와 어긋났다.
- 새 세션이 오래된 상태를 전제로 움직이면 불필요한 재확인과 잘못된 우선순위가 생긴다.

### 검증 결과

- 사용자 VM의 `/proc/nvmev/debug`에서 다음을 확인했다.
  - `TLC_GC_CNT 15253`
  - `TLC_GC_VALID_PAGE_MIGRATE_CNT 0`
  - `SLC_MIGRATION_CNT 45059`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1397376`
- 위 결과는 현재 코드에서 host write가 SLC를 사용하고, SLC가 차면 TLC로 migration이 발생하며, 이후 TLC GC도 실제로 돈다는 것을 보여준다.
- 같은 smoke workload에서는 `DIAG_TOTAL_GC 15253`이지만 `DIAG_IDENTITY_DIVERGE`, `DIAG_SUM_GREEDY_VPC`, `DIAG_SUM_CB_VPC`, `DIAG_SUM_ABS_VPC_DIFF`, `DIAG_SAME_VPC_DIFF_LINE`은 모두 `0`이었다.
- 이는 현재 smoke workload로는 Greedy와 Cost-Benefit 차이가 드러나지 않았음을 뜻한다.

### 남은 위험

- 이 검증은 기능 smoke 수준이며 read-back 또는 `fio verify` 기반 데이터 정합성 검증은 아직 없다.
- 로컬 VM은 용량이 작아 파일시스템 ENOSPC가 쉽게 섞이므로 정책 비교 실험 환경으로는 부적합할 수 있다.
- policy 비교는 서버에서 fresh reload 조건(`umount -> rmmod -> insmod -> mkfs -> mount`)으로 다시 수행해야 한다.

## 2026-08-21: commit/push 및 서버 동기화 마무리

### 확인한 내용

- 로컬 작업 트리의 실습2 코드와 인계 문서를 하나의 커밋으로 정리할 수 있는 상태였다.
- 서버 저장소는 처음에는 `main` 브랜치에 있었고, `origin/practice2-slc-cache`에는 최신 commit `8aa39ca`가 존재했다.

### 변경한 내용

- 로컬에서 다음 커밋을 만들었다.
  - `8aa39ca` `Add SLC migration scaffolding and session docs`
- 이후 원격 `origin/practice2-slc-cache`로 push를 완료했다.
- 서버에서는 `practice2-slc-cache`를 checkout하고 `git pull origin practice2-slc-cache`로 최신 상태를 반영했다.

### 변경 이유

- 다음 세션의 실제 실험은 로컬 VM이 아니라 서버에서 진행하기로 했으므로, 서버가 현재 실습2 코드와 동일한 commit을 가리키도록 맞춰 둘 필요가 있었다.
- branch가 `main`에 머물러 있으면 사용자가 서버에서 오래된 코드로 실험을 시작할 위험이 있다.

### 검증 결과

- 서버 `~/nvmevirt`에서 `git log --oneline -n 5` 기준 `HEAD -> practice2-slc-cache`, `origin/practice2-slc-cache`가 모두 `8aa39ca`를 가리키는 것을 확인했다.
- 서버 `git status --short`는 빈 출력이었고 clean worktree 상태였다.

### 남은 위험

- 다음 세션은 서버에서 시작하되, 실험 전에 `make`와 block device 경로(`/dev/nvme1n1`)를 다시 한 번 확인해야 한다.
- 아직 정책 비교 실험과 데이터 정합성 검증은 수행하지 않았다.

## 2026-08-23: 로컬 4정책 비교 및 로컬 실행 스크립트 추가

### 확인한 내용

- 서버 쪽 이슈 때문에 오늘은 로컬 VM 기준으로 이어서 진행했다.
- 기존 서버용 workload(`600M x 250`)를 로컬에 그대로 쓰면 지나치게 오래 걸릴 수 있어, 로컬용 기준을 따로 두는 편이 맞다.
- 사용자 로컬 실행 결과 `results/local_20260823_212734_slc_policy_compare/`에 fresh reload 기반 4정책 비교 결과가 남았다.
- 이 비교에서 정책 매핑은 현재 코드 기준으로 `0=Greedy`, `1=Random`, `2=FIFO`, `3=Cost-Benefit`이다.

### 변경한 내용

- [scripts/run_local_slc_policy_compare.sh](/home/hjyu216/nvmevirt/scripts/run_local_slc_policy_compare.sh)를 새로 추가했다.
  - `smoke` 모드: 기본 `128M x 20`
  - `compare` 모드: 기본 `600M x 10`
  - `gc_policy=0`을 고정하고 `slc_migration_policy`만 바꾸도록 했다.
  - 모듈 리로드는 `umount -> rmmod -> insmod -> mkfs -> mount` 순서를 자동화했다.
  - device 대기는 `udevadm settle`을 우선 사용하고, 최종적으로 block device 존재만 확인한다.
- [docs/CURRENT_TASK.md](/home/hjyu216/nvmevirt/docs/CURRENT_TASK.md)와 [docs/CODEX_BOOTSTRAP.md](/home/hjyu216/nvmevirt/docs/CODEX_BOOTSTRAP.md)를 오늘 기준 로컬 진행 상태에 맞게 갱신했다.

### 변경 이유

- 기존 [scripts/run_experiment.sh](/home/hjyu216/nvmevirt/scripts/run_experiment.sh)는 아직 `gc_policy` 중심 서버 실험 스크립트라, 오늘 필요한 로컬 `slc_migration_policy` 비교와 바로 맞지 않았다.
- 매번 수동으로 길게 입력한 로컬 명령을 재사용 가능한 형태로 묶어 두면 다음 세션 진입 비용이 줄어든다.
- 인계 문서가 계속 서버 우선 상태로 남아 있으면 다음 세션이 현재 실제 흐름과 어긋날 수 있다.

### 검증 결과

- 사용자는 로컬에서 smoke test와 4정책 비교를 직접 완료했다.
- `results/local_20260823_212734_slc_policy_compare/` 기준:
  - Greedy(`0`): `TLC_GC_CNT 15540`, `SLC_MIGRATION_CNT 45060`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440939`, fio runtime 약 `292211 ms`
  - Random(`1`): `TLC_GC_CNT 5835`, `SLC_MIGRATION_CNT 45018`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1130392`, fio runtime 약 `73571 ms`
  - FIFO(`2`): `TLC_GC_CNT 15527`, `SLC_MIGRATION_CNT 45020`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440508`, fio runtime 약 `94600 ms`
  - Cost-Benefit(`3`): `TLC_GC_CNT 15526`, `SLC_MIGRATION_CNT 45030`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440485`, fio runtime 약 `100708 ms`
- Random만 다른 3개와 꽤 다르고, Greedy/FIFO/Cost-Benefit은 현재 로컬 workload에서 거의 같은 범주로 묶였다.
- `DIAG_*` 값은 네 정책 모두 `0`이라 TLC GC Greedy vs Cost-Benefit 차이는 이 로컬 조건에선 드러나지 않았다.
- `bash -n scripts/run_local_slc_policy_compare.sh` 문법 확인은 통과했다.

### 남은 위험

- smoke test는 별도 저장 파일이 남지 않아, 자세한 수치는 4정책 비교 결과 쪽이 사실상 오늘의 기준 기록이다.
- 현재 로컬 workload(`600M x 10`)에서는 `0/2/3` 차이가 충분히 드러나지 않아, 더 적절한 workload 탐색이 필요하다.
- 데이터 정합성 검증(`fio verify` 또는 read-back)은 아직 추가되지 않았다.

## 2026-08-23: `run_experiment.sh`를 SLC migration policy 기준으로 전환

### 확인한 내용

- 기존 [scripts/run_experiment.sh](/home/hjyu216/nvmevirt/scripts/run_experiment.sh)는 여전히 실습1/초기 실습2 기준의 `gc_policy` 중심 실험 스크립트였다.
- 현재 코드에서는 `gc_policy`와 `slc_migration_policy`의 의미가 분리됐으므로, 기존처럼 첫 번째 policy 인자를 곧바로 `gc_policy`에 연결하면 실습2 실험 의도와 어긋난다.
- 사용자는 오늘 “기존 단일 policy 실험 흐름을 지금은 TLC GC 고정 + SLC migration 비교로 연결하는 의미냐”라고 확인했고, 그 방향으로 정리하기로 했다.

### 변경한 내용

- [scripts/run_experiment.sh](/home/hjyu216/nvmevirt/scripts/run_experiment.sh)를 수정했다.
  - 첫 번째 인자 `policy`를 `slc_migration_policy` 의미로 재정의했다.
  - 허용 범위를 `0|1|2|3`으로 늘리고 이름 매핑을 `Greedy/Random/FIFO/Cost-Benefit`으로 바꿨다.
  - `TLC_GC_POLICY` 환경변수를 추가하고 기본값을 `0`으로 뒀다.
  - `insmod` 시 `gc_policy="$TLC_GC_POLICY"`와 `slc_migration_policy="$POLICY"`를 함께 넘기도록 바꿨다.
  - 결과 디렉터리 이름을 `slcpolicy*` 형태로 바꿨다.
  - `meta.txt`에 `policy_target=slc_migration`, `tlc_gc_policy`, `slc_migration_policy`를 추가 기록하게 했다.
  - 기존 sleep loop는 제거하고 `udevadm settle` 우선 방식으로 device 생성을 기다리게 했다.
  - `summary.txt`는 `SLC_MIGRATION_CNT`, `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT`, `TLC_GC_CNT`, `TLC_GC_VALID_PAGE_MIGRATE_CNT`를 직접 읽어 요약하게 바꿨다.

### 변경 이유

- 실습2에서 비교 대상은 TLC GC 정책이 아니라 SLC migration victim policy이므로, 실험 스크립트의 policy 의미도 거기에 맞춰야 한다.
- `gc_policy`를 그대로 실험축으로 두면 “정책 실험을 하고 있다”는 이름과 달리 실제로는 TLC GC만 바꾸게 되어, 현재 로컬에서 확인한 SLC migration 결과와 연결이 끊긴다.
- 로컬 스크립트와 본 실험 스크립트의 의미를 맞춰 두면 다음 세션부터 manual command와 scripted run이 같은 실험축을 공유하게 된다.

### 검증 결과

- `bash -n scripts/run_experiment.sh` 문법 확인을 통과했다.
- 이번 세션에서는 실제 full run까지는 아직 다시 돌리지 않았다.

### 남은 위험

- `scripts/collect_summary.sh`는 여전히 `policy`/`policy_name` 중심 CSV만 모으므로, 필요하면 `policy_target`이나 migration counter를 추가 열로 확장할 수 있다.
- `run_filebench_experiment.sh`는 아직 `gc_policy` 중심이라, filebench도 실습2 migration 비교에 쓸 계획이면 같은 정리가 추가로 필요하다.

## 2026-08-23: 로컬 CRC verify 모드 추가

### 확인한 내용

- 현재까지는 SLC migration/TLC GC가 "돈다"는 것만 확인했지, 데이터 정합성은 아직 검증하지 않았다.
- 저장소 과거 기록에는 `fio --verify=crc32c --verify_fatal=1`로 GC 이후 read-back CRC 검증을 수행한 방법론이 이미 남아 있다.
- 지금 로컬 흐름에서는 기존 수동 명령 대신 [scripts/run_local_slc_policy_compare.sh](/home/hjyu216/nvmevirt/scripts/run_local_slc_policy_compare.sh)에 verify 모드를 붙이는 편이 다음 재실행에 유리하다.

### 변경한 내용

- [scripts/run_local_slc_policy_compare.sh](/home/hjyu216/nvmevirt/scripts/run_local_slc_policy_compare.sh)에 `verify` 모드를 추가했다.
  - 사용법: `./scripts/run_local_slc_policy_compare.sh verify [policy]`
  - 기본 workload: `VERIFY_SIZE=600M`, `VERIFY_LOOPS=10`, `VERIFY_BS=4k`
  - fio 옵션: `--verify=crc32c --verify_fatal=1 --verify_state_save=0 --do_verify=1`
  - 결과 저장: `results/local_*_slc_verify_policyN/`
  - 산출물: `fio.json`, `debug.txt`, `meta.txt`, `fio_cmd.txt`

### 변경 이유

- 정합성 검증을 workload 조정보다 먼저 해 두는 편이 이후 비교 실험의 해석 안정성이 높다.
- manual command보다 스크립트 모드로 남겨 두면 같은 fresh reload 조건을 반복 재사용하기 쉽다.

### 검증 결과

- `bash -n scripts/run_local_slc_policy_compare.sh` 문법 확인을 통과했다.
- 실제 verify run 결과는 아직 이 세션에서 생성하지 않았다.

### 남은 위험

- random overwrite + verify workload에서 정책별 runtime이 길어질 수 있으므로, 필요하면 `VERIFY_SIZE`나 `VERIFY_LOOPS`를 줄여 먼저 smoke verify를 할 수 있다.
- verify 결과가 나오기 전까지는 데이터 정합성이 실제로 통과했다는 결론을 내릴 수 없다.

## 2026-08-23: `zipf_nrm` 로컬 조건으로 SLC migration policy 차이 확인

### 확인한 내용

- 기존 로컬 uniform(`600M x 10`)에서는 Random만 크게 다르고 Greedy/FIFO/Cost-Benefit은 거의 수렴했다.
- 과거 기록을 다시 확인한 결과, 단순 사용률 확대나 `zoned` 분포보다 `zipf:1.2`가 가장 강하게 정책 차이를 만들었다.
- `NORANDOMMAP=1`을 켜야 fio가 "한 pass에 모든 블록을 정확히 한 번씩 방문"하는 인공적인 완전 무효화 패턴을 피할 수 있다는 점도 기존 스크립트 주석과 과거 로그에 정리돼 있었다.

### 변경한 내용

- 코드 변경은 하지 않았다.
- [scripts/run_experiment.sh](/home/hjyu216/nvmevirt/scripts/run_experiment.sh)로 다음 로컬 실험을 4정책 모두 수행했다.
  - `UNIFORM_SIZE=600M`
  - `UNIFORM_LOOPS=10`
  - `RANDOM_DIST=zipf:1.2`
  - `NORANDOMMAP=1`
  - `TLC_GC_POLICY=0`
  - label=`zipf_nrm`
- 결과 경로:
  - [results/20260823_225741_slcpolicy0_greedy_zipf_nrm](/home/hjyu216/nvmevirt/results/20260823_225741_slcpolicy0_greedy_zipf_nrm)
  - [results/20260823_230204_slcpolicy1_random_zipf_nrm](/home/hjyu216/nvmevirt/results/20260823_230204_slcpolicy1_random_zipf_nrm)
  - [results/20260823_230615_slcpolicy2_fifo_zipf_nrm](/home/hjyu216/nvmevirt/results/20260823_230615_slcpolicy2_fifo_zipf_nrm)
  - [results/20260823_231332_slcpolicy3_costbenefit_zipf_nrm](/home/hjyu216/nvmevirt/results/20260823_231332_slcpolicy3_costbenefit_zipf_nrm)

### 변경 이유

- uniform과 zoned가 계속 수렴한다면, "valid 상태로 오래 살아남는 데이터"가 실제로 생기는 분포를 만들어야 SLC migration policy 차이를 볼 수 있다.
- `zipf:1.2`는 과거 TLC GC 실험에서 가장 뚜렷한 분리 신호를 줬으므로, 현재 실습2 로컬 조건에서도 가장 먼저 시도할 가치가 있었다.

### 검증 결과

- `0/2/3`도 더 이상 완전히 수렴하지 않았다.
  - Greedy(`0`): `sum=180772`, `max=42`, `slc_migrate_pages=112766`, `tlc_gc_cnt=0`
  - Random(`1`): `sum=180904`, `max=37`, `slc_migrate_pages=154228`, `tlc_gc_cnt=0`
  - FIFO(`2`): `sum=180844`, `max=21`, `slc_migrate_pages=122230`, `tlc_gc_cnt=0`
  - Cost-Benefit(`3`): `sum=180700`, `max=32`, `slc_migrate_pages=104875`, `tlc_gc_cnt=0`
- 해석:
  - TLC GC가 전혀 발생하지 않았으므로(`tlc_gc_cnt=0`), 이 비교는 사실상 SLC migration policy 차이만 읽어도 된다.
  - Cost-Benefit은 4정책 중 `slc_migrate_pages`가 가장 낮았다.
  - FIFO는 `max`가 가장 낮아 peak wear 억제 측면은 가장 강했지만, migration cost는 Cost-Benefit보다 높았다.
  - Random은 migration cost가 가장 높았다.

### 남은 위험

- 현재 `zipf_nrm`은 각 정책당 1회 측정이라 반복측정이 아직 없다.
- `scripts/collect_summary.sh`는 migration counter를 CSV 열로 모으지 않으므로, 결과 정리를 더 하려면 스크립트 보강이 필요할 수 있다.

## 2026-08-23: 로컬 CRC verify 결과 확보 (`policy 0/1`)

### 확인한 내용

- verify 모드 추가 뒤 실제로 CRC 정합성 검증을 돌려 결과를 남겼다.
- verify는 단순 write/read가 아니라 migration과 TLC GC가 함께 발생하는 조건에서도 수행됐다.

### 변경한 내용

- 코드 변경은 하지 않았다.
- 다음 두 verify run 결과를 생성했다.
  - [results/local_20260823_224010_slc_verify_policy0](/home/hjyu216/nvmevirt/results/local_20260823_224010_slc_verify_policy0)
  - [results/local_20260823_224607_slc_verify_policy1](/home/hjyu216/nvmevirt/results/local_20260823_224607_slc_verify_policy1)

### 변경 이유

- workload 차이 해석보다 먼저, SLC migration/TLC GC가 섞인 상태에서 데이터가 깨지지 않는 최소 근거를 확보하는 게 우선이었다.

### 검증 결과

- `fio.json` 기준 두 run 모두 `error=0`으로 끝났다.
- `policy 0` verify run:
  - `SLC_MIGRATION_CNT 45030`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440521`
  - `TLC_GC_CNT 15526`
- `policy 1` verify run:
  - `SLC_MIGRATION_CNT 45031`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1130585`
  - `TLC_GC_CNT 5842`
- 즉 migration/GC가 실제로 발생한 상태에서도 CRC mismatch 없이 통과했다.

## 2026-08-23: 로컬 CRC verify 결과 완료 (`policy 2/3`)

### 확인한 내용

- 앞서 `policy 0/1` verify는 통과했지만 `2/3`가 비어 있어, 오늘 마감 전 이 둘도 같은 조건으로 채웠다.

### 변경한 내용

- 코드 변경은 하지 않았다.
- 다음 두 verify run 결과를 추가 생성했다.
  - [results/local_20260823_232744_slc_verify_policy2](/home/hjyu216/nvmevirt/results/local_20260823_232744_slc_verify_policy2)
  - [results/local_20260823_233241_slc_verify_policy3](/home/hjyu216/nvmevirt/results/local_20260823_233241_slc_verify_policy3)

### 변경 이유

- `0/1`만 통과한 상태로 마무리하면, migration policy 4종 전체에 대한 최소 정합성 체크가 비어 있게 된다.

### 검증 결과

- `policy 2` verify run:
  - `fio.json` 기준 `error=0`
  - `TLC_GC_CNT 15524`
  - `SLC_MIGRATION_CNT 45028`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440426`
- `policy 3` verify run:
  - `fio.json` 기준 `error=0`
  - `TLC_GC_CNT 15524`
  - `SLC_MIGRATION_CNT 45028`
  - `SLC_MIGRATION_VALID_PAGE_MIGRATE_CNT 1440425`
- 이로써 `policy 0/1/2/3` 네 정책 모두 migration/GC가 실제로 발생하는 조건에서 CRC verify를 통과했다.

### 남은 위험

- verify는 통과했지만, `zipf_nrm`은 아직 각 정책 1회씩만 있어 반복측정이 없다.

## 2026-08-24: `zipf_nrm` 반복측정 완료 (`rep2`, `rep2_rerun`, `rep3`)

### 확인한 내용

- 로컬 `zipf_nrm` baseline 1회만으로는 정책 경향은 보였지만 반복측정이 없어 해석 안정성이 부족했다.
- `scripts/collect_summary.sh` 확장으로 migration counter와 workload 조건을 CSV로 함께 읽을 수 있게 되어, 반복 run 비교가 이전보다 쉬워졌다.
- 로컬 VM에서는 `run_experiment.sh`의 기본값이 `uniform 600M x 250`이라, `RANDOM_DIST`/`NORANDOMMAP`/`UNIFORM_LOOPS=10`를 빠뜨리면 의도보다 훨씬 긴 실험이 된다.

### 변경한 내용

- 코드 변경은 하지 않았다.
- 다음 유효한 로컬 결과를 추가 생성했다.
  - `zipf_nrm_rep2`
    - [results/20260824_173902_slcpolicy0_greedy_zipf_nrm_rep2](/home/hjyu216/nvmevirt/results/20260824_173902_slcpolicy0_greedy_zipf_nrm_rep2)
    - [results/20260824_174027_slcpolicy1_random_zipf_nrm_rep2](/home/hjyu216/nvmevirt/results/20260824_174027_slcpolicy1_random_zipf_nrm_rep2)
    - [results/20260824_174206_slcpolicy2_fifo_zipf_nrm_rep2](/home/hjyu216/nvmevirt/results/20260824_174206_slcpolicy2_fifo_zipf_nrm_rep2)
    - [results/20260824_175416_slcpolicy3_costbenefit_zipf_nrm_rep2](/home/hjyu216/nvmevirt/results/20260824_175416_slcpolicy3_costbenefit_zipf_nrm_rep2)
  - `zipf_nrm_rep2_rerun`
    - [results/20260824_223708_slcpolicy0_greedy_zipf_nrm_rep2_rerun](/home/hjyu216/nvmevirt/results/20260824_223708_slcpolicy0_greedy_zipf_nrm_rep2_rerun)
    - [results/20260824_224519_slcpolicy1_random_zipf_nrm_rep2_rerun](/home/hjyu216/nvmevirt/results/20260824_224519_slcpolicy1_random_zipf_nrm_rep2_rerun)
    - [results/20260824_225438_slcpolicy2_fifo_zipf_nrm_rep2_rerun](/home/hjyu216/nvmevirt/results/20260824_225438_slcpolicy2_fifo_zipf_nrm_rep2_rerun)
    - [results/20260824_230218_slcpolicy3_costbenefit_zipf_nrm_rep2_rerun](/home/hjyu216/nvmevirt/results/20260824_230218_slcpolicy3_costbenefit_zipf_nrm_rep2_rerun)
  - `zipf_nrm_rep3`
    - [results/20260824_232544_slcpolicy0_greedy_zipf_nrm_rep3](/home/hjyu216/nvmevirt/results/20260824_232544_slcpolicy0_greedy_zipf_nrm_rep3)
    - [results/20260824_232938_slcpolicy1_random_zipf_nrm_rep3](/home/hjyu216/nvmevirt/results/20260824_232938_slcpolicy1_random_zipf_nrm_rep3)
    - [results/20260824_233522_slcpolicy2_fifo_zipf_nrm_rep3](/home/hjyu216/nvmevirt/results/20260824_233522_slcpolicy2_fifo_zipf_nrm_rep3)
    - [results/20260824_234119_slcpolicy3_costbenefit_zipf_nrm_rep3](/home/hjyu216/nvmevirt/results/20260824_234119_slcpolicy3_costbenefit_zipf_nrm_rep3)
- `results/20260824_173844_slcpolicy1_random_zipf_nrm_rep2/`와 일부 `rep2_rerun`/`rep3` 빈 디렉터리는 중간 실패 흔적으로 보고 집계에서 제외했다.

### 변경 이유

- baseline 1회 결과만으로는 우연 변동인지 구조적 차이인지 분리하기 어렵다.
- 같은 `zipf:1.2 + NORANDOMMAP=1 + 600M x 10` 조건에서 반복측정을 추가하면, 정책 간 순위가 안정적인지 빠르게 확인할 수 있다.

### 검증 결과

- 공통 조건: `UNIFORM_SIZE=600M`, `UNIFORM_LOOPS=10`, `RANDOM_DIST=zipf:1.2`, `NORANDOMMAP=1`, `TLC_GC_POLICY=0`
- `slc_migrate_pages`는 4회 모두 같은 순위를 유지했다.
  - Cost-Benefit(`3`): `104229`, `105106`, `105195`
  - Greedy(`0`): `112686`, `113526`, `113104`
  - FIFO(`2`): `120384`, `128099`, `126602`
  - Random(`1`): `152216`, `163745`, `159498`
- baseline까지 포함하면 `slc_migrate_pages` 순위는 4회 내내 `Cost-Benefit < Greedy < FIFO < Random`이다.
- `max`는 baseline, `rep2`, `rep2_rerun`, `rep3` 네 번 모두 FIFO(`2`)가 최저였다 (`21` 고정).
- `tlc_gc_cnt`는 이번 반복측정 12개 run 전부 `0`이라, 이 조건은 사실상 SLC migration policy만 비교한 결과로 읽을 수 있다.

### 남은 위험

- 로컬 `zipf_nrm`에서는 순위가 안정적이지만, `hotcold v7`에서도 같은 방향인지 아직 모른다.
- VS Code Remote 단절은 대개 `umount/rmmod/insmod/mkfs/mount` 경계에서 발생하므로, 다음 로컬 반복 실행은 `tmux` 안에서 진행하는 편이 안전하다.

## 2026-08-27: guarded reclaim/write-credit + reserve admission control 검증

### 확인한 내용

- `random hotcold full`에서 `No data available`와 함께 `Refusing TLC GC: victim line 832 does not fit current TLC GC capacity`가 반복됐다.
- 첫 guarded patch만으로는 fit 불가능한 victim을 같은 기준으로 반복 선택하는 문제가 남아 있었다.
- `hotcold`는 `zipf`보다 오래된 고-vpc line을 더 오래 유지해 SLC migration/TLC GC capacity 충돌을 더 쉽게 드러냈다.

### 변경한 내용

- `conv_ftl.c`
  - reclaim 시작 전 TLC GC capacity precheck를 넣었다.
  - TLC GC 성공 시에만 write credit를 refill하도록 바꿨다.
  - host write path에서 `advance_write_pointer()`가 hidden reclaim을 호출하지 않게 정리했다.
  - fit 가능한 victim만 선택하도록 TLC GC/SLC migration victim selection을 수정했다.
  - SLC migration 후에도 TLC GC 1 line capacity를 남기도록 reserve-style admission control을 추가했다.
- `conv_ftl.h`
  - 더 이상 쓰지 않는 `credits_to_refill` 필드를 제거했다.
- 인계 문서
  - `docs/CODEX_BOOTSTRAP.md`
  - `docs/CURRENT_TASK.md`

### 변경 이유

- 기존 경로는 reclaim/write-credit 실패가 hang 대신 `WRITE_FAULT`로 올라오게 만드는 데는 진전이 있었지만, TLC capacity에 맞지 않는 victim을 반복 선택해 `full`에서 계속 실패할 수 있었다.
- `hotcold full`을 안전하게 끝내려면 migration admission control이 TLC GC runway를 보존해야 했다.

### 검증 결과

- 실패 흔적:
  - `results/20260827_191221_slcpolicy1_random_hotcold_server_random_full_guarded/`
  - `results/20260827_192227_slcpolicy1_random_hotcold_server_random_full_guarded/`
  - 둘 다 `fio.json` 기준 `error=61`
- 성공 run:
  - `overflow` 재검증
    - [results/local_20260827_193407_slc_overflow_validation](/home/hjyoo/nvmevirt2/results/local_20260827_193407_slc_overflow_validation)
    - `SLC_MIGRATION_CNT=1476`
    - `USER_READ_TLC_PAGES=476118`
    - `INTERNAL_WRITE_TLC_PAGES=566781`
  - `hotcold full guarded`
    - [results/20260827_192853_slcpolicy1_random_hotcold_server_random_full_guarded](/home/hjyoo/nvmevirt2/results/20260827_192853_slcpolicy1_random_hotcold_server_random_full_guarded)
    - [results/20260827_193453_slcpolicy0_greedy_hotcold_server_greedy_full_guarded](/home/hjyoo/nvmevirt2/results/20260827_193453_slcpolicy0_greedy_hotcold_server_greedy_full_guarded)
    - [results/20260827_193630_slcpolicy2_fifo_hotcold_server_fifo_full_guarded](/home/hjyoo/nvmevirt2/results/20260827_193630_slcpolicy2_fifo_hotcold_server_fifo_full_guarded)
    - [results/20260827_193804_slcpolicy3_costbenefit_hotcold_server_cb_full_guarded](/home/hjyoo/nvmevirt2/results/20260827_193804_slcpolicy3_costbenefit_hotcold_server_cb_full_guarded)
    - `slc_migrate_pages` 순위: `FIFO < Cost-Benefit < Greedy < Random`
    - `max erase` 최소: FIFO(`25`)
  - `CRC verify policy1`
    - [results/local_20260827_194155_slc_verify_policy1](/home/hjyoo/nvmevirt2/results/local_20260827_194155_slc_verify_policy1)
    - `fio error=0`
    - `verify_status=pass`
    - `SLC_MIGRATION_CNT=38380`
    - `USER_READ_TLC_PAGES=6563552`

### 남은 위험

- 오늘 성공한 `CRC verify`는 `policy 1` 한 세트만 추가 확인했다.
- 최종 보고서용으로는 `baseline/SLC-on`, 서버 `zipf_nrm`, 서버 `hotcold full guarded`를 같은 CSV 형식으로 묶어 비교표를 정리해야 한다.

## 2026-08-28: SLC resident-to-sustained crossover 실험 준비

### 변경한 내용

- `ssd.c`
  - 기존 compile-time `WRITE_EARLY_COMPLETION` 값을 기본값으로 유지하면서,
    `write_early_completion=0/1` insmod parameter로 같은 binary에서 선택할 수 있게 했다.
- `scripts/run_experiment.sh`
  - 선택적 `WRITE_EARLY_COMPLETION`과 `FIO_IODEPTH` 환경변수를 추가하고 meta에 기록한다.
- `scripts/run_slc_crossover_experiments.sh`
  - resident `1G x 1`, overflow `6G x 1`, sustained `22G x 3`을 ratio 0/10,
    각 3회 fresh reload로 실행하는 18-run suite를 추가했다.
- `report/make_slc_crossover_figure.py`
  - 18개 조건 완성도, fio 오류, completion/iodepth, migration counter를 검사하고
    raw/aggregate CSV와 평균±표준편차 그림을 생성한다.
- 실행 가이드
  - `docs/PRACTICE2_SLC_CROSSOVER_EXPERIMENT.md`

### 변경 이유

- 기존 `WRITE_EARLY_COMPLETION=1`에서는 짧은 write의 host completion이 controller buffer에
  가려져 SLC/TLC NAND program latency 차이가 fio에 충분히 드러나지 않았다.
- 같은 completion 조건에서 SLC 내부 resident 구간과 saturation 이후 migration 구간을 함께
  비교해야 "SLC는 항상 빠르다"가 아니라 workload 크기에 따른 crossover를 보여줄 수 있다.

### 검증 상태

- Bash 구문 검사 통과.
- Dry-run은 기본 매트릭스 18개를 정확히 출력했다.
- Python 집계기 `--help` import/구문 확인 통과.
- 결과가 없는 현재 상태에서 strict 집계기가 누락 18개와 종료 코드 2를 반환하는 것을 확인했다.
- 현재 Codex 셸은 WSL2 커널 header 경로가 없어 모듈 빌드는 수행하지 못했다. 서버에서 재빌드가 필요하다.

## 2026-08-28: 확장 결과 집계와 p99.9 crossover 보고서 반영

### 변경한 내용

- 서버에서 완료한 확장 실험 60개와 crossover rep1 6개를 검증하고 집계했다.
- `report/make_slc_crossover_figure.py`
  - fio의 `99.900000` percentile을 읽어 p99.9를 raw/aggregate CSV와 그래프에 사용하도록 변경했다.
- `report/make_practice2_extended_figures.py`
  - ratio 민감도 그림의 무의미한 TLC GC 0 패널을 erase/GiB 패널로 교체했다.
- `report/REPORT.md`
  - ratio 0/5/10/20 민감도, Zipf/Hot-cold/Uniform 3회 반복, crossover 결과를 새 표와 그림으로 반영했다.
  - 기본 확장 실험(`early_completion=1`, `iodepth=16`)과 crossover(`early_completion=0`, `iodepth=1`)의 절대 성능을 직접 비교하지 않도록 실험 방법과 한계를 명시했다.

### 핵심 결과

- Resident 1 GiB: SLC throughput +23.5%, p99.9 -44.3%, migration 0%.
- Overflow 6 GiB: SLC throughput +16.9%이나 p99.9 +76.2%, migration/host write 20.1%.
- Sustained 66 GiB: throughput +0.6%로 사실상 동일, p99.9 13.6배, erase 합계 3.43배.
- Zipf 3회 반복: Cost-Benefit이 migrated pages/GiB 최소, FIFO가 peak erase 최소.
- Hot-cold 3회 반복: FIFO가 throughput, p99, SLC/TLC copy cost, erase 지표에서 종합 우위.
- Uniform: 정책 간 throughput 및 SLC copy 차이가 각각 1.46%, 1.58%로 작아 locality 의존성을 확인했다.

### 생성물

- `report/extended_results/practice2_extended_raw.csv`
- `report/extended_results/practice2_extended_aggregate.csv`
- `report/crossover_results/slc_crossover_raw.csv`
- `report/crossover_results/slc_crossover_aggregate.csv`
- `report/figures/practice2_ext_fig1_ratio_sensitivity.png`부터 `practice2_ext_fig5_slc_crossover.png`

## 2026-08-28: 제출용 Word 초안 생성

- `report/build_practice2_docx.py`를 추가했다.
- Markdown 원고의 초안 상태 문구를 제외하고 heading level을 Word 목차 구조에 맞춰 변환한다.
- Pandoc DOCX에 A4/25 mm 여백, 표지와 목차 분리, Heading 1 새 페이지, 한글/영문 글꼴, 페이지 번호, 목차 자동 갱신, 그림 폭 제한, 표 자동 맞춤과 첫 행 반복을 후처리한다.
- 생성 파일: `report/PRACTICE2_REPORT.docx`
- 구조 검증: DOCX ZIP 오류 없음, 그림 8개, 표 17개, 반복 머리행 17개, footer 및 updateFields 설정 확인.
- 재생성 명령: `python3 report/build_practice2_docx.py`

## 2026-08-28: GitHub 렌더링용 REPORT.md 정리

- `practice2-slc-cache` 브랜치의 기존 `report/REPORT.md`를 실습 2 최종 원고로 교체했다.
- `report/figures/*.png` 상대경로를 사용하므로 브랜치 push 후 GitHub에서 표와 그래프가 본문 안에 바로 표시된다.
- Word 파일 링크를 원고 상단에 추가하고 `build_practice2_docx.py`도 `report/REPORT.md`를 단일 원본으로 사용하도록 변경했다.

## 2026-08-28: 보고서 가독성 중심 압축

- 원고를 428줄/5,217단어에서 191줄/1,851단어로 줄였다.
- 초기 baseline/SLC-only/overflow 그래프 3개는 핵심 counter 표 하나로 통합하고, ratio/crossover/Zipf/Hot-cold/workload sensitivity의 핵심 그림 5개만 유지했다.
- 구현 절은 구조·migration 정책·검증의 3개 절로, 실험 방법은 환경·실험 구성의 2개 절로 합쳤다.
- 결과에서 이미 설명한 내용을 분석과 결론에서 반복하지 않고, 운영 구간·locality·write amplification의 핵심 해석만 남겼다.
- Word를 재생성해 그림 5개, 표 9개, 반복 머리행 9개와 목차/페이지 번호 설정을 검증했다.

## 2026-08-28: 제출용 코드 구조 안내

- `Code_Structure_Notice.txt`에 Practice 1 기준선 대비 핵심 변경 파일과 주요 함수, 실험/분석 파일, 검증 결과를 정리했다.
- 핵심 구현 파일은 `conv_ftl.c`, `conv_ftl.h`, `ssd.c`, `ssd.h`, `ssd_config.h`이며 계측/안정성 파일 `main.c`, `io.c`도 첨부 대상으로 분류했다.
- Word와 위 7개 코드를 개별 첨부할 수 있도록 필수/선택 파일을 구분했다.

## 2026-08-28: Workload 설명 보강

- 압축 보고서의 실험 방법에 workload별 접근 패턴, 크기/반복, 확인 목적을 정리한 표를 추가했다.
- Uniform/Zipf 통제 조건, `norandommap`, Hot-cold 동시 실행, crossover의 low-queue/early-completion 조건이 왜 필요한지 설명했다.

## 2026-08-28: 4장 결과 그래프 8개 복원

- 압축 과정에서 제외했던 Baseline, SLC-only, Overflow 그래프를 4장에 다시 추가했다.
- 최신 ratio/crossover/Zipf repeat/Hot-cold repeat/workload sensitivity 5개와 합쳐 총 8개를 사용한다.
- 이전 single-run Zipf/Hot-cold 그래프 2개는 최신 3회 반복 그림과 중복되고 binary 기준이 달라 제외했다.
- Word 재생성 검증: 그림 8개, 표 11개, 반복 머리행 11개.

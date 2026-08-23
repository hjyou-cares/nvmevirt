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

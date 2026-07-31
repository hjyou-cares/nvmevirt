실습 1: NVMeVirt Cost-Benefit GC 구현 및 성능 분석
====================================================

제출자: 유형진 (인턴)
제출일: 2026-07-31

원본 저장소: https://github.com/snu-csl/nvmevirt
작업 저장소: https://github.com/hjyou-cares/nvmevirt


1. 보고서
---------
report/REPORT.pdf      <- 제출용 보고서 (REPORT.html을 브라우저에서 변환)
report/REPORT.html     <- 그림까지 포함한 단일 HTML (report/make_html.sh로 생성)
report/REPORT.md       <- 같은 내용의 원본 (Markdown)
report/figures/        <- 보고서에 실린 그래프 6장 (fig1~fig6)
report/make_figures.py <- 그래프 생성 스크립트 (results/의 실측값에서 직접 계산)


2. 구현한 코드
--------------
conv_ftl.c / conv_ftl.h
  - gc_policy 모듈 파라미터 (0=Greedy, 1=Random, 2=Cost-Benefit)
  - Random 정책: select_victim_line()에서 victim pqueue의 무작위 인덱스를
    pqueue_remove()로 회수
  - Cost-Benefit 정책: struct line에 mtime 필드와 전역 논리 시계 cb_clock을
    추가해 age를 추적하고, cb_victim_pri()가 (ipc * age) / (2 * vpc)를 계산
  - mark_page_invalid(): pqueue_change_priority() 대신 remove + insert 사용
    (파생 우선순위를 쓰면 change_priority의 단위 전제가 깨지기 때문)
  - select_victim_line(): Cost-Benefit일 때 pqueue_pop() 대신 전체 스캔
    (힙 staleness 버그 수정 -- 보고서 2.3절)
  - diag_scan_greedy_vs_cb(): 두 정책의 선택을 매 GC마다 비교하는 분석 계측
    (read-only, 실제 GC 동작에는 영향 없음 -- 보고서 3.4절)
  - gc_valid_page_migrate_cnt: GC가 실제로 옮긴 valid page 수 누적

main.c
  - /proc/nvmev/debug 읽기: 블록별 erase_cnt 덤프 + 진단 카운터 출력
  - /proc/nvmev/debug에 "reset" 쓰기: 카운터 전체 초기화


3. 실험 스크립트
----------------
scripts/run_experiment.sh           fio 벤치마크 (정책마다 모듈 완전 리로드 + mkfs)
scripts/run_filebench_experiment.sh filebench 벤치마크
scripts/collect_summary.sh          results/ 전체를 CSV로 집계
scripts/workloads/hotcold.fio       핫/콜드 분리 워크로드 (v7)


4. 실험 결과 원본
-----------------
results/<타임스탬프>_policy<N>_<정책>_<라벨>/
  summary.txt   집계 지표 (erase 합/최댓값, migration 비용, 진단 카운터 등)
  meta.txt      실행 조건 (정책, 워크로드, insmod 파라미터, fio 커맨드)
  fio.json      fio 원본 출력 (latency 포함)

  * 블록별 erase 덤프 원본(erase_cnt.txt)은 실행당 131,072줄로 전체 222MB에
    달해 제출본에서는 제외했습니다. 위 summary.txt에 합계/최댓값/변동계수가
    모두 집계되어 있고, 보고서의 모든 수치는 이 파일들에서 계산했습니다.

EXPERIMENT_LOG.md  실험 진행 기록 (시행착오와 판단 근거)


5. 빌드 및 실행
---------------
빌드:
  make                          # Kbuild의 CONFIG_NVMEVIRT_SSD := y 확인

로드 (실험 서버 기준):
  sudo insmod ./nvmev.ko memmap_start=16G memmap_size=48G cpus=7,8 gc_policy=2
  sudo mkfs -t ext4 /dev/nvme1n1
  sudo mount /dev/nvme1n1 ~/nvme_mount

  * gc_policy는 런타임 읽기 전용(0444)입니다. 정책 전환 시 힙이 이전 정책의
    우선순위로 정렬된 상태로 남아 조용히 잘못된 victim을 고르게 되므로,
    정책을 바꾸려면 반드시 모듈을 다시 로드해야 합니다 (보고서 3.1절).

정책 확인:
  cat /sys/module/nvmev/parameters/gc_policy

erase 카운터:
  cat /proc/nvmev/debug | head
  echo reset | sudo tee /proc/nvmev/debug

벤치마크 (정책 0/1/2를 각각):
  NVME_DEV=/dev/nvme1n1 MEMMAP_START=16G MEMMAP_SIZE=48G NVME_CPUS=7,8 \
    ./scripts/run_experiment.sh 0 mytest hotcold

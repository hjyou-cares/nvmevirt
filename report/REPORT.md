# 실습 1: NVMeVirt Cost-Benefit GC 구현 및 성능 분석

## 1. 실습 목표

NVMeVirt(가상 NVMe SSD 커널 모듈)의 Conventional FTL에서 GC(Garbage Collection) victim 선택 정책 3가지를 구현하고, 정책별 성능을 비교한다.

1. **Greedy** — valid page 수(vpc)가 가장 적은 line을 victim으로 선택 (baseline, 원래 구현되어 있던 정책)
2. **Random** — victim queue에서 무작위로 line을 선택
3. **Cost-Benefit** — `(ipc × age) / (2 × vpc)` 값이 가장 큰 line을 victim으로 선택. `age`는 그 line이 마지막으로 쓰여진 시점부터 지금까지 지난 논리 시간(전역 클럭). Valid page 수뿐 아니라 "얼마나 오래 방치됐는가"까지 고려해서, 오래된 콜드 데이터가 많은 line을 우선 회수하는 게 목표.

## 2. 구현 내용

### 2.1 정책 선택 (`conv_ftl.c`)
- 모듈 파라미터 `gc_policy`(0=Greedy, 1=Random, 2=Cost-Benefit)로 정책을 선택. `insmod` 시점에만 지정 가능하도록 런타임 읽기 전용(`0444`)으로 두었다 — 실행 중에 정책을 바꾸면 (a) 이전 정책이 남긴 FTL 내부 상태를 물려받아 비교가 오염되고, (b) Cost-Benefit에서 Greedy로 바꿀 경우 힙이 CB 우선순위로 정렬된 상태라 Greedy가 최소 vpc가 아닌 line을 조용히 회수하게 되기 때문이다.
- `victim_line_get_pri()`가 정책별 우선순위 값을 계산해 pqueue(min-heap)에 반영. Cost-Benefit은 클수록 좋은 victim이라는 점(min-heap과 반대 방향)을 `CB_PRI_MAX - bc`로 뒤집어서 처리.
- `struct line`에 `mtime` 필드를 추가해 line이 닫히는 시점의 전역 논리 클럭(`cb_clock`, 매 page write마다 +1)을 기록 — 이게 Cost-Benefit의 `age` 계산 기준.

### 2.2 Random 정책
victim priority 자체를 무작위화하면 pqueue의 힙 불변식이 깨지므로, `select_victim_line()`에서 pqueue의 원본 배열(`pq->d[]`)에서 무작위 인덱스를 뽑아 `pqueue_remove()`로 꺼내는 방식으로 구현.

### 2.3 Cost-Benefit 정책과 발견한 버그 (중요 — 방법론)

초기 구현은 `victim_line_get_pri()`에 Cost-Benefit 계산식을 추가하고 `pqueue_pop()`으로 heap root를 꺼내는 방식이었다. 그런데 uniform/hotcold 등 여러 워크로드로 반복 측정한 결과 **Greedy와 Cost-Benefit의 GC 통계(erase 횟수, migration 비용)가 계속 거의 동일하게 나오는 현상**을 발견했다. 워크로드를 여러 차례 재설계(핫/콜드 데이터 분리, 시간축 분리 등)해봐도 이 현상은 사라지지 않았다.

원인을 코드 레벨에서 조사한 결과, **pqueue(이진 힙) 구현의 근본적인 한계**를 발견했다:

- Cost-Benefit의 우선순위 값은 `age = cb_clock - mtime`을 포함하는데, `cb_clock`은 매 write마다 계속 증가한다. 즉 큐 안에 있는 line의 "진짜 우선순위"는 시간이 지나면서 계속 바뀐다.
- 하지만 이진 힙(`pqueue/pqueue.c`)은 **어떤 line이 insert/remove될 때 그 line의 조상 경로만** 재정렬한다. 큐 전체를 주기적으로 재검증하는 로직이 없다.
- 그 결과, 한동안 아무 변화가 없던 line들 사이의 상대적 순서가 실제로는 역전됐는데도 힙에는 반영되지 않을 수 있다 — heap root(`pqueue_peek()`/`pqueue_pop()`의 결과)가 "지금 이 순간 진짜 최고의 victim"이 아닐 수 있다는 뜻이다.

이 문제를 실측으로 검증하기 위해:
1. `pqueue/pqueue.c`의 알고리즘을 그대로 재현한 간단한 시뮬레이션으로, 두 개의 line만 있는 최소 예제에서도 몇 스텝만 지나면 heap root가 진짜 최고 우선순위 line과 달라지고 그 상태가 영구적으로 유지됨을 확인했다.
2. 실제 커널 모듈에 임시 카운터를 추가해 워크로드 실행 중 실측한 결과, 전체 GC 판정의 약 5.5%에서 이 문제로 인해 실제 선택이 달라짐을 확인했다.

**해결**: `select_victim_line()`에서 Cost-Benefit 정책일 때는 `pqueue_pop()` 대신, 매 GC마다 victim queue 전체를 스캔해서 그 순간 진짜 우선순위가 가장 높은 line을 찾아 `pqueue_remove()`로 꺼내도록 수정했다. 큐 크기가 GC 빈도에 비해 크지 않아 이 방식의 오버헤드는 감당할 수 있는 수준이었다.

## 3. 실험 방법

### 3.1 환경
- CPU: 서버 2코어 격리(`isolcpus`), NVMeVirt `memmap_size=48G`
- 정책 비교 시마다 커널 모듈을 완전히 리로드(`rmmod`→`insmod`)한 뒤 파일시스템도 새로 생성(`mkfs`) — GC 내부 상태(`cb_clock`, write pointer 등)가 이전 정책의 실행 흔적을 물려받지 않도록 하기 위함.

### 3.2 워크로드
- **uniform**: 4KB 랜덤쓰기를 SSD 용량의 약 3.3배만큼 반복(fio, `loops=250`). 핫/콜드 구분이 없는 균일 워크로드.
- **hotcold (v7)**: 콜드 파일(30GB)을 1회 순차쓰기한 뒤, 콜드 파일 일부 재기록과 핫 파일(1GB) 반복 재기록을 **같은 90초 동안 동시에** 실행(`time_based`). 핫/콜드 데이터가 시간·물리적으로 모두 분리되도록 여러 차례 워크로드를 재설계한 최종 버전.
- **filebench**: 2GB 파일에 4KB 랜덤쓰기 + 매 write마다 fsync, 120초 동안 실행. fio 결과를 다른 도구로 재확인하는 보조 벤치마크.

### 3.3 측정 지표
- **erase 횟수**: 블록별 erase 카운터(`/proc/nvmev/debug`)를 합산·최댓값 확인
- **migration 비용**: GC 한 번당 실제로 옮긴 valid page 수 누적 (`gc_valid_page_migrate_cnt`) — erase 횟수만으론 정책 차이가 잘 안 드러나서 별도로 추가한 지표
- **호스트 IO latency**: fio의 평균/p99 tail latency
- **victim divergence 분석**: 매 GC마다 "Greedy라면 골랐을 line"과 "Cost-Benefit이라면 골랐을 line"을 큐 전체 스캔으로 각각 계산해서, 서로 다른 line을 고른 비율과 그 vpc(비용) 차이를 실시간 누적하는 진단 기능을 코드에 추가(`diag_scan_greedy_vs_cb`, 읽기 전용, 실제 GC 동작에는 영향 없음)

time_based 워크로드(hotcold)는 정책마다 실제 처리한 데이터량이 달라서, 모든 수치를 **GiB당**으로 정규화해 비교했다. uniform은 항상 정확히 같은 바이트 수를 기록하므로 정규화 없이 raw 값을 그대로 비교했다.

### 3.4 결과의 신뢰성 확보를 위해 추가로 수행한 검증

측정값을 그대로 믿기 전에, "구현이 의도대로 동작하는가"와 "고친 코드가 데이터를 손상시키지 않는가"를 각각 따로 검증했다.

**(1) 정책이 실제로 의도한 line을 고르는지 — 교차검증.** 커널이 집계한 `gc_valid_page_migrate_cnt / total_gc`(실제로 회수된 victim의 평균 vpc)를, 진단 기능이 큐 전체 스캔으로 독립 계산한 `avg_greedy_vpc`/`avg_cb_vpc`와 대조했다.

| 실제 구동 정책 | 실제 회수된 victim 평균 vpc | Greedy 이론값 | Cost-Benefit 이론값 |
|---|---|---|---|
| Greedy (3회) | 80.707 / 78.142 / 77.171 | **완전 일치** | 92.6 / 89.2 / 88.2 |
| Cost-Benefit (3회) | 89.925 / 86.706 / 87.716 | 55.2 / 53.9 / 53.9 | **완전 일치** |
| Random (3회) | 187.3 / 186.1 / 188.0 | 8.9 / 8.1 / 8.9 | 10.9 / 9.2 / 10.0 |

Greedy는 항상 최소 vpc line을, Cost-Benefit은 항상 그 순간의 CB 최적 line을 소수점 3자리까지 정확히 회수하고 있음이 확인된다(Random은 어느 쪽과도 맞지 않아 무작위 선택이 정상 동작함을 보인다). 특히 Cost-Benefit의 일치는 2.3절의 힙 staleness 수정이 실제로 작동함을 직접 보여준다.

**(2) GC가 데이터를 손상시키지 않는지 — CRC 검증.** victim 선택 로직을 수정했으므로, 아직 valid page가 남은 line을 잘못 회수하면 이후 읽기에서 잘못된 데이터가 반환될 수 있다. 이를 확인하기 위해 Cost-Benefit 정책으로 8 GiB 파일에 48 GiB(용량 초과 → GC 다수 발생)를 쓰면서 매 블록에 CRC32C를 심고, 종료 후 전부 되읽어 검증했다(`fio --verify=crc32c --verify_fatal=1`). **불일치 0건**으로 통과했다.

**(3) 집계의 물리적 정합성.** 디바이스는 총 131,072 블록 / 32,768 line(line 하나 = 블록 4개 ≈ 1.40 MiB)으로 구성된다. uniform에서 측정된 erase 총합 271,620을 line당 블록 수 4로 나누면 line 회수 67,905회가 되는데, 이는 커널이 독립적으로 센 `total_gc = 67,905`와 정확히 일치한다.

## 4. 결과

### 4.1 hotcold — 정책 간 실질적 차이 (핵심 결과)

**[그림 1: fig1_hotcold_efficiency.png]** — GiB당 migration 비용과 erase 횟수
**[그림 2: fig2_hotcold_wear_leveling.png]** — 최대 erase 횟수(peak wear)와 erase된 블록 수
**[그림 3: fig3_hotcold_latency.png]** — 호스트 IO 평균/p99 latency

| 지표 | Greedy | Cost-Benefit | Random |
|---|---|---|---|
| migrate pages / GiB | 48,493 ± 1,302 | 55,079 ± 1,198 | 134,288 ± 954 |
| erase / GiB | 2,465.4 ± 8.9 | 2,500.2 ± 7.6 | 2,870.4 ± 6.4 |
| erase 최댓값 | 10.3 | **8.3** | 11.3 |
| erase된 블록 수 | 85,624 | **89,433** | 86,500 |
| erase 변동계수 (전체 블록) | 0.786 ± 0.002 | **0.738 ± 0.005** | 0.937 ± 0.003 |
| latency 평균 | 80.2 μs | 84.5 μs | 152.4 μs |
| latency p99 | 432.1 μs | 439.0 μs | 1,521.0 μs |

(각 정책 3회 반복 측정, 평균 ± 표준편차. Greedy-CB 간 range가 거의 겹치지 않아 노이즈가 아닌 실질적 차이로 판단. 변동계수는 전체 131,072개 블록의 erase 횟수 표준편차/평균으로, 낮을수록 마모가 고르다 — Greedy 최저값 0.784와 Cost-Benefit 최고값 0.742가 겹치지 않는다.)

**Cost-Benefit은 총 migration 비용을 Greedy보다 13.6% 더 쓰지만(latency도 약 5% 높지만), 블록 하나의 최대 erase 횟수는 더 낮고(8.3 vs 10.3), 마모를 더 많은 블록에 더 고르게 분산시킨다(블록 수 89,433 vs 85,624, 변동계수 0.738 vs 0.786).** 이는 Cost-Benefit GC가 이론적으로 의도하는 트레이드오프 — 전체 효율을 다소 희생하는 대신 특정 블록에 마모가 집중되는 것을 막아 SSD 수명을 고르게 소모시킴 — 와 정확히 일치하는 결과다.

**Random은 모든 지표에서 확실하게 가장 나쁘다.** victim을 무작위로 골라서 아직 valid page가 많이 남은 line도 자주 회수하게 되고, 그 결과 migration 비용(2.8배), erase 횟수, latency(평균 1.9배, p99 3.5배) 모두 가장 나쁘게 나온다.

### 4.2 uniform — 핫/콜드 구분이 없으면 두 정책은 "증명 가능하게" 동일하다

**[그림 4: fig4_uniform_comparison.png]** — erase 총합과 최댓값
**[그림 8: fig8_workload_decides.png]** — uniform vs hotcold 대비

| 지표 | Greedy | Cost-Benefit | Random |
|---|---|---|---|
| erase 총합 | 271,620 | 271,620 (3회 다 완전 동일) | 273,372 |
| erase 최댓값 | 161 | 161 | 10 |

균일 랜덤쓰기 워크로드에서는 Greedy와 Cost-Benefit이 3회 반복 모두 소수점까지 완전히 동일한 결과를 낸다. 이것이 우연한 수렴인지 구조적 필연인지를 가리기 위해, 같은 워크로드를 진단 기능이 포함된 빌드로 다시 측정했다.

| 진단 지표 (uniform) | Greedy | Cost-Benefit |
|---|---|---|
| GC 총 횟수 (`total_gc`) | 67,905 | 67,905 |
| 두 정책이 다른 line을 고른 횟수 | **0** | **0** |
| 회수된 victim의 평균 vpc | **0.000** | **0.000** |
| GC 중 옮긴 valid page 총합 | **0** | **0** |

**67,905번의 GC 전부에서 victim의 vpc가 정확히 0이었고, 두 정책의 선택이 단 한 번도 갈리지 않았다. 옮겨진 valid page는 하나도 없다 — 이 워크로드에서 GC는 비용이 0이다.**

원인은 워킹셋 크기에 있다. 이 워크로드는 44.86 GiB 디바이스에서 600 MiB 파일 하나만 반복해서 덮어쓰므로, 라이브 데이터가 용량의 1.3%에 불과하다. 그 결과 GC 후보 풀이 사실상 전부 "완전히 무효화된(vpc=0)" line으로 채워지고, 두 정책 모두 이런 line을 무조건 최우선으로 선택하도록 구현돼 있어(`victim_line_get_pri()`의 vpc==0 가드) **선택이 갈릴 여지 자체가 없다.** 즉 이 수렴은 측정 오차나 구현 결함이 아니라 워크로드가 강제한 구조적 결과다.

이는 4.1의 hotcold와 정확히 대비된다 — hotcold에서는 두 정책이 GC의 90.3%에서 다른 line을 골랐고, 그 line들의 vpc 차이는 평균 33.8(평균 vpc의 47%)이었다. **Cost-Benefit의 이점은 회수 후보 사이에 실질적인 "선택의 여지"가 있을 때만 발현된다**는 것이 이 대비로 확인된다.

한편 Random은 이 워크로드에서 뚜렷한 반대 트레이드오프를 보인다: erase 최댓값이 10으로 Greedy/CB(161)의 16분의 1 수준이라 마모는 훨씬 고르지만, 총 erase 횟수는 오히려 0.6% 더 많다. 정확한 회수를 포기한 대가로 마모 분산을 얻는 셈이다.

### 4.3 filebench — fio 결과 재확인 (보조 벤치마크)

**[그림 5: fig5_filebench_comparison.png]**

fio와 별개의 도구인 filebench로도 유사한 패턴(Random이 확실히 열세, Greedy/CB는 핫/콜드 스큐 없는 단일 파일 워크로드라 erase 최댓값 동일)이 재확인되어, fio 기반 결론이 특정 도구에 국한된 결과가 아님을 뒷받침한다. (1회 측정, 보조 데이터로만 사용)

### 4.4 victim divergence 분석 — "다른 line을 골라도 비용은 비슷한가?"

**[그림 6: fig6_vpc_divergence.png]**

Greedy와 Cost-Benefit은 hotcold 워크로드에서 GC 판정의 약 90%에서 서로 다른 line을 선택한다. 그런데 "다르게 고른 게 실제 비용(옮겨야 할 valid page 수, vpc) 차이로 이어지는가"를 확인하기 위해, 매 GC마다 두 정책이 각각 골랐을 line의 vpc를 큐 전체 스캔으로 비교하는 진단을 추가했다.

결과: Cost-Benefit이 실제로 구동 중일 때, 두 정책이 골랐을 line의 vpc 차이는 평균 33.8(평균 vpc의 47%)로 매우 크다. 반면 "다른 line을 골랐는데 vpc는 우연히 같았던" 경우는 0.02%로 사실상 없다. 즉 **다른 line을 고르면 비용도 실제로 다르다** — 이게 앞서 4.1의 GiB당 migration 비용 13.6% 격차의 직접적인 근거다.

### 4.5 버그 수정 전후 비교 (참고)

**[그림 7: fig7_bugfix_before_after.png]**

힙 staleness 버그를 수정하기 전에는 Greedy와 Cost-Benefit의 migration 비용 차이가 각 정책 자체의 반복 측정 간 편차보다 작아 "노이즈 수준"으로만 보였다. 버그를 수정한 뒤에는 3회 반복 모두 range가 겹치지 않는 뚜렷한 차이로 나타났다 — 지금까지 관찰된 "Greedy≈Cost-Benefit 수렴"은 워크로드 설계 문제가 아니라 이 힙 staleness 버그가 Cost-Benefit을 우연히 Greedy와 비슷하게 행동하게 만든 결과였다.

## 5. 결론

1. **Cost-Benefit GC는 총 GC 효율(migration 비용, erase 횟수)을 다소 희생하는 대신, 최대 마모를 낮추고 마모를 더 많은 블록에 분산시켜 웨어 레벨링을 개선한다.** 이는 이론적으로 기대되는 Cost-Benefit GC의 동작과 일치한다.
2. **이 이점은 핫/콜드 데이터가 섞인 워크로드에서만 드러난다.** 균일한 랜덤쓰기 워크로드에서는 Greedy와 Cost-Benefit이 구조적으로 동일하게 수렴한다.
3. **Random 정책은 마모를 가장 고르게 분산시키지만, 총 GC 비용과 latency 모두 가장 나쁘다** — victim 선택 시 valid page 수를 전혀 고려하지 않기 때문.
4. 구현 과정에서 이진 힙 기반 우선순위 큐에 "시간에 따라 계속 변하는 우선순위"를 적용할 때 생기는 근본적인 한계(heap staleness)를 발견하고 수정했다 — 이 수정이 없었다면 Cost-Benefit의 실제 이점이 측정 결과에 제대로 반영되지 않았을 것이다.
5. 결과의 신뢰성을 위해 세 가지 검증을 별도로 수행했다(3.4절): 각 정책이 실제로 의도한 line을 회수하는지 교차검증했고(소수점 3자리까지 일치), 수정된 GC가 데이터를 손상시키지 않음을 CRC32C 검증으로 확인했으며(불일치 0건), erase 집계가 디바이스의 물리적 구조와 정합함을 확인했다(계산값과 커널 카운터가 67,905로 정확히 일치).

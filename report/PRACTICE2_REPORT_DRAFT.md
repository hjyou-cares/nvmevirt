# 실습 2 보고서 초안

## 1. 결과물 1 검증

### 1.1 Baseline: `slc_cache_ratio_percent=0` vs `10`

실험 목적은 동일한 빌드 산출물에서 `slc_cache_ratio_percent`만 `0`과 `10`으로 바꿨을 때, 기본 랜덤쓰기 workload의 성능과 내부 write traffic이 어떻게 달라지는지 확인하는 것이다.

- 환경: `memmap_start=16G`, `memmap_size=48G`, `cpus=7,8`
- workload: `randwrite`, `BASELINE_SIZE=22G`, `BASELINE_LOOPS=7`
- 실행 방식: 각 조건마다 `umount -> rmmod -> insmod -> mkfs -> mount`의 fresh reload
- 결과 디렉터리:
  - `ratio=0`: `results/local_20260828_113345_slc_baseline_compare/tlc_only/`
  - `ratio=10`: `results/local_20260828_113345_slc_baseline_compare/slc_on/`

![Practice 2 Figure 1. Baseline ratio comparison](figures/practice2_fig1_baseline_ratio_compare.png)

| Ratio | Write BW (MiB/s) | Write IOPS | Avg Latency (us) | p99 Latency (us) | SLC Migration Cnt | SLC Migrated Pages | TLC GC Cnt |
|---|---:|---:|---:|---:|---:|---:|---:|
| `0` (TLC-only) | 1,351.3 | 345,940 | 46.0 | 146.4 | 0 | 0 | 73,332 |
| `10` (SLC cache) | 822.0 | 210,410 | 75.8 | 634.9 | 102,812 | 39,472,631 | 73,308 |

내부 page traffic도 크게 갈린다. `ratio=0`에서는 host write가 전부 TLC로 직접 기록되며 `user_write_tlc_pages=40,673,368`, `internal_write_tlc_pages=0`이다. 반면 `ratio=10`에서는 host write가 거의 전부 SLC에 먼저 기록되고(`user_write_slc_pages=40,670,348`), 그 뒤 유효 페이지 `39,472,631`개가 TLC로 migration되었다(`internal_write_tlc_pages=39,472,631`).

이 결과는 이번 baseline 조건이 SLC cache의 이점을 보는 workload라기보다, SLC overflow와 migration 비용을 강하게 드러내는 workload였음을 보여준다. `ratio=10`은 host write를 더 빠른 SLC에 먼저 기록했지만, working set이 SLC 용량을 지속적으로 넘어서면서 거의 동일한 양의 데이터를 다시 TLC로 옮겨야 했다. 그 결과 내부 write amplification이 크게 증가했고, throughput은 `1,351.3 -> 822.0 MiB/s`로 감소했으며 p99 latency는 `146.4 -> 634.9 us`로 악화되었다.

이 baseline 비교는 "SLC cache는 항상 빠르다"는 결론이 아니라, "SLC cache는 overflow가 적고 hot data가 캐시에 머무르는 조건에서 유리하며, sustained write로 migration이 계속 발생하면 오히려 손해가 날 수 있다"는 점을 보여주는 근거로 해석하는 편이 맞다.

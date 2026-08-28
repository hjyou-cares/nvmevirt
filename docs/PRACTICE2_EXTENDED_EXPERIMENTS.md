# Practice 2 추가 실험 실행 가이드

## 목적

보고서의 세 가지 근거를 보강한다.

1. SLC ratio `0/5/10/20%`에서 burst와 sustained write의 성능 및 migration 비용 비교
2. Zipf와 Hot-cold의 네 migration 정책을 현재 binary에서 각 3회 반복
3. 동일한 `22 GiB x 7`, `norandommap=1` 조건의 Uniform 정책 결과를 추가해 workload 민감도 비교

비율 실험은 `slc_migration_policy=Greedy`, 정책 실험은 `slc_cache_ratio_percent=10`,
모든 실험은 `gc_policy=Greedy`로 고정한다. 한 실험에서 하나의 독립 변수만 바꾸기
위한 구성이다.

## 전체 매트릭스

| Suite | 조건 | 반복 | Run 수 |
|---|---|---:|---:|
| Ratio burst | 4 ratios × 1 GiB random write | 3 | 12 |
| Ratio sustained | 4 ratios × 22 GiB × 7 uniform random write | 3 | 12 |
| Policy repeat: Zipf | 4 policies × `zipf:1.2` | 3 | 12 |
| Policy repeat: Hot-cold | 4 policies × 30G/15G/1G, 90초 | 3 | 12 |
| Workload sensitivity: Uniform | 4 policies × uniform random write | 3 | 12 |
| 합계 |  |  | **60** |

Uniform과 Zipf는 `randrepeat=1`, `norandommap=1`, `22 GiB x 7`로 파일 크기와 총
write 양을 통제하고 접근 분포만 바꾼다. Hot-cold는 시간 기반이므로 migrated page와
erase를 written GiB로 정규화한다.

## 실행 전 확인

일반 서버 shell에서 다음이 가능해야 한다.

- 현재 worktree의 `nvmev.ko` 빌드
- `sudo`, `fio`, `mkfs`, `mount`, `rmmod`, `insmod`
- NVMeVirt 장치 `/dev/nvme1n1`
- `memmap_start=16G`, `memmap_size=48G`, `cpus=7,8`

먼저 실제 명령을 실행하지 않는 dry-run으로 60개 조건을 확인한다.

```bash
./scripts/run_practice2_extended_experiments.sh dry-run
```

## 서버 실행

긴 실행이므로 `tmux` 안에서 suite별로 나누어 수행하는 편이 안전하다.

```bash
export NVME_DEV=/dev/nvme1n1
export MEMMAP_START=16G
export MEMMAP_SIZE=48G
export NVME_CPUS=7,8

./scripts/run_practice2_extended_experiments.sh ratio
./scripts/run_practice2_extended_experiments.sh policy
./scripts/run_practice2_extended_experiments.sh sensitivity
```

한 번에 실행하려면 다음을 사용한다.

```bash
./scripts/run_practice2_extended_experiments.sh all
```

기존 완료 label은 자동으로 건너뛴다. 중간에 실패하거나 shell이 끊기면 같은 명령을
다시 실행하면 된다. 완료 run까지 다시 측정하려면 `FORCE_RERUN=1`을 지정한다.

현재 서버 결과를 기준으로 전체 실행은 대략 수 시간이 걸릴 수 있다. 실제 시간은
ratio가 큰 sustained run과 Hot-cold의 TLC GC pressure에 따라 달라진다.

## 빠른 축소 실행

먼저 한 번씩 pilot을 돌려 안정성을 확인할 수 있다.

```bash
RATIO_REPS="1" ./scripts/run_practice2_extended_experiments.sh ratio
POLICY_REPS="1" ./scripts/run_practice2_extended_experiments.sh policy
SENSITIVITY_REPS="1" ./scripts/run_practice2_extended_experiments.sh sensitivity
```

Pilot이 끝난 뒤 기본 명령을 다시 실행하면 rep2와 rep3만 이어서 수행한다.

## 집계 및 그래프

60개 run이 모두 끝난 뒤 다음을 실행한다.

```bash
python3 report/make_practice2_extended_figures.py
```

생성 파일:

- `report/extended_results/practice2_extended_raw.csv`
- `report/extended_results/practice2_extended_aggregate.csv`
- `report/figures/practice2_ext_fig1_ratio_sensitivity.png`
- `report/figures/practice2_ext_fig2_zipf_repeat.png`
- `report/figures/practice2_ext_fig3_hotcold_repeat.png`
- `report/figures/practice2_ext_fig4_workload_sensitivity.png`

진행 중인 결과만 파싱하고 누락 조건을 확인하려면 다음을 사용한다.

```bash
python3 report/make_practice2_extended_figures.py --allow-partial
```

기본 실행은 60개 매트릭스가 완성되지 않으면 종료 코드 2로 중단한다. 불완전한 결과를
최종 error bar 그래프로 오인하는 것을 막기 위한 동작이다.

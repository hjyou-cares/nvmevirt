# SLC Cache Crossover 추가 실험

## 목적

같은 NVMeVirt binary에서 다음 두 영역을 함께 보여준다.

1. Working set이 SLC 안에 머물고 migration이 없는 짧은 write에서는 SLC가 TLC-only보다 유리한 영역
2. SLC가 포화된 뒤 foreground migration이 반복되면 SLC가 TLC-only보다 불리해지는 영역

일반 write-buffer 조기 완료가 NAND program latency 차이를 가리지 않도록
`write_early_completion=0`을 사용한다. 비교하는 모든 ratio와 workload에 동일하게 적용한다.

## 기본 매트릭스

| Variant | Workload | 의미 | Ratios | 반복 | Run 수 |
|---|---|---|---|---:|---:|
| Resident | 1 GiB × 1 | SLC 내부, migration 0 기대 | 0%, 10% | 3 | 6 |
| Overflow | 6 GiB × 1 | SLC 경계 초과 | 0%, 10% | 3 | 6 |
| Sustained | 22 GiB × 3 | 반복 migration/reclaim | 0%, 10% | 3 | 6 |
| 합계 | | | | | **18** |

공통 조건은 4 KiB random write, `iodepth=1`, `numjobs=1`, `randrepeat=1`,
`norandommap=1`, TLC GC Greedy, SLC migration Greedy다. 각 run은 모듈 reload와
새 ext4 생성부터 시작한다.

## 실행 전

`write_early_completion` module parameter가 추가됐으므로 현재 소스로 반드시 다시 빌드한다.

```bash
make -j"$(nproc)"
./scripts/run_slc_crossover_experiments.sh dry-run
```

Dry-run 출력은 기본값 기준 18줄이어야 한다.

## 서버 실행

```bash
export NVME_DEV=/dev/nvme1n1
export MEMMAP_START=16G
export MEMMAP_SIZE=48G
export NVME_CPUS=7,8

tmux new -A -s p2-crossover
./scripts/run_slc_crossover_experiments.sh all
```

Suite별로 나눠 실행할 수도 있다.

```bash
./scripts/run_slc_crossover_experiments.sh resident
./scripts/run_slc_crossover_experiments.sh overflow
./scripts/run_slc_crossover_experiments.sh sustained
```

완료 label은 자동으로 건너뛰므로 중단되면 같은 명령으로 재개한다. 완료 결과까지 다시
측정하려면 `FORCE_RERUN=1`을 지정한다.

## 집계와 검증

```bash
python3 report/make_slc_crossover_figure.py
```

집계기는 기본 18개 조건, fio error, completion/iodepth/workload 설정과 다음 counter를 검사한다.

- TLC-only에서 SLC migration page가 0인지
- Resident SLC 조건에서 migration page가 0인지
- Overflow/Sustained SLC 조건에서 migration이 실제로 발생했는지

생성 파일:

- `report/crossover_results/slc_crossover_raw.csv`
- `report/crossover_results/slc_crossover_aggregate.csv`
- `report/figures/practice2_ext_fig5_slc_crossover.png`

## 해석 기준

- Resident에서 SLC의 throughput이 높고 평균/p99 latency가 낮아야 SLC media 이득을 주장할 수 있다.
- Overflow와 Sustained에서는 migrated page 비율 증가와 함께 성능이 역전되는지 본다.
- 결과가 예상과 다르면 유리하다고 단정하지 않고 실제 평균과 표준편차를 그대로 보고한다.

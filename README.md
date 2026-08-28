> ## 📄 실습 2 제출물 안내
>
> 이 저장소에는 **실습 2: SLC cache 기반 이기종 SSD 구현 및 성능 분석** 결과가 포함되어 있습니다. SLC에 host write를 우선 배치하고, SLC가 가득 차면 TLC로 migration하도록 Conventional FTL을 확장했습니다. SLC migration victim 정책(Greedy / Random / FIFO / Cost-Benefit)을 구현하고, TLC-only baseline과 비교해 resident·overflow·sustained 구간에서 SLC의 이점과 비용을 분석했습니다.
> 제출자: **유형진 (인턴)**
>
> | 항목 | 위치 |
> |---|---|
> | **보고서 (Markdown 원본)** | [`report/REPORT.md`](report/REPORT.md) |
> | **보고서 (Word 제출본)** | [`report/PRACTICE2_REPORT.docx`](report/PRACTICE2_REPORT.docx) |
> | 보고서 그래프 | [`report/figures/`](report/figures) — 확장 실험 및 SLC crossover 결과 포함 |
> | 핵심 구현 코드 | [`conv_ftl.c`](conv_ftl.c) / [`conv_ftl.h`](conv_ftl.h), [`ssd.c`](ssd.c) / [`ssd.h`](ssd.h), [`ssd_config.h`](ssd_config.h), [`main.c`](main.c) |
> | 실험 및 집계 스크립트 | [`scripts/`](scripts), [`report/make_practice2_extended_figures.py`](report/make_practice2_extended_figures.py) |
> | 실험 결과 원본·집계 | [`results/`](results), [`report/extended_results/`](report/extended_results), [`report/crossover_results/`](report/crossover_results) |
> | 파일 구성 및 첨부 안내 | [`Code_Structure_Notice.txt`](Code_Structure_Notice.txt) |
> | 실습 2 실험 진행 기록 | [`docs/PRACTICE2_IMPLEMENTATION_LOG.md`](docs/PRACTICE2_IMPLEMENTATION_LOG.md) |
>
> 주요 런타임 옵션은 `slc_cache_ratio_percent`(SLC cache 비율), `slc_migration_policy`(SLC migration 정책), `gc_policy`(TLC GC 정책)입니다. 재현 절차와 workload 조건은 [`docs/`](docs) 아래 실험 안내 문서를 참고하세요.
>
> ## 📄 실습 1 제출물 안내
>
> 이 저장소는 [snu-csl/nvmevirt](https://github.com/snu-csl/nvmevirt)를 fork하여 **실습 1: GC victim 선택 정책(Greedy / Random / Cost-Benefit) 구현 및 성능 비교**를 수행한 결과입니다.
> 제출자: **유형진 (인턴)**
>
> | 항목 | 위치 |
> |---|---|
> | **보고서 (제출본)** | [`report/REPORT.pdf`](report/REPORT.pdf) — 같은 내용의 [HTML](report/REPORT.html) / [Markdown](report/REPORT.md) 원본도 함께 있습니다 |
> | 보고서 그래프 | [`report/figures/`](report/figures) (fig1~fig6) |
> | 구현 코드 | [`conv_ftl.c`](conv_ftl.c) / [`conv_ftl.h`](conv_ftl.h) (정책 구현), [`main.c`](main.c) (`/proc/nvmev/debug` 측정 인터페이스) |
> | 실험 스크립트 | [`scripts/`](scripts) |
> | 실험 결과 원본 | [`results/`](results) (실행별 `summary.txt` / `meta.txt` / `fio.json`) |
> | 파일 구성 상세 · 빌드/실행 방법 | [`report/SUBMISSION_README.txt`](report/SUBMISSION_README.txt) |
> | 실험 진행 기록 (시행착오와 판단 근거) | [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) |
>
> 아래는 원본 NVMeVirt 저장소의 README입니다.

---

# NVMeVirt

## Introduction

NVMeVirt is a versatile software-defined virtual NVMe device. It is implemented as a Linux kernel module providing the system with a virtual NVMe device of various kinds. Currently, NVMeVirt supports conventional SSDs, NVM SSDs, ZNS SSDs, etc. The device is emulated at the PCI layer, presenting a native NVMe device to the entire system. Thus, NVMeVirt has the capability not only to function as a standard storage device, but also to be utilized in advanced storage configurations, such as NVMe-oF target offloading, kernel bypassing, and PCI peer-to-peer communication.

Further details on the design and implementation of NVMeVirt can be found in the following papers.
- [NVMeVirt: A Versatile Software-defined Virtual NVMe Device (FAST 2023)](https://www.usenix.org/conference/fast23/presentation/kim-sang-hoon)
- [Empowering Storage Systems Research with NVMeVirt: A Comprehensive NVMe Device Emulator (Transactions on Storage 2023)](https://dl.acm.org/doi/full/10.1145/3625006)

Please feel free to contact us at [nvmevirt@gmail.com](mailto:nvmevirt@gmail.com) if you have any questions or suggestions. Also you can raise an issue anytime for bug reports or discussions.

We encourage you to cite our paper at FAST 2023 as follows:
```
@InProceedings{NVMeVirt:FAST23,
  author = {Sang-Hoon Kim and Jaehoon Shim and Euidong Lee and Seongyeop Jeong and Ilkueon Kang and Jin-Soo Kim},
  title = {{NVMeVirt}: A Versatile Software-defined Virtual {NVMe} Device},
  booktitle = {Proceedings of the 21st USENIX Conference on File and Storage Technologies (USENIX FAST)},
  address = {Santa Clara, CA},
  month = {February},
  year = {2023},
}
```


## Installation

### Linux kernel requirement

The recommended Linux kernel version is v5.15.x and higher (tested on Linux vanilla kernel v5.15.37 and Ubuntu kernel v5.15.0-58-generic).

### Reserving physical memory

A part of the main memory should be reserved for the storage of the emulated NVMe device. To reserve a chunk of physical memory, add the following option to `GRUB_CMDLINE_LINUX` in `/etc/default/grub` as follows:

```bash
GRUB_CMDLINE_LINUX="memmap=64G\\\$128G"
```

This example will reserve 64GiB of physical memory chunk (out of the total 192GiB physical memory) starting from the 128GiB memory offset. You may need to adjust those values depending on the available physical memory size and the desired storage capacity.

After changing the `/etc/default/grub` file, you are required to run the following commands to update `grub` and reboot your system.

```bash
$ sudo update-grub
$ sudo reboot
```

### Compiling `nvmevirt`

Please download the latest version of `nvmevirt` from Github:

```bash
$ git clone https://github.com/snu-csl/nvmevirt
```

`nvmevirt` is implemented as a Linux kernel module. Thus, the kernel headers should be installed in the `/lib/modules/$(shell uname -r)` directory to compile `nvmevirt`.

Currently, you need to select the target device type by manually editing the `Kbuild`. You may find the following lines in the `Kbuild`, which imply that NVMeVirt is currently configured for emulating NVM(Non-Volatile Memory) SSD (such as Intel Optane SSD). You may uncomment other one to change the target device type. Note that you can select one device type at a time.

```Makefile
# Select one of the targets to build
CONFIG_NVMEVIRT_NVM := y
#CONFIG_NVMEVIRT_SSD := y
#CONFIG_NVMEVIRT_ZNS := y
#CONFIG_NVMEVIRT_KV := y
```

You may find the detailed configuration parameters for conventional SSD and ZNS SSD from `ssd_config.h`.

Build the kernel module by running the `make` command in the `nvmevirt` source directory.
```bash
$ make
make -C /lib/modules/5.15.37/build M=/path/to/nvmev modules
make[1]: Entering directory '/path/to/linux-5.15.37'
  CC [M]  /path/to/nvmev/main.o
  CC [M]  /path/to/nvmev/pci.o
  CC [M]  /path/to/nvmev/admin.o
  CC [M]  /path/to/nvmev/io.o
  CC [M]  /path/to/nvmev/dma.o
  CC [M]  /path/to/nvmev/simple_ftl.o
  LD [M]  /path/to/nvmev/nvmev.o
  MODPOST /path/to/nvmev/Module.symvers
  CC [M]  /path/to/nvmev/nvmev.mod.o
  LD [M]  /path/to/nvmev/nvmev.ko
  BTF [M] /path/to/nvmev/nvmev.ko
make[1]: Leaving directory '/path/to/linux-5.15.37'
$
```

### Using `nvmevirt`

`nvmevirt` is configured to emulate the NVM SSD by default. You can attach an emulated NVM SSD in your system by loading the `nvmevirt` kernel module as follows:

```bash
$ sudo insmod ./nvmev.ko \
  memmap_start=128G \       # e.g., 1M, 4G, 8T
  memmap_size=64G   \       # e.g., 1M, 4G, 8T
  cpus=7,8                  # List of CPU cores to process I/O requests (should have at least 2)
```

In the above example, `memmap_start` and `memmap_size` indicate the relative offset and the size of the reserved memory, respectively. Those values should match the configurations specified in the `/etc/default/grub` file shown earlier. In addition, the `cpus` option specifies the id of cores on which I/O dispatcher and I/O worker threads run. You have to specify at least two cores for this purpose: one for the I/O dispatcher thread, and one or more cores for the I/O worker thread(s).

It is highly recommended to use the `isolcpus` Linux command-line configuration to avoid schedulers putting tasks on the CPUs that NVMeVirt uses:

```bash
GRUB_CMDLINE_LINUX="memmap=64G\\\$128G isolcpus=7,8"
```

When you are successfully load the `nvmevirt` module, you can see something like these from the system message.

```log
$ sudo dmesg
[  144.812917] nvme nvme0: pci function 0001:10:00.0
[  144.812975] NVMeVirt: Successfully created virtual PCI bus (node 1)
[  144.813911] NVMeVirt: nvmev_proc_io_0 started on cpu 7 (node 1)
[  144.813972] NVMeVirt: Successfully created Virtual NVMe device
[  144.814032] NVMeVirt: nvmev_dispatcher started on cpu 8 (node 1)
[  144.822075] nvme nvme0: 48/0/0 default/read/poll queues
```

If you encounter a kernel panic in `__pci_enable_msix()` or in `nvme_hwmon_init()` during `insmod`, it is because the current implementation of `nvmevirt` is not compatible with IOMMU. In this case, you can either turn off Intel VT-d or IOMMU in BIOS, or disable the interrupt remapping using the grub option as shown below:

```bash
GRUB_CMDLINE_LINUX="memmap=64G\\\$128G intremap=off"
```

Now the emulated `nvmevirt` device is ready to be used as shown below. The actual device number (`/dev/nvme0`) can vary depending on the number of real NVMe devices in your system.


```bash
$ ls -l /dev/nvme*
crw------- 1 root root 242, 0 Feb 22 14:13 /dev/nvme0
brw-rw---- 1 root disk 259, 5 Feb 22 14:13 /dev/nvme0n1
```

## Contributing
When contributing to this repository, please first discuss the change you wish to make via [issues](https://github.com/snu-csl/nvmevirt/issues) or email(nvmevirt@gmail.com) before making a change.

### Pull Requests
1. Create a personal fork of the project on Github.
2. Clone the fork on your local machine.
3. Implement/fix your feature, comment your code.
4. Follow the code style of this project, including indentation.
5. Run tests using [nvmev-evaluation](https://github.com/snu-csl/nvmev-evaluation).
6. From your fork open a pull request in our `main` branch!
7. Please wait for the maintainer's review.


## License

NVMeVirt is offered under the terms of the GNU General Public License version 2 as published by the Free Software Foundation. More information about this license can be found [here](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html).

Priority queue implementation [`pqueue/`](pqueue/) is offered under the terms of the BSD 2-clause license (GPL-compatible). (Copyright (c) 2014, Volkan Yazıcı <volkan.yazici@gmail.com>. All rights reserved.)


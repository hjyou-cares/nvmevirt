// SPDX-License-Identifier: GPL-2.0-only

#ifndef _NVMEVIRT_CONV_FTL_H
#define _NVMEVIRT_CONV_FTL_H

#include <linux/types.h>
#include "pqueue/pqueue.h"
#include "ssd_config.h"
#include "ssd.h"

extern uint64_t gc_valid_page_migrate_cnt;
extern uint64_t tlc_gc_cnt;
extern uint64_t tlc_gc_valid_page_migrate_cnt;
extern uint64_t slc_migration_cnt;
extern uint64_t slc_migration_valid_page_migrate_cnt;

/* GC victim divergence analysis (2026-07-30): see diag_scan_greedy_vs_cb()
 * in conv_ftl.c. */
extern uint64_t diag_total_gc;
extern uint64_t diag_identity_diverge;
extern uint64_t diag_sum_greedy_vpc;
extern uint64_t diag_sum_cb_vpc;
extern uint64_t diag_sum_abs_vpc_diff;
extern uint64_t diag_same_vpc_diff_line;

struct convparams {
	uint32_t gc_thres_lines;
	uint32_t gc_thres_lines_high;
	bool enable_gc_delay;

	double op_area_pcent;
	int pba_pcent; /* (physical space / logical space) * 100*/
};

enum line_pool_id {
	LINE_POOL_SHARED = 0,
	LINE_POOL_SLC = 1,
	LINE_POOL_TLC = 2,
};

struct line {
	int id; /* line id, the same as corresponding block id */
	int ipc; /* invalid page count in this line */
	int vpc; /* valid page count in this line */
	struct list_head entry;
	/* position in the priority queue for victim lines */
	size_t pos;
	/* which pool currently owns this line; SHARED keeps the legacy mode */
	enum line_pool_id pool;
	/* logical timestamp (cb_clock) when this line was last closed */
	uint64_t mtime;
	/* monotonically increasing close order for FIFO-style migration */
	uint64_t close_seq;
};

/* wp: record next write addr */
struct write_pointer {
	struct line *curline;
	uint32_t ch;
	uint32_t lun;
	uint32_t pg;
	uint32_t blk;
	uint32_t pl;
};

struct line_mgmt {
	struct line *lines;

	/* free line list, we only need to maintain a list of blk numbers */
	struct list_head free_line_list;
	pqueue_t *victim_line_pq;
	struct list_head full_line_list;

	uint32_t tt_lines;
	uint32_t free_line_cnt;
	uint32_t victim_line_cnt;
	uint32_t full_line_cnt;
};

struct write_flow_control {
	uint32_t write_credits;
	uint32_t credits_to_refill;
};

struct slc_cache_layout {
	uint32_t slc_ratio_percent;
	uint32_t total_line_cnt;
	uint32_t slc_line_cnt;
	uint32_t tlc_line_cnt;
	uint32_t slc_line_boundary;
};

struct slc_cache_runtime {
	struct line_mgmt slc_lm;
	struct line_mgmt tlc_lm;
	struct write_pointer slc_wp;
	struct write_pointer tlc_wp;
	struct write_pointer tlc_gc_wp;
	uint64_t line_close_seq;
};

struct conv_ftl {
	struct ssd *ssd;

	struct convparams cp;
	struct ppa *maptbl; /* page level mapping table */
	uint64_t *rmap; /* reverse mapptbl, assume it's stored in OOB */
	struct write_pointer wp;
	struct write_pointer gc_wp;
	struct line_mgmt lm;
	/*
	 * Practice 2 is migrating toward separate SLC/TLC managers and write
	 * pointers. Keep the legacy single-pool fields above alive until the
	 * actual I/O path switches over in later steps.
	 */
	struct slc_cache_layout slc_layout;
	struct slc_cache_runtime slc_rt;
	struct write_flow_control wfc;
};

void conv_init_namespace(struct nvmev_ns *ns, uint32_t id, uint64_t size, void *mapped_addr,
			 uint32_t cpu_nr_dispatcher);

void conv_remove_namespace(struct nvmev_ns *ns);

bool conv_proc_nvme_io_cmd(struct nvmev_ns *ns, struct nvmev_request *req,
			   struct nvmev_result *ret);

#endif

// SPDX-License-Identifier: GPL-2.0-only

#include <linux/vmalloc.h>
#include <linux/ktime.h>
#include <linux/sched/clock.h>
#include <linux/random.h>
#include <linux/moduleparam.h>

#include "nvmev.h"
#include "conv_ftl.h"

enum tlc_gc_victim_policy {
	TLC_GC_POLICY_GREEDY = 0,
	TLC_GC_POLICY_RANDOM = 1,
	TLC_GC_POLICY_COST_BENEFIT = 2,
};

enum slc_migration_victim_policy {
	SLC_MIGRATION_POLICY_GREEDY = 0,
	SLC_MIGRATION_POLICY_RANDOM = 1,
	SLC_MIGRATION_POLICY_FIFO = 2,
	SLC_MIGRATION_POLICY_COST_BENEFIT = 3,
};

static unsigned int gc_policy = TLC_GC_POLICY_GREEDY;
/* 0444 (read-only at runtime) on purpose: set this with an insmod parameter,
 * never by writing to /sys/module/nvmev/parameters/gc_policy. Switching from
 * Cost-Benefit to Greedy on a live module leaves the victim heap ordered by
 * CB priority, and Greedy's pqueue_pop() trusts that order -- so it would
 * silently stop returning the min-vpc line, with no error and no self-repair.
 * (Switching policies also carries over FTL state -- cb_clock, the write
 * pointer, the free line list -- which contaminated an earlier cross-policy
 * comparison; see CLAUDE.md.) Reading it back is still allowed. */
module_param(gc_policy, uint, 0444);
MODULE_PARM_DESC(gc_policy,
		 "TLC GC victim selection policy: 0=Greedy, 1=Random, 2=Cost-Benefit");

static unsigned int slc_migration_policy = SLC_MIGRATION_POLICY_GREEDY;
module_param(slc_migration_policy, uint, 0444);
MODULE_PARM_DESC(slc_migration_policy,
		 "SLC migration victim selection policy: 0=Greedy, 1=Random, 2=FIFO, 3=Cost-Benefit");

static unsigned int slc_cache_ratio_percent = SLC_CACHE_RATIO_PERCENT;
module_param(slc_cache_ratio_percent, uint, 0444);
MODULE_PARM_DESC(slc_cache_ratio_percent,
		 "SLC cache ratio percent: 0 disables SLC cache, 100 means all lines are SLC");

/* logical clock for Cost-Benefit GC: incremented once per page write.
 * Only ever touched from the single nvmev_dispatcher kthread, so no locking needed. */
static uint64_t cb_clock = 0;

/* Total valid pages copied during GC across all do_gc() calls (2026-07-30).
 * erase_cnt alone is mostly driven by total write volume, not by victim choice,
 * so it barely differs between policies; this is the actual migration cost
 * Cost-Benefit is designed to reduce. Exposed via /proc/nvmev/debug. */
uint64_t gc_valid_page_migrate_cnt = 0;
uint64_t tlc_gc_cnt = 0;
uint64_t tlc_gc_valid_page_migrate_cnt = 0;
uint64_t slc_migration_cnt = 0;
uint64_t slc_migration_valid_page_migrate_cnt = 0;
uint64_t user_read_slc_pages = 0;
uint64_t user_read_tlc_pages = 0;
uint64_t user_write_slc_pages = 0;
uint64_t user_write_tlc_pages = 0;
uint64_t internal_read_slc_pages = 0;
uint64_t internal_read_tlc_pages = 0;
uint64_t internal_write_slc_pages = 0;
uint64_t internal_write_tlc_pages = 0;

/* GC victim divergence analysis (2026-07-30). Regardless of which gc_policy is
 * actually driving real GC, scan the raw victim queue on every
 * select_victim_line() call to find what Greedy (min vpc) and Cost-Benefit
 * (max cb_victim_pri) would each pick right now, and accumulate whether the
 * two pick different lines that nonetheless carry the same vpc (i.e. the same
 * migration cost). Purpose: even where Greedy and CB disagree on WHICH line to
 * reclaim, do they disagree on HOW MANY valid pages that reclaim costs? This
 * is what showed the two policies' migration cost per GC genuinely differs
 * (not just which line gets picked) -- see the report. Read-only, no effect
 * on pq state or on which line actually gets reclaimed. Exposed via
 * /proc/nvmev/debug (main.c), reset together with the other debug counters. */
uint64_t diag_total_gc = 0;
uint64_t diag_identity_diverge = 0;
uint64_t diag_sum_greedy_vpc = 0;
uint64_t diag_sum_cb_vpc = 0;
uint64_t diag_sum_abs_vpc_diff = 0;
uint64_t diag_same_vpc_diff_line = 0;

enum reclaim_reason {
	RECLAIM_REASON_TLC_GC = 0,
	RECLAIM_REASON_SLC_MIGRATION = 1,
};

static inline bool last_pg_in_wordline(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	uint32_t oneshot_pgs;

	if (conv_ftl->slc_layout.slc_line_cnt > 0 &&
	    ppa->g.blk < conv_ftl->slc_layout.slc_line_boundary)
		oneshot_pgs = spp->slc_pgs_per_oneshotpg;
	else
		oneshot_pgs = spp->pgs_per_oneshotpg;

	return (ppa->g.pg % oneshot_pgs) == (oneshot_pgs - 1);
}

static bool should_gc(struct conv_ftl *conv_ftl)
{
	return (conv_ftl->slc_rt.tlc_lm.free_line_cnt <= conv_ftl->cp.gc_thres_lines);
}

static inline bool should_gc_high(struct conv_ftl *conv_ftl)
{
	return conv_ftl->slc_rt.tlc_lm.free_line_cnt <= conv_ftl->cp.gc_thres_lines_high;
}

static inline struct ppa get_maptbl_ent(struct conv_ftl *conv_ftl, uint64_t lpn)
{
	return conv_ftl->maptbl[lpn];
}

static inline void set_maptbl_ent(struct conv_ftl *conv_ftl, uint64_t lpn, struct ppa *ppa)
{
	NVMEV_ASSERT(lpn < conv_ftl->ssd->sp.tt_pgs);
	conv_ftl->maptbl[lpn] = *ppa;
}

static uint64_t ppa2pgidx(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	uint64_t pgidx;

	NVMEV_DEBUG_VERBOSE("%s: ch:%d, lun:%d, pl:%d, blk:%d, pg:%d\n", __func__,
			ppa->g.ch, ppa->g.lun, ppa->g.pl, ppa->g.blk, ppa->g.pg);

	pgidx = ppa->g.ch * spp->pgs_per_ch + ppa->g.lun * spp->pgs_per_lun +
		ppa->g.pl * spp->pgs_per_pl + ppa->g.blk * spp->pgs_per_blk + ppa->g.pg;

	NVMEV_ASSERT(pgidx < spp->tt_pgs);

	return pgidx;
}

static inline uint64_t get_rmap_ent(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	uint64_t pgidx = ppa2pgidx(conv_ftl, ppa);

	return conv_ftl->rmap[pgidx];
}

/* set rmap[page_no(ppa)] -> lpn */
static inline void set_rmap_ent(struct conv_ftl *conv_ftl, uint64_t lpn, struct ppa *ppa)
{
	uint64_t pgidx = ppa2pgidx(conv_ftl, ppa);

	conv_ftl->rmap[pgidx] = lpn;
}

static inline int victim_line_cmp_pri(pqueue_pri_t next, pqueue_pri_t curr)
{
	return (next > curr);
}

/* biggest possible pqueue_pri_t value, used to invert Cost-Benefit scores
 * so that "smaller priority = better victim" still holds for the min-heap */
#define CB_PRI_MAX (~0ULL)

/* Cost-Benefit priority for a line, independent of the currently active
 * gc_policy (used both by victim_line_get_pri() when CB is active, and by the
 * diagnostic scan below so it can evaluate "what would CB pick" even while
 * Greedy/Random is the one actually driving GC). */
static inline pqueue_pri_t cb_victim_pri(struct line *line)
{
	uint64_t age, bc;

	if (line->vpc == 0)
		return 0; /* already fully invalid: best possible victim */

	age = cb_clock - line->mtime;
	bc = ((uint64_t)line->ipc * age) / (2ULL * (uint64_t)line->vpc);
	/* bigger bc = better victim; invert so the min-heap picks it first */
	return CB_PRI_MAX - bc;
}

static inline pqueue_pri_t victim_line_get_pri(void *a)
{
	struct line *line = (struct line *)a;

	if (gc_policy == TLC_GC_POLICY_COST_BENEFIT)
		return cb_victim_pri(line);

	return line->vpc;
}

/* See the comment on diag_total_gc et al. above. */
static void diag_scan_greedy_vs_cb(pqueue_t *pq)
{
	struct line *greedy_pick = NULL, *cb_pick = NULL;
	int min_vpc = INT_MAX;
	pqueue_pri_t best_cb_pri = 0;
	int diff;
	size_t i;

	if (!pq || pq->size <= 1)
		return;

	for (i = 1; i < pq->size; i++) {
		struct line *l = (struct line *)pq->d[i];
		pqueue_pri_t pri = cb_victim_pri(l);

		if (l->pool != LINE_POOL_TLC)
			continue;

		if (l->vpc < min_vpc) {
			min_vpc = l->vpc;
			greedy_pick = l;
		}
		if (!cb_pick || pri < best_cb_pri) {
			best_cb_pri = pri;
			cb_pick = l;
		}
	}

	if (!greedy_pick || !cb_pick)
		return;

	diag_total_gc++;
	diag_sum_greedy_vpc += greedy_pick->vpc;
	diag_sum_cb_vpc += cb_pick->vpc;

	diff = greedy_pick->vpc - cb_pick->vpc;
	diag_sum_abs_vpc_diff += (diff < 0) ? -diff : diff;

	if (greedy_pick != cb_pick) {
		diag_identity_diverge++;
		if (greedy_pick->vpc == cb_pick->vpc)
			diag_same_vpc_diff_line++;
	}
}

static inline void victim_line_set_pri(void *a, pqueue_pri_t pri)
{
	((struct line *)a)->vpc = pri;
}

static inline size_t victim_line_get_pos(void *a)
{
	return ((struct line *)a)->pos;
}

static inline void victim_line_set_pos(void *a, size_t pos)
{
	((struct line *)a)->pos = pos;
}

static inline void consume_write_credit(struct conv_ftl *conv_ftl)
{
	conv_ftl->wfc.write_credits--;
}

static void foreground_gc(struct conv_ftl *conv_ftl);
static void foreground_slc_migration(struct conv_ftl *conv_ftl);
static enum line_pool_id get_configured_line_pool(struct conv_ftl *conv_ftl, uint32_t line_id);
static struct line_mgmt *get_pool_lm(struct conv_ftl *conv_ftl, enum line_pool_id pool);
static int do_gc(struct conv_ftl *conv_ftl, bool force);

static inline void check_and_refill_write_credit(struct conv_ftl *conv_ftl)
{
	struct write_flow_control *wfc = &(conv_ftl->wfc);
	if (wfc->write_credits <= 0) {
		foreground_gc(conv_ftl);

		wfc->write_credits += wfc->credits_to_refill;
	}
}

static void init_lines(struct conv_ftl *conv_ftl)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct line_mgmt *slc_lm = &conv_ftl->slc_rt.slc_lm;
	struct line_mgmt *tlc_lm = &conv_ftl->slc_rt.tlc_lm;
	struct line_mgmt *pool_lm;
	struct line *line;
	int i;

	NVMEV_ASSERT(spp->tt_lines == conv_ftl->slc_layout.total_line_cnt);
	conv_ftl->lines = vmalloc(sizeof(struct line) * spp->tt_lines);

	INIT_LIST_HEAD(&slc_lm->free_line_list);
	INIT_LIST_HEAD(&slc_lm->full_line_list);
	INIT_LIST_HEAD(&tlc_lm->free_line_list);
	INIT_LIST_HEAD(&tlc_lm->full_line_list);
	slc_lm->victim_line_pq = slc_lm->tt_lines ?
		pqueue_init(slc_lm->tt_lines, victim_line_cmp_pri, victim_line_get_pri,
			    victim_line_set_pri, victim_line_get_pos, victim_line_set_pos) :
		NULL;
	tlc_lm->victim_line_pq = tlc_lm->tt_lines ?
		pqueue_init(tlc_lm->tt_lines, victim_line_cmp_pri, victim_line_get_pri,
			    victim_line_set_pri, victim_line_get_pos, victim_line_set_pos) :
		NULL;

	slc_lm->free_line_cnt = 0;
	slc_lm->victim_line_cnt = 0;
	slc_lm->full_line_cnt = 0;
	tlc_lm->free_line_cnt = 0;
	tlc_lm->victim_line_cnt = 0;
	tlc_lm->full_line_cnt = 0;

	for (i = 0; i < spp->tt_lines; i++) {
		conv_ftl->lines[i] = (struct line){
			.id = i,
			.ipc = 0,
			.vpc = 0,
			.pos = 0,
			.pool = get_configured_line_pool(conv_ftl, i),
			.mtime = 0,
			.close_seq = 0,
			.entry = LIST_HEAD_INIT(conv_ftl->lines[i].entry),
		};
		line = &conv_ftl->lines[i];
		pool_lm = get_pool_lm(conv_ftl, line->pool);

		/* initialize all the lines as free lines */
		list_add_tail(&line->entry, &pool_lm->free_line_list);
		pool_lm->free_line_cnt++;
	}
}

static void init_slc_layout_metadata(struct conv_ftl *conv_ftl)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct slc_cache_layout *layout = &conv_ftl->slc_layout;

	layout->total_line_cnt = spp->tt_lines;
	NVMEV_ASSERT(slc_cache_ratio_percent <= 100);
	layout->slc_ratio_percent = slc_cache_ratio_percent;
	layout->slc_line_cnt = (layout->total_line_cnt * layout->slc_ratio_percent) / 100;
	layout->tlc_line_cnt = layout->total_line_cnt - layout->slc_line_cnt;
	layout->slc_line_boundary = layout->slc_line_cnt;

	conv_ftl->slc_rt.slc_lm = (struct line_mgmt){ 0 };
	conv_ftl->slc_rt.tlc_lm = (struct line_mgmt){ 0 };
	conv_ftl->slc_rt.slc_wp = (struct write_pointer){ 0 };
	conv_ftl->slc_rt.tlc_wp = (struct write_pointer){ 0 };
	conv_ftl->slc_rt.tlc_gc_wp = (struct write_pointer){ 0 };
	conv_ftl->slc_rt.line_close_seq = 0;
	conv_ftl->slc_rt.slc_lm.tt_lines = layout->slc_line_cnt;
	conv_ftl->slc_rt.tlc_lm.tt_lines = layout->tlc_line_cnt;
}

static void remove_lines(struct conv_ftl *conv_ftl)
{
	if (conv_ftl->slc_rt.slc_lm.victim_line_pq)
		pqueue_free(conv_ftl->slc_rt.slc_lm.victim_line_pq);
	if (conv_ftl->slc_rt.tlc_lm.victim_line_pq)
		pqueue_free(conv_ftl->slc_rt.tlc_lm.victim_line_pq);
	vfree(conv_ftl->lines);
}

static void init_write_flow_control(struct conv_ftl *conv_ftl)
{
	struct write_flow_control *wfc = &(conv_ftl->wfc);
	struct ssdparams *spp = &conv_ftl->ssd->sp;

	wfc->write_credits = spp->pgs_per_line;
	wfc->credits_to_refill = spp->pgs_per_line;
}

static inline void check_addr(int a, int max)
{
	NVMEV_ASSERT(a >= 0 && a < max);
}

static inline void count_media_reads(uint32_t io_type, int media, uint64_t pages)
{
	if (!pages)
		return;

	if (io_type == USER_IO) {
		if (media == NAND_MEDIA_SLC)
			user_read_slc_pages += pages;
		else
			user_read_tlc_pages += pages;
		return;
	}

	if (media == NAND_MEDIA_SLC)
		internal_read_slc_pages += pages;
	else
		internal_read_tlc_pages += pages;
}

static inline void count_media_writes(uint32_t io_type, int media, uint64_t pages)
{
	if (!pages)
		return;

	if (io_type == USER_IO) {
		if (media == NAND_MEDIA_SLC)
			user_write_slc_pages += pages;
		else
			user_write_tlc_pages += pages;
		return;
	}

	if (media == NAND_MEDIA_SLC)
		internal_write_slc_pages += pages;
	else
		internal_write_tlc_pages += pages;
}

static inline uint32_t get_total_free_line_cnt(struct conv_ftl *conv_ftl)
{
	return conv_ftl->slc_rt.slc_lm.free_line_cnt + conv_ftl->slc_rt.tlc_lm.free_line_cnt;
}

static enum line_pool_id get_configured_line_pool(struct conv_ftl *conv_ftl, uint32_t line_id)
{
	struct slc_cache_layout *layout = &conv_ftl->slc_layout;

	NVMEV_ASSERT(line_id < layout->total_line_cnt);

	if (layout->slc_line_cnt == 0)
		return LINE_POOL_TLC;

	if (line_id < layout->slc_line_boundary)
		return LINE_POOL_SLC;

	return LINE_POOL_TLC;
}

static inline enum line_pool_id get_ppa_pool(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return get_configured_line_pool(conv_ftl, ppa->g.blk);
}

static inline bool ppa_is_slc(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return get_ppa_pool(conv_ftl, ppa) == LINE_POOL_SLC;
}

static inline uint32_t get_pool_pgs_per_oneshotpg(struct conv_ftl *conv_ftl,
						  enum line_pool_id pool)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;

	if (pool == LINE_POOL_SLC)
		return spp->slc_pgs_per_oneshotpg;

	return spp->pgs_per_oneshotpg;
}

static inline uint32_t get_ppa_pgs_per_oneshotpg(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return get_pool_pgs_per_oneshotpg(conv_ftl, get_ppa_pool(conv_ftl, ppa));
}

static inline int get_ppa_nand_media(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return ppa_is_slc(conv_ftl, ppa) ? NAND_MEDIA_SLC : NAND_MEDIA_TLC;
}

static struct line_mgmt *get_pool_lm(struct conv_ftl *conv_ftl, enum line_pool_id pool)
{
	if (pool == LINE_POOL_SLC)
		return &conv_ftl->slc_rt.slc_lm;
	if (pool == LINE_POOL_TLC)
		return &conv_ftl->slc_rt.tlc_lm;

	NVMEV_ASSERT(0);
	return NULL;
}

static struct line *get_next_free_line_by_pool(struct conv_ftl *conv_ftl, enum line_pool_id pool)
{
	struct line_mgmt *lm = get_pool_lm(conv_ftl, pool);
	struct line *line = NULL;

	list_for_each_entry(line, &lm->free_line_list, entry) {
		list_del_init(&line->entry);
		NVMEV_ASSERT(lm->free_line_cnt > 0);
		lm->free_line_cnt--;
		return line;
	}

	NVMEV_ERROR("No free line left in requested pool %d\n", pool);
	return NULL;
}

static enum line_pool_id get_io_target_pool(struct conv_ftl *conv_ftl, uint32_t io_type)
{
	if (io_type == USER_IO) {
		if (conv_ftl->slc_layout.slc_line_cnt > 0)
			return LINE_POOL_SLC;
		return LINE_POOL_TLC;
	}

	if (io_type == GC_IO)
		return LINE_POOL_TLC;

	NVMEV_ASSERT(0);
	return LINE_POOL_TLC;
}

static bool should_migrate_slc(struct conv_ftl *conv_ftl)
{
	return conv_ftl->slc_layout.slc_line_cnt > 0 && conv_ftl->slc_rt.slc_lm.free_line_cnt == 0;
}

static struct line *select_tlc_gc_victim_line(struct conv_ftl *conv_ftl, bool force)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct line_mgmt *lm = &conv_ftl->slc_rt.tlc_lm;
	struct line *victim_line = NULL;
	pqueue_t *pq = lm->victim_line_pq;
	size_t i;

	if (!pq || pq->size <= 1)
		return NULL;

	diag_scan_greedy_vs_cb(lm->victim_line_pq);

	if (gc_policy == TLC_GC_POLICY_RANDOM) {
		unsigned int eligible = 0;
		unsigned int pick;

		eligible = pq->size - 1;

		if (eligible == 0)
			return NULL;

		pick = get_random_u32() % eligible;
		for (i = 1; i < pq->size; i++) {
			struct line *cand = pq->d[i];

			if (pick-- == 0) {
				victim_line = cand;
				break;
			}
		}
	} else {
		for (i = 1; i < pq->size; i++) {
			struct line *cand = pq->d[i];

			if (!victim_line) {
				victim_line = cand;
				continue;
			}

			if (gc_policy == TLC_GC_POLICY_COST_BENEFIT) {
				if (victim_line_get_pri(cand) < victim_line_get_pri(victim_line))
					victim_line = cand;
			} else if (cand->vpc < victim_line->vpc) {
				victim_line = cand;
			}
		}
	}

	if (!victim_line)
		return NULL;

	if (!force && (victim_line->vpc > (spp->pgs_per_line / 8)))
		return NULL;

	pqueue_remove(pq, victim_line);
	victim_line->pos = 0;
	lm->victim_line_cnt--;

	return victim_line;
}

static bool slc_migration_candidate_is_better(struct line *candidate,
					      struct line *current_line)
{
	if (!current_line)
		return true;

	switch (slc_migration_policy) {
	case SLC_MIGRATION_POLICY_FIFO:
		if (candidate->close_seq != current_line->close_seq)
			return candidate->close_seq < current_line->close_seq;
		return candidate->vpc < current_line->vpc;
	case SLC_MIGRATION_POLICY_COST_BENEFIT:
		if (cb_victim_pri(candidate) != cb_victim_pri(current_line))
			return cb_victim_pri(candidate) < cb_victim_pri(current_line);
		if (candidate->vpc != current_line->vpc)
			return candidate->vpc < current_line->vpc;
		return candidate->close_seq < current_line->close_seq;
	case SLC_MIGRATION_POLICY_GREEDY:
	default:
		if (candidate->vpc != current_line->vpc)
			return candidate->vpc < current_line->vpc;
		return candidate->close_seq < current_line->close_seq;
	}
}

static unsigned int count_slc_migration_candidates(struct conv_ftl *conv_ftl)
{
	struct line_mgmt *lm = &conv_ftl->slc_rt.slc_lm;
	struct line *line;
	pqueue_t *pq = lm->victim_line_pq;
	unsigned int count = 0;
	size_t i;

	list_for_each_entry(line, &lm->full_line_list, entry)
		count++;

	if (!pq)
		return count;

	for (i = 1; i < pq->size; i++)
		count++;

	return count;
}

static struct line *pick_nth_slc_migration_candidate(struct conv_ftl *conv_ftl, unsigned int pick)
{
	struct line_mgmt *lm = &conv_ftl->slc_rt.slc_lm;
	struct line *line;
	pqueue_t *pq = lm->victim_line_pq;
	size_t i;

	list_for_each_entry(line, &lm->full_line_list, entry) {
		if (pick-- == 0)
			return line;
	}

	if (!pq)
		return NULL;

	for (i = 1; i < pq->size; i++) {
		struct line *cand = pq->d[i];

		if (pick-- == 0)
			return cand;
	}

	return NULL;
}

static struct line *select_slc_migration_victim_line(struct conv_ftl *conv_ftl)
{
	struct line_mgmt *lm = &conv_ftl->slc_rt.slc_lm;
	struct line *victim_line = NULL;
	struct line *line = NULL;
	pqueue_t *pq = lm->victim_line_pq;
	unsigned int eligible;
	size_t i;

	if (slc_migration_policy == SLC_MIGRATION_POLICY_RANDOM) {
		eligible = count_slc_migration_candidates(conv_ftl);
		if (eligible == 0)
			return NULL;
		victim_line = pick_nth_slc_migration_candidate(conv_ftl, get_random_u32() % eligible);
		goto out;
	}

	list_for_each_entry(line, &lm->full_line_list, entry) {
		if (slc_migration_candidate_is_better(line, victim_line))
			victim_line = line;
	}

	if (pq) {
		for (i = 1; i < pq->size; i++) {
			struct line *cand = pq->d[i];

			if (slc_migration_candidate_is_better(cand, victim_line))
				victim_line = cand;
		}
	}

	if (!victim_line)
		return NULL;

out:
	if (victim_line->pos) {
		pqueue_remove(lm->victim_line_pq, victim_line);
		lm->victim_line_cnt--;
		victim_line->pos = 0;
	} else {
		list_del_init(&victim_line->entry);
		lm->full_line_cnt--;
	}

	return victim_line;
}

static struct write_pointer *__get_wp(struct conv_ftl *ftl, uint32_t io_type)
{
	if (io_type == USER_IO) {
		if (ftl->slc_layout.slc_line_cnt > 0)
			return &ftl->slc_rt.slc_wp;
		return &ftl->slc_rt.tlc_wp;
	} else if (io_type == GC_IO) {
		return &ftl->slc_rt.tlc_gc_wp;
	}

	NVMEV_ASSERT(0);
	return NULL;
}

static void prepare_write_pointer(struct conv_ftl *conv_ftl, uint32_t io_type)
{
	struct write_pointer *wp = __get_wp(conv_ftl, io_type);
	enum line_pool_id target_pool = get_io_target_pool(conv_ftl, io_type);
	struct line *curline = get_next_free_line_by_pool(conv_ftl, target_pool);

	NVMEV_ASSERT(wp);
	NVMEV_ASSERT(curline);

	/* wp->curline is always our next-to-write super-block */
	*wp = (struct write_pointer){
		.curline = curline,
		.ch = 0,
		.lun = 0,
		.pg = 0,
		.blk = curline->id,
		.pl = 0,
	};
}

static void advance_write_pointer(struct conv_ftl *conv_ftl, uint32_t io_type)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct write_pointer *wpp = __get_wp(conv_ftl, io_type);
	struct line_mgmt *lm = get_pool_lm(conv_ftl, wpp->curline->pool);
	enum line_pool_id next_pool;
	uint32_t oneshot_pgs = get_pool_pgs_per_oneshotpg(conv_ftl, wpp->curline->pool);

	cb_clock++;

	NVMEV_DEBUG_VERBOSE("current wpp: ch:%d, lun:%d, pl:%d, blk:%d, pg:%d\n",
			wpp->ch, wpp->lun, wpp->pl, wpp->blk, wpp->pg);

	check_addr(wpp->pg, spp->pgs_per_blk);
	wpp->pg++;
	if ((wpp->pg % oneshot_pgs) != 0)
		goto out;

	wpp->pg -= oneshot_pgs;
	check_addr(wpp->ch, spp->nchs);
	wpp->ch++;
	if (wpp->ch != spp->nchs)
		goto out;

	wpp->ch = 0;
	check_addr(wpp->lun, spp->luns_per_ch);
	wpp->lun++;
	/* in this case, we should go to next lun */
	if (wpp->lun != spp->luns_per_ch)
		goto out;

	wpp->lun = 0;
	/* go to next wordline in the block */
	wpp->pg += oneshot_pgs;
	if (wpp->pg != spp->pgs_per_blk)
		goto out;

	wpp->pg = 0;
	/* line is now fully written and closed: stamp its age for Cost-Benefit */
	wpp->curline->mtime = cb_clock;
	wpp->curline->close_seq = conv_ftl->slc_rt.line_close_seq++;
	/* move current line to {victim,full} line list */
	if (wpp->curline->vpc == spp->pgs_per_line) {
		/* all pgs are still valid, move to full line list */
		NVMEV_ASSERT(wpp->curline->ipc == 0);
		list_add_tail(&wpp->curline->entry, &lm->full_line_list);
		lm->full_line_cnt++;
		NVMEV_DEBUG_VERBOSE("wpp: move line to full_line_list\n");
	} else {
		NVMEV_DEBUG_VERBOSE("wpp: line is moved to victim list\n");
		NVMEV_ASSERT(wpp->curline->vpc >= 0 && wpp->curline->vpc < spp->pgs_per_line);
		/* there must be some invalid pages in this line */
		NVMEV_ASSERT(wpp->curline->ipc > 0);
		pqueue_insert(lm->victim_line_pq, wpp->curline);
		lm->victim_line_cnt++;
	}
	/* current line is used up, pick another empty line */
	check_addr(wpp->blk, spp->blks_per_pl);
	next_pool = wpp->curline->pool;
	if (next_pool == LINE_POOL_SLC && conv_ftl->slc_rt.slc_lm.free_line_cnt == 0)
		foreground_slc_migration(conv_ftl);
	wpp->curline = get_next_free_line_by_pool(conv_ftl, next_pool);
	NVMEV_DEBUG_VERBOSE("wpp: got new clean line %d\n", wpp->curline->id);

	wpp->blk = wpp->curline->id;
	check_addr(wpp->blk, spp->blks_per_pl);

	/* make sure we are starting from page 0 in the super block */
	NVMEV_ASSERT(wpp->pg == 0);
	NVMEV_ASSERT(wpp->lun == 0);
	NVMEV_ASSERT(wpp->ch == 0);
	/* TODO: assume # of pl_per_lun is 1, fix later */
	NVMEV_ASSERT(wpp->pl == 0);
out:
	NVMEV_DEBUG_VERBOSE("advanced wpp: ch:%d, lun:%d, pl:%d, blk:%d, pg:%d (curline %d)\n",
			wpp->ch, wpp->lun, wpp->pl, wpp->blk, wpp->pg, wpp->curline->id);
}

static struct ppa get_new_page(struct conv_ftl *conv_ftl, uint32_t io_type)
{
	struct ppa ppa;
	struct write_pointer *wp = __get_wp(conv_ftl, io_type);

	ppa.ppa = 0;
	ppa.g.ch = wp->ch;
	ppa.g.lun = wp->lun;
	ppa.g.pg = wp->pg;
	ppa.g.blk = wp->blk;
	ppa.g.pl = wp->pl;

	NVMEV_ASSERT(ppa.g.pl == 0);

	return ppa;
}

static void init_maptbl(struct conv_ftl *conv_ftl)
{
	int i;
	struct ssdparams *spp = &conv_ftl->ssd->sp;

	conv_ftl->maptbl = vmalloc(sizeof(struct ppa) * spp->tt_pgs);
	for (i = 0; i < spp->tt_pgs; i++) {
		conv_ftl->maptbl[i].ppa = UNMAPPED_PPA;
	}
}

static void remove_maptbl(struct conv_ftl *conv_ftl)
{
	vfree(conv_ftl->maptbl);
}

static void init_rmap(struct conv_ftl *conv_ftl)
{
	int i;
	struct ssdparams *spp = &conv_ftl->ssd->sp;

	conv_ftl->rmap = vmalloc(sizeof(uint64_t) * spp->tt_pgs);
	for (i = 0; i < spp->tt_pgs; i++) {
		conv_ftl->rmap[i] = INVALID_LPN;
	}
}

static void remove_rmap(struct conv_ftl *conv_ftl)
{
	vfree(conv_ftl->rmap);
}

static void conv_init_ftl(struct conv_ftl *conv_ftl, struct convparams *cpp, struct ssd *ssd)
{
	/*copy convparams*/
	conv_ftl->cp = *cpp;

	conv_ftl->ssd = ssd;

	/* initialize maptbl */
	init_maptbl(conv_ftl); // mapping table

	/* initialize rmap */
	init_rmap(conv_ftl); // reverse mapping table (?)

	/* initialize all the lines */
	init_slc_layout_metadata(conv_ftl);
	init_lines(conv_ftl);

	/* initialize write pointer, this is how we allocate new pages for writes */
	prepare_write_pointer(conv_ftl, USER_IO);
	prepare_write_pointer(conv_ftl, GC_IO);

	init_write_flow_control(conv_ftl);

	NVMEV_INFO("Init FTL instance with %d channels (%ld pages)\n", conv_ftl->ssd->sp.nchs,
		   conv_ftl->ssd->sp.tt_pgs);

	return;
}

static void conv_remove_ftl(struct conv_ftl *conv_ftl)
{
	remove_lines(conv_ftl);
	remove_rmap(conv_ftl);
	remove_maptbl(conv_ftl);
}

static void conv_init_params(struct convparams *cpp)
{
	cpp->op_area_pcent = OP_AREA_PERCENT;
	cpp->gc_thres_lines = 2; /* Need only two lines.(host write, gc)*/
	cpp->gc_thres_lines_high = 2; /* Need only two lines.(host write, gc)*/
	cpp->enable_gc_delay = 1;
	cpp->pba_pcent = (int)((1 + cpp->op_area_pcent) * 100);
}

void conv_init_namespace(struct nvmev_ns *ns, uint32_t id, uint64_t size, void *mapped_addr,
			 uint32_t cpu_nr_dispatcher)
{
	struct ssdparams spp;
	struct convparams cpp;
	struct conv_ftl *conv_ftls;
	struct ssd *ssd;
	uint32_t i;
	const uint32_t nr_parts = SSD_PARTITIONS;

	ssd_init_params(&spp, size, nr_parts);
	conv_init_params(&cpp);

	conv_ftls = kmalloc(sizeof(struct conv_ftl) * nr_parts, GFP_KERNEL);

	for (i = 0; i < nr_parts; i++) {
		ssd = kmalloc(sizeof(struct ssd), GFP_KERNEL);
		ssd_init(ssd, &spp, cpu_nr_dispatcher);
		conv_init_ftl(&conv_ftls[i], &cpp, ssd);
	}

	/* PCIe, Write buffer are shared by all instances*/
	for (i = 1; i < nr_parts; i++) {
		kfree(conv_ftls[i].ssd->pcie->perf_model);
		kfree(conv_ftls[i].ssd->pcie);
		kfree(conv_ftls[i].ssd->write_buffer);

		conv_ftls[i].ssd->pcie = conv_ftls[0].ssd->pcie;
		conv_ftls[i].ssd->write_buffer = conv_ftls[0].ssd->write_buffer;
	}

	ns->id = id;
	ns->csi = NVME_CSI_NVM;
	ns->nr_parts = nr_parts;
	ns->ftls = (void *)conv_ftls;
	ns->size = (uint64_t)((size * 100) / cpp.pba_pcent);
	ns->mapped = mapped_addr;
	/*register io command handler*/
	ns->proc_io_cmd = conv_proc_nvme_io_cmd;

	NVMEV_INFO("FTL physical space: %lld, logical space: %lld (physical/logical * 100 = %d)\n",
		   size, ns->size, cpp.pba_pcent);

	return;
}

void conv_remove_namespace(struct nvmev_ns *ns)
{
	struct conv_ftl *conv_ftls = (struct conv_ftl *)ns->ftls;
	const uint32_t nr_parts = SSD_PARTITIONS;
	uint32_t i;

	/* PCIe, Write buffer are shared by all instances*/
	for (i = 1; i < nr_parts; i++) {
		/*
		 * These were freed from conv_init_namespace() already.
		 * Mark these NULL so that ssd_remove() skips it.
		 */
		conv_ftls[i].ssd->pcie = NULL;
		conv_ftls[i].ssd->write_buffer = NULL;
	}

	for (i = 0; i < nr_parts; i++) {
		conv_remove_ftl(&conv_ftls[i]);
		ssd_remove(conv_ftls[i].ssd);
		kfree(conv_ftls[i].ssd);
	}

	kfree(conv_ftls);
	ns->ftls = NULL;
}

static inline bool valid_ppa(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	int ch = ppa->g.ch;
	int lun = ppa->g.lun;
	int pl = ppa->g.pl;
	int blk = ppa->g.blk;
	int pg = ppa->g.pg;
	//int sec = ppa->g.sec;

	if (ch < 0 || ch >= spp->nchs)
		return false;
	if (lun < 0 || lun >= spp->luns_per_ch)
		return false;
	if (pl < 0 || pl >= spp->pls_per_lun)
		return false;
	if (blk < 0 || blk >= spp->blks_per_pl)
		return false;
	if (pg < 0 || pg >= spp->pgs_per_blk)
		return false;

	return true;
}

static inline bool valid_lpn(struct conv_ftl *conv_ftl, uint64_t lpn)
{
	return (lpn < conv_ftl->ssd->sp.tt_pgs);
}

static inline bool mapped_ppa(struct ppa *ppa)
{
	return !(ppa->ppa == UNMAPPED_PPA);
}

static inline struct line *get_line(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	return &(conv_ftl->lines[ppa->g.blk]);
}

/* update SSD status about one page from PG_VALID -> PG_VALID */
static void mark_page_invalid(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct nand_block *blk = NULL;
	struct nand_page *pg = NULL;
	bool was_full_line = false;
	struct line *line;
	struct line_mgmt *lm;

	/* update corresponding page status */
	pg = get_pg(conv_ftl->ssd, ppa);
	NVMEV_ASSERT(pg->status == PG_VALID);
	pg->status = PG_INVALID;

	/* update corresponding block status */
	blk = get_blk(conv_ftl->ssd, ppa);
	NVMEV_ASSERT(blk->ipc >= 0 && blk->ipc < spp->pgs_per_blk);
	blk->ipc++;
	NVMEV_ASSERT(blk->vpc > 0 && blk->vpc <= spp->pgs_per_blk);
	blk->vpc--;

	/* update corresponding line status */
	line = get_line(conv_ftl, ppa);
	lm = get_pool_lm(conv_ftl, line->pool);
	NVMEV_ASSERT(line->ipc >= 0 && line->ipc < spp->pgs_per_line);
	if (line->vpc == spp->pgs_per_line) {
		NVMEV_ASSERT(line->ipc == 0);
		was_full_line = true;
	}
	line->ipc++;
	NVMEV_ASSERT(line->vpc > 0 && line->vpc <= spp->pgs_per_line);
	/* Adjust the position of the victime line in the pq under over-writes */
	if (line->pos) {
		/* remove+insert always re-reads get_pri() live, so this stays
		 * correct regardless of what the active gc_policy's priority
		 * formula is (unlike pqueue_change_priority, which trusts an
		 * externally-computed new_pri that may be in different units) */
		pqueue_remove(lm->victim_line_pq, line);
		line->vpc--;
		pqueue_insert(lm->victim_line_pq, line);
	} else {
		line->vpc--;
	}

	if (was_full_line) {
		/* move line: "full" -> "victim" */
		list_del_init(&line->entry);
		lm->full_line_cnt--;
		pqueue_insert(lm->victim_line_pq, line);
		lm->victim_line_cnt++;
	}
}

static void mark_page_valid(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct nand_block *blk = NULL;
	struct nand_page *pg = NULL;
	struct line *line;

	/* update page status */
	pg = get_pg(conv_ftl->ssd, ppa);
	NVMEV_ASSERT(pg->status == PG_FREE);
	pg->status = PG_VALID;

	/* update corresponding block status */
	blk = get_blk(conv_ftl->ssd, ppa);
	NVMEV_ASSERT(blk->vpc >= 0 && blk->vpc < spp->pgs_per_blk);
	blk->vpc++;

	/* update corresponding line status */
	line = get_line(conv_ftl, ppa);
	NVMEV_ASSERT(line->vpc >= 0 && line->vpc < spp->pgs_per_line);
	line->vpc++;
}

static void mark_block_free(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct nand_block *blk = get_blk(conv_ftl->ssd, ppa);
	struct nand_page *pg = NULL;
	int i;

	for (i = 0; i < spp->pgs_per_blk; i++) {
		/* reset page status */
		pg = &blk->pg[i];
		NVMEV_ASSERT(pg->nsecs == spp->secs_per_pg);
		pg->status = PG_FREE;
	}

	/* reset block status */
	NVMEV_ASSERT(blk->npgs == spp->pgs_per_blk);
	blk->ipc = 0;
	blk->vpc = 0;
	blk->erase_cnt++;
}

static void gc_read_page(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct convparams *cpp = &conv_ftl->cp;
	int media = get_ppa_nand_media(conv_ftl, ppa);

	count_media_reads(GC_IO, media, 1);
	/* advance conv_ftl status, we don't care about how long it takes */
	if (cpp->enable_gc_delay) {
		struct nand_cmd gcr = {
			.type = GC_IO,
			.cmd = NAND_READ,
			.media = media,
			.stime = 0,
			.xfer_size = spp->pgsz,
			.interleave_pci_dma = false,
			.ppa = ppa,
		};
		ssd_advance_nand(conv_ftl->ssd, &gcr);
	}
}

/* move valid page data (already in DRAM) from victim line to a new page */
static uint64_t gc_write_page(struct conv_ftl *conv_ftl, struct ppa *old_ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct convparams *cpp = &conv_ftl->cp;
	struct ppa new_ppa;
	uint64_t lpn = get_rmap_ent(conv_ftl, old_ppa);

	NVMEV_ASSERT(valid_lpn(conv_ftl, lpn));
	new_ppa = get_new_page(conv_ftl, GC_IO);
	/* update maptbl */
	set_maptbl_ent(conv_ftl, lpn, &new_ppa);
	/* update rmap */
	set_rmap_ent(conv_ftl, lpn, &new_ppa);

	mark_page_valid(conv_ftl, &new_ppa);
	count_media_writes(GC_IO, get_ppa_nand_media(conv_ftl, &new_ppa), 1);

	/* need to advance the write pointer here */
	advance_write_pointer(conv_ftl, GC_IO);

	if (cpp->enable_gc_delay) {
		struct nand_cmd gcw = {
			.type = GC_IO,
			.cmd = NAND_NOP,
			.media = NAND_MEDIA_TLC,
			.stime = 0,
			.interleave_pci_dma = false,
			.ppa = &new_ppa,
		};
		if (last_pg_in_wordline(conv_ftl, &new_ppa)) {
			gcw.cmd = NAND_WRITE;
			gcw.xfer_size = spp->pgsz * get_ppa_pgs_per_oneshotpg(conv_ftl, &new_ppa);
		}

		ssd_advance_nand(conv_ftl->ssd, &gcw);
	}

	/* advance per-ch gc_endtime as well */
#if 0
	new_ch = get_ch(conv_ftl, &new_ppa);
	new_ch->gc_endtime = new_ch->next_ch_avail_time;

	new_lun = get_lun(conv_ftl, &new_ppa);
	new_lun->gc_endtime = new_lun->next_lun_avail_time;
#endif

	return 0;
}

/* here ppa identifies the block we want to clean */
static void clean_one_block(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct nand_page *pg_iter = NULL;
	int cnt = 0;
	int pg;

	for (pg = 0; pg < spp->pgs_per_blk; pg++) {
		ppa->g.pg = pg;
		pg_iter = get_pg(conv_ftl->ssd, ppa);
		/* there shouldn't be any free page in victim blocks */
		NVMEV_ASSERT(pg_iter->status != PG_FREE);
		if (pg_iter->status == PG_VALID) {
			gc_read_page(conv_ftl, ppa);
			/* delay the maptbl update until "write" happens */
			gc_write_page(conv_ftl, ppa);
			cnt++;
		}
	}

	NVMEV_ASSERT(get_blk(conv_ftl->ssd, ppa)->vpc == cnt);
}

/* here ppa identifies the block we want to clean */
static void clean_one_flashpg(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct convparams *cpp = &conv_ftl->cp;
	struct nand_page *pg_iter = NULL;
	int cnt = 0, i = 0;
	uint64_t completed_time = 0;
	struct ppa ppa_copy = *ppa;

	for (i = 0; i < spp->pgs_per_flashpg; i++) {
		pg_iter = get_pg(conv_ftl->ssd, &ppa_copy);
		/* there shouldn't be any free page in victim blocks */
		NVMEV_ASSERT(pg_iter->status != PG_FREE);
		if (pg_iter->status == PG_VALID)
			cnt++;

		ppa_copy.g.pg++;
	}

	ppa_copy = *ppa;

	if (cnt <= 0)
		return;

	count_media_reads(GC_IO, get_ppa_nand_media(conv_ftl, &ppa_copy), cnt);

	if (cpp->enable_gc_delay) {
		struct nand_cmd gcr = {
			.type = GC_IO,
			.cmd = NAND_READ,
			.media = get_ppa_nand_media(conv_ftl, &ppa_copy),
			.stime = 0,
			.xfer_size = spp->pgsz * cnt,
			.interleave_pci_dma = false,
			.ppa = &ppa_copy,
		};
		completed_time = ssd_advance_nand(conv_ftl->ssd, &gcr);
	}

	for (i = 0; i < spp->pgs_per_flashpg; i++) {
		pg_iter = get_pg(conv_ftl->ssd, &ppa_copy);

		/* there shouldn't be any free page in victim blocks */
		if (pg_iter->status == PG_VALID) {
			/* delay the maptbl update until "write" happens */
			gc_write_page(conv_ftl, &ppa_copy);
		}

		ppa_copy.g.pg++;
	}
}

static void mark_line_free(struct conv_ftl *conv_ftl, struct ppa *ppa)
{
	struct line *line = get_line(conv_ftl, ppa);
	struct line_mgmt *lm = get_pool_lm(conv_ftl, line->pool);
	line->ipc = 0;
	line->vpc = 0;
	/* move this line to free line list */
	list_add_tail(&line->entry, &lm->free_line_list);
	lm->free_line_cnt++;
}

static int reclaim_one_line(struct conv_ftl *conv_ftl, struct line *victim_line,
			    enum reclaim_reason reason, bool refill_credit)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct line_mgmt *lm;
	struct ppa ppa;
	int flashpg;

	if (!victim_line) {
		return -1;
	}

	ppa.g.blk = victim_line->id;
	lm = get_pool_lm(conv_ftl, victim_line->pool);
	NVMEV_DEBUG_VERBOSE("GC-ing line:%d,ipc=%d(%d),victim=%d,full=%d,free=%d\n", ppa.g.blk,
		    victim_line->ipc, victim_line->vpc, lm->victim_line_cnt,
		    lm->full_line_cnt, get_total_free_line_cnt(conv_ftl));

	if (reason == RECLAIM_REASON_TLC_GC) {
		tlc_gc_cnt++;
		tlc_gc_valid_page_migrate_cnt += victim_line->vpc;
		/* Keep the legacy counter for existing scripts; it now explicitly
		 * means TLC GC valid-page copies rather than all migration types. */
		gc_valid_page_migrate_cnt += victim_line->vpc;
	} else {
		slc_migration_cnt++;
		slc_migration_valid_page_migrate_cnt += victim_line->vpc;
	}

	if (refill_credit) {
		conv_ftl->wfc.credits_to_refill = victim_line->ipc;
	}

	/* copy back valid data */
	for (flashpg = 0; flashpg < spp->flashpgs_per_blk; flashpg++) {
		int ch, lun;

		ppa.g.pg = flashpg * spp->pgs_per_flashpg;
		for (ch = 0; ch < spp->nchs; ch++) {
			for (lun = 0; lun < spp->luns_per_ch; lun++) {
				struct nand_lun *lunp;

				ppa.g.ch = ch;
				ppa.g.lun = lun;
				ppa.g.pl = 0;
				lunp = get_lun(conv_ftl->ssd, &ppa);
				clean_one_flashpg(conv_ftl, &ppa);

				if (flashpg == (spp->flashpgs_per_blk - 1)) {
					struct convparams *cpp = &conv_ftl->cp;

					mark_block_free(conv_ftl, &ppa);

					if (cpp->enable_gc_delay) {
						struct nand_cmd gce = {
							.type = GC_IO,
							.cmd = NAND_ERASE,
							.media = get_ppa_nand_media(conv_ftl, &ppa),
							.stime = 0,
							.interleave_pci_dma = false,
							.ppa = &ppa,
						};
						ssd_advance_nand(conv_ftl->ssd, &gce);
					}

					lunp->gc_endtime = lunp->next_lun_avail_time;
				}
			}
		}
	}

	/* update line status */
	mark_line_free(conv_ftl, &ppa);

	return 0;
}

static int do_gc(struct conv_ftl *conv_ftl, bool force)
{
	struct line *victim_line = select_tlc_gc_victim_line(conv_ftl, force);

	return reclaim_one_line(conv_ftl, victim_line, RECLAIM_REASON_TLC_GC, true);
}

static int do_slc_migration(struct conv_ftl *conv_ftl)
{
	struct line *victim_line;

	if (conv_ftl->slc_rt.tlc_lm.free_line_cnt == 0)
		do_gc(conv_ftl, true);

	victim_line = select_slc_migration_victim_line(conv_ftl);
	return reclaim_one_line(conv_ftl, victim_line, RECLAIM_REASON_SLC_MIGRATION, false);
}

static void foreground_gc(struct conv_ftl *conv_ftl)
{
	if (should_gc_high(conv_ftl)) {
		NVMEV_DEBUG_VERBOSE("should_gc_high passed");
		/* perform GC here until !should_gc(conv_ftl) */
		do_gc(conv_ftl, true);
	}
}

static void foreground_slc_migration(struct conv_ftl *conv_ftl)
{
	while (should_migrate_slc(conv_ftl)) {
		if (do_slc_migration(conv_ftl) != 0)
			break;
	}
}

static bool is_same_flash_page(struct conv_ftl *conv_ftl, struct ppa ppa1, struct ppa ppa2)
{
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	uint32_t ppa1_page = ppa1.g.pg / spp->pgs_per_flashpg;
	uint32_t ppa2_page = ppa2.g.pg / spp->pgs_per_flashpg;

	return (ppa1.h.blk_in_ssd == ppa2.h.blk_in_ssd) && (ppa1_page == ppa2_page);
}

static bool conv_read(struct nvmev_ns *ns, struct nvmev_request *req, struct nvmev_result *ret)
{
	struct conv_ftl *conv_ftls = (struct conv_ftl *)ns->ftls;
	struct conv_ftl *conv_ftl = &conv_ftls[0];
	/* spp are shared by all instances*/
	struct ssdparams *spp = &conv_ftl->ssd->sp;

	struct nvme_command *cmd = req->cmd;
	uint64_t lba = cmd->rw.slba;
	uint64_t nr_lba = (cmd->rw.length + 1);
	uint64_t start_lpn = lba / spp->secs_per_pg;
	uint64_t end_lpn = (lba + nr_lba - 1) / spp->secs_per_pg;
	uint64_t lpn;
	uint64_t nsecs_start = req->nsecs_start;
	uint64_t nsecs_completed, nsecs_latest = nsecs_start;
	uint32_t xfer_size, i;
	uint32_t nr_parts = ns->nr_parts;

	struct ppa prev_ppa;
	struct nand_cmd srd = {
		.type = USER_IO,
		.cmd = NAND_READ,
		.media = NAND_MEDIA_TLC,
		.stime = nsecs_start,
		.interleave_pci_dma = true,
	};

	NVMEV_ASSERT(conv_ftls);
	NVMEV_DEBUG_VERBOSE("%s: start_lpn=%lld, len=%lld, end_lpn=%lld", __func__, start_lpn, nr_lba, end_lpn);
	if ((end_lpn / nr_parts) >= spp->tt_pgs) {
		NVMEV_ERROR("%s: lpn passed FTL range (start_lpn=%lld > tt_pgs=%ld)\n", __func__,
			    start_lpn, spp->tt_pgs);
		return false;
	}

	if (LBA_TO_BYTE(nr_lba) <= (KB(4) * nr_parts)) {
		srd.stime += spp->fw_4kb_rd_lat;
	} else {
		srd.stime += spp->fw_rd_lat;
	}

	for (i = 0; (i < nr_parts) && (start_lpn <= end_lpn); i++, start_lpn++) {
		conv_ftl = &conv_ftls[start_lpn % nr_parts];
		xfer_size = 0;
		prev_ppa = get_maptbl_ent(conv_ftl, start_lpn / nr_parts);

		/* normal IO read path */
		for (lpn = start_lpn; lpn <= end_lpn; lpn += nr_parts) {
			uint64_t local_lpn;
			struct ppa cur_ppa;

			local_lpn = lpn / nr_parts;
			cur_ppa = get_maptbl_ent(conv_ftl, local_lpn);
			if (!mapped_ppa(&cur_ppa) || !valid_ppa(conv_ftl, &cur_ppa)) {
				NVMEV_DEBUG_VERBOSE("lpn 0x%llx not mapped to valid ppa\n", local_lpn);
				NVMEV_DEBUG_VERBOSE("Invalid ppa,ch:%d,lun:%d,blk:%d,pl:%d,pg:%d\n",
					    cur_ppa.g.ch, cur_ppa.g.lun, cur_ppa.g.blk,
					    cur_ppa.g.pl, cur_ppa.g.pg);
				continue;
			}

			// aggregate read io in same flash page
			if (mapped_ppa(&prev_ppa) &&
			    is_same_flash_page(conv_ftl, cur_ppa, prev_ppa)) {
				xfer_size += spp->pgsz;
				continue;
			}

			if (xfer_size > 0) {
				count_media_reads(USER_IO, get_ppa_nand_media(conv_ftl, &prev_ppa),
						 xfer_size / spp->pgsz);
				srd.xfer_size = xfer_size;
				srd.ppa = &prev_ppa;
				srd.media = get_ppa_nand_media(conv_ftl, &prev_ppa);
				nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &srd);
				nsecs_latest = max(nsecs_completed, nsecs_latest);
			}

			xfer_size = spp->pgsz;
			prev_ppa = cur_ppa;
		}

		// issue remaining io
		if (xfer_size > 0) {
			count_media_reads(USER_IO, get_ppa_nand_media(conv_ftl, &prev_ppa),
					 xfer_size / spp->pgsz);
			srd.xfer_size = xfer_size;
			srd.ppa = &prev_ppa;
			srd.media = get_ppa_nand_media(conv_ftl, &prev_ppa);
			nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &srd);
			nsecs_latest = max(nsecs_completed, nsecs_latest);
		}
	}

	ret->nsecs_target = nsecs_latest;
	ret->status = NVME_SC_SUCCESS;
	return true;
}

static bool conv_write(struct nvmev_ns *ns, struct nvmev_request *req, struct nvmev_result *ret)
{
	struct conv_ftl *conv_ftls = (struct conv_ftl *)ns->ftls;
	struct conv_ftl *conv_ftl = &conv_ftls[0];

	/* wbuf and spp are shared by all instances */
	struct ssdparams *spp = &conv_ftl->ssd->sp;
	struct buffer *wbuf = conv_ftl->ssd->write_buffer;

	struct nvme_command *cmd = req->cmd;
	uint64_t lba = cmd->rw.slba;
	uint64_t nr_lba = (cmd->rw.length + 1);
	uint64_t start_lpn = lba / spp->secs_per_pg;
	uint64_t end_lpn = (lba + nr_lba - 1) / spp->secs_per_pg;

	uint64_t lpn;
	uint32_t nr_parts = ns->nr_parts;

	uint64_t nsecs_latest;
	uint64_t nsecs_xfer_completed;
	uint32_t allocated_buf_size;

	struct nand_cmd swr = {
		.type = USER_IO,
		.cmd = NAND_WRITE,
		.media = NAND_MEDIA_SLC,
		.interleave_pci_dma = false,
		.xfer_size = 0,
	};

	NVMEV_DEBUG_VERBOSE("%s: start_lpn=%lld, len=%lld, end_lpn=%lld", __func__, start_lpn, nr_lba, end_lpn);
	if ((end_lpn / nr_parts) >= spp->tt_pgs) {
		NVMEV_ERROR("%s: lpn passed FTL range (start_lpn=%lld > tt_pgs=%ld)\n",
				__func__, start_lpn, spp->tt_pgs);
		return false;
	}

	allocated_buf_size = buffer_allocate(wbuf, LBA_TO_BYTE(nr_lba));
	if (allocated_buf_size < LBA_TO_BYTE(nr_lba))
		return false;

	nsecs_latest =
		ssd_advance_write_buffer(conv_ftl->ssd, req->nsecs_start, LBA_TO_BYTE(nr_lba));
	nsecs_xfer_completed = nsecs_latest;

	swr.stime = nsecs_latest;

	for (lpn = start_lpn; lpn <= end_lpn; lpn++) {
		uint64_t local_lpn;
		uint64_t nsecs_completed = 0;
		struct ppa ppa;

		conv_ftl = &conv_ftls[lpn % nr_parts];
		local_lpn = lpn / nr_parts;
		ppa = get_maptbl_ent(
			conv_ftl, local_lpn); // Check whether the given LPN has been written before
		if (mapped_ppa(&ppa)) {
			/* update old page information first */
			mark_page_invalid(conv_ftl, &ppa);
			set_rmap_ent(conv_ftl, INVALID_LPN, &ppa);
			NVMEV_DEBUG("%s: %lld is invalid, ", __func__, ppa2pgidx(conv_ftl, &ppa));
		}

		/* new write */
		ppa = get_new_page(conv_ftl, USER_IO);
		/* update maptbl */
		set_maptbl_ent(conv_ftl, local_lpn, &ppa);
		NVMEV_DEBUG("%s: got new ppa %lld, ", __func__, ppa2pgidx(conv_ftl, &ppa));
		/* update rmap */
		set_rmap_ent(conv_ftl, local_lpn, &ppa);

		mark_page_valid(conv_ftl, &ppa);

		/* need to advance the write pointer here */
		advance_write_pointer(conv_ftl, USER_IO);

		/* Aggregate write io in flash page */
		if (last_pg_in_wordline(conv_ftl, &ppa)) {
			uint64_t write_pages = get_ppa_pgs_per_oneshotpg(conv_ftl, &ppa);
			swr.ppa = &ppa;
			swr.media = get_ppa_nand_media(conv_ftl, &ppa);
			swr.xfer_size = spp->pgsz * write_pages;
			count_media_writes(USER_IO, swr.media, write_pages);

			nsecs_completed = ssd_advance_nand(conv_ftl->ssd, &swr);
			nsecs_latest = max(nsecs_completed, nsecs_latest);

			schedule_internal_operation(req->sq_id, nsecs_completed, wbuf,
						    swr.xfer_size);
		}

		if (!ppa_is_slc(conv_ftl, &ppa)) {
			consume_write_credit(conv_ftl);
			check_and_refill_write_credit(conv_ftl);
		}
	}

	if ((cmd->rw.control & NVME_RW_FUA) || (spp->write_early_completion == 0)) {
		/* Wait all flash operations */
		ret->nsecs_target = nsecs_latest;
	} else {
		/* Early completion */
		ret->nsecs_target = nsecs_xfer_completed;
	}
	ret->status = NVME_SC_SUCCESS;

	return true;
}

static void conv_flush(struct nvmev_ns *ns, struct nvmev_request *req, struct nvmev_result *ret)
{
	uint64_t start, latest;
	uint32_t i;
	struct conv_ftl *conv_ftls = (struct conv_ftl *)ns->ftls;

	start = local_clock();
	latest = start;
	for (i = 0; i < ns->nr_parts; i++) {
		latest = max(latest, ssd_next_idle_time(conv_ftls[i].ssd));
	}

	NVMEV_DEBUG_VERBOSE("%s: latency=%llu\n", __func__, latest - start);

	ret->status = NVME_SC_SUCCESS;
	ret->nsecs_target = latest;
	return;
}

bool conv_proc_nvme_io_cmd(struct nvmev_ns *ns, struct nvmev_request *req, struct nvmev_result *ret)
{
	struct nvme_command *cmd = req->cmd;

	NVMEV_ASSERT(ns->csi == NVME_CSI_NVM);

	switch (cmd->common.opcode) {
	case nvme_cmd_write:
		if (!conv_write(ns, req, ret))
			return false;
		break;
	case nvme_cmd_read:
		if (!conv_read(ns, req, ret))
			return false;
		break;
	case nvme_cmd_flush:
		conv_flush(ns, req, ret);
		break;
	default:
		NVMEV_ERROR("%s: command not implemented: %s (0x%x)\n", __func__,
				nvme_opcode_string(cmd->common.opcode), cmd->common.opcode);
		break;
	}

	return true;
}

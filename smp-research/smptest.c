// SPDX-License-Identifier: BSD-3-Clause
/*
 * historical reset probes, nokia lumia 930 (martini) SMP bring-up.
 * the successful mailbox tests are in parking/. only the cache-invalidating
 * smpmarkers reader below was reused; reset release is not the working path.
 *
 * "oem smptest": sets the secondary cpu boot address via lk2nd's own
 * cpu_boot_set_addr() (lk2nd/smp/cpu-boot.c) -- tries the modern atomic
 * scm_call2 "set_addr_mc" first, falls back to the legacy
 * scm_call_atomic2(SCM_SVC_BOOT, 0x01, ...). originally this file hand-rolled
 * the legacy call via the buffered scm_call() transport instead; switched to
 * the real helper so this matches what lk2nd actually ships, not a
 * from-scratch reimplementation using a different transport. does NOT power
 * on a secondary core -- see "oem smprelease" below for that. requires the
 * GPL krait helpers (GPL=1; this checkout already defaults to it).
 *
 * "oem smprelease": after a successful "oem smptest", calls lk2nd's own
 * cpu_boot_kpssv2() (lk2nd/smp/gpl/krait.c) for cpu1 only, instead of a
 * hand-rolled register sequence -- same register values either way, but the
 * real helper adds dsb() after every write and wraps the whole sequence in
 * enter/exit_critical_section(), which the original hand-rolled version in
 * this file omitted entirely (plain writel() in this tree is just a bare
 * volatile store, no barrier). deliberately scoped to one core; does not
 * attempt to construct or send a gic ipi/sgi afterward. resetting an
 * already parked core is not the demonstrated release mechanism, and a
 * missing marker alone is not proof of non-execution.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <arch/ops.h>
#include <fastboot.h>
#include <platform.h>
#include <platform/timer.h>
#include <qgic_common.h>
#include <reg.h>
#include <scm.h>
#include "../smp/cpu-boot.h"

/* cpu1 acc, shared l2 saw -- confirmed against qcom-msm8974.dtsi tonight.
 * register offsets within these blocks are cpu_boot_kpssv2()'s own concern
 * now, not duplicated here. */
#define ACC1_BASE   0xf9098000
#define L2_SAW_BASE 0xf9012000

/* dedicated trampoline: writes a magic marker, then parks. not reused
 * command-handler code, a real inert stub, and not combined with the
 * linux smp path -- this test stays entirely inside lk. */
static volatile uint32_t smp_marker __attribute__((aligned(4))) = 0;
#define SMP_MARKER_MAGIC 0xdead930c

/* no_stack_protector matters here, not just belt-and-suspenders: gcc still
 * emitted a stack-protector canary prologue/epilogue around this despite
 * naked (confirmed in a real build, see smp-research/README.md) -- cpu1
 * fresh out of reset has an architecturally undefined sp, so that canary
 * write at [sp+4] could fault or corrupt shared low memory before this
 * ever reaches the marker store below. */
__attribute__((naked, used, aligned(4), no_stack_protector))
static void smp_trampoline(void)
{
	__asm__ volatile(
		"ldr r0, =smp_marker\n"
		"ldr r1, =0xdead930c\n"
		"str r1, [r0]\n"
		"dsb\n"		/* force the marker store to actually complete,
				 * not just retire into a write buffer, before
				 * parking -- otherwise cpu0 invalidating and
				 * rereading it could still race the write. */
		"1: wfe\n"
		"b 1b\n"
	);
}

static void cmd_oem_smptest(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];
	int ret;

	ret = cpu_boot_set_addr((uintptr_t)&smp_trampoline, false);

	snprintf(response, sizeof(response), "cpu_boot_set_addr ret=%d\n", ret);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smptest", cmd_oem_smptest);

/*
 * "oem smpfix": same legacy set-boot-address call as "oem smptest" but with
 * flags=0x52 instead of QCOM_SCM_BOOT_FLAG_COLD_ALL=0x29.
 * these are the standard warm and cold masks for cpu1–3, respectively.
 * both firmware tables are read; the earlier write-only-table and custom
 * flags-mismatch interpretations were wrong. the historical command name
 * is retained, but this does not fix a demonstrated firmware flags bug.
 */
static void cmd_oem_smpfix(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];
	int ret;

	ret = scm_call_atomic2(SCM_SVC_BOOT, 0x01, 0x52, (uint32_t)(uintptr_t)&smp_trampoline);

	snprintf(response, sizeof(response), "scm_call_atomic2(flags=0x52) ret=%d\n", ret);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smpfix", cmd_oem_smpfix);

static void cmd_oem_smprelease(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];

	smp_marker = 0;

	cpu_boot_kpssv2(ACC1_BASE, L2_SAW_BASE);

	/* this immediate cached read is inconclusive on its own; smpmarkers
	 * explicitly invalidates the marker cache line before observing it. */
	mdelay(50);

	snprintf(response, sizeof(response), "cpu1 release done, marker=0x%x\n", smp_marker);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smprelease", cmd_oem_smprelease);

/*
 * "oem smpwake": does NOT repeat the acc/saw release -- that register state
 * should persist across fastboot commands within the same boot session.
 * sends a plain sev (send event), a basic arm instruction that wakes any
 * core sitting in wfe, broadcast to all cores, architecturally harmless if
 * nothing is listening. not a gic/interrupt-controller construction -- if
 * this doesn't move the marker, the next step really would need that.
 */
static void cmd_oem_smpwake(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];

	__asm__ volatile("sev" ::: "memory");
	mdelay(50);

	snprintf(response, sizeof(response), "post-sev marker=0x%x\n", smp_marker);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smpwake", cmd_oem_smpwake);

/*
 * "oem smpsgi": does NOT repeat the release sequence either. sends an
 * actual GIC SGI (software generated interrupt) to cpu1 specifically,
 * using GIC_DIST_SOFTINT -- already defined in qgic_common.h, already
 * initialized by lk1st's own normal boot (platform/msm8974/platform.c
 * calls qgic_init() unconditionally), so no new gic setup here, just one
 * register write to an already-running, already-verified-working
 * interrupt controller.
 *
 * GICD_SGIR layout (standard GICv2, architectural, not soc-specific):
 *   bits[25:24] TargetListFilter, 00 = use CPUTargetList below
 *   bits[23:16] CPUTargetList, bit N targets cpu interface N
 *   bits[3:0]   SGIINTID, 0-15
 * targeting cpu1 (bit 1) with sgi id 0.
 */
static void cmd_oem_smpsgi(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];

	writel((1 << 17) /* CPUTargetList bit 1 = cpu interface 1 */ | 0 /* sgi id 0 */, GIC_DIST_SOFTINT);
	mdelay(50);

	snprintf(response, sizeof(response), "post-sgi marker=0x%x\n", smp_marker);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smpsgi", cmd_oem_smpsgi);

/*
 * "oem smpmarkers": re-reads both markers (this file's trampoline
 * smp_marker, and crt0.s's secondary_core_marker) after an explicit cache
 * invalidate of each one's line. "fastboot oem debug readl" on its own
 * goes through cpu0's normal cacheable mapping of lk ram (see
 * platform/msm8974/platform.c, non-shareable) -- if cpu0 cached a 0 at
 * either address any time before cpu1 could have written it, a plain readl
 * would keep returning that stale cached 0 forever regardless of what
 * cpu1 actually did, with no way to tell the two cases apart. this forces
 * a fresh fetch from dram before reporting either value.
 */
extern volatile uint32_t secondary_core_marker;

static void cmd_oem_smpmarkers(const char *arg, void *data, unsigned sz)
{
	char response[MAX_RSP_SIZE];

	arch_invalidate_cache_range((addr_t)&smp_marker, sizeof(smp_marker));
	arch_invalidate_cache_range((addr_t)&secondary_core_marker, sizeof(secondary_core_marker));

	snprintf(response, sizeof(response),
		 "trampoline marker=0x%x entry marker=0x%x\n",
		 smp_marker, secondary_core_marker);
	fastboot_info(response);
	fastboot_okay("");
}
FASTBOOT_REGISTER("oem smpmarkers", cmd_oem_smpmarkers);

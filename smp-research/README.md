# stock parking research and four-core Linux

**cpu1, cpu2 and cpu3 have each executed our own non-secure ARM code on the
lumia 930.** cpu0 kept running lk throughout. the successful mechanism is
the stock UEFI parking mailbox plus a targeted interrupt, not another core
reset or a TZ boot-address patch.

**Linux SMP is now implemented and verified on all four cores.** see
[the Linux results](../docs/linux-smp.md) and [build instructions](../README.md).
the rest of this page records the earlier bare-metal proof and corrected
firmware analysis. the original single-core image remains preserved.

## hardware results

| core | mailbox page | test stub | completion marker | raw MPIDR |
| --- | --- | --- | --- | --- |
| cpu1 | `0x00302000` | `0x00302100` | `0x930c0001` | `0x80000001` |
| cpu2 | `0x00303000` | `0x00303100` | `0x930c0002` | `0x80000002` |
| cpu3 | `0x00304000` | `0x00304100` | `0x930c0003` | `0x80000003` |

all positive results were confirmed twice through the existing
`fastboot oem smpmarkers` command, which explicitly invalidates the CPU0
D-cache lines before reading them. the completion magic is unique to each
stub; MPIDR.Aff0 independently identifies the executing core.

this is proof of CPU execution, not just a successful SCM return or register
readback. the old marker command labels are reused: its `entry marker`
field contains raw MPIDR in these tests, not a reset-entry-trap result.

see [parking/](parking/) for the original executed assembly, curated output
and build-specific safety constraints. no proprietary firmware binaries or
extracted module code are included.

## finding the actual firmware path

offline analysis of the device-owned UEFI dump found `MpParkDxe`, FFS GUID
`8fdadcd4-c723-4ded-ab9e-aee4f3e0c2a2`, inside an LZMA-compressed firmware
volume. its PE32 image mixes Thumb C and ARM assembly.

all addresses in this paragraph are **module RVAs**, not deployed physical
addresses. driver entry registers an event at `0x249c`, with callback
`0x2144` and group `27abf055-b1b8-4c26-8048-748f37baa2df`: the standard
`EFI_EVENT_GROUP_EXIT_BOOT_SERVICES`. that callback calls setup `0x2524`.
parking is scheduled for ExitBootServices, not executed immediately at DXE
entry. the actual assertion-enable property bit permits the setup call in
this image.

the config sets `NumCpus = 4` and reserves DDR-base offset `0x00300000`,
size `0x00040000`, as uncached/unbuffered `MPPark Code`. the Windows physical
memory map independently excludes that region. with DDR base zero, setup
places each mailbox at:

```
0x00300000 + (MPIDR.Aff0 + 1) * 0x1000
```

the page-local ARM parking loop is copied to mailbox +`0x800`. a read-only
live check in lk found the expected mailbox fields and **all 29 words of
the parking loop matched the extracted firmware** on each tested core.
the shared startup acknowledgement at `0x00300ffc` read `4`; that was useful
context, but not substituted for the independent execution tests.

## mailbox contract

| page offset | initial value | purpose observed in the firmware |
| --- | --- | --- |
| +0 | `0xffffffff` | target cpu id; low byte compared to MPIDR.Aff0 |
| +4 | `0xffffffff` | unused by this polling loop |
| +8 | zero | low word of requested entry address |
| +12 | zero | upper word, loaded into r9 |
| +`0x800` | parking code | position-independent ARM loop |

when the cpu id matches and the low entry word is nonzero, the loop loads
the entry words, clears both words, sets r0 to the mailbox address and r1
to zero, then branches through the low entry word with `bx`. this is an
ARM32 branch; loading an upper word does not make it an ARM64 entry path.
otherwise it uses **`dsb; wfi`**, not WFE. SEV alone is not the appropriate
wake-up mechanism.

the firmware bootstrap clears SCTLR.M and SCTLR.C. its secondary helper
initializes the GIC CPU interface, enables SGIs 0–15, sets priority mask
`0xfe`, acknowledges startup, and enters the parking loop. GIC distributor
and CPU-interface bases are `0xf9000000` and `0xf9002000`.

the successful tests published the entry words, published cpu id last,
used the existing cache-maintenance/DSB command for ordering, and sent one
SGI1 to the selected CPU interface via `GICD_SGIR` at `0xf9000f00`:

| core | SGIR value |
| --- | --- |
| cpu1 | `0x00020001` |
| cpu2 | `0x00040001` |
| cpu3 | `0x00080001` |

there were no SCM calls or ACC/SAW/core-reset writes in these successful
tests. each mailbox was disarmed afterward and read back as
`ffffffff ffffffff 00000000 00000000`. the stubs branch back to the stock
loop; post-test PCs were not directly sampled. the phone remained
responsive in fastboot. tiny inert stubs remained in unused page space;
no persistent phone storage was written.

## corrections to the earlier reverse engineering

the earlier version of this writeup overstated several conclusions.

### the flags are ordinary cold/warm flags

the TZ descriptor at `0xfe82919c` contains command ID `0x401`, name
`tzbsp_set_boot_addr`, Thumb handler `0xfe811090`, and two four-byte
arguments. this independently confirms the legacy boot-address service.

| core | cold flag / slot in `0xfe829a30` | warm flag / slot in `0xfe829a40` |
| --- | --- | --- |
| cpu0 | no cold flag here | `0x04` / +0 |
| cpu1 | `0x01` / +4 | `0x02` / +4 |
| cpu2 | `0x08` / +8 | `0x10` / +8 |
| cpu3 | `0x20` / +12 | `0x40` / +12 |

**both tables are read.** the selector at `0xfe810e46` chooses the cold
table through a branch at `0xfe810ef4` when a nonzero core has zero state
at `0xfe838980 + cpu_id*4`; otherwise it selects the warm table at
`0xfe810e76`. the previous analysis missed the cold-table branch and also
misreported its cpu1 slot as +0 rather than +4.

`0x29` is therefore the standard cold mask for cpu1–3, and `0x52` the
standard warm mask. this is not a discovered Windows-specific flag
mismatch. the stock UEFI setup independently uses these same cold and warm
bits. the historical `oem smpfix` name is retained, but that experiment
selects warm addresses; it does not fix a proven firmware flags bug.

### the counter is not simply accumulated reboot counts

`0xfe810d3a` increments a per-core byte at `0xfe8389a0`, scans the four
bytes and rejects values >=2. however, the same bytes are **decremented**
at `0xfe80ea90–0xfe80ea98` before a firmware WFI path and **incremented**
at `0xfe80ec3c–0xfe80ec44` afterward. the on-disk initialized data is zero.
this is consistent with active-state/entry-exit accounting, not a counter
exhausted by an evening of rebooting. actual warm-reset loader behavior
was not proved by inspecting the ELF initial values.

the LDREX/STREX loop at `0xfe81008c` acquires a lock by storing cpu_id+1
only when the word is zero. it is not an atomic all-core check-in increment.
the earlier all-core-barrier interpretation was not established.

forcing an already parked core through reset might violate secure state
accounting, but that remains a hypothesis, not the demonstrated cause of
the old failures. the successful parking path avoids that question.

### discovery and negative results were overinterpreted

`0x02000601` is `IS_CALL_AVAIL`, not CPU_ON. mainline SCM code already
falls back to the legacy convention; failure of that discovery call does
not establish that no legacy boot-address call can be attempted.

negative probes in selected Windows binaries did not rule out a firmware
parking/mailbox path. successful register writes never proved a core
executed their configured vector. nor did the old failures establish a
JTAG-only research wall: the stock UEFI module and its live mailbox were
available to investigate without JTAG.

## historical reset probes and real build bugs

`smptest.c` and `lk2nd-patches/0003-smp-research-cpu1-entry-trap.patch` are
historical research tools, **not part of the normal build or the successful
parking release mechanism**. only the cache-invalidating `oem smpmarkers`
reader from those probes was reused to observe the new stubs.

past probes programmed cold/warm vectors, used the actual lk2nd
`cpu_boot_set_addr()` / `cpu_boot_kpssv2()` helpers, and tried SEV/SGI after
reset release. no execution was observed in those old tests. they are not
a recommended starting point now that the mailbox route is demonstrated.

three genuine build bugs remain relevant when reproducing early work:

- explicitly set `-e 0x7cc00000` when wrapping the flat lk binary as a
  single-PT_LOAD ELF. relying on the default entry produced an ELF with
  entry zero on the observed toolchain.
- a naked C trampoline still acquired GCC stack-protector accesses;
  `no_stack_protector` was needed. the successful new probes instead use
  stack-free assembly, checked in disassembly.
- inserting a marker before the startup stack broke 8-byte stack alignment;
  `.balign 8` before the stack fixes the AAPCS32 violation.

the GPL krait helpers are controlled by `GPL=1` / `BUILD_GPL`; this checkout
already defaults `GPL` to 1. the new mailbox stubs do not call those helpers.

## next

the staged ARM32 implementation succeeded: cpu1 first, then all three
secondaries under Linux. see [NEXT-STEPS.md](NEXT-STEPS.md) for the completed
scope and remaining limits. the bare-metal SGI1 probes below are historical;
the Linux backend intentionally uses SGI0, its wake-up IPI.

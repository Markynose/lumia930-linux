# four-core Linux hardware results

## staged trials

first boot used cpu0 + cpu1 (`maxcpus=2`). both affinity-pinned workers
passed, Linux reported two CPUs online, and cpu1 timer/IPI activity and USB
were independently checked. the phone was then rebooted through the normal
firmware/lk path for the four-core image (`maxcpus=4`).

four-core results were confirmed in two independent TCP reports:

```
online: 0-3
possible: 0-3
smp: Brought up 1 node, 4 CPUs
SMP: Total of 4 processors activated (153.60 BogoMIPS).

cpu=0 state=2 before=0 after=0 checksum=1152182802 affinity=0
cpu=1 state=2 before=1 after=1 checksum=1022427398 affinity=0
cpu=2 state=2 before=2 after=2 checksum=2562841059 affinity=0
cpu=3 state=2 before=3 after=3 checksum=3768333047 affinity=0
```

`state=2` means pass. `affinity=0` is a successful `sched_setaffinity` call.
each child ran 30 million xorshift iterations on its selected CPU, checking
`getcpu` before and after. the checksums differ because the initial seed
contains the CPU id. a CPU label or marker alone was not accepted as proof.

all four had timer interrupts, rescheduling IPIs and function-call IPIs.
USB remained responsive between reports, with no panic, BUG or stall
observed. the owner visually confirmed the phone panel shows `4/4 online`
and separate cpu0–cpu3 activity lines.

these were bounded bring-up checks, not a long stress test, charging test,
hotplug test or power-management qualification. idle cores do not need to
show constant activity. repeat boots and sustained load remain useful
validation before broader claims of stability.

## kernel implementation

`kernel/0001-lumia930-uefi-parking-smp.patch` adds a board-specific ARM32
`smp_operations` backend. DTS method `nokia,lumia930-parking-v1` selects it;
the machine guard is `nokia,martini`. existing Qualcomm reset methods are
unchanged for unrelated devices.

it validates/ioremaps the reserved firmware region, checks idle mailboxes,
publishes the physical assembly entry with cpu id last and DSB ordering,
then sends **SGI0**, the Linux wake-up IPI. CPU-interface targeting is
explicit because the GIC map for an unstarted Linux CPU is not yet known.

SGIR values for CPU interfaces 1/2/3 are `0x00020000`, `0x00040000` and
`0x00080000` at `0xf9000f00`. this differs intentionally from the earlier
bare-metal marker tests, which used SGI1. no SCM or ACC/SAW release call is
part of the new backend.

the stack-free ARM entry receives r0 = stock mailbox, records raw MPIDR,
CPSR, SCTLR and ACTLR in unused page space starting at +`0x200`, restores
the mailbox id, acknowledges SGI0 if pending, and branches to ordinary
`secondary_startup_arm`. Linux supplies the usual secondary stack/page
tables through `secondary_data`. the branch is PC-relative and remains
valid at the physical load address.

observed firmware-entry state on all three secondaries:

```
cpu1 MPIDR=80000001 SCTLR=00c55878 ACTLR=00000000 stage=1
cpu2 MPIDR=80000002 SCTLR=00c55878 ACTLR=00000000 stage=1
cpu3 MPIDR=80000003 SCTLR=00c55878 ACTLR=00000000 stage=1
```

SCTLR.M/C are off. the ordinary processor initialization and Linux GIC
startup complete after the small entry shim. there is no CPU-offline/dead
backend; hotplug and secure idle/power collapse are deliberately unsupported.

## preservation and scope

- original single-core image and initramfs preserved, hashes verified.
- separate kernel source/build tree used for the trials.
- no persistent phone writes, BCD changes, TZ edits or lk deployment.
- normal Windows default retained; only `fastboot boot` was used.
- original bare-metal scratch stubs were not overwritten by the kernel
  diagnostics, which use a different part of each reserved page.

## reproducing diagnostics

use `SMP_TEST=1 MAX_CPUS=2 sh tools/build-image.sh ...` for the first stage,
then `SMP_TEST=1 sh tools/build-image.sh ...` for all four. after RAM boot and
USB setup, a TCP connection to port 7000 receives the pinned-work results
and read-only kernel reports, ending in `--- report complete ---`.

normal builds omit this helper and only receive dashboard lines. raw logs
can contain device identifiers: keep them private and publish only reviewed,
curated extracts like the ones above.

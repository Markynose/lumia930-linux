# original successful mailbox probes

`cpu1.S`, `cpu2.S` and `cpu3.S` are the original assembly used for the
successful on-device tests. `results.txt` is curated output, not a raw
firmware dump. the stubs are our own code; stock firmware code is not
redistributed here.

**these are build-specific research artifacts, not a turnkey installer.**
the two marker addresses belong to the exact lk image used in this test:

- `0x7cc4c000`: `secondary_core_marker`, reused to hold raw MPIDR.
- `0x7cc82de0`: `smp_marker`, reused for a core-specific completion magic.

resolve those symbols in your own lk ELF before adapting anything. stale
addresses can corrupt live bootloader memory. do not paste RAM-write
commands into another build, another device or an already modified test
session. the older reset/SCM probes are not prerequisites for this release
path, and must not be run as an initialization step.

## local assembly, no phone commands

for example:

```
arm-none-eabi-as -o /tmp/cpu1.o cpu1.S
arm-none-eabi-objcopy -O binary -j .text /tmp/cpu1.o /tmp/cpu1.bin
arm-none-eabi-objdump -dr /tmp/cpu1.o
```

the tested cpu1/cpu2 blobs are 96 bytes; cpu3 is 92 bytes because its mailbox
constant fits a single ARM MOV, removing a literal-pool word. inspect the
actual disassembly rather than assuming every blob has the same length.
no relocations or stack accesses remain in these objects.

## procedure used on the phone

1. started from a fresh stock-firmware -> BootShim -> lk boot, without
   issuing the old reset/release probes.
2. verified each mailbox had words `ffffffff ffffffff 00000000 00000000`,
   all 29 stock parking-code words matched the device-owned firmware, and
   the chosen scratch range at mailbox +`0x100` was zero. saved originals.
3. checked the CPU0 3 MiB section mapping was normal write-through,
   read/write (`0x00300c1a` in the tested short-descriptor table), and the
   GIC distributor was enabled. no MMU mappings were changed.
4. wrote the selected stub into scratch, read it back in full, and reset
   the marker globals to zero. explicitly invalidated their D-cache lines
   with the existing `oem smpmarkers` command and checked both were zero.
5. published high entry word zero, low entry word equal to the physical
   stub address, then target cpu id last. the existing marker-reader cache
   maintenance ends with DSB; called it after publication for ordering.
6. sent exactly one SGI1 to the selected CPU interface. the tested SGIR
   values and addresses are in the parent README.
7. after 200 ms, observed the core-specific magic and MPIDR using the
   cache-invalidating command, then independently confirmed the result.
8. cleared entry low/high and restored cpu-id `ffffffff`; issued cache
   maintenance/DSB and read back the disarmed mailbox. left the tiny stub
   intact rather than race its final return branch.

CPU0 data caching is non-shareable here. an ordinary cached debug read is
not a substitute for the explicit invalidation above. CPU1–3 entered from
the stock loop with MMU and D-cache off; fresh stub locations were not
previously used as executable code in this test session.

each stub records MPIDR, reads GICC_IAR, EOIs it if interrupt ID is 1,
restores the mailbox cpu-id, writes the completion magic, DSB, and branches
back to the original page-local parking loop. the current post-test PC was
not directly sampled; the recorded completion proves the stub executed.

no SCM calls, core resets, lk rebuild/deployment, kernel boot or persistent
phone writes were used in these bare-metal tests. Linux SMP subsequently
succeeded on all four cores; see [the Linux results](../../docs/linux-smp.md).
CPU hotplug remains unsupported.

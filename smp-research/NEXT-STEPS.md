# basic four-core Linux SMP is complete

the parking-aware ARM32 backend is implemented and tested. the first
cpu0+cpu1 trial passed, followed by cpu0–cpu3 online with pinned work on each,
timer/IPI activity, working USB and a visually confirmed phone CPU panel.

see [the Linux results](../docs/linux-smp.md),
[the kernel patch](../kernel/0001-lumia930-uefi-parking-smp.patch) and
[the current build instructions](../README.md). this source-only tree is a
clean single-commit snapshot, not the old research history.

remaining limits: bounded tests are not long-term stress qualification.
CPU hotplug, secure idle/power collapse and charging are not validated.
keep `cpuidle.off=1`, the stock firmware parking reservation and the normal
Windows boot path. do not revive the old SCM/ACC reset probes or assume
ARM64 parking code is a drop-in ARM32 backend.

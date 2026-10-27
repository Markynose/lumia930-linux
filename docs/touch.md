# touchscreen IRQ pull-up

corner taps, vertical swipes and two simultaneous contacts passed on the
Lumia930 in a separate RAM boot. this is input validation, not an X11/GUI,
suspend, ten-finger or long-term stability claim. no touchscreen firmware was
flashed. existing installed images are not updated by pulling this source.

## fault and fix

the stock ACPI touch resource requests TLMM GPIO61, falling-edge, active-low,
with a pull-up. the earlier board DTS specified the interrupt but no pinctrl
state. the live pin was input/low/no-pull and touch IRQ counters remained zero.

the board DTS now selects a default state containing only GPIO61 as GPIO
input with `bias-pull-up`. GPIO60, the interrupt edge, supplies and RMI function
settings are unchanged. the test used explicit unused phandle `0x10000` so
all existing phandles stayed unchanged for the DTB comparison.

after RAM boot the pin read input/high/pull-up. the parent RMI interrupt and
F12 handler both ran. a coordinated capture recorded1799 non-SYN events,
221 sync frames,8 contact starts and8 releases, no `SYN_DROPPED`, and two
simultaneous contacts in slots0/1. four corner taps matched portrait X/Y
orientation and vertical swipes produced position updates.10 slots are
advertised, but only two concurrent fingers were tested.

the F34 bootloader-version probe warning remained. F01/F12 normal input works
despite that firmware-update interface failure; it is not a reason to flash
or patch touchscreen firmware speculatively.

## controlled test

- build privately and use `fastboot boot`, never `fastboot flash`.
- verify the Synaptics input device and its actual event node each boot.
- inspect IRQ counters and GPIO state before and after gestures.
- start the event reader first and confirm that it is actually listening,
  then ask for gestures. a ready prompt before starting the reader can miss
  short gestures entirely; an empty trace alone is not a driver diagnosis.
- check corner mapping, press/release, swipes, simultaneous contacts and
  dropped events. registration/capability lists alone do not prove input.

in this test only the appended DTB differed. the kernel, ramdisk and command
line were reused byte-for-byte from the tested persistence image. parsed DTBs
confirmed every old property, phandle and memory reservation was unchanged,
except two added touchscreen pinctrl references and the new GPIO61 state.
MMC guards, SMP and charging configuration were not modified. four CPUs and
pinned SSH remained working; Data was read-only and unmounted afterward.

USB was online while battery status alternated between charging and
discharging. the owner reported actual Linux battery depletion. this touch
fix does not establish charging correctness; keep tests bounded and recharge
in Windows when needed.

## source-only regression

with a prepared kernel checkout containing its built `scripts/dtc/dtc`, and
a private output directory outside this repository:

```sh
git show 99af377c3ba5bb4ccb489f5f93a719f4987e54db:dts/qcom-msm8974-nokia-martini.dts \
    > /private/work/pre-touch.dts
python3 alpine/tests/test-touch-dtb.py /path/to/kernel /private/work/pre-touch.dts
```

this compiles both boards against the same prepared kernel common include in
a temporary directory, preserving its selected MMC profile, and compares all
parsed properties and reservations. optional `--baseline-dtb` and `--expected-dtb`
arguments also require byte identity with privately retained pre-fix/tested
DTBs. it does not change the kernel checkout, access a phone or run a boot.

copy the current board DTS into a fresh kernel checkout when following the
normal build recipes. the guarded persistence source manifest also includes
this updated board; do not bypass its checks to use an older copied DTS.

installing a tested image is a separate, backed-up Windows file operation.
back up the current persistence-capable image before replacing
`EFIESP\alpine\boot.img`; an older pre-persistence image is not an equivalent
fallback. preserve Windows default, lk, BCD and stock early boot files.
`lumia-save` preserves selected RAM-root files, not a kernel or DTB update.

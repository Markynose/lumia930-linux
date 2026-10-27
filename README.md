# lumia930-linux

**all four cores running Linux on a nokia lumia 930**, with a framebuffer
status screen and USB networking. device: RM-975, `martini`, MSM8974.

this is an experimental Linux6.16 setup, not a Windows replacement. the
original tiny-init image supports RAM boot and a CPU dashboard. the newer
Alpine image supports installed lk file boot, key-only SSH and manual
Data-backed diskless persistence. Windows remains the default. RAM boot does
not flash anything; installing BootShim/lk or replacing the EFI image does
write boot files and requires separate backups.

## verified on the phone

- cpu0–cpu3 online: `/sys/devices/system/cpu/online` reports `0-3`.
- Linux reports `SMP: Total of 4 processors activated`.
- four separate affinity-pinned workers ran real work, with `getcpu`
  confirming the correct core before and after each workload.
- timer and rescheduling/function-call IPIs active across all four cores.
- USB NCM networking and the TCP status screen remain responsive.
- phone-local CPU online count and per-core busy percentages, visually
  confirmed on the actual screen.

this works through the **stock UEFI parking mailboxes**, without TZ patches,
SCM boot-address calls or resetting the secondary cores. the kernel backend
is ARM32 and specific to this board/firmware. see [the SMP results](docs/linux-smp.md)
and [the corrected firmware research](smp-research/README.md).

basic SMP is verified, not CPU hotplug or secure power collapse. keep
`cpuidle.off=1`, `clk_ignore_unused` and `pd_ignore_unused` for this setup.
charging, audio, camera, modem, touch and wireless are not validated here;
pronto is disabled. the display inherits firmware scanout, not a full GPU
or panel driver. do not treat this as a daily-driver phone port.

## alpine and persistence

[the Alpine build and test notes](alpine/README.md) cover the installed-menu
path, authenticated USB SSH, host USB internet helpers and the guarded MMC
kernel. [persistence usage](alpine/PERSISTENCE.md) describes `lumia-save`:
configuration, selected files and official signed packages are saved on Data
and restored into RAM at boot. Data is unmounted between manual saves.

RAM boot, installed-menu restoration, offline save and desktop SSH/HTTPS were
verified. unplugged boot and thinkpad operation were also reported working by
the owner. the new Data-only kernel is specific to the audited32GB layout;
do not enable unrestricted MMC writes or reuse its bounds on another layout.
there is no repartitioning, formatting or automated deployment here.

## layout

- `kernel/`: tested configs, ARM32 parking backend and Data-only MMC patch.
- `alpine/`: private image/lk builders, read-only FAT/image validation, USB SSH
  services, host helpers and diskless save/restore sources.
- `dts/`: 930 board tree and the common 1520-derived regulator/USB base.
- `status-screen/`: tiny static, libc-free PID1 and the host dashboard sender.
- `tools/build-image.sh`: build a four-core Android v0 RAM-boot image.
- `lk2nd-patches/`: load-address/display fixes; the numbered research trap
  patch is historical and not needed for Linux SMP.
- `smp-research/`: original bare-metal probes and corrected analysis.
- `device-nokia-martini/`: older pmOS packaging drafts, **not the tested
  build recipe**. do not use their old cmdline/ramoops values for this setup.

## prerequisite: working lk fastboot

you need an already unlocked phone with a working
[imbushuo BootShim](https://github.com/imbushuo/boot-shim) -> lk1st chain.
unlocking and initial EFI/BCD installation are not automated here. back up
the phone first, keep Windows default, and do not replace `bootarm.efi`.

known chain: stock UEFI -> Windows Boot Manager selectable lk entry ->
BootShim `elf-loader-pre3` -> EFIESP `emmc_appsboot.mbn` -> lk fastboot.
stock MpParkDxe parks the secondary cores at ExitBootServices. preserve that
firmware path; do not use `lk2nd.spin-table=force` or the old reset probes.

lk base: [Mainline4Lumia/lk2nd](https://github.com/Mainline4Lumia/lk2nd),
`martini-support`, tested checkout `55dc0857000881b0fa82008c0bd796534ff6227e`.
apply **only 0001 and 0002** for the normal lk build:

```
git apply /path/to/lumia930-linux/lk2nd-patches/0001-raise-forced-load-addresses.patch
git apply /path/to/lumia930-linux/lk2nd-patches/0002-remove-framebuffer-relocation-hack.patch
make TOOLCHAIN_PREFIX=arm-none-eabi- DEBUG=1 DEBUG_FBCON=1 \
     ENABLE_DISPLAY=1 LK2ND_DISPLAY=cont-splash \
     LK2ND_BUNDLE_DTB=msm8974-nokia-martini.dtb lk1st-msm8974
```

BootShim needs a valid ELF with entry `0x7cc00000`, not a renamed flat MBN.
the tested deployment wrapped `lk.bin` into a single-PT_LOAD ELF at that
address with the entry explicitly set. never assume a generated ELF has the
right entry: inspect it with `readelf -h -l`. preserve a working lk payload
before replacing it. Linux SMP itself requires no lk modification or redeploy.

## build the Linux image

host dependencies: git, GNU make, clang/LLVM, lld, Python 3, cpio, gzip,
mkbootimg and fastboot, plus the usual Linux kernel build dependencies.
use a **separate kernel checkout and output directory**. preserve the
known-good single-core image as a recovery reference.

```
git clone https://github.com/msm8974-mainline/linux.git linux-lumia930
cd linux-lumia930
git checkout f243f840064d20797ff18fa59b857dd33f0b3db8
git apply /path/to/lumia930-linux/kernel/0001-lumia930-uefi-parking-smp.patch
cd /path/to/lumia930-linux
sh tools/build-image.sh /path/to/linux-lumia930 /path/to/output
```

the script copies the supplied config/DTS, builds the kernel and PID1, then
packages `output/boot.img`. it never deploys or flashes. the image uses:

```
console=tty0 loglevel=8 ignore_loglevel consoleblank=0
maxcpus=4 cpuidle.off=1 clk_ignore_unused pd_ignore_unused
rdinit=/init panic=0 log_buf_len=1M lk2nd.pass-ramoops
```

Android header v0, page 2048, kernel `0x10008000`, ramdisk `0x14000000`,
tags `0x13e00000`; the DTB is appended to zImage. parking memory at
`0x00300000–0x00340000` is reserved and no-map in the board DTS.

once the phone is in lk fastboot:

```
fastboot boot /path/to/output/boot.img
```

**do not use `fastboot flash`.** for initial validation on another firmware,
start with `MAX_CPUS=2`, then use the default four-core image after cpu1
works. `SMP_TEST=1` enables bounded pinned workers and a read-only TCP boot
report; this is a diagnostic build, not enabled in the normal image.
status-screen artifacts are built under the selected output directory rather
than shared in the source tree. parallel image builds still need separate
kernel checkouts and output directories.

## status screen and USB

the top panel reads **the phone** `/proc/stat`: online count and cpu0–cpu3
busy percentages, refreshed once a second. offline cores are labelled
rather than faked. idle cores normally show zero or low usage.

the lower dashboard receives **host** text over USB NCM at
`172.16.42.1:7000`. give the host USB interface `172.16.42.2/24`; on Arch,
NetworkManager may need to stop managing that connection before adding a
temporary address/route. use the actual USB interface name, not the LAN.

```
sudo nmcli device disconnect <usb-interface>
sudo ip addr replace 172.16.42.2/24 dev <usb-interface>
sudo ip link set <usb-interface> up
sudo ip route replace 172.16.42.1/32 dev <usb-interface> src 172.16.42.2
python3 status-screen/host/push.py
```

`host/push.py` reads host uptime/load/memory, not phone metrics. you can also
send arbitrary text: `# ` prefixes accent lines and `!c` clears only the
host dashboard, leaving the phone CPU panel intact.

```
printf '# hello\nfour-core Linux\n' | nc 172.16.42.1 7000
```

PID1 uses the Linux 8x16 bitmap font at 3x scale, not an installed desktop
font. the font header is generated locally from the kernel source and is
not committed. the service is for a trusted direct USB connection, with
no authentication or encryption.

native runtime, TELNET and parallel-build regression checks are documented
in [status-screen/TESTING.md](status-screen/TESTING.md). these source-level
checks are separate from hardware boot validation.

## privacy and licensing

source, patches and curated results only. no proprietary firmware dumps,
extracted UEFI/TZ modules, device serials, credentials or raw private logs.
`.gitignore` is a guardrail, not a substitute for reviewing staged files.
Linux backend code is GPL-2.0-only; see `LICENSE` for the other source and
upstream attribution. generated/compiled artifacts are not distributed here.

credits: [KorelisLabs](https://github.com/KorelisLabs/lumia-1520-mainline)
for the shared Lumia base; [Mainline4Lumia](https://github.com/Mainline4Lumia),
[msm8974-mainline](https://github.com/msm8974-mainline/linux), and
[imbushuo](https://github.com/imbushuo/boot-shim) for the boot/kernel work.

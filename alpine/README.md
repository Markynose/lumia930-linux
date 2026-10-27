# alpine file boot

alpine3.24.3 armv7, BusyBox/OpenRC, key-only Dropbear on USB NCM. the installed
lk menu can read `/alpine/boot.img` from EFIESP and invoke its existing Android
boot path. Windows stays default. no firmware, personalized rootfs or images
are distributed here.

## verified

- four-core RAM boot with authenticated, pinned SSH.
- installed lk file boot, without `fastboot boot`.
- USB internet and real apk/HTTPS operation.
- guarded eMMC enumeration, primary/backup GPT agreement and read-only NTFS
  inspection before persistence writes.
- manual saves with clean NTFS unmount, plus offline package/config/script
  restoration through RAM boot and installed-menu boot.
- an offline second save, with the phone default route removed for the test.
- unplugged startup and thinkpad operation reported working by the owner.

charging, suspend, full touch/graphics, wireless/audio/modem/camera and
long-term filesystem reliability are not certified. this is an experimental
single-phone setup, not a generic installer or full hardware-support claim.

## private RAM-only image

prepare the four-core kernel using the main README, then use a separate
private workdir outside this repository:

```sh
sh alpine/build.sh /path/to/tested-kernel /path/to/private-work
fastboot boot /path/to/private-work/boot/boot.img
```

host: Arch Linux, GNU make, clang/LLVM, cpio/gzip, mkbootimg, bsdtar, curl,
GnuPG, sudo, qemu-arm/binfmt and the usual kernel tools. the builder runs ARM
apk in a private QEMU chroot. it verifies the pinned release SHA512 and GPG
signing fingerprint before unpacking. no QEMU binary is added to the image.

it generates a client login key and a separate phone server host key, locks
the root password, and emits `known_hosts`. keep those private. use
`SSH_AUTHORIZED_KEYS=/path/to/client.pub` to authorize an existing client.
reuse the same private root/server key and login identity when rebuilding an
existing phone with saved state: the saved config also contains its identity.
never publish the generated workdir or upload a personalized image to GitHub.

this default mode has no internal-storage persistence. the optional init
restore hook is inactive unless the persistence helpers are installed.

## guarded persistence kernel

**only the tested32GB layout is supported by this patch.** it bounds normal
MMC writes to sectors `[5308416,61071327)`, which were verified as Data on the
test phone. the save helper additionally checks its label/start/length. do
not assume those bounds fit another phone, modified GPT or firmware layout.
first inspect storage read-only and take an independent backup. no automatic
partitioning, formatting, repair, unrestricted MMC enablement or deployment.

start with the strict read-only audit profile in a fresh checkout prepared
with the parking patch and copied board DTS files. use
`kernel/mmc-audit-read-only.patch` instead of the Data-write patch and
`kernel/lumia930-mmc-ro.config` instead of the Data-write config below.
these are alternative patches, not cumulative. build zImage/board DTB, then
use `alpine/build.sh` without `LUMIA_PERSISTENCE`. its request/block guards
reject data writes, raw ioctls, CQE and non-read queue operations before
ordinary block access. debugfs status/EXT_CSD requests are also denied by that
strict queue profile. initialization still changes permitted volatile card
and controller settings; it is not hardware write protection.

only after a read-only audit/backup and explicit write approval, use a NEW
separate checkout for the bounded writer recipe below. do not run
`tools/build-image.sh` after these steps: that tiny-init builder would
overwrite this config/DTS.

```sh
project=/absolute/path/to/lumia930-linux
git clone https://github.com/msm8974-mainline/linux.git linux-data-save
cd linux-data-save
git checkout f243f840064d20797ff18fa59b857dd33f0b3db8
git apply "$project/kernel/0001-lumia930-uefi-parking-smp.patch"
cp "$project/dts/qcom-msm8974-microsoft-common.dtsi" arch/arm/boot/dts/qcom/
cp "$project/dts/qcom-msm8974-nokia-martini.dts" arch/arm/boot/dts/qcom/
git apply "$project/kernel/0002-lumia930-data-only-mmc.patch"
cp "$project/kernel/lumia930-data-save.config" .config
make ARCH=arm LLVM=1 olddefconfig
python3 "$project/kernel/test-data-policy.py" "$PWD"
LUMIA_PERSISTENCE=1 sh "$project/alpine/build.sh" "$PWD" /path/to/private-persistent-work
```

the builder checks critical source hashes and required config, builds that
guarded kernel, then installs the diskless
helpers into the private root. it never flashes or deploys. validate with
`fastboot boot` first. deployment to the existing EFI image is a separate,
backed-up Windows file operation; do not use `fastboot flash`.

see [persistence usage, limits and rollback](PERSISTENCE.md). saved generations
and the pre-write Data backup contain private user data and credentials.

## lk menu source

use a separate lk checkout at `55dc0857000881b0fa82008c0bd796534ff6227e`
(`martini-support`) with the existing load-address/display fixes described in
the main README. the Alpine integration is gated by `LUMIA930_ALPINE=1`:

```sh
sh alpine/build-lk.sh /path/to/separate-lk /path/to/private-lk-output
```

requires `arm-none-eabi-*`. this builds and verifies a one-PT_LOAD ELF with
entry/load address `0x7cc00000`; it does not install it. the new menu action
and read-only `oem alpine-check` use a narrow FAT16/FAT32 reader with8.3 names,
bounded chains and image/address/DTB checks. these are structural checks, not
cryptographic authenticity. keep stock `bootarm.efi`, BootShim and BCD backups.

## host commands

`alpine/host/lumia-usb` is the desktop/thinkpad USB-sharing helper;
`alpine/persistence/host-save` is the host `lumia-save` wrapper. install them
as your user in `~/.local/bin`, backed up first if already present. both are
POSIX sh; the thinkpad uses doas and the desktop uses sudo. sharing needs
iproute2/nftables and an actual internet uplink. it changes only runtime USB
addressing, a scoped nft table and IPv4 forwarding, not saved firewall files.
it does not forward new inbound connections. the helper also sets the phone
running UTC clock from the host, not its RTC.

configure a pinned SSH alias using your own private paths:

```sshconfig
Host lumia930
    HostName 172.16.42.1
    User root
    IdentityFile /private/path/to/client-key
    IdentitiesOnly yes
    UserKnownHostsFile /private/path/to/known_hosts
    StrictHostKeyChecking yes
    ConnectTimeout 5
```

then `lumia-usb`, `ssh lumia930`, or host `lumia-save`. runtime sharing can be
removed with `sudo nft delete table ip lumia930_usb` or doas on the thinkpad;
restore forwarding only if appropriate to its previous host state.

## host regressions

```sh
python3 alpine/tests/test-fat.py --boot-image /private/path/to/boot.img
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -Ialpine/lk alpine/tests/test-image.c alpine/lk/image-valid.c -o /tmp/test-image
/tmp/test-image /private/path/to/boot.img
python3 kernel/test-data-policy.py /path/to/guarded-linux
python3 kernel/test-mmc-ro-policy.py /path/to/read-only-linux
```

snapshot tests require a private ARM root containing the helper and a valid
fixture: run `snapshot pack /tmp/snapshot-app` inside that private QEMU chroot,
then `sudo python3 alpine/tests/test-persistence.py /private/root`. this tests
corrupt checksums, missing files, symlinks, unsafe paths and unsigned packages.
SSD-backed chroots alone miss APK3 volatile-root policy: also test restoration
on an actual tmpfs root, with networking disabled. local signed APK restoration
uses `--force-non-repository` because the external cache is managed here, not
by APK repository discovery; signature verification remains mandatory.

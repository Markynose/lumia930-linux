#!/bin/sh
set -eu
umask 077

PROJECT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
KSRC=$(CDPATH= cd "${1:?usage: $0 /path/to/tested-kernel /path/to/private-workdir}" && pwd)
mkdir -p "${2:?usage: $0 /path/to/tested-kernel /path/to/private-workdir}"
WORK=$(CDPATH= cd "$2" && pwd)
chmod 700 "$WORK"
case "$WORK/" in
"$PROJECT/"*) echo 'use a private workdir outside the git repository' >&2; exit 1 ;;
esac
ROOT=$WORK/root
PERSISTENCE=${LUMIA_PERSISTENCE:-0}
case "$PERSISTENCE" in
0) ;;
1)
	(cd "$KSRC" && sha256sum -c "$PROJECT/kernel/data-save-source.sha256")
	for option in CONFIG_MMC=y CONFIG_MMC_BLOCK=y CONFIG_MMC_SDHCI_MSM=y 'CONFIG_LOCALVERSION="-lumia930-data-save"'; do
		grep -qxF "$option" "$KSRC/.config" || { echo "missing guarded kernel option: $option" >&2; exit 1; }
	done
	grep -qxF '# CONFIG_MMC_TEST is not set' "$KSRC/.config" || { echo 'MMC test driver must be disabled' >&2; exit 1; }
	make -C "$KSRC" ARCH=arm LLVM=1 -j"${JOBS:-4}" zImage qcom/qcom-msm8974-nokia-martini.dtb
	;;
*) echo 'LUMIA_PERSISTENCE must be 0 or 1' >&2; exit 1 ;;
esac
if [ "$PERSISTENCE" = 0 ] && [ -e "$ROOT/usr/lib/lumia-persist/lumia-persist" ]; then
	echo 'use a separate workdir for a non-persistent image' >&2
	exit 1
fi
DL=$WORK/downloads
VERSION=3.24.3
BASE=https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/armv7
ARCHIVE=alpine-minirootfs-$VERSION-armv7.tar.gz
HASH=a2e278d280483706a358d0f5ae9622d1f44ed374125d6dc9949b555fdfe8cecb10fcea815178b3c9a26719e1922adb78735293a4aacdb3e58f56f4d395bc9d30
FINGERPRINT=0482D84022F52DF1C4E7CD43293ACD0907D9495A
mkdir -p "$DL" "$WORK/gnupg" "$WORK/keys" "$WORK/boot"
chmod 700 "$WORK/gnupg" "$WORK/keys"
fetch() {
	[ -f "$2" ] || { curl -fL --proto '=https' --tlsv1.2 "$1" -o "$2.part"; mv "$2.part" "$2"; }
}
fetch "$BASE/$ARCHIVE" "$DL/$ARCHIVE"
fetch "$BASE/$ARCHIVE.asc" "$DL/$ARCHIVE.asc"
fetch https://alpinelinux.org/keys/ncopa.asc "$DL/ncopa.asc"
printf '%s  %s\n' "$HASH" "$DL/$ARCHIVE" | sha512sum -c -
gpg --homedir "$WORK/gnupg" --import "$DL/ncopa.asc"
gpg --homedir "$WORK/gnupg" --status-fd 1 --verify "$DL/$ARCHIVE.asc" "$DL/$ARCHIVE" > "$WORK/signature.status"
grep -q "^\[GNUPG:\] VALIDSIG $FINGERPRINT " "$WORK/signature.status"
if [ ! -e "$ROOT" ]; then
	mkdir "$ROOT"
	bsdtar -xpf "$DL/$ARCHIVE" -C "$ROOT"
fi
chmod 755 "$ROOT"
read -r installed < "$ROOT/etc/alpine-release"
[ "$installed" = "$VERSION" ] || { echo 'wrong existing rootfs version' >&2; exit 1; }
sudo -n install -m 644 /etc/resolv.conf "$ROOT/etc/resolv.conf"
alpine() { sudo -n env QEMU_CPU=cortex-a15 chroot "$ROOT" "$@"; }
alpine /sbin/apk add --no-cache openrc dropbear iproute2 ca-certificates

if [ -z "${SSH_AUTHORIZED_KEYS:-}" ] && [ ! -f "$WORK/keys/id_ed25519" ]; then
	ssh-keygen -q -t ed25519 -N "" -C lumia930-usb -f "$WORK/keys/id_ed25519"
fi
sudo -n chown 0:0 "$ROOT/root"
sudo -n chmod 700 "$ROOT/root"
sudo -n install -d -m 700 "$ROOT/root/.ssh" "$ROOT/etc/dropbear"
sudo -n install -m 600 "${SSH_AUTHORIZED_KEYS:-$WORK/keys/id_ed25519.pub}" "$ROOT/root/.ssh/authorized_keys"
if ! sudo -n test -f "$ROOT/etc/dropbear/dropbear_ed25519_host_key"; then
	alpine /usr/bin/dropbearkey -t ed25519 -f /etc/dropbear/dropbear_ed25519_host_key > "$WORK/host-key-generation.txt"
fi
alpine /usr/bin/dropbearkey -y -f /etc/dropbear/dropbear_ed25519_host_key > "$WORK/host-key-public.txt"
awk '/^ssh-ed25519 / { print "172.16.42.1 " $1 " " $2 }' "$WORK/host-key-public.txt" > "$WORK/known_hosts"
test -s "$WORK/known_hosts"
if ! alpine /usr/bin/awk -F: '$1 == "root" { exit($2 !~ /^[!*]/) }' /etc/shadow; then
	alpine /usr/bin/passwd -l root
fi

sudo -n install -m 755 "$PROJECT/alpine/init" "$ROOT/init"
sudo -n install -m 755 "$PROJECT/alpine/lumia-usb" "$ROOT/usr/sbin/lumia-usb"
sudo -n install -m 755 "$PROJECT/alpine/lumia-usb.initd" "$ROOT/etc/init.d/lumia-usb"
sudo -n install -m 755 "$PROJECT/alpine/lumia-ssh.initd" "$ROOT/etc/init.d/lumia-ssh"
printf 'lumia930\n' | sudo -n tee "$ROOT/etc/hostname" > /dev/null
printf 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n' | sudo -n tee "$ROOT/etc/resolv.conf" > /dev/null
if [ "$PERSISTENCE" = 1 ]; then
	sudo -n install -d -m 755 "$ROOT/usr/lib/lumia-persist"
	for file in snapshot lumia-persist; do
		sudo -n install -m 755 "$PROJECT/alpine/persistence/$file" "$ROOT/usr/lib/lumia-persist/$file"
	done
	sudo -n install -m 755 "$PROJECT/alpine/persistence/lumia-save" "$ROOT/usr/sbin/lumia-save"
	printf 'diskless alpine on the lumia 930\nrun lumia-save to commit /etc, /root, /usr/local and package state.\nData is unmounted between saves. unsaved changes remain RAM-only.\n' | sudo -n tee "$ROOT/etc/motd" > /dev/null
else
	printf 'alpine on the lumia 930\nRAM root: files and packages reset on reboot.\nUSB SSH uses keys only. Windows remains the default boot.\n' | sudo -n tee "$ROOT/etc/motd" > /dev/null
fi
for service in devfs dmesg procfs sysfs; do alpine /sbin/rc-update add "$service" sysinit; done
for service in bootmisc hostname; do alpine /sbin/rc-update add "$service" boot; done
for service in lumia-usb lumia-ssh; do alpine /sbin/rc-update add "$service" default; done
for node in 'console 600 5 1' 'null 666 1 3'; do
	set -- $node
	if [ -L "$ROOT/dev/$1" ] || [ ! -c "$ROOT/dev/$1" ]; then
		if [ -e "$ROOT/dev/$1" ] || [ -L "$ROOT/dev/$1" ]; then
			sudo -n mv "$ROOT/dev/$1" "$WORK/dev-$1.pre-lumia"
		fi
		sudo -n mknod -m "$2" "$ROOT/dev/$1" c "$3" "$4"
	fi
done
sudo -n sh -c 'cd "$1" && find . -print0 | sort -z | cpio --null -o -H newc --owner=0:0' sh "$ROOT" > "$WORK/boot/initramfs.cpio"
gzip -n -c "$WORK/boot/initramfs.cpio" > "$WORK/boot/initramfs.cpio.gz"
python3 - "$KSRC" "$WORK/boot/zImage-dtb" <<'PY'
from pathlib import Path
import struct
import sys
src = Path(sys.argv[1])
kernel = (src / 'arch/arm/boot/zImage').read_bytes()
dtb = (src / 'arch/arm/boot/dts/qcom/qcom-msm8974-nokia-martini.dtb').read_bytes()
assert struct.unpack_from('<I', kernel, 0x24)[0] == 0x016f2818
assert struct.unpack_from('>I', dtb)[0] == 0xd00dfeed
assert dtb.count(b'nokia,lumia930-parking-v1\0') == 4
assert b'nokia,lumia930-mp-park\0' in dtb
Path(sys.argv[2]).write_bytes(kernel + dtb)
PY
CMDLINE='console=tty0 loglevel=6 consoleblank=0 maxcpus=4 cpuidle.off=1 clk_ignore_unused pd_ignore_unused rdinit=/init panic=0 log_buf_len=1M lk2nd.pass-ramoops'
mkbootimg --header_version 0 --kernel "$WORK/boot/zImage-dtb" \
	--ramdisk "$WORK/boot/initramfs.cpio.gz" --base 0x10000000 \
	--kernel_offset 0x8000 --ramdisk_offset 0x4000000 --tags_offset 0x3e00000 \
	--pagesize 2048 --cmdline "$CMDLINE" -o "$WORK/boot/boot.img"
chmod 600 "$WORK/boot/boot.img" "$WORK/boot/initramfs.cpio.gz"
sha256sum "$WORK/boot/boot.img" > "$WORK/boot/boot.img.sha256"
printf '\nbuilt %s\nRAM test only: fastboot boot %s\n' "$WORK/boot/boot.img" "$WORK/boot/boot.img"
printf 'authorized keys: %s\npinned host key file: %s\n' "${SSH_AUTHORIZED_KEYS:-$WORK/keys/id_ed25519.pub}" "$WORK/known_hosts"
if [ -z "${SSH_AUTHORIZED_KEYS:-}" ]; then
	printf 'client private key: %s\n' "$WORK/keys/id_ed25519"
fi

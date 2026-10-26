#!/bin/sh
# use a separate kernel checkout, never the preserved single-core build.
set -eu

ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
KSRC=$(CDPATH= cd "${1:?usage: $0 /path/to/patched-linux /path/to/output}" && pwd)
mkdir -p "${2:?usage: $0 /path/to/patched-linux /path/to/output}"
OUT=$(CDPATH= cd "$2" && pwd)
MAX_CPUS=${MAX_CPUS:-4}
case "$MAX_CPUS" in
2|4) ;;
*) echo 'MAX_CPUS must be 2 or 4' >&2; exit 1 ;;
esac

test -f "$KSRC/arch/arm/mach-qcom/platsmp-lumia930.c" || {
	echo 'apply kernel/0001-lumia930-uefi-parking-smp.patch first' >&2
	exit 1
}
if [ -f "$KSRC/.config" ] && [ ! -f "$KSRC/.config.pre-lumia930" ]; then
	cp -p "$KSRC/.config" "$KSRC/.config.pre-lumia930"
fi
cp "$ROOT/kernel/lumia930.config" "$KSRC/.config"
cp "$ROOT/dts/qcom-msm8974-microsoft-common.dtsi" "$ROOT/dts/qcom-msm8974-nokia-martini.dts" \
	"$KSRC/arch/arm/boot/dts/qcom/"
make -C "$KSRC" ARCH=arm LLVM=1 olddefconfig
make -C "$KSRC" ARCH=arm LLVM=1 -j"${JOBS:-$(getconf _NPROCESSORS_ONLN)}" \
	zImage qcom/qcom-msm8974-nokia-martini.dtb
(cd "$ROOT/status-screen" && sh ./build.sh "$KSRC")
cp "$ROOT/status-screen/initramfs.cpio.gz" "$OUT/initramfs.cpio.gz"
python3 - "$KSRC" "$OUT/zImage-dtb" <<'PY'
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
CMDLINE="console=tty0 loglevel=8 ignore_loglevel consoleblank=0 maxcpus=$MAX_CPUS cpuidle.off=1 clk_ignore_unused pd_ignore_unused rdinit=/init panic=0 log_buf_len=1M lk2nd.pass-ramoops"
mkbootimg --header_version 0 --kernel "$OUT/zImage-dtb" \
	--ramdisk "$OUT/initramfs.cpio.gz" --base 0x10000000 \
	--kernel_offset 0x00008000 --ramdisk_offset 0x04000000 \
	--tags_offset 0x03e00000 --pagesize 2048 --cmdline "$CMDLINE" \
	-o "$OUT/boot.img"
echo "built: $OUT/boot.img"
echo 'RAM boot only: fastboot boot boot.img; do not flash'

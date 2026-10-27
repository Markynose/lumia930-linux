#!/bin/sh
# needs clang, lld, llvm-strip and a kernel tree for the 8x16 font bitmap.
# usage: ./build.sh /path/to/linux-source-tree [/path/to/output]
set -eu

SRC=$(CDPATH= cd "$(dirname "$0")" && pwd)
KSRC=$(CDPATH= cd "${1:?usage: $0 /path/to/linux-source-tree [/path/to/output]}" && pwd)
FONT_SRC="$KSRC/lib/fonts/font_8x16.c"
[ -f "$FONT_SRC" ] || { echo "font source not found: $FONT_SRC" >&2; exit 1; }
mkdir -p "${2:-$SRC}"
OUT=$(CDPATH= cd "${2:-$SRC}" && pwd)
BUILD=$(mktemp -d "$OUT/.status-screen.XXXXXX")
trap 'rm -rf "$BUILD"' 0
trap 'exit 1' 1 2 15

cp "$SRC/init.c" "$SRC/smp-test.h" "$BUILD/"
python3 -I "$SRC/gen-font.py" "$FONT_SRC" > "$BUILD/font8x16.h"

TEST_CPPFLAGS=""
[ "${SMP_TEST:-0}" != 1 ] || TEST_CPPFLAGS="-DSMP_TEST"

clang --target=armv7-linux-gnueabihf -mcpu=krait -marm -mfloat-abi=soft $TEST_CPPFLAGS -O2 -ffreestanding -fno-builtin \
	-fno-pic -fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Wextra \
	-Wno-unused-parameter -std=gnu11 -static -nostdlib -fuse-ld=lld -Wl,-e,_start \
	-Wl,-z,norelro -Wl,--build-id=none -o "$BUILD/init" "$BUILD/init.c"

llvm-strip --strip-all -o "$BUILD/init.stripped" "$BUILD/init"
mkdir -p "$BUILD/root/dev" "$BUILD/root/proc" "$BUILD/root/sys"
cp "$BUILD/init.stripped" "$BUILD/root/init"
chmod 755 "$BUILD/root/init"
(cd "$BUILD/root" && printf 'init\n' | cpio -o -H newc --quiet) > "$BUILD/initramfs.cpio"
gzip -9 -n -c "$BUILD/initramfs.cpio" > "$BUILD/initramfs.cpio.gz"
for artifact in init init.stripped initramfs.cpio initramfs.cpio.gz; do
	mv -f "$BUILD/$artifact" "$OUT/$artifact"
done

echo "built: $OUT/initramfs.cpio.gz"

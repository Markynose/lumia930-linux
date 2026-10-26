#!/bin/sh
# builds init and the cpio initramfs. run from this directory.
# needs: clang, lld, llvm-strip, a kernel source tree (for the 8x16 font bitmap).
#
# usage: ./build.sh /path/to/linux-source-tree
set -e

KSRC="${1:?usage: $0 /path/to/linux-source-tree}"
FONT_SRC="$KSRC/lib/fonts/font_8x16.c"
[ -f "$FONT_SRC" ] || { echo "font source not found: $FONT_SRC" >&2; exit 1; }

python3 -I gen-font.py "$FONT_SRC" > font8x16.h

TEST_CPPFLAGS=""
[ "${SMP_TEST:-0}" != 1 ] || TEST_CPPFLAGS="-DSMP_TEST"

clang --target=armv7-linux-gnueabihf -mcpu=krait -marm -mfloat-abi=soft $TEST_CPPFLAGS -O2 -ffreestanding -fno-builtin \
	-fno-pic -fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Wextra \
	-Wno-unused-parameter -std=gnu11 -static -nostdlib -fuse-ld=lld -Wl,-e,_start \
	-Wl,-z,norelro -Wl,--build-id=none -o init init.c

llvm-strip --strip-all -o init.stripped init
rm -rf root && mkdir -p root/dev root/proc root/sys
cp init.stripped root/init && chmod 755 root/init
(cd root && printf 'init\n' | cpio -o -H newc --quiet) > initramfs.cpio
gzip -9 -n -c initramfs.cpio > initramfs.cpio.gz

echo "built: initramfs.cpio.gz"

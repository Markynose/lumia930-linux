#!/bin/sh
set -eu
PROJECT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LK=$(CDPATH= cd "${1:?usage: $0 /path/to/separate-lk /path/to/output}" && pwd)
mkdir -p "${2:?usage: $0 /path/to/separate-lk /path/to/output}"
OUT=$(CDPATH= cd "$2" && pwd)
PREFIX=${TOOLCHAIN_PREFIX:-arm-none-eabi-}
PATCH=$PROJECT/alpine/lk-menu.patch
if git -C "$LK" apply --check "$PATCH" 2>/dev/null; then
	[ -f "$LK/lk2nd/boot/rules.mk.pre-alpine" ] || cp -p "$LK/lk2nd/boot/rules.mk" "$LK/lk2nd/boot/rules.mk.pre-alpine"
	[ -f "$LK/lk2nd/device/menu/menu.c.pre-alpine" ] || cp -p "$LK/lk2nd/device/menu/menu.c" "$LK/lk2nd/device/menu/menu.c.pre-alpine"
	git -C "$LK" apply "$PATCH"
elif ! git -C "$LK" apply --reverse --check "$PATCH" 2>/dev/null; then
	echo 'lk integration does not match; preserve local changes and inspect first' >&2
	exit 1
fi
mkdir -p "$LK/lk2nd/boot/lumia930"
cp "$PROJECT"/alpine/lk/*.c "$PROJECT"/alpine/lk/*.h "$LK/lk2nd/boot/lumia930/"
make -C "$LK" TOOLCHAIN_PREFIX="$PREFIX" DEBUG=1 DEBUG_FBCON=1 ENABLE_DISPLAY=1 \
	LK2ND_DISPLAY=cont-splash LUMIA930_ALPINE=1 \
	LK2ND_BUNDLE_DTB=msm8974-nokia-martini.dtb lk1st-msm8974
cp "$LK/build-lk1st-msm8974/lk.bin" "$OUT/lk.bin"
printf 'PHDRS { lk PT_LOAD FLAGS(7); }\nSECTIONS { . = 0x7cc00000; .lk : { *(.data) } :lk }\n' > "$OUT/lk.ld"
(cd "$OUT" && "${PREFIX}objcopy" -I binary -O elf32-littlearm -B arm lk.bin lkbin.o && \
	"${PREFIX}ld" -T lk.ld -e 0x7cc00000 -o lk-alpine.elf lkbin.o)
python3 - "$OUT/lk-alpine.elf" "$OUT/lk.bin" <<'PY'
from pathlib import Path
import struct
import sys
elf, flat = (Path(p).read_bytes() for p in sys.argv[1:])
assert elf[:6] == b'\x7fELF\x01\x01'
assert struct.unpack_from('<H', elf, 18)[0] == 40
assert struct.unpack_from('<I', elf, 24)[0] == 0x7cc00000
phoff = struct.unpack_from('<I', elf, 28)[0]
phsize, phnum = struct.unpack_from('<HH', elf, 42)
assert phsize == 32 and phnum == 1
type_, offset, va, pa, filesz, memsz, flags, align = struct.unpack_from('<8I', elf, phoff)
assert (type_, va, pa, filesz, memsz, flags) == (1, 0x7cc00000, 0x7cc00000, len(flat), len(flat), 7)
assert len(flat) < 0x100000 and elf[offset:offset + filesz] == flat
print('ELF verified: one exact payload, correct entry, under the 1 MiB lk window')
PY
echo "built: $OUT/lk-alpine.elf; not deployed"

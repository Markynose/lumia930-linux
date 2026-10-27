#!/usr/bin/env python3
import argparse
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--boot-image', type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]
payload = args.boot_image.read_bytes() if args.boot_image else bytes((i * 17 + i // 101) & 255 for i in range(7003))


def u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def fixture(path, bits):
    with path.open('wb') as file:
        file.truncate((32 if bits == 16 else 64) * 1024 * 1024)
    subprocess.run(['mkfs.fat', '-F', str(bits), '-n', 'LUMIATEST', str(path)],
                   check=True, stdout=subprocess.DEVNULL)
    with path.open('r+b') as file:
        boot = file.read(512)
        reserved, copies = u16(boot, 14), boot[16]
        fat_sectors = u16(boot, 22) or u32(boot, 36)
        root_entries, spc = u16(boot, 17), boot[13]
        data = (reserved + copies * fat_sectors + (root_entries * 32 + 511) // 512) * 512
        cluster_bytes = spc * 512
        root = (reserved + copies * fat_sectors) * 512 if bits == 16 else data + (u32(boot, 44) - 2) * cluster_bytes
        fat_offset = reserved * 512
        file.seek(fat_offset)
        fat = bytearray(file.read(fat_sectors * 512))

        def cluster(number):
            return data + (number - 2) * cluster_bytes

        def link(number, value):
            struct.pack_into('<H' if bits == 16 else '<I', fat, number * (bits // 8), value)

        def entry(name, attr, first=0, size=0):
            item = bytearray(32)
            item[:11] = name
            item[11] = attr
            struct.pack_into('<H', item, 26, first & 65535)
            struct.pack_into('<H', item, 20, first >> 16)
            struct.pack_into('<I', item, 28, size)
            return item

        end = 0xffff if bits == 16 else 0x0fffffff
        link(3, 4)
        link(4, end)
        file.seek(root + 32)
        file.write(entry(b'ALPINE     ', 0x10, 3))
        file.seek(cluster(3))
        file.write((b'\xe5' + bytes(31)) * (cluster_bytes // 32))
        file.seek(cluster(4))
        file.write(entry(b'.          ', 0x10, 3))
        file.write(entry(b'..         ', 0x10))
        file.write(b'\xe5' + bytes(31))
        file.write(entry(b'BOOT    IMG', 0x0f))
        file_entry = cluster(4) + 128
        chain = [10 + 2 * i for i in range(math.ceil(len(payload) / cluster_bytes))]
        assert chain[-1] * (bits // 8) + bits // 8 <= len(fat)
        file.write(entry(b'BOOT    IMG', 0x20, chain[0], len(payload)))
        for i, number in enumerate(chain):
            link(number, chain[i + 1] if i + 1 < len(chain) else end)
            file.seek(cluster(number))
            file.write(payload[i * cluster_bytes:(i + 1) * cluster_bytes])
        for i in range(copies):
            file.seek(fat_offset + i * len(fat))
            file.write(fat)
    return dict(fat=fat_offset, fat_bytes=len(fat), file=file_entry,
                folder=root + 32, bits=bits, copies=copies, first=chain[0])


with tempfile.TemporaryDirectory(prefix='lumia-fat-test-') as tmp:
    work = Path(tmp)
    runner = work / 'fat-runner'
    subprocess.run([os.environ.get('CC', 'clang'), '-std=c11', '-Wall', '-Wextra',
                    '-Wconversion', '-Werror', '-g', '-fsanitize=address,undefined',
                    '-I', str(source / 'lk'), str(source / 'tests/fat-runner.c'),
                    str(source / 'lk/fat-ro.c'), '-o', str(runner)], check=True)
    reference = work / 'payload'
    reference.write_bytes(payload)
    count = 0
    for bits in (16, 32):
        image = work / f'fat{bits}.img'
        meta = fixture(image, bits)

        def test(name, success, changes=(), path='/alpine/boot.img', io=None):
            global count
            arguments = [str(runner), str(image), str(reference), path, 'pass' if success else 'fail']
            arguments.extend(f'{offset:x}:{value:x}' for offset, value in changes)
            if io is not None:
                arguments.append(f'io={io}')
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, f'fat{bits} {name}: {result.stderr}'
            count += 1

        def field(offset, value, width):
            return [(offset + i, byte) for i, byte in enumerate(value.to_bytes(width, 'little'))]

        test('fragmented file and chained directory', True)
        test('uppercase', True, path='ALPINE/BOOT.IMG')
        for path in ('/missing/boot.img', '/alpine/missing.img', '/alpine/../boot.img',
                     '/alpine//boot.img', '/alpine/boot.img/x', '/alpine',
                     '/alpine/boot.long', '/alpine/boot.', '/alpine/bo?t.img', ''):
            test('bad path ' + path, False, path=path)
        for name, offset, value, width in (
            ('signature', 510, 0, 2), ('sector size', 11, 4096, 2),
            ('zero cluster size', 13, 0, 1), ('bad cluster size', 13, 3, 1),
            ('oversized cluster', 13, 255, 1), ('zero reserved', 14, 0, 2),
            ('zero FAT copies', 16, 0, 1), ('too many FAT copies', 16, 3, 1),
            ('huge total', 32, 0xffffffff, 4),
            ('wrong object type', meta['file'] + 11, 0x10, 1),
            ('volume label', meta['file'] + 11, 8, 1),
            ('oversized file', meta['file'] + 28, len(payload) + 1, 4),
            ('invalid initial cluster', meta['file'] + 26, 1, 2),
            ('reserved initial cluster', meta['file'] + 26, 0xfff0, 2),
            ('file as parent', meta['folder'] + 11, 0x20, 1),
            ('only LFN matches', meta['file'], ord('X'), 1),
        ):
            test(name, False, field(offset, value, width))
        for name, value in (('free', 0), ('bad', 0xfff7 if bits == 16 else 0x0ffffff7),
                            ('premature end', 0xffff if bits == 16 else 0x0fffffff),
                            ('file cycle', meta['first'])):
            offset = meta['fat'] + meta['first'] * (bits // 8)
            test(name, False, field(offset, value, bits // 8))
        test('directory cycle', False, field(meta['fat'] + 3 * (bits // 8), 3, bits // 8))
        for after in (0, 1, 2, 5, 10):
            test('read failure', False, io=after)
        if bits == 32:
            test('active FAT 1', True, field(40, 0x81, 2))
            test('inactive FAT ignored', True, field(40, 0x81, 2) + field(meta['fat'] + meta['first'] * 4, 0, 4))
            test('invalid active FAT', False, field(40, 0x82, 2))
            test('unknown FAT version', False, field(42, 1, 2))
            test('invalid root', False, field(44, 1, 4))
            test('tiny FAT', False, field(36, 1, 4))
        else:
            test('missing fixed root', False, field(17, 0, 2))
            test('tiny FAT', False, field(22, 1, 2))
    print(f'{count} FAT16/FAT32 cases passed under ASan/UBSan; payload {len(payload)} bytes')

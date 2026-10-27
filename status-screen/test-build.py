#!/usr/bin/env python3
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent
kernel = Path(sys.argv[1]).resolve()
artifacts = ('font8x16.h', 'init', 'init.stripped', 'initramfs.cpio', 'initramfs.cpio.gz')


def source_hashes():
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in artifacts if (root / name).is_file()}


before = source_hashes()
with tempfile.TemporaryDirectory(prefix='lumia930-parallel-build-') as tmp:
    work = Path(tmp)
    jobs = []
    for index, diagnostic in enumerate((False, True, False, True)):
        out = work / str(index)
        env = dict(os.environ, SMP_TEST=str(int(diagnostic)))
        log = (work / f'{index}.log').open('w')
        process = subprocess.Popen(['sh', str(root / 'build.sh'), str(kernel), str(out)],
                                   cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
        jobs.append((process, log, out, diagnostic))
    failed = []
    for process, log, out, diagnostic in jobs:
        result = process.wait(timeout=90)
        log.close()
        if result:
            failed.append((out.name, result))
    assert not failed, failed
    for process, log, out, diagnostic in jobs:
        packed = gzip.decompress((out / 'initramfs.cpio.gz').read_bytes())
        assert packed == (out / 'initramfs.cpio').read_bytes()
        assert packed[:6] == b'070701'
        size = int(packed[54:62], 16)
        name_size = int(packed[94:102], 16)
        assert packed[110:110 + name_size] == b'init\0'
        start = (110 + name_size + 3) & ~3
        binary = (out / 'init.stripped').read_bytes()
        assert packed[start:start + size] == binary
        assert (b'lumia930 SMP validation\n' in binary) == diagnostic
        assert not list(out.glob('.status-screen.*'))
    assert source_hashes() == before
print('four concurrent ARM builds passed: private outputs, correct normal/SMP payloads, no shared artifacts changed')

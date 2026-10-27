#!/usr/bin/env python3
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root = Path(sys.argv[1]).resolve()
assert os.geteuid() == 0, 'run as root for the private QEMU chroot'
source = root / 'tmp/snapshot-app'
assert source.is_dir()
helper = '/usr/lib/lumia-persist/snapshot'

def run(command, success=True):
    result = subprocess.run(['env', 'QEMU_CPU=cortex-a15', 'chroot', str(root),
                             *command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert (result.returncode == 0) == success, result.stdout.decode(errors='replace')

def checksum():
    run(['/bin/sh','-c','cd /tmp/invalid-snapshot && sha256sum config.tar.gz installed.txt world packages/*.apk > SHA256SUMS'])

candidate = root / 'tmp/invalid-snapshot'
cases = ['changed-world','missing-world','missing-packages','package-symlink',
         'config-symlink','bad-name','bad-tar','traversal','nested-traversal',
         'outside-path','unsigned-package']
for case in cases:
    shutil.rmtree(candidate, ignore_errors=True)
    shutil.copytree(source,candidate)
    if case == 'changed-world':
        (candidate/'world').write_text('changed\n')
    elif case == 'missing-world':
        (candidate/'world').unlink()
    elif case == 'missing-packages':
        shutil.rmtree(candidate/'packages')
    elif case == 'package-symlink':
        file=next((candidate/'packages').glob('*.apk'))
        file.unlink(); file.symlink_to('/bin/busybox')
    elif case == 'config-symlink':
        (candidate/'config.tar.gz').unlink()
        (candidate/'config.tar.gz').symlink_to('/etc/shadow')
    elif case == 'bad-name':
        shutil.copyfile(next((candidate/'packages').glob('*.apk')),candidate/'packages/bad name.apk')
    elif case == 'bad-tar':
        (candidate/'config.tar.gz').write_bytes(b'not a gzip archive')
        checksum()
    elif case in ('traversal','nested-traversal','outside-path'):
        name={'traversal':'../escape','nested-traversal':'etc/../escape','outside-path':'bin/sh'}[case]
        with tarfile.open(candidate/'config.tar.gz','w:gz') as tar:
            entry=tarfile.TarInfo(name); entry.size=4
            tar.addfile(entry,io.BytesIO(b'bad\n'))
        checksum()
    elif case == 'unsigned-package':
        next((candidate/'packages').glob('*.apk')).write_bytes(b'invalid package')
        checksum()
    run([helper,'apply' if case=='unsigned-package' else 'verify','/tmp/invalid-snapshot'],False)
    print(case + ': rejected')
shutil.rmtree(candidate)
run([helper,'verify','/tmp/snapshot-app'])
print('valid snapshot accepted; eleven corrupt/unsafe snapshot cases rejected')

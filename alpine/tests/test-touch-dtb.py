#!/usr/bin/env python3
"""compare pre-touch and pull-up DTBs without changing the kernel checkout."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def decode(data):
    magic, total, off, strings, reserve, _, _, cpu, _, size = struct.unpack_from('>10I', data)
    assert magic == 0xd00dfeed and total == len(data)
    end = off + size
    stack = []
    nodes = {}
    while off < end:
        token = struct.unpack_from('>I', data, off)[0]
        off += 4
        if token == 1:
            stop = data.index(b'\0', off)
            stack.append(data[off:stop].decode())
            off = (stop + 4) & ~3
            nodes['/' + '/'.join(stack).strip('/')] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            count, nameoff = struct.unpack_from('>II', data, off)
            off += 8
            start = strings + nameoff
            name = data[start:data.index(b'\0', start)].decode()
            nodes['/' + '/'.join(stack).strip('/')][name] = data[off:off + count]
            off = (off + count + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            break
        else:
            raise AssertionError(f'unexpected FDT token {token}')
    reservations = []
    while True:
        entry = struct.unpack_from('>QQ', data, reserve)
        reservations.append(entry)
        reserve += 16
        if entry == (0, 0):
            break
    return nodes, reservations, cpu


def compare(before, after):
    old, reservations, cpu = decode(before)
    new, new_reservations, new_cpu = decode(after)
    assert reservations == new_reservations and cpu == new_cpu
    fixed = struct.pack('>I', 0x10000)
    assert all(p.get('phandle') != fixed for p in old.values())
    touch = [path for path, p in old.items()
             if p.get('compatible') == b'syna,rmi4-i2c\0']
    assert len(touch) == 1
    touch = touch[0]
    parent = old[touch]['interrupt-parent']
    tlmm = [path for path, p in old.items() if p.get('phandle') == parent]
    assert len(tlmm) == 1
    pin = tlmm[0] + '/touch-irq-state'
    assert set(new) == set(old) | {pin}
    for path, props in old.items():
        expected = dict(props)
        if path == touch:
            expected.update({'pinctrl-names': b'default\0', 'pinctrl-0': fixed})
        assert new[path] == expected, f'unexpected property change in {path}'
    assert new[pin] == {'phandle': fixed, 'pins': b'gpio61\0',
                        'function': b'gpio\0', 'bias-pull-up': b'', 'input-enable': b''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('baseline_dts', type=Path)
    parser.add_argument('--baseline-dtb', type=Path)
    parser.add_argument('--expected-dtb', type=Path)
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    include = kernel / 'scripts/dtc/include-prefixes'
    with tempfile.TemporaryDirectory(prefix='lumia-touch-') as name:
        tmp = Path(name)
        shutil.copyfile(kernel / 'arch/arm/boot/dts/qcom/qcom-msm8974-microsoft-common.dtsi',
                        tmp / 'qcom-msm8974-microsoft-common.dtsi')
        output = []
        for label, source in [('before', args.baseline_dts),
                              ('after', ROOT / 'dts/qcom-msm8974-nokia-martini.dts')]:
            dts = tmp / (label + '.dts')
            cpp = tmp / (label + '.preprocessed.dts')
            dtb = tmp / (label + '.dtb')
            shutil.copyfile(source, dts)
            subprocess.run(['clang', '-E', '-P', '-nostdinc', '-undef', '-D__DTS__',
                            '-x', 'assembler-with-cpp', '-I', str(include),
                            '-I', str(kernel / 'arch/arm/boot/dts/qcom'),
                            str(dts), '-o', str(cpp)], check=True)
            subprocess.run([str(kernel / 'scripts/dtc/dtc'), '-o', str(dtb), '-b', '0',
                            '-Wno-unique_unit_address', '-Wno-unit_address_vs_reg',
                            '-Wno-avoid_unnecessary_addr_size', '-Wno-alias_paths',
                            '-Wno-graph_child_address', '-Wno-simple_bus_reg', str(cpp)],
                           check=True)
            output.append(dtb.read_bytes())
        compare(*output)
        if args.baseline_dtb:
            assert output[0] == args.baseline_dtb.read_bytes(), 'baseline binary differs'
        if args.expected_dtb:
            assert output[1] == args.expected_dtb.read_bytes(), 'tested binary differs'
    print('touch DTB: only GPIO61 input/pull-up group and touch references added;')
    print('all other properties, phandles and reserved memory unchanged')


if __name__ == '__main__':
    main()

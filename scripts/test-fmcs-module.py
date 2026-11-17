#!/usr/bin/env python3
"""Check real stripped FMCS registration and mutate actual ELF fields, not guessed offsets."""
import argparse
from pathlib import Path
import struct
from verify_fmcs_module import Elf64, verify_port_count


def test(data):
    result = verify_port_count(data)
    elf = Elf64(data)
    param = elf.by_name['__param']
    start = result['record_offset']
    name = elf.pointer(param['index'], start)
    ops = elf.pointer(param['index'], start + 16)
    argument = elf.pointer(param['index'], start + 32)

    def location(pointer):
        return elf.sections[pointer['section']]['offset'] + pointer['offset']

    def rel_location(section, offset):
        found = []
        for sec in elf.sections:
            if sec['type'] == 4 and sec['info'] == section:
                for pos in range(sec['offset'], sec['offset'] + sec['size'], 24):
                    if struct.unpack_from('<Q', data, pos)[0] == offset:
                        found.append(pos)
        assert len(found) == 1, (section, offset, found)
        return found[0]

    checks = 0

    def reject(label, blob, fragment):
        nonlocal checks
        assert blob != data, label + ': mutation did not change the input'
        try:
            verify_port_count(blob)
        except ValueError as exc:
            assert fragment in str(exc), (label, str(exc))
            print('PASS reject ' + label)
            checks += 1
        else:
            raise AssertionError(label + ': corrupted registration accepted')

    print('PASS actual stripped module:', result)
    # An unrelated global must not cause rejection: the old test changed one.
    unrelated = bytearray(data)
    text = elf.by_name['.text']
    unrelated[text['offset']] ^= 1
    assert verify_port_count(unrelated) == result
    print('PASS unrelated bytes do not impersonate the port_count field')

    b = bytearray(data)
    struct.pack_into('<I', b, location(argument), 17)
    reject('invalid default at resolved argument', b, 'legacy default 16')

    b = bytearray(data)
    b[location(name)] = ord('x')
    reject('renamed real parameter', b, 'one real port_count')

    b = bytearray(data)
    struct.pack_into('<H', b, param['offset'] + start + 24, 0o644)
    reject('writable port_count', b, 'read-only 0444')

    b = bytearray(data)
    struct.pack_into('<b', b, param['offset'] + start + 26, 0)
    reject('wrong load-time level', b, 'load-time')

    b = bytearray(data)
    b[param['offset'] + start + 27] = 1
    reject('unsafe flag', b, 'safe parameter')

    b = bytearray(data)
    arg_rel = rel_location(param['index'], start + 32)
    old_info = struct.unpack_from('<Q', b, arg_rel + 8)[0]
    struct.pack_into('<Q', b, arg_rel + 8, old_info & ~0xffffffff)
    reject('removed argument relocation', b, 'ABS64 parameter pointer missing')

    b = bytearray(data)
    struct.pack_into('<q', b, arg_rel + 16, 1 << 40)
    reject('argument outside section', b, 'outside target section')

    b = bytearray(data)
    owner_rel = rel_location(param['index'], start + 8)
    struct.pack_into('<q', b, owner_rel + 16, 1)
    reject('wrong module owner', b, 'owner does not reference')

    b = bytearray(data)
    getter_rel = rel_location(ops['section'], ops['offset'] + 16)
    struct.pack_into('<q', b, getter_rel + 16, 4)
    reject('wrong uint getter', b, 'getter must be param_get_uint')

    b = bytearray(data)
    setter_rel = rel_location(ops['section'], ops['offset'] + 8)
    # Replace the local setter relocation with the external getter.
    b[setter_rel + 8:setter_rel + 24] = data[getter_rel + 8:getter_rel + 24]
    reject('external rather than checked setter', b, 'setter is not module executable')

    b = bytearray(data)
    struct.pack_into('<I', b, location(ops), 1)
    reject('unexpected no-argument ops flag', b, 'ops structure')

    b = bytearray(data)
    b[location(ops) + 24] = 1
    reject('unexpected free callback', b, 'free callback')

    b = bytearray(data)
    sec_name = elf.by_name['.shstrtab']['offset'] + param['name_offset']
    b[sec_name] = ord('x')
    # Fake metadata strings must never substitute for the real parameter table.
    b.extend(b'parmtype=port_count:uint\0parm=port_count:fake\0')
    reject('metadata-only impostor without __param', b, 'registration table')

    b = data[:40]
    reject('truncated ELF', b, 'ELF64')
    b = bytearray(data)
    struct.pack_into('<Q', b, 40, len(data))
    reject('section table outside file', b, 'outside file bounds')
    print(f'PASS {checks} negative cases and real positive/control cases')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path)
    args = parser.parse_args()
    test(args.module.read_bytes())

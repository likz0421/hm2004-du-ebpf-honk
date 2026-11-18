#!/usr/bin/env python3
"""Inspect the actual arm64 kernel parameter registration, including stripped modules.

Linux module_param_cb does not emit parmtype. CONFIG_MODULE_STRIPPED also
removes MODULE_PARM_DESC. Neither .modinfo string proves runtime registration;
follow __param RELA pointers to the name, ops and argument instead.
"""
from pathlib import Path
import io
import struct


class Elf64:
    def __init__(self, data):
        self.data = data
        if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
            raise ValueError('FMCS: expected little-endian ELF64')
        header = self.unpack('<HHIQQQIHHHHHH', 16)
        etype, machine = header[:2]
        if etype != 1 or machine != 183:
            raise ValueError('FMCS: expected AArch64 relocatable kernel module')
        shoff, shsize, count, shstr = header[5], header[10], header[11], header[12]
        if shsize != 64 or not count or shstr >= count:
            raise ValueError('FMCS: unsupported or invalid section table')
        self.sections = []
        for index in range(count):
            values = self.unpack('<IIQQQQIIQQ', shoff + index * shsize)
            sec = dict(zip(('name_offset', 'type', 'flags', 'addr', 'offset', 'size',
                            'link', 'info', 'align', 'entsize'), values))
            sec['index'] = index
            self.sections.append(sec)
        names = self.section_data(shstr)
        for sec in self.sections:
            sec['name'] = self.string(names, sec['name_offset'])
        self.by_name = {s['name']: s for s in self.sections}
        self.symbols = {}
        for sec in self.sections:
            if sec['type'] != 2:
                continue
            if sec['entsize'] != 24 or sec['size'] % 24:
                raise ValueError('FMCS: malformed symbol table')
            strings = self.section_data(sec['link'])
            symbols = []
            for offset in range(sec['offset'], sec['offset'] + sec['size'], 24):
                name, info, other, section, value, size = self.unpack('<IBBHQQ', offset)
                symbols.append(dict(name=self.string(strings, name), section=section,
                                    value=value, size=size, info=info))
            self.symbols[sec['index']] = symbols
        self.relocations = {}
        for sec in self.sections:
            if sec['type'] != 4:
                continue
            if sec['entsize'] != 24 or sec['size'] % 24 or sec['info'] >= count:
                raise ValueError('FMCS: malformed RELA table')
            symbols = self.symbols.get(sec['link'])
            if symbols is None:
                raise ValueError('FMCS: RELA has no linked symbol table')
            for offset in range(sec['offset'], sec['offset'] + sec['size'], 24):
                location, info, addend = self.unpack('<QQq', offset)
                symbol = info >> 32
                if symbol >= len(symbols):
                    raise ValueError('FMCS: invalid relocation symbol')
                key = (sec['info'], location)
                if key in self.relocations:
                    raise ValueError('FMCS: duplicate relocation at pointer')
                self.relocations[key] = dict(type=info & 0xffffffff,
                                            symbol=symbols[symbol], addend=addend)

    def unpack(self, fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(self.data):
            raise ValueError('FMCS: ELF structure outside file bounds')
        return struct.unpack_from(fmt, self.data, offset)

    def section_data(self, index):
        if not 0 <= index < len(self.sections):
            raise ValueError('FMCS: invalid section reference')
        sec = self.sections[index]
        if sec['type'] == 8:
            return b'\0' * sec['size']
        start, end = sec['offset'], sec['offset'] + sec['size']
        if end > len(self.data):
            raise ValueError('FMCS: ELF section outside file bounds')
        return self.data[start:end]

    @staticmethod
    def string(data, offset):
        if not 0 <= offset < len(data):
            raise ValueError('FMCS: string offset outside section')
        end = data.find(b'\0', offset)
        if end < 0:
            raise ValueError('FMCS: unterminated ELF string')
        return data[offset:end].decode('ascii')

    def pointer(self, section, offset):
        rel = self.relocations.get((section, offset))
        if rel is None or rel['type'] != 257:  # R_AARCH64_ABS64
            raise ValueError('FMCS: required ABS64 parameter pointer missing')
        sym = rel['symbol']
        if not sym['section']:
            return dict(external=sym['name'], addend=rel['addend'])
        index = sym['section']
        if index >= len(self.sections):
            raise ValueError('FMCS: pointer references invalid section')
        # ET_REL st_value and RELA addends are section-relative offsets.
        target = sym['value'] + rel['addend']
        if not 0 <= target < self.sections[index]['size']:
            raise ValueError('FMCS: pointer outside target section')
        return dict(section=index, offset=target)


def verify_port_count(data):
    elf = Elf64(data)
    param = elf.by_name.get('__param')
    if param is None or not param['size'] or param['size'] % 40:
        raise ValueError('FMCS: missing or invalid arm64 __param registration table')
    records = []
    for start in range(0, param['size'], 40):
        pointer = elf.pointer(param['index'], start)
        if 'external' in pointer:
            raise ValueError('FMCS: parameter name is not stored in module')
        name = elf.string(elf.section_data(pointer['section']), pointer['offset'])
        if name == 'port_count':
            records.append(start)
    if len(records) != 1:
        raise ValueError('FMCS: expected one real port_count registration')
    start = records[0]
    perm, level, flags = struct.unpack_from('<HbB', elf.section_data(param['index']), start + 24)
    if (perm, level, flags) != (0o444, -1, 0):
        raise ValueError('FMCS: port_count must be load-time, read-only 0444, safe parameter')
    owner = elf.pointer(param['index'], start + 8)
    if owner.get('external'):
        raise ValueError('FMCS: parameter owner is not this module')
    if elf.sections[owner['section']]['name'] != '.gnu.linkonce.this_module' or owner['offset']:
        raise ValueError('FMCS: parameter owner does not reference this module')
    ops = elf.pointer(param['index'], start + 16)
    if 'external' in ops:
        raise ValueError('FMCS: port_count requires its custom checked setter ops')
    ops_data = elf.section_data(ops['section'])
    op_start = ops['offset']
    if op_start + 32 > len(ops_data) or struct.unpack_from('<I', ops_data, op_start)[0]:
        raise ValueError('FMCS: invalid port_count ops structure')
    setter = elf.pointer(ops['section'], op_start + 8)
    getter = elf.pointer(ops['section'], op_start + 16)
    if 'external' in setter or not elf.sections[setter['section']]['flags'] & 4:
        raise ValueError('FMCS: port_count setter is not module executable code')
    if getter != dict(external='param_get_uint', addend=0):
        raise ValueError('FMCS: port_count getter must be param_get_uint')
    if (ops['section'], op_start + 24) in elf.relocations or any(ops_data[op_start + 24:op_start + 32]):
        raise ValueError('FMCS: unexpected port_count free callback')
    argument = elf.pointer(param['index'], start + 32)
    if 'external' in argument or not elf.sections[argument['section']]['flags'] & 1:
        raise ValueError('FMCS: port_count storage must be module writable data')
    arg_data = elf.section_data(argument['section'])
    if argument['offset'] + 4 > len(arg_data) or struct.unpack_from('<I', arg_data, argument['offset'])[0] != 16:
        raise ValueError('FMCS: expected unsigned int port_count legacy default 16')
    return dict(name='port_count', permission='0444', load_time=True,
                getter='param_get_uint', custom_setter=True, default=16,
                record_offset=start,
                setter_section=elf.sections[setter['section']]['name'],
                setter_offset=setter['offset'])


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path, help='uncompressed arm64 h3c-fmcs.ko')
    args = parser.parse_args()
    print(json.dumps(verify_port_count(args.module.read_bytes()), indent=2))

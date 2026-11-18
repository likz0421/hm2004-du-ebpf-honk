#!/usr/bin/env python3
"""Compare built HM2004 FIT/manifest with released v29; not a hardware boot test."""
import hashlib
import json
from pathlib import Path
import subprocess

BASELINE = Path(__file__).with_name('fixtures') / 'v29-baseline.json'
ALLOWED_PACKAGES = {'openwrt-fttr', 'luci-app-fttr', 'luci-i18n-fttr-zh-cn', 'kmod-h3c-fmcs'}


def verify_baseline(image, installed, temporary):
    reference = json.loads(BASELINE.read_text())
    expected = reference['packages']
    actual = {k: v for k, v in installed.items() if k not in ALLOWED_PACKAGES}
    frozen = {k: v for k, v in expected.items() if k not in ALLOWED_PACKAGES}
    if actual != frozen:
        changes = {k: {'v29': frozen.get(k), 'candidate': actual.get(k)}
                   for k in sorted(set(actual) | set(frozen)) if frozen.get(k) != actual.get(k)}
        raise ValueError('Non-FTTR manifest drift: ' + json.dumps(changes, sort_keys=True))
    dtb = temporary / 'v29-board-check.dtb'
    subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', '1', '-o', str(dtb), str(image)],
                   check=True, stdout=subprocess.DEVNULL)
    digest = hashlib.sha256(dtb.read_bytes()).hexdigest()
    if digest != reference['dtb_sha256']:
        raise ValueError(f'HM2004 device tree changed from v29: {digest}')
    for field in ['load', 'entry']:
        value = subprocess.check_output(['fdtget', '-t', 'x', str(image),
                                          '/images/kernel-1', field], text=True).strip()
        if value != '8a000000':
            raise ValueError(f'Kernel {field} differs from v29: {value}')
    compression = subprocess.check_output(['fdtget', '-t', 's', str(image),
                                           '/images/kernel-1', 'compression'], text=True).strip()
    if compression != 'gzip':
        raise ValueError(f'Kernel compression differs from v29: {compression}')
    print(f'PASS v29 DTB, kernel package/ABI, FIT addresses and {len(frozen)} non-FTTR package versions unchanged', flush=True)
    return {'reference_tag': 'v2026.11.29', 'reference_image_sha256': reference['image_sha256'],
            'dtb_sha256': digest, 'kernel': installed['kernel'],
            'non_fttr_packages_unchanged': len(frozen), 'hardware_boot_tested': False}

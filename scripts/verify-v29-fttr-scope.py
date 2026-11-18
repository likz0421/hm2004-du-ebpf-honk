#!/usr/bin/env python3
"""Reject any non-FTTR source drift from the fixed v2026.11.29 baseline."""
import copy
import json
from pathlib import Path
import subprocess

BASE = 'c9f015395cab41309066ddf501acea457c382cb4'
ROOT = Path(__file__).resolve().parents[1]
FTTR_SOURCES = {'fttr-backend', 'fttr-frontend'}
FTTR_PACKAGES = {'openwrt-fttr', 'luci-app-fttr', 'kmod-h3c-fmcs'}


def baseline(path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASE}:{path}'])


def validate_lock(original, current):
    current = copy.deepcopy(current)
    original = copy.deepcopy(original)
    current.pop('checked_at', None); original.pop('checked_at', None)
    for source in FTTR_SOURCES:
        current['sources'].pop(source); original['sources'].pop(source)
    for package in FTTR_PACKAGES:
        current['expected']['packages'].pop(package, None)
        original['expected']['packages'].pop(package, None)
    current['expected'].pop('fttr_assets_sha256', None)
    assert current == original, 'Non-FTTR source/feed/archive/default/capability lock changed'


def main():
    validate_lock(json.loads(baseline('configs/plugins.lock.json')),
                  json.loads((ROOT/'configs/plugins.lock.json').read_text()))
    # These files may alter hardware, package selection, or first-boot defaults.
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', '-r', '--name-only', BASE,
                                    'configs', 'files', 'onu', 'patches/plugins'], text=True).splitlines()
    paths += ['diy-part1.sh', 'diy-part2.sh', 'scripts/diy-part2-crypto.sh',
              'scripts/pin-feeds.py', 'scripts/plugin-lock.py', 'scripts/update-plugin-packages.py']
    for path in paths:
        if path == 'configs/plugins.lock.json':
            continue
        old = baseline(path)
        assert (ROOT/path).read_bytes() == old, f'Non-FTTR baseline file changed: {path}'
    print(f'PASS: v29 base/kernel/DTS/PON/WiFi/feeds/ONU/defaults frozen; only FTTR pins changed ({len(paths)} protected files)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Reject drift between the driver gate and the full HM2004 firmware sources."""
import json
from pathlib import Path


def validate(root):
    gate = json.loads((root / 'configs/stable-kernel.lock.json').read_text())
    full = json.loads((root / 'configs/plugins.lock.json').read_text())
    def canonical(url):
        return url.removesuffix('.git').rstrip('/')
    pairs = [
        ('base', gate['base'], full['build_base']),
        ('PON drivers', gate['pon_drivers'], full['feeds']['pon_drivers']),
        ('FTTR backend', gate['fttr'], dict(full['sources']['fttr-backend'],
            url='https://github.com/' + full['sources']['fttr-backend']['repo'])),
    ]
    for name, left, right in pairs:
        for field in ('url', 'branch', 'commit'):
            a, b = left[field], right[field]
            if field == 'url':
                a, b = canonical(a), canonical(b)
            if a != b:
                raise ValueError(f'{name} {field} differs between gate and full build: {a} != {b}')
        print(f'{name}: {left["commit"]}')
    if gate['base']['official_commit'] != full['build_base']['official_commit']:
        raise ValueError('Official stable source revisions differ')
    feed_path = root / 'configs/hm2004-stable.feeds.conf'
    seen = set()
    for line in feed_path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        kind, name, url = line.split()
        if kind != 'src-git' or name in seen:
            raise ValueError(f'Unexpected or duplicate stable feed: {line}')
        if canonical(url) != canonical(full['feeds'][name]['url']):
            raise ValueError(f'{name}: feed URL differs from source lock')
        seen.add(name)
    required = set(full['feeds']) - {'honk'}  # honk-feeds.sh inserts its locked feed.
    if seen != required:
        raise ValueError(f'Stable feed set differs: {sorted(seen ^ required)}')
    print('PASS: stable base, FTTR backend, PON drivers and feed sources agree')


if __name__ == '__main__':
    validate(Path(__file__).resolve().parents[1])

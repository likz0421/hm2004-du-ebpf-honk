#!/usr/bin/env python3
"""Pin the feed to its audited commit and verify feed package source revisions."""
import json
from pathlib import Path
import re
import sys

lock = json.loads((Path(__file__).resolve().parents[1] / "configs/plugins.lock.json").read_text())
feed_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("feeds.conf.default")
verify = "--verify" in sys.argv
text = feed_file.read_text()
lines = text.splitlines()
seen = set()
result = []
for line in lines:
    match = re.match(r"^(\s*src-git\s+)(\S+)(\s+)(\S+)(.*)$", line)
    if not match:
        result.append(line)
        continue
    prefix, name, space, url, suffix = match.groups()
    if name not in lock["feeds"]:
        raise SystemExit(f"Unlocked active git feed: {name}. Refusing an unpinned build.")
    spec = lock["feeds"][name]
    expected = f"{spec['url']}^{spec['commit']}"
    if verify:
        if url != expected:
            raise SystemExit(f"Feed {name} not pinned to audited SHA {spec['commit']}: {url}")
        result.append(line)
    else:
        if url not in (spec["url"], expected):
            raise SystemExit(f"Feed URL changed for {name}: {url} != {spec['url']}")
        result.append(f"{prefix}{name}{space}{expected}{suffix}")
    seen.add(name)
missing = set(lock["feeds"]) - seen
if missing:
    raise SystemExit("Pinned feed not configured: " + ", ".join(sorted(missing)))
if not verify:
    feed_file.write_text("\n".join(result) + "\n")
for name in sorted(seen):
    print(f"Verified feed {name}: {lock['feeds'][name]['commit']}")

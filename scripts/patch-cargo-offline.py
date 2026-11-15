#!/usr/bin/env python3
"""Relax cargo offline flags only in build recipes, preserving Cargo.lock."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
p = subprocess.run(["rg", "--files", "--hidden", "-L", "-g", "Makefile", "-g", "*.mk", "-g", "!.git/**", "package", "feeds"], cwd=root, capture_output=True, text=True, check=True)
seen = set()
changed = 0
for name in p.stdout.splitlines():
    file = (root / name).resolve()
    if file in seen or any(x in file.parts for x in ("build_dir", "staging_dir", ".git")):
        continue
    seen.add(file)
    before = file.read_text()
    after = re.sub(r"--(?:frozen|offline)\b", "", before)
    # --frozen also supplies --locked in Cargo. Preserve lockfile determinism.
    if "--frozen" in before and "--locked" not in after:
        after = re.sub(r"((?:CARGO_PKG_ARGS\s*\+?=)[^\n]*)", r"\1 --locked", after, count=1)
    if after != before:
        file.write_text(after)
        print("Relaxed build recipe:", file.relative_to(root))
        changed += 1
print(f"Build recipes changed: {changed}; Rust and frontend source files untouched")

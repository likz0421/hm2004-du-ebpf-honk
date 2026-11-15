#!/usr/bin/env python3
"""Resolve and verify audited plugin source revisions. Never handles credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = REPO_ROOT / "configs/plugins.lock.json"


def lock_data():
    return json.loads(LOCK_PATH.read_text())


def git(directory, *args):
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True).strip()


def checkout(name, directory):
    spec = lock_data()["sources"][name]
    directory = Path(directory)
    # A failed fetch is fatal. Never silently fall back to a moving branch HEAD.
    subprocess.run(["git", "-C", str(directory), "fetch", "--depth", "1", "origin", spec["commit"]], check=True)
    subprocess.run(["git", "-C", str(directory), "checkout", "--detach", spec["commit"]], check=True)
    actual = git(directory, "rev-parse", "HEAD")
    if actual != spec["commit"]:
        raise ValueError(f"{name}: unexpected revision {actual}")
    if name == "fttr-frontend":
        readme = (directory / "README.md").read_text()
        if spec["source_commit"] not in readme:
            raise ValueError("FTTR package does not originate from the audited frontend source")
    print(f"Pinned {name}: {actual}", flush=True)

def manifest_data(openwrt):
    data = lock_data()
    data["build_source"] = git(openwrt, "rev-parse", "HEAD")
    data["build_repo"] = git(REPO_ROOT, "rev-parse", "HEAD")
    return data


def write_manifest(openwrt, output=None):
    data = manifest_data(openwrt)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"Wrote plugin provenance: {output}")
        return
    path = Path(openwrt) / "files/etc/firmware-plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote plugin provenance: {path}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("get")
    q.add_argument("key")
    q = sub.add_parser("checkout")
    q.add_argument("name")
    q.add_argument("directory")
    q = sub.add_parser("manifest")
    q.add_argument("openwrt")
    q.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.command == "get":
        value = lock_data()
        for part in args.key.split("."):
            value = value[part]
        print(value if isinstance(value, (str, int)) else json.dumps(value))
    elif args.command == "checkout":
        checkout(args.name, args.directory)
    else:
        write_manifest(args.openwrt, args.output)


if __name__ == "__main__":
    main()

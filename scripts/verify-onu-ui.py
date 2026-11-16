#!/usr/bin/env python3
"""Validate the frontend-only ONU port before it enters package/custom."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
root = (args.source / "onu/luci-app-onu").resolve()
if not root.is_dir():
    raise SystemExit(f"ONU UI source missing: {root}")
required = [
    "Makefile", "README.md", "UPSTREAM.json",
    "htdocs/luci-static/resources/onu-dashboard/data.js",
    "htdocs/luci-static/resources/onu-dashboard/components.js",
    "htdocs/luci-static/resources/view/onu-dashboard/overview.js",
    "htdocs/luci-static/resources/view/onu-dashboard/status.js",
    "htdocs/luci-static/resources/view/onu-dashboard/hardware.js",
    "htdocs/luci-static/resources/view/onu-dashboard/diagnostics.js",
    "htdocs/luci-static/resources/view/onu-dashboard/dashboard.css",
    "htdocs/luci-static/resources/view/onu-dashboard/onu.css",
    "po/zh_Hans/onu.po",
    "root/usr/share/luci/menu.d/luci-app-onu.json",
    "root/usr/share/rpcd/acl.d/luci-app-onu.json",
]
missing = [name for name in required if not (root / name).is_file()
           or (root / name).stat().st_size == 0]
if missing:
    raise SystemExit("ONU UI files missing or empty: " + ", ".join(missing))
for forbidden in ["root/etc", "root/usr/libexec", "root/usr/sbin", "src"]:
    if (root / forbidden).exists():
        raise SystemExit(f"ONU frontend port must not install runtime writer/backend path: {forbidden}")
for path in root.rglob("*.js"):
    text = path.read_text()
    for token in ("uci.set(", "uci.save(", "uci.apply(", "fs.write(", "fs.exec('/usr/libexec", "fs.exec(\"/usr/libexec"):
        if token in text:
            raise SystemExit(f"ONU read-only page contains forbidden operation {token}: {path}")
acl = json.loads((root / "root/usr/share/rpcd/acl.d/luci-app-onu.json").read_text())
acl_text = json.dumps(acl, ensure_ascii=False)
for token in ('"write"', '"upload"', 'pon-board-identity', 'airoha-pon-data', 'restart', 'mtd', 'ubiupdatevol'):
    if token in acl_text:
        raise SystemExit(f"ONU read-only ACL contains forbidden permission or operation: {token}")
menu = json.loads((root / "root/usr/share/luci/menu.d/luci-app-onu.json").read_text())
expected_paths = {"admin/onu/overview", "admin/onu/status", "admin/onu/hardware", "admin/onu/diagnostics"}
actual_paths = {k for k, v in menu.items() if "action" in v and v["action"].get("path", "").startswith("onu-dashboard/")}
if not expected_paths.issubset(actual_paths):
    raise SystemExit(f"ONU menu is missing read-only pages (have {sorted(actual_paths)})")
for k, v in menu.items():
    if "action" in v and v["action"].get("path", "").startswith("onu-dashboard/"):
        if k not in expected_paths:
            raise SystemExit(f"Unexpected ONU menu entry {k}")
upstream = json.loads((root / "UPSTREAM.json").read_text())
if upstream.get("repository") != "naoki66/OpenWrt_ONU_CONFIG" or upstream.get("commit") != "3cb13560459f1d51136dac662baa1f399028b2b4":
    raise SystemExit("ONU UI upstream provenance changed unexpectedly")
if "frontend-only" not in upstream.get("scope", "").lower():
    raise SystemExit("ONU UI provenance does not declare frontend-only scope")
print(f"ONU frontend-only port verified: {len(required)} files, {len(actual_paths)} pages, no write/flash backend")

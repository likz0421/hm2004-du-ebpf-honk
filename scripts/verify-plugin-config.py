#!/usr/bin/env python3
"""Fail the build if selected HM2004 plugins/features disappear in defconfig."""
import json
from pathlib import Path
import sys

ow = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parents[1]
lock = json.loads((repo / "configs/plugins.lock.json").read_text())
config = dict(line.split("=", 1) for line in (ow / ".config").read_text().splitlines() if line.startswith("CONFIG_") and "=" in line)
required = ["CONFIG_PACKAGE_" + name for name in lock["expected"]["packages"]]
required += ["CONFIG_PACKAGE_kmod-h3c-fmcs", "CONFIG_KERNEL_DEBUG_INFO_BTF"]
required += ["CONFIG_FTTR_" + part for part in ["PLATFORM_H3C_HM2004_DU", "DEVICE_HL202", "DEVICE_HWTC", "DEVICE_STAR", "DEVICE_ZTE", "DEVICE_SCTY", "DEVICE_FIBERHOME", "DEVICE_REALTEK", "ACS", "MQTT", "NPU", "MIMALLOC"]]
missing = [key for key in required if config.get(key) != "y"]
if missing:
    raise SystemExit("Missing required plugin settings after defconfig: " + ", ".join(missing))
devices = {key for key, value in config.items()
           if key.startswith("CONFIG_TARGET_DEVICE_airoha_") and value == "y"}
if devices != {"CONFIG_TARGET_DEVICE_airoha_an7581_DEVICE_h3c_hm2004-du"}:
    raise SystemExit("Unexpected selected device profiles: " + ", ".join(sorted(devices)))
print("Only HM2004-DU is selected; all required PON/FTTR plugins present")
for key in required:
    if key.startswith("CONFIG_FTTR_"):
        print(key + "=" + config[key])

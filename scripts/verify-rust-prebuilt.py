#!/usr/bin/env python3
"""Verify OpenWrt used the selected prebuilt Rust, before compiling firmware."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def install_host(openwrt, report):
    """Run the actual OpenWrt host target; retain its log even on failure."""
    report.mkdir(parents=True, exist_ok=True)
    with (report / "rust-host-install.log").open("w") as log:
        result = subprocess.run(["make", "package/feeds/packages/rust/host/compile", "FORCE_HOST_INSTALL=1", "-j1", "V=s"],
                                cwd=openwrt, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    text = (report / "rust-host-install.log").read_text(errors="replace")
    print(text[-10000:], flush=True)
    if result.returncode:
        raise ValueError(f"OpenWrt Rust host install failed (exit {result.returncode})")
    if "x.py --" in text or "failed to download llvm from ci" in text:
        raise ValueError("source Rust bootstrap ran in prebuilt mode")


def verify(openwrt, report):
    state_path = report / "rust-toolchain.json"
    state = json.loads(state_path.read_text())
    root = Path(state["root"]).resolve()
    bindir = Path(state["staging_bin"])
    for tool in ("cargo", "rustc", "rustdoc"):
        installed = bindir / tool
        if not installed.is_symlink() or installed.resolve() != (root / "bin" / tool).resolve():
            raise ValueError(f"{tool}: OpenWrt staging must link to selected prebuilt: {installed}")
        subprocess.run([str(installed), "--version"], check=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="verify-rust-") as temporary:
        temporary = Path(temporary)
        source = temporary / "probe.rs"
        source.write_text("pub fn probe() -> usize { std::mem::size_of::<usize>() }\n")
        output = temporary / "probe.rmeta"
        subprocess.run([str(bindir / "rustc"), "--target", state["target"], "--crate-type", "rlib",
                        "--emit=metadata", "-o", str(output), str(source)], check=True, timeout=60)
        if not output.is_file() or not output.stat().st_size:
            raise ValueError("installed Rust produced no target metadata")
    state["host_install_verified"] = True
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"PASS: installed prebuilt Rust host and target std: {state['target']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("openwrt", type=Path)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--install", action="store_true", help="execute the actual OpenWrt Rust host target first")
    args = parser.parse_args()
    if args.install:
        install_host(args.openwrt.resolve(), args.reports.resolve())
    verify(args.openwrt.resolve(), args.reports.resolve())


if __name__ == "__main__":
    main()

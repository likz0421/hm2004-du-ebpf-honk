#!/usr/bin/env python3
"""Inspect the built HM2004 image before it can be uploaded to a release."""
import argparse
import hashlib
import json
import mmap
import os
import platform
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from verify_fmcs_module import verify_port_count


def require(ok, message):
    if not ok:
        raise ValueError(message)
    print("PASS", message, flush=True)


def verify_argon_templates(root, qemu, temporary, native=False):
    template_dir = root / "usr/share/ucode/luci/template/themes/argon"
    templates = sorted(template_dir.glob("*.ut"))
    expected = {"footer.ut", "footer_login.ut", "head.ut", "head_meta.ut", "header.ut",
                "header_login.ut", "login_background.ut", "login_form.ut", "out_header_login.ut",
                "page_scripts.ut", "sysauth.ut"}
    require({file.name for file in templates} == expected, "all 11 pinned Argon ucode templates installed")
    require(all(file.stat().st_size > 0 for file in templates), "Argon templates are non-empty source files")
    for file in templates:
        if native:
            command = ["chroot", str(root), "/usr/bin/ucode", "-T", "-c",
                       "-o", "/tmp/template.ucb", "/" + str(file.relative_to(root))]
        else:
            command = [qemu, "-L", str(root), str(root / "usr/bin/ucode"), "-T", "-c",
                       "-o", str(temporary / "template.ucb"), str(file)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise ValueError(f"Argon template compile failed: {file.name}\n{result.stderr}\n{result.stdout}")
    require(True, f"target ucode compiles {len(templates)} Argon templates in -T template mode")
    return {"count": len(templates), "compiler_mode": "-T -c", "passed": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("openwrt", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--build-commit", help="require this exact embedded firmware build commit")
    parser.add_argument("--native", action="store_true", help="run on native AArch64 Linux via chroot (requires root)")
    args = parser.parse_args()
    if args.native:
        require(platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64"), "native verification host is ARM64 Linux")
        require(os.geteuid() == 0, "native verification has chroot privilege")
    ow = args.openwrt.resolve()
    repo = Path(__file__).resolve().parents[1]
    lock = json.loads((repo / "configs/plugins.lock.json").read_text())
    images = list((ow / "bin/targets").glob("*/*/*h3c_hm2004-du-squashfs-sysupgrade.itb"))
    require(len(images) == 1, "exactly one HM2004 sysupgrade image")
    image = images[0]
    manifests = list(image.parent.glob("*airoha-an7581-h3c_hm2004-du.manifest"))
    require(len(manifests) == 1, "exactly one HM2004 package manifest")
    manifest = manifests[0]
    installed = dict(line.split(" - ", 1) for line in manifest.read_text().splitlines() if " - " in line)
    for name, version in lock["expected"]["packages"].items():
        if name == "honk-core":
            continue  # Core binary is statically sourced; manifest reports only the package wrapper.
        require(installed.get(name) == version, f"{name} = {version}; actual {installed.get(name)}")
    require(installed.get("honk") == lock["expected"]["packages"]["honk"], "Honk package wrapper version matches the audited feed")
    with tempfile.TemporaryDirectory(prefix="verify-hm2004-") as temp:
        tmp = Path(temp)
        squashfs = tmp / "root.squashfs"
        with image.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            offset = data.find(b"hsqs")
            require(offset >= 0, "SquashFS found in FIT image")
            # SquashFS v4 superblock: root_inode is at 32, bytes_used at 40.
            length = struct.unpack_from("<Q", data, offset + 40)[0]
            require(96 < length <= len(data) - offset, "SquashFS size is within image bounds")
            squashfs.write_bytes(data[offset:offset + length])
        root = tmp / "root"
        # All target libraries are required by the musl binary and ucode runtime.
        subprocess.run(["unsquashfs", "-q", "-d", str(root), str(squashfs),
                        "etc/*", "lib/*", "usr/sbin/fttrd", "usr/sbin/nft", "usr/bin/ucode", "usr/bin/rtp2httpd", "usr/bin/honk-core",
                        "usr/lib/*", "usr/libexec/*", "usr/share/ucode/*", "usr/share/firewall4/*", "www/*"], check=True)
        release = (root / "etc/openwrt_release").read_text()
        print(release, flush=True)
        desc = re.search(r"^DISTRIB_DESCRIPTION='(.*)'$", release, re.M)
        require(desc is not None and args.tag in desc.group(1), "firmware description contains exact release tag")
        provenance = root / "etc/firmware-plugins.json"
        require(provenance.is_file(), "plugin provenance is embedded in the image")
        embedded = json.loads(provenance.read_text())
        for field in ("build_base", "sources", "feeds", "archives", "expected"):
            require(embedded.get(field) == lock.get(field), f"embedded {field} matches audited lock")
        require(embedded.get("build_source") == lock["build_base"]["commit"], "firmware uses the locked OpenWrt stable derived commit")
        require(embedded.get("feed_commits") == {name: spec["commit"] for name, spec in lock["feeds"].items()}, "actual checked-out feed commits match locks")
        require(bool(embedded.get("build_repo")), "build repository commit recorded")
        if args.build_commit:
            require(embedded.get("build_repo") == args.build_commit, "embedded build commit matches the downloaded candidate")
        qemu = None if args.native else (shutil.which("qemu-aarch64-static") or shutil.which("qemu-aarch64"))
        if args.native:
            (root / "tmp").mkdir(exist_ok=True)
        else:
            require(bool(qemu), "aarch64 user emulator available")
        def target(path, *params):
            command = (["chroot", str(root), "/" + path, *params] if args.native else
                       [qemu, "-L", str(root), str(root / path), *params])
            result = subprocess.run(command, text=True, capture_output=True, timeout=45)
            if result.returncode:
                raise ValueError(f"target {path} {params} exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}")
            return result.stdout
        caps = json.loads(target("usr/sbin/fttrd", "--capabilities"))
        require(isinstance(caps.get("adapters"), dict), "FTTR grouped adapter schema")
        for layer, key in [("omci", "omci_adapters"), ("bootstrap", "bootstrap_adapters")]:
            actual = {item["id"] for item in caps["adapters"][layer]}
            require(actual == set(lock["expected"][key]), f"FTTR {layer}: {sorted(actual)}")
        require(caps["features"].get("acs") is True and caps["features"].get("mqtt") is True, "ACS and MQTT compiled")
        require(any(item.get("id") == "auto" for item in caps["adapters"]["omci"]), "auto OMCI adapter exists in pinned upstream")
        config = (root / "etc/config/fttr").read_text()
        require("config omci_auth 'global'" in config and "option auth_mode 'disabled'" in config, "ONU authentication defaults to disabled")
        ports = re.search(r"(?ms)^config\s+ports\s+['\"]ports['\"]\s*$(.*?)(?=^config\s|\Z)", config)
        require(ports is not None, "FTTR downstream port configuration installed")
        for key, value in [("enabled", "1"), ("count", "4")]:
            require(re.search(r"option\s+" + key + r"\s+['\"]" + value + r"['\"]", ports.group(1)) is not None,
                    f"FTTR fresh {key}={value}")
        for relative, expected in lock["expected"]["fttr_assets_sha256"].items():
            file = root / relative
            require(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == expected,
                    "FTTR paired artifact hash: " + relative)
        init_link = root / "etc/rc.d/S19h3c-fmcs"
        require(init_link.is_symlink() and str(init_link.readlink()).endswith("init.d/h3c-fmcs"),
                "FMCS port-aware driver loads at S19 before network")
        autoload = root / "etc/modules.d"
        require(not any("h3c-fmcs" in file.read_text(errors="ignore") or "h3c_fmcs" in file.read_text(errors="ignore")
                        for file in autoload.glob("*") if file.is_file()),
                "no early FMCS autoload can bypass selected port count")
        modules = list((root / "lib/modules").glob("*/h3c-fmcs.ko*"))
        require(len(modules) == 1, "one FMCS kernel module installed")
        module = modules[0]
        if module.suffix == ".zst":
            data = subprocess.check_output(["zstd", "-dc", str(module)])
        elif module.suffix == ".xz":
            import lzma
            data = lzma.decompress(module.read_bytes())
        elif module.suffix == ".gz":
            import gzip
            data = gzip.decompress(module.read_bytes())
        else:
            data = module.read_bytes()
        # module_param_cb has no automatic parmtype, and MODULE_STRIPPED
        # removes descriptions. Check the real __param + RELA registration.
        fmcs_parameter = verify_port_count(data)
        require(True, "FMCS ELF registers read-only boot-time port_count with custom setter, uint getter and default 16")
        require(f"DISTRIB_RELEASE='{lock['build_base']['stable_release']}'" in release,
                "firmware identifies the selected OpenWrt stable series")
        require(hashlib.sha256((root / "lib/firmware/FTTR_TOP.sbit").read_bytes()).hexdigest() == lock["expected"]["fpga_sha256"], "FPGA bitstream matches audited upstream")
        honk_core = root / "usr/bin/honk-core"
        require(honk_core.is_file() and bool(honk_core.stat().st_mode & 0o111),
                "honk core executable is installed")
        with honk_core.open("rb") as stream:
            header = stream.read(20)
        require(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01"
                and struct.unpack_from("<H", header, 18)[0] == 183,
                "honk core is a 64-bit little-endian AArch64 ELF")
        require("1.1.6" in target("usr/sbin/nft", "--version"), "target nftables binary reports pinned stable version")
        fullcone_modules=list((root / "lib/modules").glob("*/nft_fullcone.ko*"))
        require(len(fullcone_modules) == 1, "one fullcone kernel module installed")
        fw4=(root / "usr/share/ucode/fw4.uc").read_text()
        rules=(root / "usr/share/firewall4/templates/ruleset.uc").read_text()
        require("delete defs.fullcone6;" in fw4 and "due to masq_src/masq_dest address restrictions" in fw4,
                "firewall probe fallback and restricted-zone protection installed")
        require("zone.fullcone" in rules and "zone.fullcone6" in rules,
                "firewall templates use per-zone fullcone decisions")
        honk = (root / "etc/config/honk").read_text()
        require(re.search(r"option\s+enabled\s+['\"]0['\"]", honk) is not None, "honk defaults disabled")
        lan = (root / "etc/uci-defaults/93-lan-dhcp").read_text()
        for expected in ["network.lan.ipaddr='10.1.1.1'", "dhcp.lan.start='2'"]:
            require(expected in lan, expected)
        require("dhcp.@dnsmasq[0].sequential_ip='1'" in lan, "dnsmasq sequential IP allocation enabled")
        wifi = (root / "etc/uci-defaults/95-wifi-hanzi").read_text()
        require("SSID='hanzi'" in wifi and "KEY='hanziwawa'" in wifi, "both WiFi bands retain user defaults")
        rtp_init = (root / "etc/init.d/rtp2httpd").read_text()
        require("zerocopy_on_send" not in rtp_init, "rtp2httpd init does not send removed option")
        require("3.17.2" in target("usr/bin/rtp2httpd", "--help"), "target rtp2httpd binary reports 3.17.2")
        theme = root / "www/luci-static/resources/argon-compat.js"
        if not theme.is_file():
            theme = root / "www/luci-static/resources/argon/argon-compat.js"
        require(theme.is_file(), "Argon 3.1.4 browser compatibility module installed")
        template_result = verify_argon_templates(root, qemu, tmp, native=args.native)
        (image.parent / "plugin-sources.json").write_text(json.dumps(embedded, ensure_ascii=False, indent=2) + "\n")
        (image.parent / "plugin-verification.json").write_text(json.dumps({"tag":args.tag,"passed":True,"packages":lock["expected"]["packages"],"fttr_capabilities":caps,"sources":lock["sources"],"argon_templates":template_result,"fmcs_parameter":fmcs_parameter,"image_sha256":hashlib.sha256(image.read_bytes()).hexdigest(),"build_commit":embedded["build_repo"]}, ensure_ascii=False, indent=2) + "\n")
    print("All HM2004 image checks passed; target-device IPTV/WiFi traffic remains an on-device test.")


if __name__ == "__main__":
    main()

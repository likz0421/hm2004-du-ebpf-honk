#!/usr/bin/env python3
"""Apply audited package updates after feeds install, before package indexing."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]
LOCK = json.loads((REPO / "configs/plugins.lock.json").read_text())


def replace_once(path, old, new):
    text = path.read_text()
    if new in text and old not in text:
        return
    if text.count(old) != 1:
        raise ValueError(f"{path}: upstream layout changed; expected exactly one old block")
    path.write_text(text.replace(old, new, 1))


def argon(ow):
    theme = ow / "feeds/luci/themes/luci-theme-argon"
    version = LOCK["archives"]["argon"]["version"]
    if f"PKG_VERSION:={version}\n" in (theme / "Makefile").read_text():
        subprocess.run(["git", "apply", "--reverse", "--check", str(REPO / "patches/plugins/argon-3.1.4.patch")], cwd=ow, check=True)
        print("Argon update already applied")
        return
    baseline = subprocess.check_output(["git", "-C", str(ow / "feeds/luci"), "rev-parse", "HEAD:themes/luci-theme-argon"], text=True).strip()
    if baseline != "9e656c9ca28d1dd4845d8c13ac30fc6f3948bd0b":
        raise ValueError("Argon feed base changed; rebase audited official 3.1.4 delta first")
    patch = REPO / "patches/plugins/argon-3.1.4.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != "779788de9cc5fff59367e561f6ec15d83f4641ce088a7428dbb904ef282d1de0":
        raise ValueError("Argon compatibility patch hash mismatch")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=ow, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=ow, check=True)
    text = (theme / "Makefile").read_text()
    for expected in ["PKG_PROVIDES:=luci-app-argon-config", "LUCI_MINIFY_UT:=0", "/www/luci-static/argon/background/"]:
        if expected not in text:
            raise ValueError("Argon feed integration lost: " + expected)
    print("Argon 3.1.4 official runtime delta applied; feed wallpaper/config integration retained")


def rtp2httpd(ow):
    directory = ow / "feeds/packages/net/rtp2httpd"
    spec = LOCK["archives"]["rtp2httpd"]
    replace_once(directory / "Makefile", "PKG_VERSION:=3.16.0\n", f"PKG_VERSION:={spec['version']}\n")
    replace_once(directory / "Makefile", "PKG_HASH:=83ff812c5b454cf70057bd2b714c891c8650260d4092d6b86629e451fda57d26", "PKG_HASH:=" + spec["sha256"])
    init = directory / "files/rtp2httpd.init"
    text = init.read_text()
    text = ''.join(line for line in text.splitlines(keepends=True) if "zerocopy_on_send" not in line)
    init.write_text(text)
    config = directory / "files/rtp2httpd.config"
    text = config.read_text().replace("buffers in zero-copy pool", "buffers in buffer pool")
    text = ''.join(line for line in text.splitlines(keepends=True) if "zerocopy_on_send" not in line and "Enable zero-copy send" not in line)
    config.write_text(text)
    view = ow / "feeds/luci/applications/luci-app-rtp2httpd"
    js = view / "htdocs/luci-static/resources/view/rtp2httpd.js"
    text = js.read_text()
    text, count = re.subn(r"\n\t\to = s\.taboption\('general', form\.Flag, 'zerocopy_on_send',.*?\n\t\t\t_\('Enable zero-copy send.*?\n", "\n", text, count=1, flags=re.S)
    if count == 0 and "zerocopy_on_send" in text:
        raise ValueError("rtp2httpd LuCI zerocopy block layout changed")
    text = text.replace("Maximum number of buffers in zero-copy pool.", "Maximum number of buffers in buffer pool.")
    js.write_text(text)
    for f in (view / "po").rglob("*"):
        if not f.is_file() or f.suffix not in (".po", ".pot"):
            continue
        text = f.read_text()
        for msgid in [
            'msgid "Zero-copy on send"',
            '"Enable zero-copy send with <code>MSG_ZEROCOPY</code> for better performance."',
        ]:
            pattern = re.compile(r"(?m)^#:[^\n]*rtp2httpd\.js:[^\n]*\n" + re.escape(msgid) + r"\n(?:msgstr[^\n]*\n(?:\"[^\n]*\n)*)")
            text, _ = pattern.subn("", text)
        text = text.replace("Maximum number of buffers in zero-copy pool.", "Maximum number of buffers in buffer pool.")
        text = text.replace("零拷贝池中缓冲区的最大数量。", "缓冲池中缓冲区的最大数量。")
        f.write_text(text)
    if "zerocopy_on_send" in init.read_text() or "zerocopy_on_send" in js.read_text():
        raise ValueError("Removed rtp2httpd option still exposed")
    print("rtp2httpd 3.17.2 recipe, init and LuCI updated; removed obsolete zerocopy flag")


def geosite(ow):
    file = ow / "feeds/packages/net/v2ray-geodata/Makefile"
    spec = LOCK["archives"]["geosite"]
    replace_once(file, "GEOSITE_VER:=20261108011013\n", f"GEOSITE_VER:={spec['version']}\n")
    replace_once(file, "HASH:=dc4192dd1b644a38276ed06136d26e729fa674d25785adb38c87e040e92376b2", "HASH:=" + spec["sha256"])
    print("GeoSite updated with independently downloaded SHA256; current GeoIP preserved")


def pon_ui(ow):
    """Beautify the existing luci-app-pon status page with the ONU_CONFIG rich layout.

    The rich status view, shared components and stylesheets are vendored in the
    build repo under pon-ui/ and copied into the pinned pon_userspace feed's
    luci-app-pon, so the PON menu keeps its single status entry. The feed's
    package version is bumped so the image manifest reflects the new build.
    """
    app = ow / "feeds/pon_userspace/luci-app-pon"
    ui = REPO / "pon-ui"
    for rel, dest in [
        ("status.js", app / "htdocs/luci-static/resources/view/pon/status.js"),
        ("components.js", app / "htdocs/luci-static/resources/pon/components.js"),
        ("pon.css", app / "htdocs/luci-static/resources/view/pon/pon.css"),
        ("dashboard.css", app / "htdocs/luci-static/resources/view/pon/dashboard.css"),
    ]:
        src = ui / rel
        if not src.is_file():
            raise ValueError(f"pon-ui/{rel} missing")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    makefile = app / "Makefile"
    text = makefile.read_text()
    old = "PKG_RELEASE:=3\n"
    if old not in text:
        raise ValueError("luci-app-pon Makefile expected PKG_RELEASE:=3")
    makefile.write_text(text.replace(old, "PKG_RELEASE:=4\n", 1))
    print("PON status page beautified with ONU_CONFIG rich layout; luci-app-pon bumped to r4")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("openwrt", type=Path)
    args = p.parse_args()
    ow = args.openwrt.resolve()
    argon(ow)
    rtp2httpd(ow)
    geosite(ow)
    pon_ui(ow)


if __name__ == "__main__":
    main()

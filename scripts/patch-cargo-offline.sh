#!/usr/bin/env bash
# =============================================================
# patch-cargo-offline.sh —— 放宽 rust 包的「禁止联网」限制
#
#   背景：openwrt-fttr 的 Makefile 用 cargo install --locked --frozen。
#   --frozen = 锁版本 + 禁止联网，只认 CARGO_HOME(dl/cargo) 里已有的 crate；
#   而 dl/cargo 从缓存继承（只增不减），上游在 Cargo.lock 加新依赖时缓存里没有：
#     Caused by: failed to download `core_detect v1.0.0`
#     Caused by: attempting to make an HTTP request, but --frozen was specified
#   现象是编到一半某个 rust 包必挂，换机型、换缓存都复现。
#
#   这里只摘掉 --frozen / --offline，--locked 保留（版本仍锁死，结果可复现）。
# ⚠ 这是 CI 侧兜底。更正统的做法在包侧：Build/Prepare 里 cargo fetch --locked
#   把 crate 拉进 CARGO_HOME，编译阶段再用 --frozen。
#   用法: bash patch-cargo-offline.sh <openwrt_dir>
# =============================================================

set -u
SCRIPT_ROOT="$(cd "$(dirname "$0")" && pwd)"
# 只修改构建文件，不进入 Rust/JS 等业务源码；保留 --locked。
exec python3 "$SCRIPT_ROOT/patch-cargo-offline.py" "${1:-$PWD}"

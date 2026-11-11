#!/bin/bash
# ================================================================
# honk-feeds.sh —— 把 honk 需要的第三方 feed 注入 feeds.conf.default
#
# 为什么单独一个函数而不是直接改文件：
#   feeds.conf.default 在 workflow 里可能被 FEEDS_CONF 覆盖过一次，
#   这里在「Update & install feeds」之前再补一次，保证 honk 的依赖都在。
#
# honk（dae 系 eBPF 透明代理）本体在 kenzok8/openwrt-honk，
# 其依赖的 kmod 与用户态工具在 immortalwrt 官方 feed 里已有。
# ================================================================
set -euo pipefail

FEEDS_FILE="feeds.conf.default"
[ -f "$FEEDS_FILE" ] || { echo "::error::feeds.conf.default 不存在"; exit 1; }

# 已有就不再加（幂等）
if ! grep -q '^src-git honk ' "$FEEDS_FILE"; then
  echo 'src-git honk https://github.com/kenzok8/openwrt-honk.git^7b1c0140ec6f0f0e2ce5c8b6f7e78f6716344a45' >> "$FEEDS_FILE"
  echo "✅ 已注入 honk feed（锁 commit 7b1c0140）"
else
  echo "✅ honk feed 已存在，跳过"
fi

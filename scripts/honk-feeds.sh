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

# 已存在旧 feed 时也要替换，不能“有一行就跳过”而永久停在旧 pin。
SCRIPT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HONK_COMMIT="$(python3 "$SCRIPT_ROOT/scripts/plugin-lock.py" get sources.honk-feed.commit)"
HONK_REPO="$(python3 "$SCRIPT_ROOT/scripts/plugin-lock.py" get sources.honk-feed.repo)"
export HONK_COMMIT HONK_REPO FEEDS_FILE
python3 - <<'PY'
from pathlib import Path
import os
p = Path(os.environ['FEEDS_FILE'])
lines = [line for line in p.read_text().splitlines()
         if not (len(line.split()) >= 2 and line.split()[0] in ('src-git', 'src-git-full')
                 and line.split()[1] == 'honk')]
lines.append('src-git honk https://github.com/' + os.environ['HONK_REPO'] + '.git^' + os.environ['HONK_COMMIT'])
p.write_text('\n'.join(lines) + '\n')
PY
echo "✅ honk feed 已锁定：$HONK_COMMIT（核心仍为已发布 beta.6）"

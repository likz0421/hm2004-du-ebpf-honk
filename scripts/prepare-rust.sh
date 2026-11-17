#!/usr/bin/env bash
# =============================================================
# prepare-rust.sh —— 用 runner 的 rustup 替代 rustc 源码自举（省 30~60 分钟）
#
#   关键：target triple 必须向 feed 要、不能自己拼 —— 读
#   feeds/packages/lang/rust/rust-values.mk 的 RUSTC_TARGET_ARCH，
#   才能保证 CI 装的 target 与 OpenWrt 期望的一致。
# 必须在唯一一次 make defconfig 之后运行：ARCH 与 libc 后缀都来自最终
# .config。预编译模式任一步失败即终止，不能静默退回数小时的源码自举。
# 用法: bash prepare-rust.sh <openwrt_dir>
# =============================================================

set -euo pipefail

OW="${1:-$PWD}"
cd "$OW" || { echo "::error::无法进入 $OW"; exit 1; }

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPORT_DIR="${GITHUB_WORKSPACE:-$OW}/build-reports"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/rust-toolchain.txt"

log() { echo "$1" | tee -a "$REPORT"; }
fail() { log "::error::$1"; exit 1; }
warn() { log "::warning::$1"; }

: > "$REPORT"
log "===== Rust 预编译工具链 ====="

# ---------------------------------------------------------------
# 0. 前置检查
# ---------------------------------------------------------------
RUST_FEED="$PWD/feeds/packages/lang/rust"
if [ ! -f "$RUST_FEED/Makefile" ]; then
  fail "Rust: 缺少 feeds/packages/lang/rust/Makefile"
fi

if [ ! -f "$RUST_FEED/rust-values.mk" ]; then
  fail "Rust: 缺 rust-values.mk，无法推导目标"
fi

# ---------------------------------------------------------------
# 1. 向固定 feed 要 target triple；只接受 defconfig 后的真实配置。
#    不猜 ARCH，不补 libc 后缀，也不再次运行 defconfig（保留版本注入）。
# ---------------------------------------------------------------
[ -s .config ] || fail "Rust: 缺少最终 .config；请在 Validate configuration 后运行"
if ! make --no-print-directory -s -f - TOPDIR="$PWD" ci-rust-values \
  > "$REPORT_DIR/rust-values.txt" 2> "$REPORT_DIR/rust-values-errors.txt" <<'MAKE'
include $(TOPDIR)/rules.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-values.mk
.PHONY: ci-rust-values
ci-rust-values:
	@printf '%s\n' '$(CONFIG_HAVE_DOT_CONFIG)' '$(ARCH)' '$(TARGET_SUFFIX)' '$(RUSTC_TARGET_ARCH)' '$(STAGING_DIR)/host/bin'
MAKE
then
  cat "$REPORT_DIR/rust-values-errors.txt" >&2
  fail "Rust: 无法读取最终目标，make 查询失败"
fi
mapfile -t RUST_VALUES < "$REPORT_DIR/rust-values.txt"
[ "${#RUST_VALUES[@]}" = 5 ] || fail "Rust: make 目标查询输出不完整"
[ "${RUST_VALUES[0]}" = y ] && [ -n "${RUST_VALUES[1]}" ] \
  && [ -n "${RUST_VALUES[2]}" ] || fail "Rust: .config 尚未 defconfig 展开，缺 ARCH/libc suffix"
RUST_TARGET=${RUST_VALUES[3]}
RUST_STAGING_BIN=${RUST_VALUES[4]}
[[ "$RUST_TARGET" =~ ^[a-zA-Z0-9_]+-[a-zA-Z0-9_.-]+-[a-zA-Z0-9_.-]+-[a-zA-Z0-9_.-]+$ ]] \
  || fail "Rust: 无效或不完整的目标 triple: $RUST_TARGET"
log "Rust target: $RUST_TARGET"
log "Rust target staging: $RUST_STAGING_BIN"

# ---------------------------------------------------------------
# 2. 找 rustup（runner 预装，但 PATH 未必包含 ~/.cargo/bin）
# ---------------------------------------------------------------
RUSTUP_BIN=$(command -v rustup || true)
if [ -z "$RUSTUP_BIN" ]; then
  for c in "$HOME/.cargo/bin/rustup" /usr/bin/rustup /usr/local/bin/rustup; do
    [ -x "$c" ] && { RUSTUP_BIN=$c; break; }
  done
fi
if [ -z "$RUSTUP_BIN" ]; then
  fail "Rust: runner 缺少 rustup，预编译模式不可用"
fi
PATH="$(dirname "$RUSTUP_BIN"):$PATH"; export PATH

RUST_TOOLCHAIN=$(rustup show active-toolchain | cut -d' ' -f1)
[ -n "$RUST_TOOLCHAIN" ] || RUST_TOOLCHAIN=stable
log "Rust toolchain: $RUST_TOOLCHAIN"

# ---------------------------------------------------------------
# 3. 装对应的 target
# ---------------------------------------------------------------
if ! rustup target add --toolchain "$RUST_TOOLCHAIN" "$RUST_TARGET" 2>&1 | tee -a "$REPORT"; then
  fail "Rust: rustup target add $RUST_TARGET 失败，停止预编译构建"
fi

RUST_ROOT=$(rustup run "$RUST_TOOLCHAIN" rustc --print sysroot 2>/dev/null)
if [ -z "$RUST_ROOT" ] || [ ! -d "$RUST_ROOT" ]; then
  fail "Rust: rustc --print sysroot 未返回可用目录"
fi

# ---------------------------------------------------------------
# 4. 校验：target 的 std 与三个工具必须真的在
#    否则后面编译会因为缺 std 而失败，不如现在就退回
# ---------------------------------------------------------------
if [ ! -d "$RUST_ROOT/lib/rustlib/$RUST_TARGET/lib" ]; then
  fail "Rust: 缺少 $RUST_TARGET 的目标标准库目录"
fi
for t in cargo rustc rustdoc; do
  if [ ! -x "$RUST_ROOT/bin/$t" ]; then
    fail "Rust: 缺少可执行工具 $RUST_ROOT/bin/$t"
  fi
done

# ---------------------------------------------------------------
# 4.4 可选固定到 feed 版本；固定失败必须报错，不能偷偷换回 stable。
# ---------------------------------------------------------------
FEED_VER=$(rg '^PKG_VERSION:=' "$RUST_FEED/Makefile" | cut -d= -f2 | tr -d ' \r')
[ -n "$FEED_VER" ] || fail "Rust: 无法读取固定 feed 的 PKG_VERSION"
if [[ "${RUST_PIN_FEED:-false}" = 1 || "${RUST_PIN_FEED:-false}" = true ]]; then
  RUST_TOOLCHAIN=$FEED_VER
  rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal 2>&1 | tee -a "$REPORT"
  rustup target add --toolchain "$RUST_TOOLCHAIN" "$RUST_TARGET" 2>&1 | tee -a "$REPORT"
  RUST_ROOT=$(rustup run "$RUST_TOOLCHAIN" rustc --print sysroot)
fi
for t in cargo rustc rustdoc; do
  [ -x "$RUST_ROOT/bin/$t" ] || fail "Rust: 工具链缺少 $t"
  "$RUST_ROOT/bin/$t" --version >> "$REPORT"
done
compgen -G "$RUST_ROOT/lib/rustlib/$RUST_TARGET/lib/libstd-*.rlib" > /dev/null \
  || fail "Rust: $RUST_TARGET 标准库缺少 libstd rlib"
compgen -G "$RUST_ROOT/lib/rustlib/$RUST_TARGET/lib/libcore-*.rlib" > /dev/null \
  || fail "Rust: $RUST_TARGET 标准库缺少 libcore rlib"
PROBE_DIR=$(mktemp -d "$REPORT_DIR/rust-probe.XXXXXX")
trap 'rm -rf "$PROBE_DIR"' EXIT
printf '%s\n' 'pub fn probe() -> usize { std::mem::size_of::<usize>() }' > "$PROBE_DIR/probe.rs"
"$RUST_ROOT/bin/rustc" --target "$RUST_TARGET" --crate-type rlib --emit=metadata \
  -o "$PROBE_DIR/probe.rmeta" "$PROBE_DIR/probe.rs"
[ -s "$PROBE_DIR/probe.rmeta" ] || fail "Rust: 目标 std 编译测试没有输出"
log "PASS: Rust target std compilation: $RUST_TARGET"

# ---------------------------------------------------------------
# 4.5 纠正 staging_dir 里那三个「指向上次 runner」的符号链接
#   缓存命中时 host/bin/rustc 是上次留下的链接，指向 /home/runner/.rustup/…。
#   镜像换了 rustup 布局或工具链名，它就悬空；而 Host/Install 只在 stamp 失效
#   时重跑、不会自己修，于是报 /bin/sh: .../staging_dir/host/bin/rustc: not found，
#   看起来像缓存坏了。这里就地改正，只动符号链接、不碰真实二进制。
# ---------------------------------------------------------------
LINKED=0
for d in "$RUST_STAGING_BIN" "$PWD/staging_dir/host/bin" "$PWD/staging_dir/hostpkg/bin"; do
  [ -d "$d" ] || continue
  for t in cargo rustc rustdoc; do
    if [ -L "$d/$t" ]; then
      ln -sfn "$RUST_ROOT/bin/$t" "$d/$t"
      LINKED=$((LINKED + 1))
    fi
  done
done
if [ "$LINKED" -gt 0 ]; then
  log "已纠正 $LINKED 个 staging_dir 里的 rust 符号链接（缓存恢复的残留）"
fi

# ---------------------------------------------------------------
# 4.6 版本对照：feed 期望的 rustc vs runner 实际提供的
#   runner 的 stable 省 30~60 分钟，但不一定等于 feed pin 的版本 —— codegen
#   随版本变，产物不完全相同；极少数 crate 在新版上会报错（版本相关，不是
#   静默错误）。两个版本号并排打出来，出问题时一眼能判断是不是版本引起的。
# ---------------------------------------------------------------
FEED_RUST_VER=$FEED_VER
RUNNER_RUST_VER=$("$RUST_ROOT/bin/rustc" --version | cut -d' ' -f2)
log "rustc 版本：feed 期望 ${FEED_RUST_VER:-未知} ｜ 实际使用 ${RUNNER_RUST_VER:-未知}"
if [ -n "${FEED_RUST_VER:-}" ] && [ -n "${RUNNER_RUST_VER:-}" ] \
   && [ "$FEED_RUST_VER" != "$RUNNER_RUST_VER" ]; then
  log "  两者不同属正常（这就是省下 30~60 分钟的原因）；若 rust 包编译报版本相关错误，"
  log "  把 workflow 的 RUST_PIN_FEED 设为 1，会按 feed 的版本另装一个 toolchain。"
fi

# ---------------------------------------------------------------
# 5. 注入 ci-prebuilt.mk，替换源码自举
#
#    必须在 OpenWrt 展开 HostBuild 规则【之前】插入，
#    所以 sed 插到 $(eval $(call HostBuild)) 之前。
# ---------------------------------------------------------------
{
  printf 'CI_RUST_ROOT:=%s\n' "$RUST_ROOT"
  cat "$SCRIPT_DIR/rust-prebuilt.mk"
} > "$RUST_FEED/ci-prebuilt.mk"

RUST_MAKEFILE="$RUST_FEED/Makefile"
# perl 需要从环境里拿这两个字面量（避免 shell 转义把 $ 吃掉）
export CI_MARKER='include ./ci-prebuilt.mk'
export CI_HOSTBUILD='$(eval $(call HostBuild))'

# ⚠ 必须用 perl，不能用 sed -i：
#   GNU sed 处理含 `$` 的模式（$(eval $(call HostBuild))）时，
#   -i 原地模式下 i\ 命令会静默失效 —— 实测插入不进去且不报错。
#   perl 的 \Q...\E 把整串当字面量，可靠得多。
MARKER='include ./ci-prebuilt.mk'
HOSTBUILD='$(eval $(call HostBuild))'

perl -i -pe '
  BEGIN { $m = quotemeta($ENV{"CI_MARKER"}); $h = quotemeta($ENV{"CI_HOSTBUILD"}); }
  if ($_ =~ /^$m$/) { $_ = ""; }                 # 先删掉旧的（幂等）
  elsif ($_ =~ /^$h$/) { $_ = "$ENV{CI_MARKER}\n" . $_; }   # 再插到 HostBuild 之前
' "$RUST_MAKEFILE"

[ -s "$RUST_FEED/ci-prebuilt.mk" ] || fail "Rust: ci-prebuilt.mk 缺失或为空"
python3 - "$RUST_MAKEFILE" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
marker = 'include ./ci-prebuilt.mk'
hostbuild = '$(eval $(call HostBuild))'
if lines.count(marker) != 1 or lines.count(hostbuild) != 1:
    sys.exit('Rust: expected one prebuilt include and one HostBuild')
if lines.index(marker) + 1 != lines.index(hostbuild):
    sys.exit('Rust: prebuilt must be immediately before HostBuild')
PY
# ⚠ 别把 $HOSTBUILD 直接放进带 $(...) 的字符串：
#   它的内容是字面量 $(eval $(call HostBuild))，
#   双引号里的 $(...) 会被 shell 当命令替换执行，
#   直接报 "意外令牌附近语法错误 '('"（第147行就是这么炸的）。
log "注入: $MARKER（在 HostBuild 求值之前）"

"$RUST_ROOT/bin/rustc" --version | tee -a "$REPORT"
log "PASS: runner Rust ($RUST_TOOLCHAIN) target std and prebuilt injection verified"
python3 - "$REPORT_DIR/rust-toolchain.json" "$RUST_TARGET" "$RUST_ROOT" "$RUST_TOOLCHAIN" "$RUST_STAGING_BIN" "$FEED_RUST_VER" "$RUNNER_RUST_VER" <<'PY'
from pathlib import Path
import json
import sys
path, target, root, toolchain, staging_bin, expected, actual = sys.argv[1:]
Path(path).write_text(json.dumps(dict(target=target, root=root, toolchain=toolchain,
    staging_bin=staging_bin, feed_version=expected, actual_version=actual,
    target_std_compiled=True, prebuilt_include_verified=True), indent=2) + '\n')
PY
sha256sum "$RUST_MAKEFILE" >> "$REPORT"
exit 0

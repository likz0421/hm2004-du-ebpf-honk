# SPDX-License-Identifier: Apache-2.0
include $(TOPDIR)/rules.mk

LUCI_TITLE:=ONU dashboard and detailed PON status
LUCI_URL:=https://github.com/naoki66/OpenWrt_ONU_CONFIG
LUCI_DEPENDS:=+luci-base +luci-app-pon +luci-app-pon-status +airoha-pon-debug
PKG_VERSION:=0.2.0
PKG_RELEASE:=1
PKG_PO_VERSION:=$(PKG_VERSION)-r$(PKG_RELEASE)
# Keep exact ported assets for reproducible image integrity verification.
LUCI_MINIFY_JS:=0
LUCI_MINIFY_CSS:=0
PKG_LICENSE:=Apache-2.0 GPL-2.0-only

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature

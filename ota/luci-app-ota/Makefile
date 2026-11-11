include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-ota
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=likz0421

LUCI_TITLE:=HM2004-DU 在线升级（OTA）
LUCI_DEPENDS:=+luci-base +rpcd +curl +ca-bundle +jq
LUCI_DESCRIPTION:=从 GitHub Release 检查、下载并安装 sysupgrade 镜像；下载前校验可用内存，安装前校验 sha256 与机型。

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature

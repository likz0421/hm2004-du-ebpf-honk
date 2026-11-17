# Fullcone isolated runtime gate

`run.py` builds checksum-locked Linux 6.12.116 with the stable source tree's conntrack chain patch and its patched nft_fullcone module. It boots a disposable x86_64 QEMU guest with no external network interface. No test modules or rules are loaded into the runner host. Native nft/libnftnl from `../verify-fullcone-userspace.py` are copied into the guest.

Requirements on Ubuntu 24.04: build-essential, bison, flex, libelf-dev, libssl-dev, bc, xz-utils, zstd, qemu-system-x86, busybox-static, cpio, kmod, conntrack, iproute2, Python 3.12. The separate native userspace gate also requires autoconf, automake, libtool, libmnl-dev and libjansson-dev.

```
python3 scripts/verify-fullcone-userspace.py openwrt --work /tmp/fullcone-native
python3 scripts/fullcone-runtime/run.py openwrt --native-prefix /tmp/fullcone-native/prefix --work /tmp/fullcone-runtime
```

Checks: ctnetlink/fullcone load order, nft check/create/flush/reload, two namespace subscription lifetimes, conntrack DESTROY notification, unsupported port-attribute rejection, module unload, IPv4 UDP replies from both contacted and previously uncontacted endpoints, and kernel diagnostic scan. JSON redirect round-trip runs in a fresh host network namespace before QEMU. It does not claim physical PON/FTTR/WiFi behavior, IPv6 UDP dataplane, real OLT interoperability, or exhaustive conntrack expectation/RCU stress coverage.

Guest success requires the explicit `HM_FULLCONE_RUNTIME_PASS` marker and clean QEMU exit; missing marker, guest test failure, exception or timeout fails the job. Artifacts retain console output, kernel config, and verification JSON.

Status at creation: scripts syntax checked; package patch sequence, 29 real ucode firewall tests and extracted notifier host tests passed separately. Complete native userspace and QEMU executions remain pending CI; do not describe them as passed until the job succeeds.

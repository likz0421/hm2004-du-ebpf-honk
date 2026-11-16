# HM2004 ONU interface port

The detailed PON page, component stylesheet and Chinese catalog originate from
`naoki66/OpenWrt_ONU_CONFIG` commit `3cb13560459f1d51136dac662baa1f399028b2b4`.
Original file hashes are recorded in `UPSTREAM.json`; SPDX notices are preserved.
This frontend-only port uses the installed pbs05 `ponctl`/`pondctl` status API and
qwe's connection/offload statistics. It does not install a replacement protocol
stack, service, UCI defaults, flash writer or business-network apply helper.

## Pages

- Overview: line readiness, optical telemetry, session-local history, physical
  port traffic rates, connection/offload counts and links to existing managers.
- Detailed PON: upstream protocol, OLT, GEM/T-CONT, VLAN and counter information,
  adapted for the pbs05 fields actually present. Missing values remain unknown.
- Hardware: board identity layout, current line identity and system information;
  it does not read or rewrite a complete factory flash image.
- Diagnostics: live read-only health checks; explicit links to the installed
  PON capture/restart interface, with its existing permissions and confirmations.

New pages use the isolated resource namespace `view/onu-dashboard` and a read-only
ACL. Existing PON, IPTV, NAT, IGMP and FTTR pages keep their own paths and access
controls. Voice configuration and unsupported fork-specific auth/IGMP controls
are intentionally not registered. Read-only UI is not proof of actual OLT/PHY
hardware operation; post-flash runtime verification is still needed.

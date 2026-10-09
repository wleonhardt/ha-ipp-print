# Printer/scanner compatibility and optional bridges

Direct eSCL and IPP remain the default. A bridge is an optional separately managed
service. It can expose a device through a protocol these integrations understand;
it does not guarantee every function of that device works.

## Choose an endpoint

| Need | Route | Integration connection |
|---|---|---|
| Network scanner offers eSCL | Direct device | Scanner host, advertised port/TLS and `rs` path |
| Printer accepts the document's format | Direct IPP | Printer host, advertised port/TLS and `rp` path |
| Printer needs a driver or format conversion | Configured CUPS queue or Printer Application | Bridge host and that queue's exact IPP endpoint |
| SANE-supported scanner without usable eSCL | AirSane | Bridge host, advertised eSCL endpoint |
| USB device implements IPP-over-USB | ipp-usb | Bridge host and its assigned IPP/eSCL service ports/paths |

Discovery may not cross VLANs. Manual configuration uses the same advertised
endpoint. A bridge's `localhost` refers to the bridge machine, not a different
Home Assistant host/container. Keep the full queue/resource path and port,
including for IPv6. Print duplex and scan duplex are independent capabilities.

## CUPS / Printer Application recipe

1. Create a functioning queue on the bridge with the appropriate driver/filter
   or Printer Application. Confirm the bridge can print locally first.
2. Share that queue to the Home Assistant host. A CUPS example is
   `ipp://bridge.local:631/printers/office`; set integration host `bridge.local`,
   port `631`, path `/printers/office`, TLS off for this plain-IPP example.
3. For a Printer Application, use its advertised endpoint instead of assuming
   the CUPS path. Verify PDF/JPEG/PNG support on the queue you actually select.
4. Confirm authentication works with the integration's HTTP Basic support. A queue
   requiring Kerberos, browser sign-in or another unsupported method needs a
   compatible policy or another endpoint. Use TLS when available for credentials.
5. Test one small document, then copies, both bindings, paper and tray. A successful
   Validate-Job does not prove the installed conversion filter will print correctly.

CUPS shares via IPP/DNS-SD and supports queue-specific policies; the bridge owns
rendering/spooling and its availability affects printing.
[Official CUPS sharing guide](https://openprinting.github.io/cups/doc/sharing.html).

## AirSane recipe

1. On the bridge, install a SANE backend that can see and operate the scanner.
   Confirm discovery as the service user (`scanimage -L`) and a local scan.
2. Install AirSane using its platform instructions. Its documented default port
   is 8090. Permit the HA host in its access rules and firewall.
3. Prefer its discovered eSCL advertisement. For manual setup use the bridge
   host, actual port/TLS and advertised resource path. The compatible first
   scanner path is normally `eSCL`; do not assume that path for every scanner.
4. Verify glass/feeder, colors and DPI. This integration selects one scanner
   endpoint; AirSane's ability to publish several does not add multi-scanner
   routing to this integration.

Capabilities and scan quality depend on the SANE backend. AirSane access files
control allowed addresses; do not assume browser login or new authentication
schemes are supported here. [AirSane documentation](https://github.com/SimulPiscator/AirSane).

## ipp-usb recipe

1. Confirm the USB device implements IPP-over-USB; this is not a generic USB driver.
2. Install ipp-usb on the computer attached to it. Use DNS-SD/service discovery to
   find the assigned port and each service path; never assume a particular port.
3. Its default exposure is local to the bridge. For a separate HA machine,
   deliberately configure reachable interfaces/access controls. Do not enter
   the bridge's loopback address into a remote HA installation.
4. Configure print and scan independently from their advertised endpoints, then
   verify capabilities and a small job. The proxy does not convert arbitrary
   documents into a printer language.

[ipp-usb documentation](https://github.com/OpenPrinting/ipp-usb) describes its HTTP
proxy, DNS-SD, persisted port allocation and loopback/default interface policy.

## Evidence, not blanket support claims

| Target | Evidence available on 2026-10-08 | Remaining check |
|---|---|---|
| HP Color LaserJet MFP M283fdw | Earlier physical glass/ADF/manual-duplex PDF tests; current read-only profile, PDF settings and Validate-Job checks | Physical run with this release; earlier four-sheet print confirmation |
| Local CUPS queue to that HP | Current client queried PDF settings and passed Validate-Job; typed collections parsed | Actual conversion/output through that queue |
| Brother family / Xerox B205-B215 / Ricoh matched models | Scoped recovery policies from sane-airscan source; synthetic retry/delay/cancel regressions | Device captures and physical hardware tests |
| JPEG/PNG-only eSCL profiles | Synthetic acquisition, dimension, malformed/oversize, cancellation and duplex-order tests | A physical image-only scanner |
| AirSane / ipp-usb | Documented route and manual endpoint support | Bridge/device instance not available for live testing |
| Automatic-duplex ADF | Existing simulation and capability selection tests | A scanner that physically scans both sides automatically |

No printer or scanner was started during this compatibility implementation's
live probes. Parser fixtures distinguish real redacted captures from synthetic data.

## Reporting a failure

Download integration diagnostics from Home Assistant. They redact credentials,
addresses, device IDs, names, filenames and storage/endpoint paths while retaining
capabilities, requested/effective settings and applied scanner policies. Review any
manually collected raw XML/IPP before sharing: it may contain identifying values.
Include model/firmware, direct or bridge route, source, color, DPI, file format,
selected settings, observed result and whether the printer accepted a job.

Do not repeat a submission whose acceptance is unknown. Check the device queue.
A failed/consumed scan batch is not automatically restarted. Automatic duplex
failure does not silently switch to a second manual scan of already consumed pages.

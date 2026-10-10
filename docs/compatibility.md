# Printer compatibility

[Documentation](README.md) · [Connection settings](installation.md) · [Troubleshooting](troubleshooting.md)

IPP Print connects to an IPP/2.0 printer or queue. The selected endpoint must
accept the actual document format; PDF/JPEG/PNG support varies by model and
queue. The integration does not provide a printer driver or convert documents.

## Tested devices and evidence

Evidence recorded through 2026-10-10. A community report or successful capability
query is useful evidence, but is not the same as a complete physical test.

| Device or route | Evidence | Limits / unverified work |
| --- | --- | --- |
| HP Color LaserJet MFP M283fdw | Locally verified PDF printing, copies, both duplex bindings, offline recovery and retained activity across restart. User confirmed a JPEG retry printed successfully. | The original intermittent JPEG settings failure's cause remains unconfirmed. PNG is not advertised by this device. |
| Local CUPS queue to that HP | Read PDF capabilities and passed Validate-Job, including typed collection parsing. | Actual conversion and physical output through that queue remain unverified. |
| Other IPP printers / Printer Applications | Protocol support and simulated parser/submission regressions. | Need model-, firmware- and queue-specific device reports. |
| ipp-usb | Endpoint configuration supported; route documented below. | No local bridge/device acceptance test. |

Report your model through the [device compatibility form](https://github.com/wleonhardt/ha-ipp-print/issues/new?template=device_compatibility.yml),
including successful setups. Share firmware, integration/HA versions, route and
which functions passed. [Collect diagnostics](troubleshooting.md#collect-diagnostics)
for failures. A report does not establish support for every model from that brand.

## Choose a connection route

| Situation | Route |
| --- | --- |
| Printer accepts your format | Connect directly using its advertised IPP/IPPS endpoint. |
| Printer needs a driver or conversion | Connect to a configured CUPS queue or Printer Application. |
| USB device implements IPP-over-USB | Connect to a separately managed ipp-usb bridge's IPP endpoint. |

A bridge is an optional service you manage separately. It exposes a compatible
protocol but does not guarantee every function of the attached device.

## Networks, paths and TLS

- Discovery may not cross VLANs. Manual setup uses the same advertised endpoint.
- A bridge's `localhost` points to the bridge machine, not your Home Assistant
  host/container. Use an address Home Assistant can reach.
- Preserve the full resource/queue path and actual port, including with IPv6.
  Do not assume that an administration web page is the protocol endpoint.
- TLS and port are separate choices. In live HP discovery checks, IPPS on port
  631 needed legacy ciphers while plain IPP on 631 did not. Secure connections
  never silently switch TLS off or enable legacy ciphers.
- Authentication support is HTTP Basic. A bridge requiring browser sign-in,
  Kerberos or another scheme needs a compatible endpoint/policy.

## CUPS and Printer Applications

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

## ipp-usb

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

For scanning through AirSane, see
[eSCL Scan compatibility](https://github.com/wleonhardt/ha-escl-scan/blob/main/docs/compatibility.md).

## Before relying on a new device

Test one small document first, then the modes you need. Record physical results
separately from discovered options. For scanning, verify source, page order and
orientation; for printing, verify format, copies, binding and paper/tray.

Do not resend a print whose acceptance is unknown without checking its queue.
A failed/consumed scan batch is not automatically restarted. See the maintainer
[compatibility follow-up](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/compatibility-follow-up-2026-10-09.md)
for historical tests and remaining hardware coverage.

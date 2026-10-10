# Installation and connection settings

[Documentation](README.md) · [Next: dashboard](dashboard.md)

## Install with HACS

1. In **HACS**, search for **IPP Print** and select **Download**.
2. Restart Home Assistant.
3. Add your printer under **Settings → Devices & services**.

[Open IPP Print in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=wleonhardt&repository=ha-ipp-print&category=integration).
Both this integration and its dashboard controls are included in the download.

## Add the device

**Discovered device:** select **Configure** on the discovered printer.
The connection is checked before the entry is saved. No document is printed
during this check.

**Manual setup:** choose **Add integration → IPP Print**. Use this when discovery
is unavailable, the device is on another network, or credentials are required.
Enter the hostname or IP address separately from the port and path.

| Field | Default | When to change it |
| --- | --- | --- |
| Hostname or IP | Required | Use the address reachable from Home Assistant, such as `printer.local`. |
| Port | `443` | Use the device's advertised port. Plain IPP commonly uses `631`; IPPS can also use `631`. |
| IPP path | `/ipp/print` | A CUPS queue typically uses `/printers/QUEUE`; use the exact advertised path. |
| Use TLS | On | Match the endpoint: on for IPPS/HTTPS, off for plain IPP. The port alone does not determine this. |
| User | `anonymous` | Also sent as the IPP requesting user. Set credentials if HTTP Basic authentication is required. |
| Password | Empty | Fill in only if the endpoint requires HTTP Basic authentication. |
| Verify TLS certificate | Off | Enable for an endpoint with a certificate trusted by Home Assistant. |
| Allow legacy cipher suites | Off | Enable only for a device that needs older TLS ciphers, such as some HP LaserJets. |

TLS encrypts the connection. **Verify TLS certificate** additionally checks the
server certificate; it is off by default to accommodate self-signed devices.
Legacy ciphers are an explicit per-device option and are never enabled automatically.

Change saved connection details through the integration's **Configure / Options**
action in **Settings → Devices & services**. Copies, paper and other job settings belong to the [card or print action](printing.md), not the connection form.

Repeat setup for each printer. Give each dashboard card its own **Current job** sensor so the destination is clear.
For bridges or network discovery problems, see [Compatibility](compatibility.md).

## Update

1. Wait for active uploads and print tracking to finish.
2. Open **HACS → IPP Print** and download the offered stable update.
3. Restart Home Assistant and refresh the dashboard.

The integration refreshes its card resource automatically. Existing dashboard
cards do not need to be recreated. Recent activity survives the restart; active printer-side jobs are not automatically resubmitted.

If files were previously copied into `custom_components` manually, HACS may not
track them as installed. Download the integration through HACS once, restart,
and check that HACS shows an installed version.

## Manual installation

1. Download the source archive for a [stable release](https://github.com/wleonhardt/ha-ipp-print/releases).
2. Copy its `custom_components/ipp_print` directory into
   `<config>/custom_components/ipp_print` on the Home Assistant host.
3. Restart Home Assistant, then follow **Add the device** above.

For manual updates, back up the existing directory and replace it with the
matching directory from the new release. Do not mix files from different releases.
HACS is the easier route for ongoing update notifications.

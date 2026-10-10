# Troubleshooting

[Documentation](README.md) · [Compatibility](compatibility.md)

## Start here

Check the printer's own screen and **Connection** entity in Home Assistant.
Connected means the protocol answers; it does not promise paper, readiness or
a successful job. Idle describes the integration's current job, not connectivity.

| Symptom | What to do |
| --- | --- |
| Device is not discovered | Discovery may not cross VLANs. Use [manual setup](installation.md#add-the-device) with the advertised host, port, path and TLS setting. |
| Setup cannot connect | Confirm Home Assistant can reach the endpoint, then check path, TLS and credentials. A working web management page may use a different port/path from IPP. |
| TLS handshake failure | If the device needs older ciphers, explicitly enable **Allow legacy cipher suites**. Do not enable it for unrelated connection errors. |
| Certificate verification error | Match **Verify TLS certificate** to the device's certificate/trust setup. This is separate from cipher compatibility. |
| Authentication failed | Check HTTP Basic credentials; browser login, Kerberos and other authentication methods are not supported. |
| Cannot read current format/paper settings | Check the connection and wait the stated retry interval. If the card says **No print job was submitted**, a new explicit attempt is safe after correcting the cause. Collect diagnostics before restarting. |
| Submission uncertain / Outcome unknown | Check the printer queue and output before resending. A timeout may happen after acceptance; unknown is not the same as failure. |
| Paper or tray prompt | Match the loaded paper to the printer's configured size/tray and confirm on the device. The existing job may already be queued; do not send it again. |
| Format not supported / IPP `0x040a` | Export to a supported format or use a conversion-capable queue. Renaming a file is not conversion. |
| Another document is being uploaded | Wait for that submission to finish. The limit is shared across printers, services and browser uploads. |
| Several printers configured | Select the correct Current job sensor on the native card, or set `entity`/choose a printer in the standalone card. |
| Options disabled before choosing a file | Expected: paper, tray, color and quality depend on the document format. |
| Job no longer updates after a restart | Active tracking is not restored. Check Recent activity and the printer queue; do not infer that the physical job was canceled. |

## Card does not load

For a persistent **Configuration error**, missing feature or missing controls:

1. Confirm the integration is loaded under **Settings → Devices & services**.
2. After a HACS update, restart Home Assistant and fully reload the dashboard.
3. Check the card's entity: it must be this integration's **Current job**
   sensor, not its Connection sensor or another printer integration's sensor.
4. Check **Settings → Dashboards → Resources** (Advanced Mode may be needed).
   The integration registers a single `/ipp_print/card-…js` module. Remove only
   obsolete manual duplicates if present; do not create another copy of the module.
5. If it persists, report the full message, integration/HA versions and browser
   or Companion App version. Include a screenshot if the message is truncated.

A short loading delay can resolve itself, but a repeated configuration error
should be investigated. If history expansion moves the neighboring card, use
[one Vertical stack per card](dashboard.md#put-scan-and-print-beside-each-other)
and **Rows: Auto**.

## Collect diagnostics

1. Open **Settings → Devices & services → IPP Print**.
2. Open the integration/device overflow menu and select **Download diagnostics**.
3. Include that file with a [bug or device report](https://github.com/wleonhardt/ha-ipp-print/issues/new/choose).

For intermittent format/settings errors, collect diagnostics **before reloading
the integration or restarting Home Assistant**. The bounded query evidence is
kept only in memory. It includes generic/per-format cache freshness and one
recent failure's category, time, duration and HTTP/IPP status, even after a later
successful lookup. Format-cache eviction can remove older records.

A blocked format/paper lookup also records that pre-upload attempt and
`job_may_exist: false`. This is not a record of every print failure. Diagnostics
do not contact the printer and exclude document bytes, filenames, credentials,
addresses and raw error text. Include the actual file format, paper, tray,
sides/copies, printer-screen message, and whether any output or queued job appeared.

For additional logs, merge this into `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ipp_print: debug
```

Restart to apply the YAML, reproduce once, then remove or disable the debug
setting. Review raw logs and manually collected protocol captures for private
values before sharing. Include device model/firmware, connection route (direct
or bridge), Home Assistant version and integration version.

## Limits that can stop a job

| Limit | Behavior |
| --- | --- |
| File size | 50 MiB per document. |
| Incoming HTTP upload | Five minutes; timeout means no job was submitted. |
| Simultaneous preparation/submission | One document across all printers and interfaces. |
| Recent activity | Ten outcomes per printer, seven days from submission; no stored documents. |

These limits do not require settings. See [printing and recovery](printing.md)
for the distinction between upload, acceptance and physical printing.

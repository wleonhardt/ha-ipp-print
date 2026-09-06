# IPP Print for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![Latest release](https://img.shields.io/github/v/release/wleonhardt/ha-ipp-print?sort=semver)](https://github.com/wleonhardt/ha-ipp-print/releases)
[![validate](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml/badge.svg)](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Print PDFs and images directly to any IPP-capable network printer (or CUPS
queue) from Home Assistant. Zeroconf discovery, a `print_file` action for
automations, a per-job sensor with live page progress, bus events, and a
one-tap Lovelace card. No driver layer, no filesystem queue.

> 💡 **Sister project:** for triggering scans on the same multifunction
> printers, see [**ha-escl-scan**](https://github.com/wleonhardt/ha-escl-scan)
> — same architecture (per-job sensor + Lovelace card + bus events) targeting
> eSCL / AirScan instead of IPP.

<p align="center">
  <img src="assets/card-idle.png" width="320" alt="Idle card" />
  <img src="assets/card-printing.png" width="320" alt="Printing card" />
  <br/>
  <img src="assets/card-complete.png" width="320" alt="Complete card" />
  <img src="assets/card-failed.png" width="320" alt="Failed card" />
</p>

## Why this exists

Home Assistant's built-in `ipp` integration is read-only — it polls a printer
for status sensors but cannot submit jobs. Vendor-specific integrations
(`hpprinter`, `epson`, …) are also read-only. Existing community workarounds
route through CUPS, AppDaemon, or shell-commands and don't give you proper
HA entities, per-job progress, or a clean UI.

`ipp_print` talks IPP directly:

- `Get-Printer-Attributes` once at setup (identity, supported formats, duplex)
- `Print-Job` to submit
- `Get-Job-Attributes` to poll progress (every 1.5 s while a job is active)
- `Cancel-Job` for the cancel button

## Features

- 🖨️ Direct IPP submission — PDF, JPEG, PNG; any IPP printer or CUPS queue
- 🔎 Zeroconf discovery — printers show up under *Discovered* automatically
- 🤖 `ipp_print.print_file` action — print from automations, with copies + duplex
- 📊 Per-job sensor (`sensor.printer_current_job`) with live page progress
- 🔔 Bus events for state changes and completion
- 🛑 Cancel-Job support with a button on the card
- 🎨 Theme-aware Lovelace card with file picker, status text, and cancel UI
- 🔒 Authenticated upload endpoint at `/api/ipp_print/print`
- ⚙️ Config flow — no YAML required; device page with a link to the printer's web UI
- 🩺 Diagnostics download for bug reports
- 🔑 Works with the legacy ciphers some HP LaserJets ship with (opt-in)

## Requirements

- Home Assistant 2024.12 or newer
- A network printer that supports IPP/2.0 (most modern printers do), or a
  CUPS server
- The printer reachable from your HA host on port 80, 443, or 631

## Installation

### HACS (recommended)

IPP Print is in the HACS default store.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=wleonhardt&repository=ha-ipp-print&category=integration)

Or: HACS → search **IPP Print** → Download → restart Home Assistant.

### Manual

1. Copy `custom_components/ipp_print/` into your `<config>/custom_components/` directory
2. Restart Home Assistant

## Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ipp_print)

Printers advertising `_ipp._tcp` / `_ipps._tcp` appear under
**Settings → Devices & Services → Discovered**; confirm and you're done
(host, port, path, and TLS are taken from the advertisement).

Manual: **Settings → Devices & Services → Add Integration → IPP Print**

| Field | Notes |
|---|---|
| Hostname or IP | e.g. `printer.local` or `192.168.1.50` |
| Port | `443` for IPPS, `631` for IPP, `80` for HTTP |
| IPP path | Usually `/ipp/print`. CUPS queues use `/printers/<queue name>` |
| Use TLS | On for IPPS, off for plain IPP |
| User | Sent as `requesting-user-name`. Default `anonymous` is fine for most |
| Password | Only if the printer requires basic auth |
| Verify TLS | Off for self-signed certs (most consumer printers) |
| Allow legacy cipher suites | Enable if you see `SSLV3_ALERT_HANDSHAKE_FAILURE` in the logs (some HP LaserJets need this) |

The flow sends `Get-Printer-Attributes` before saving; a valid answer
confirms the network/auth path and fills in the device name, model, and
supported document formats.

## Adding the card to a dashboard

The integration registers the card globally — no `resources:` block needed.
It also appears in the card picker as **IPP Print Upload**.

```yaml
type: custom:ipp-print-upload-card
title: Print PDF                       # optional, defaults to "Print PDF"
entity: sensor.printer_current_job     # optional, only if you renamed the sensor
```

The card follows your active HA theme (`--primary-color` accent).

## Sensor + events

`sensor.printer_current_job`

| Field | Value |
|---|---|
| state | `idle` / `pending` / `pending-held` / `processing` / `processing-stopped` / `canceled` / `aborted` / `completed` |
| attributes.job_id | IPP-assigned integer |
| attributes.filename | Submitted filename |
| attributes.pages_done | `job-media-sheets-completed` (or `job-impressions-completed` fallback) |
| attributes.pages_total | `job-impressions` if the printer reports it |
| attributes.state_reasons | The printer's IPP `job-state-reasons` |
| attributes.submitted_at / finished_at | ISO timestamps |

Bus events you can trigger automations from:

- `ipp_print_job_state_changed` — every observed state change
- `ipp_print_job_completed` — once per terminal transition (completed / canceled / aborted)

Both carry the full job dict as `event.data`.

### Automation example

Notify when a job fails:

```yaml
automation:
  - alias: Print job failed
    triggers:
      - trigger: event
        event_type: ipp_print_job_completed
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.state in ['aborted', 'canceled'] }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >
            Print {{ trigger.event.data.filename }} {{ trigger.event.data.state }}
            ({{ trigger.event.data.state_reasons or 'no reason' }})
```

## Action: `ipp_print.print_file`

Print a file that lives on the Home Assistant host. The path must be under
`www/`, a media directory, or a directory listed in
`allowlist_external_dirs`.

| Field | Notes |
|---|---|
| `path` | Required. Absolute path, e.g. `/config/www/report.pdf` |
| `document_format` | Optional MIME type. Detected from content (PDF/JPEG/PNG) when omitted. `application/octet-stream` lets the printer auto-sense |
| `job_name` | Optional. Defaults to the file name |
| `copies` | Optional, 1–99 |
| `sides` | Optional: `one-sided`, `two-sided-long-edge`, `two-sided-short-edge` (checked against what the printer advertises) |

Returns `{job_id, filename, bytes, state}` when called with
`response_variable`.

```yaml
automation:
  - alias: Print the scan that just finished
    triggers:
      - trigger: event
        event_type: escl_scan_job_completed
    actions:
      - action: ipp_print.print_file
        data:
          path: "{{ trigger.event.data.path }}"
          sides: two-sided-long-edge
        response_variable: job
      - action: notify.mobile_app_phone
        data:
          message: "Sent to printer as job {{ job.job_id }}"
```

## REST API

The integration registers two HA HTTP views (both require a Home Assistant
auth token; any authenticated user may call them):

### `POST /api/ipp_print/print`

Multipart form-data, field name `file` (PDF, JPEG, or PNG — identified from
content). Returns:

```json
{"ok": true, "filename": "doc.pdf", "bytes": 13264, "job_id": 42, "state": "pending"}
```

Example with a long-lived access token:

```bash
curl -H "Authorization: Bearer $HA_TOKEN" -F file=@doc.pdf http://homeassistant.local:8123/api/ipp_print/print
```

### `POST /api/ipp_print/cancel`

JSON body `{"job_id": 42}`. Returns `{"ok": true, "job_id": 42}` on success.
Only job-ids submitted through this integration can be cancelled (unknown
ids return 404).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SSLV3_ALERT_HANDSHAKE_FAILURE` in the log | Printer only offers non-PFS ciphers. Enable **Allow legacy cipher suites**. |
| `authentication failed (check user/password)` | Printer requires HTTP basic auth, or credentials are wrong. |
| Job shows `aborted` with `printer-unreachable` | Printer stopped answering mid-job (power, Wi-Fi). Tracking gives up after ~10 failed polls. |
| Card stuck on "Submitted" | Sensor renamed? Set `entity:` on the card. |
| `printer does not accept image/png (supported: …)` | Checked against the printer's advertised formats. Convert, or pass `document_format: application/octet-stream` via the action if the printer auto-senses. |
| `printer refused job (ipp_status=0x040a)` | `client-error-document-format-not-supported` — printer does not accept that format natively. |
| Printer not discovered | It must advertise `_ipp._tcp`/`_ipps._tcp` on the same L2 network as HA. Add it manually otherwise. |

Attach a diagnostics download (device page → ⋮ → Download diagnostics) to
bug reports; it includes the printer's advertised capabilities with the
password redacted.

Enable debug logging for the wire-level detail:

```yaml
logger:
  logs:
    custom_components.ipp_print: debug
```

## Caveats

- **No printer driver layer.** Document bytes go straight to the printer
  with their MIME type. The printer must understand that format natively
  (almost all modern printers do PDF and JPEG; PNG varies). Point the
  integration at a CUPS queue if you need driver-side conversion.
- **50 MiB upload cap.** Open an issue if you need more.
- **Single printer per install.** The endpoints and sensor are bound to one
  configured printer (`single_config_entry`). Multiple submissions queue at
  the printer side; the sensor reflects the *most recent* job.
- **HP LaserJets:** several models (M283fdw, M227, etc.) only offer non-PFS
  TLS ciphers. Enable "Allow legacy cipher suites" in the config flow.

## Development

```
custom_components/ipp_print/
├── __init__.py        # entry setup, HTTP views, lovelace resource sync
├── config_flow.py     # user + zeroconf + options flows
├── coordinator.py     # background IPP polling
├── const.py
├── diagnostics.py
├── manifest.json
├── printer.py         # IPP wire format + client
├── sensor.py          # sensor.printer_current_job + device
├── services.yaml      # ipp_print.print_file
├── static/card.js     # the Lovelace card
├── strings.json
└── translations/en.json
```

Run the checks locally:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest tests -q
.venv/bin/ruff check custom_components tests
npm ci && npm run test:card      # jsdom tests for card.js
```

Releases: bump `manifest.json` version, add a `CHANGELOG.md` section, push a
`vX.Y.Z` tag. The release workflow verifies the version matches and publishes
the GitHub release from the changelog section.

Pull requests welcome.

## License

MIT

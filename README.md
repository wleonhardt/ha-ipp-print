# IPP Print for Home Assistant

A Home Assistant custom integration that prints PDFs directly to any IPP-capable
network printer and surfaces **per-job state** through a sensor — including
live page progress, completion, cancellation, and the printer's own error
reasons.

Ships with a companion Lovelace card so a "Print PDF" tile on your dashboard
is a single tap.

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

- `Print-Job` to submit
- `Get-Job-Attributes` to poll progress (every 1.5 s while a job is active)
- `Cancel-Job` for the cancel button

Job state flows into `sensor.printer_current_job` (state + filename + pages_done
+ pages_total + state_reasons + timestamps), and `ipp_print_job_state_changed` /
`ipp_print_job_completed` events fire on the bus so you can wire up automations.

## Features

- 🖨️ Direct IPP submission — no CUPS, no Samba, no filesystem queue
- 📊 Per-job sensor (`sensor.printer_current_job`) with live page progress
- 🔔 Bus events for state changes and completion
- 🛑 Cancel-Job support with a button on the card
- 🎨 Lovelace card with file picker, status text, and cancel UI
- 🔒 Bearer-token authenticated upload endpoint at `/api/ipp_print/print`
- ⚙️ Config flow — no YAML required
- 🔑 Works with the legacy ciphers some HP LaserJets ship with (opt-in)

## Requirements

- Home Assistant 2024.8 or newer
- A network printer that supports IPP/2.0 (most modern printers do)
- The printer reachable from your HA host on port 80, 443, or 631

## Installation

### Via HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/wleonhardt/ha-ipp-print` as type **Integration**
3. Install **IPP Print**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/ipp_print/` into your `<config>/custom_components/` directory
2. Restart Home Assistant

## Setup

After install, add the integration:

**Settings → Devices & Services → Add Integration → IPP Print**

Fill in:

| Field | Notes |
|---|---|
| Hostname or IP | e.g. `printer.local` or `192.168.1.50` |
| Port | `443` for IPPS, `631` for IPP, `80` for HTTP |
| Use TLS | On for IPPS, off for plain IPP |
| User | Sent as `requesting-user-name`. Default `anonymous` is fine for most |
| Password | Only if the printer requires basic auth |
| Verify TLS | Off for self-signed certs (most consumer printers) |
| Allow legacy cipher suites | Enable if you see `SSLV3_ALERT_HANDSHAKE_FAILURE` in the logs (some HP LaserJets need this) |

The flow does a quick IPP probe before saving — any IPP response confirms the
network/auth path works.

## Adding the card to a dashboard

The integration registers the card globally — no `resources:` block needed.

```yaml
type: custom:ipp-print-upload-card
title: Print PDF        # optional, defaults to "Print PDF"
```

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

## REST API

The integration registers two HA HTTP views (both `requires_auth = true`):

### `POST /api/ipp_print/print`

Multipart form-data, field name `file`. Returns:

```json
{"ok": true, "filename": "doc.pdf", "bytes": 13264, "job_id": 42, "state": "pending"}
```

### `POST /api/ipp_print/cancel`

JSON body `{"job_id": 42}`. Returns `{"ok": true, "job_id": 42}` on success.

## Caveats

- **No printer driver layer.** This sends the document bytes straight to the
  printer with `document-format: application/pdf`. Your printer must understand
  PDF natively (almost all modern printers do; some old/cheap models don't).
- **Hardcoded 50 MiB upload cap.** Open an issue if you need more.
- **Single sensor per entry.** Multiple submissions queue at the printer side;
  the sensor reflects the *most recent* job. Concurrent independent tracking
  is on the roadmap.
- **HP LaserJets:** several models (M283fdw, M227, etc.) only offer non-PFS
  TLS ciphers. Enable "Allow legacy cipher suites" in the config flow.

## Development

```
custom_components/ipp_print/
├── __init__.py        # entry setup, HTTP views, lovelace resource sync
├── config_flow.py     # UI flow + options flow
├── coordinator.py     # background IPP polling
├── const.py
├── manifest.json
├── printer.py         # IPP wire format + client
├── sensor.py          # sensor.printer_current_job
├── static/card.js     # the Lovelace card
├── strings.json
└── translations/en.json
```

Pull requests welcome.

## License

MIT

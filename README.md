# IPP Print for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![Latest release](https://img.shields.io/github/v/release/wleonhardt/ha-ipp-print?sort=semver)](https://github.com/wleonhardt/ha-ipp-print/releases)
[![validate](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml/badge.svg)](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Print PDFs and images directly to any IPP-capable network printer (or CUPS
queue) from Home Assistant. Zeroconf discovery, a `print_file` action for
automations, a per-job sensor with live page progress, bus events, and a
Lovelace card with file selection and an explicit Print action. No driver layer,
no filesystem queue.

> 💡 **Sister project:** for triggering scans on the same multifunction
> printers, see [**ha-escl-scan**](https://github.com/wleonhardt/ha-escl-scan)
> — same architecture (per-job sensor + Lovelace card + bus events) targeting
> eSCL / AirScan instead of IPP.

<p align="center">
  <img src="assets/card-pair.png" width="390" alt="Matching scan and print cards with a Two-sided switch and explicit actions" />
</p>

## Why this exists

Home Assistant's built-in `ipp` integration is read-only — it polls a printer
for status sensors but cannot submit jobs. Vendor-specific integrations
(`hpprinter`, `epson`, …) are also read-only. Existing community workarounds
route through CUPS, AppDaemon, or shell-commands and don't give you proper
HA entities, per-job progress, or a clean UI.

`ipp_print` talks IPP directly:

- `Get-Printer-Attributes` at setup and through a shared on-demand capability
  cache; explicit sides jobs also read current default paper before submission
- `Print-Job` to submit
- `Get-Job-Attributes` to poll progress (every 1.5 s while a job is active)
- `Cancel-Job` for the cancel button

## Features

- 🖨️ Direct IPP submission — PDF, JPEG, PNG; any IPP printer or CUPS queue
- 🔎 Zeroconf discovery — printers show up under *Discovered* automatically
- 🤖 `ipp_print.print_file` action — print from automations, with copies + duplex
- 📊 Per-job sensor (`sensor.<printer>_current_job`) with live page progress
- 🖨️🖨️ Several printers per install — one device each, pick by sensor
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
title: Print                           # optional, defaults to "Print"
entity: sensor.office_current_job      # the printer's job sensor; optional with one printer
```

With one printer configured the card finds its sensor by itself. With
several, add one card per printer and set `entity:` to that printer's job
sensor — the card uploads to the printer that sensor belongs to.

Choose a PDF, JPEG or PNG, check its filename, then press **Print**. Selecting a
file keeps it in your browser until Print is pressed. **Replace** changes the
selection and **Clear** discards it; canceling the file picker preserves your
previous selection. File changes and repeated submissions are disabled while
submitting or following the active print.

The browser releases the selected file after acceptance. If a connection fails
and submission is uncertain, check the printer queue before choosing the file
again: it may already have printed. Known validation errors retain the selection.

The card shares the scan card's neutral theme surface, native icons, readable
text, accessible buttons and sizing. Existing card types and explicit titles
continue to work. Add each card directly to a Sections grid for native sizing,
or keep your horizontal stack. See [paired Sections example](examples/dashboard-sections.yaml).
Copies and duplex are available through the print service and upload API;
upload-card settings controls are the next phase.

## Sensor + events

`sensor.<printer>_current_job` — one per configured printer, named after the
device (installs from before 0.4.0 keep `sensor.printer_current_job`).

| Field | Value |
|---|---|
| state | `idle` / `pending` / `pending-held` / `processing` / `processing-stopped` / `canceled` / `aborted` / `completed` / `unknown` |
| attributes.job_id | IPP-assigned integer |
| attributes.filename | Submitted filename |
| attributes.pages_done | `job-impressions-completed` (or `job-media-sheets-completed` fallback) |
| attributes.pages_total | `job-impressions` if the printer reports it |
| attributes.state_reasons | The printer's IPP `job-state-reasons` |
| attributes.submitted_at / finished_at | ISO timestamps |

Bus events you can trigger automations from:

- `ipp_print_job_state_changed` — every observed state change
- `ipp_print_job_completed` — once per terminal transition (completed / canceled / aborted / unknown)

Both carry the full job dict plus `config_entry_id` as `event.data`, so
automations can distinguish printers with the same job ID. `unknown` means
the printer purged a job before its final outcome could be observed; it is
not proof of successful printing. The sensor mirrors the latest submitted
job; when another submission replaces it, the card explains that live
progress for the previous job is no longer available. Bus events continue
for every tracked job. Missing or malformed job attributes are
retried and eventually reported as `aborted` / `printer-unreachable`.
A submission timeout or invalid printer response can occur after the printer
has accepted the document. Check the printer queue before retrying to avoid
duplicate output. In-memory tracking is reset when the integration reloads
or Home Assistant restarts; that does not cancel printer-side jobs.

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
        value_template: "{{ trigger.event.data.state in ['aborted', 'canceled', 'unknown'] }}"
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
| `copies` | Optional, 1–99; checked against the printer’s advertised maximum |
| `sides` | Optional: `one-sided`, `two-sided-long-edge`, `two-sided-short-edge` (checked against what the printer advertises) |
| `target` | The printer's job sensor or device. Optional with one printer configured; required with several |

Returns `{job_id, filename, bytes, state}` when called with
`response_variable`.

Explicit copies/sides require IPP attribute fidelity: the printer must accept
the requested settings or reject the job, rather than silently substituting
its defaults. When `sides` is set, the integration also sends the printer's
advertised default paper size, queried again for each print with explicit
sides. No paper-size field is required. This fixes HP firmware that ignores
duplex when paper size is implicit and picks up changed printer defaults
automatically. Load paper matching the printer's configured size. If the
current settings cannot be read, the action fails before submitting a job.

```yaml
automation:
  - alias: Print the scan that just finished
    triggers:
      - trigger: event
        event_type: escl_scan_job_completed
    actions:
      - action: ipp_print.print_file
        target:
          entity_id: sensor.office_current_job   # omit with a single printer
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
content). Send exactly one `file` field and at most one each of `entity_id`,
`copies` and `sides`. Metadata is limited to 512 bytes per field; unexpected
or duplicate fields are rejected with 400. With several printers
configured, add a text field `entity_id`
holding the target printer's job sensor (`400` without it). Returns:

```json
{"ok": true, "filename": "doc.pdf", "bytes": 13264, "job_id": 42, "state": "pending"}
```

Example with a long-lived access token:

```bash
curl -H "Authorization: Bearer $HA_TOKEN" -F file=@doc.pdf http://homeassistant.local:8123/api/ipp_print/print
# several printers:
curl -H "Authorization: Bearer $HA_TOKEN" -F entity_id=sensor.office_current_job -F file=@doc.pdf http://homeassistant.local:8123/api/ipp_print/print
# explicit copies and binding:
curl -H "Authorization: Bearer $HA_TOKEN" -F copies=2 -F sides=two-sided-long-edge -F file=@doc.pdf http://homeassistant.local:8123/api/ipp_print/print
```

Copies must be ASCII decimal integers from 1 to 99, within the printer's
advertised maximum. Fractions, booleans, signs and whitespace are rejected.
Sides accepts `one-sided`, `two-sided-long-edge` or `two-sided-short-edge`.
Omitting either leaves that option to the printer. An explicit sides request
reads current paper defaults immediately before submission; if that read fails,
no job is submitted. This validation is shared with `ipp_print.print_file`.

### `GET /api/ipp_print/capabilities?entity_id=sensor.office_current_job`

Authenticated and readable by ordinary dashboard users while no job is active.
The target is optional with one loaded printer, required with several.
Returns `schema_version: 1`, the resolved sensor, bounded identity,
`supported.formats`, `supported.sides`, `supported.copies_max`,
`request_options` and integration `limits`. Supported formats are restricted
to the upload formats (PDF/JPEG/PNG); automatic format detection is respected.
No printer address, credentials or raw IPP attributes are exposed.

The per-device cache refreshes on demand after 15 minutes, serializes simultaneous
reads and backs off failures for five minutes. Fetches are bounded to 15 seconds.
`status` is `fresh`, `stale` (last success retained) or `unknown`, with
`fetched_at`, `attempted_at`, `refresh_after_seconds` and a generic
`refresh_failed` error. This describes capability freshness, not whether the
printer is currently online. `null` means unreported; an empty supported list
means no integration-supported choices were advertised. Job sensor attributes
remain unchanged and capability reads do not create recorder updates.

Check schema/version and accepted fields before exposing options; older releases
return 404 for this endpoint. Unknown targets return 404, malformed/ambiguous
queries 400 and an unloaded integration 503. See the
[capability contract](plans/decisions/2026-10-08-capability-api.md).

### `POST /api/ipp_print/cancel`

JSON body `{"job_id": 42}`, plus `"entity_id"` (the printer's job sensor)
when several printers are configured — job ids are only unique per printer.
Returns `{"ok": true, "job_id": 42}` on success. Only job-ids submitted
through this integration can be cancelled (unknown ids return 404).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SSLV3_ALERT_HANDSHAKE_FAILURE` in the log | Printer only offers non-PFS ciphers. Enable **Allow legacy cipher suites**. |
| `authentication failed (check user/password)` | Printer requires HTTP basic auth, or credentials are wrong. |
| Job shows `aborted` with `printer-unreachable` | Printer stopped answering mid-job (power, Wi-Fi). Tracking gives up after ~10 failed polls. |
| Card stuck on "Submitted" | Sensor renamed? Set `entity:` on the card. |
| Card says `several printers configured; set entity:` | More than one printer is set up. Add `entity:` with that printer's job sensor. |
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
- **One tracked job per printer.** Multiple submissions queue at the
  printer side; each printer's sensor reflects its *most recent* job.
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
├── sensor.py          # per-printer "Current job" sensor + device
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

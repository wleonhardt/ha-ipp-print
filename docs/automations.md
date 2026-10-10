# Actions, entities and events

[Documentation](README.md) · [HTTP API](api.md)

Use **IPP Print: Print file** (`ipp_print.print_file`) to print a file already
on the Home Assistant host. No access token is needed for this action.

## Print a local file

```yaml
action: ipp_print.print_file
target:
  entity_id: sensor.office_current_job
data:
  path: /media/documents/report.pdf
  copies: 1
  sides: one-sided
response_variable: job
```

Use the actual **Current job** sensor from the printer's device page. The target
can also be its device; it is optional with one configured printer and required
with several. `response_variable` receives the submission result, including
`job_id`, `filename`, `bytes`, `state` and `submitted_at`; it does not wait for
physical printing to complete.

The path must be readable by Home Assistant and inside `www/`, a configured media
directory, or `allowlist_external_dirs`. For a separate folder, merge this into
`configuration.yaml` and restart Home Assistant:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /srv/documents
```

Use a private media/allowlisted directory for private documents. Home Assistant's
`www/` directory is web-served. Paths refer to the Home Assistant host/container,
not the computer or phone running the dashboard.

## Action fields

| Field | Meaning |
| --- | --- |
| `path` | Required absolute path. Maximum file size: 50 MiB. |
| `document_format` | Optional MIME type; detects PDF/JPEG/PNG from content when omitted. `application/octet-stream` requests device auto-sensing. It does not convert the file. |
| `job_name` | Optional name shown to the printer; defaults to the filename. |
| `copies` | Optional integer 1–99, within the printer's advertised maximum. |
| `sides` | `one-sided`, `two-sided-long-edge`, or `two-sided-short-edge`. |
| `media` | Advertised paper keyword, such as `iso_a4_210x297mm`. |
| `media_source` | Advertised tray keyword, such as `tray-1`. |
| `color_mode` | Advertised mode, such as `monochrome` or `color`. |
| `quality` | Advertised value: 3 (draft), 4 (normal), or 5 (best). |

Omitted print options use device defaults. Explicit choices are validated;
paper and tray are checked together. An explicit `sides` request with no `media`
refreshes the printer's default paper before submission. See
[settings and recovery](printing.md#choose-print-settings).

Only one document can be prepared/submitted at a time across this action and
HTTP/card uploads, including different printers. Concurrent requests fail busy;
they are not queued or resent. A submission error may occur after device acceptance.
Check the printer queue before retrying an uncertain outcome.

## Print a completed scan

First enable eSCL Scan's [copy-to-folder option](https://github.com/wleonhardt/ha-escl-scan/blob/main/docs/scanning.md#save-scans-to-a-folder)
with a folder such as `/media/scans` that Home Assistant is allowed to read.
This example prints every successful folder copy. Use a folder whose files will
remain available; a Paperless consume folder may remove them before Print reads them.

Paste this as one automation in the automation editor's YAML mode. Replace the
printer sensor with yours:

```yaml
alias: Print completed scans
triggers:
  - trigger: event
    event_type: escl_scan_completed
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.state == 'completed'
         and trigger.event.data.copied_to }}
actions:
  - action: ipp_print.print_file
    target:
      entity_id: sensor.office_current_job
    data:
      path: "{{ trigger.event.data.copied_to }}"
      copies: 1
      sides: one-sided
mode: queued
max: 5
```

The correct Scan event is `escl_scan_completed`. Its local file fields are
`file_path` and `copied_to`; this example uses the persistent copy rather than
allowlisting Scan's private storage. The condition excludes failed/canceled scans
and copy failures. The automation queue does not retry failed print actions.

## Notify when printing needs attention

```yaml
alias: Notify about unsuccessful print jobs
triggers:
  - trigger: event
    event_type: ipp_print_job_completed
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.state in ['aborted', 'canceled', 'unknown'] }}"
actions:
  - action: notify.mobile_app_phone
    data:
      message: >-
        Print {{ trigger.event.data.filename }}: {{ trigger.event.data.state }}.
        {{ trigger.event.data.state_reasons or 'Check the printer.' }}
mode: queued
```

Replace the notification action with your phone's action.

## Entities and events

Each configured printer has a **Current job** sensor and a **Connection** binary
sensor. New job sensor IDs derive from the device name; older installations can
retain `sensor.printer_current_job`. Connection means IPP is reachable, not that
paper, toner or the output tray is ready.

Current job states: `idle`, `pending`, `pending-held`, `processing`,
`processing-stopped`, `canceled`, `aborted`, `completed`, `unknown`.

| Event | When it fires |
| --- | --- |
| `ipp_print_job_state_changed` | An observed job state change. |
| `ipp_print_job_completed` | A terminal transition: `completed`, `canceled`, `aborted` or `unknown`. |

Both carry the job record plus `config_entry_id` in `event.data`. Job IDs are
unique only within a printer: filter by `config_entry_id` when distinguishing
several printers. `unknown` is not proof of success; tracking ended before a
final outcome could be established.

| Field | Meaning |
| --- | --- |
| `job_id`, `state` | Printer-assigned ID and observed job state. |
| `filename`, `bytes` | Submitted document name and byte count. |
| `pages_done`, `progress_unit` | Completed impressions (printed sides), sheets, or unknown if no counter is available. |
| `pages_total` | Printer-reported impressions total when matching completed impressions exist; it may change while rendering. |
| `state_reasons`, `warning` | Printer reasons and any submission/settings warning. |
| `requested_settings` | Explicit settings supplied for the job. |
| `submitted_at`, `finished_at` | ISO timestamps; finish time is null until terminal. |

The sensor additionally exposes `recent_activity` (up to ten seven-day records,
excluded from Recorder) and `device_connection` (`state`, `checked_at`,
`last_success_at`, `next_check_at`). These are not part of the event payload.
Reachability checks normally run every 60 seconds, back off to five minutes on
failure, and have a ten-second deadline; they do not print a test document.

The sensor follows the newest submitted job while events continue for other
tracked jobs. A reload/restart stops active tracking; it does not cancel jobs
already accepted by the printer. See [recent activity](printing.md#recent-activity-and-restarts).

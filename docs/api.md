# HTTP API

[Documentation](README.md) · [Home Assistant actions and events](automations.md)

Use the `ipp_print.print_file` action for files already on the Home Assistant
host. The HTTP endpoints support external clients and dashboard uploads. All
require Home Assistant authentication; ordinary authenticated users may call them.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/ipp_print/capabilities` | Read generic or format-specific settings. |
| POST | `/api/ipp_print/print` | Upload and submit one document. |
| POST | `/api/ipp_print/cancel` | Cancel an integration-tracked job. |

Use the printer's **Current job** sensor as `entity_id`. It is optional with
one loaded printer and required with several. IPP job IDs alone do not identify
a printer.

## Read capabilities

`GET /api/ipp_print/capabilities?entity_id=sensor.office_current_job&document_format=image%2Fjpeg`

`document_format` is optional: `application/pdf`, `image/jpeg`, or `image/png`.
Schema version 1 includes the resolved sensor, bounded identity, queried format,
`defaults`, `supported`, integration `limits` and `request_options`.

Supported settings include formats, sides, copies maximum, paper, ready paper,
trays, colors and quality. `auto_sensing` is separate: advertising octet-stream
alone does not establish upload support for PDF/JPEG/PNG. No addresses,
credentials or raw IPP attributes are returned. Routine queries omit the
potentially large `media-col-database` attribute.

Check `schema_version` and `request_options` before exposing controls. `null`
means unreported; an empty list means no integration-supported choices were
advertised. The cache refreshes on demand after 15 minutes, shares concurrent
refreshes, and backs off failures for five minutes. Fetches have a 15-second
deadline. `status` is `fresh`, `stale` (previous success retained), or `unknown`;
`fetched_at`, `attempted_at`, `refresh_after_seconds` and `refresh_failed`
describe cache freshness, not current device reachability.

Invalid/ambiguous queries return 400; unknown targets 404; an unloaded
integration 503. Capability reads do not submit a document.

## Upload and print

`POST /api/ipp_print/print` accepts multipart form data:

| Field | Value |
| --- | --- |
| `file` | Exactly one PDF, JPEG or PNG, identified from content. Maximum 50 MiB. |
| `entity_id` | Target printer's job sensor; required with several printers. |
| `copies` | Optional ASCII decimal integer 1–99, within the device limit. |
| `sides` | `one-sided`, `two-sided-long-edge`, or `two-sided-short-edge`. |
| `media`, `media_source`, `color_mode` | Advertised paper, tray and color keywords. |
| `quality` | `3`, `4`, or `5`, if advertised. |

Send each field at most once. Unknown or duplicate fields return 400. Metadata
fields are limited to 512 bytes each; excess file/field size returns 413.
Copies reject fractions, signs, booleans and surrounding whitespace. Omitted
options use device defaults; an explicit sides request with no paper choice
refreshes current default paper before submission.

For an external client, set `HA_URL` to your Home Assistant base URL and
`HA_TOKEN` to an access token kept outside scripts and logs:

```sh
curl --fail-with-body \
  -H "Authorization: Bearer $HA_TOKEN" \
  -F "entity_id=sensor.office_current_job" \
  -F "file=@document.pdf" \
  -F "copies=1" \
  -F "sides=one-sided" \
  "$HA_URL/api/ipp_print/print"
```

Success returns `ok`, `filename`, `bytes`, `job_id`, `submitted_at`, `state`,
and any warning. Acceptance is not proof of physical completion: follow the
sensor/events. A settings check can reject the request before document upload.

## Errors and retry decisions

| Result | Client response |
| --- | --- |
| 400 / 413 / 415 | Correct the malformed request, size or unsupported format. |
| 409 busy | Another document is being prepared/submitted. Wait, then make a new explicit request. |
| 408 upload timeout | The incoming upload exceeded five minutes; no job was submitted. |
| Submission error with `job_may_exist: false` | No job could have been accepted. Fix the cause before a new explicit attempt. |
| Submission error with `job_may_exist: true` | Check the printer queue/output before resending. |
| Lost response or ambiguous error | Treat acceptance as unknown; do not automatically resend. |

Error bodies provide a human-readable `message`. `job_may_exist` is provided
for submission failures and busy/upload-timeout responses; do not assume every
validation response includes it. Busy/timeouts close the upload connection.
The five-minute upload deadline ends before printer validation/submission.

All printers and the print-file action share one document preparation/submission
slot. There is no automatic print queue or resend. A new explicit submission
may retry a transient settings lookup once after 30 seconds; another failure
returns to five-minute backoff. This exception does not shorten ordinary
capability-read backoff or retry the document.

## Cancel

`POST /api/ipp_print/cancel` takes JSON:

```json
{"entity_id":"sensor.office_current_job","job_id":42,"submitted_at":"2026-10-10T12:00:00+00:00"}
```

`job_id` must be an integer from 1 to 2147483647. `submitted_at` is optional;
when supplied, use the exact value from the original response to guard against
reuse of an old queue ID. Only jobs submitted and still known by this
integration may be canceled. Unknown IDs return 404; a refused cancel returns
502. Success returns `{"ok":true,"job_id":42}`.

The detailed cache contract is in the maintainer
[capability decision](../plans/decisions/2026-10-08-capability-api.md).

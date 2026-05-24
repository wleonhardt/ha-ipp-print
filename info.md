# IPP Print

Print PDFs directly to any IPP-capable network printer from Home Assistant,
with a per-job sensor and a companion Lovelace card.

- `sensor.printer_current_job` mirrors the printer-side job state in real time
  (pending → processing → completed/aborted/canceled) with `pages_done`,
  `pages_total`, and the printer's own `state_reasons` as attributes.
- Bus events: `ipp_print_job_state_changed` and `ipp_print_job_completed`.
- `POST /api/ipp_print/print` accepts multipart PDF uploads, returns the
  printer-assigned `job_id` synchronously.
- `POST /api/ipp_print/cancel` cancels by job_id.

After install: **Settings → Devices & Services → Add Integration → IPP Print**.

See README for the full configuration and example dashboard card.

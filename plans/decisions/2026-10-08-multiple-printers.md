# 2026-10-08 — Multiple printers per install

## Context

Issue #7: users with two printers cannot add a second config entry
(`single_config_entry: true`) and the HTTP views / service always route to
"the" entry. The sensor also hardcodes `entity_id = sensor.printer_current_job`.

## Decision

- Drop `single_config_entry`; one entry = one printer = one device.
- The job sensor is the routing handle everywhere. Its entity_id is derived by
  HA from the device name (`sensor.<printer>_current_job`), like any other
  integration. Existing installs keep `sensor.printer_current_job` because the
  entity registry already stores it under the same unique_id.
- `ipp_print.print_file` takes a standard `target:` (entity/device/area);
  targets resolve to config entries via `async_extract_config_entry_ids`.
- `POST /api/ipp_print/print` accepts an optional `entity_id` form field;
  `POST /api/ipp_print/cancel` an optional `entity_id` JSON key.
- Omitting the target is still allowed when exactly one printer is configured
  (backward compatible); with several it is a 400 / ServiceValidationError.
- The card sends the sensor it follows as the target. With no `entity:` set
  it picks the single `ipp_print` sensor from `hass.entities`, and refuses to
  upload when several exist.

Rejected: a `printer:` card option with host or entry_id (users do not know
entry ids; entity_id already identifies the printer and is what the card
subscribes to anyway).

## Consequences

- New installs get `sensor.<name>_current_job`, not `sensor.printer_current_job`.
  README/examples updated; card no longer assumes the old id.
- Job ids are only unique per printer, so cancel needs the printer when more
  than one is configured.

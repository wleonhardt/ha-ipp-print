# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semver-ish `0.x`.

## [0.6.1] - 2026-10-08

### Fixed
- Clear the submitted filename when its tracked print job ends, including
  completion received immediately after submission. Late updates cannot clear
  the next document's filename, and clearing a new selection cannot revive it.

## [0.6.0] - 2026-10-08

### Added
- Authenticated, entity-scoped capability API with supported formats, binding
  modes, copy limits, request fields and fresh/stale/unknown cache metadata.
- Optional copies and sides on multipart uploads, using the same validation,
  target routing and fresh default-paper behavior as the print_file service.
- On-demand capability refresh after 15 minutes, serialized reads, five-minute
  failure backoff and a bounded fetch time; no background capability polling.

### Fixed
- Reject fractional/boolean/coerced copy counts in both upload and service calls.
  Duplicate, unknown and oversized multipart fields never submit a print.
- Ignore invalid advertised copy ranges instead of treating them as device limits.

## [0.5.0] - 2026-10-08

### Changed
- Stage PDF/JPEG/PNG files locally before an explicit Print action. Add Replace
  and Clear; canceling file selection keeps the previous document.
- Match the sister scan card with neutral theme surfaces, native icons, readable
  text, real buttons, keyboard focus and matching Sections sizing.
- Default title is Print. Existing explicit titles and card types remain valid.

### Fixed
- Recover slow-loading cards through Home Assistant's card wrapper so later
  state updates cannot reinsert a stale Configuration error beside the card.
- Prevent repeated submissions and file changes while a print is active.
- Release staged files after acceptance or an ambiguous submission. Explain
  that the printer queue must be checked before retrying; known validation
  rejections retain the selected file.
- Reject malformed success responses without a positive integer job ID.
- Register lifecycle callbacks before defining the custom element, so detached
  cards actually unsubscribe and remove open file pickers. Unlock file selection
  when tracking ends because the printer sensor disappears.

### Added
- Shared card contract, paired fixtures and direct Sections dashboard example.

## [0.4.1] - 2026-10-08

### Fixed
- Preserve configured ports in printer URLs and support IPv6 literals.
- Reject truncated/malformed IPP responses, invalid job IDs/states, error
  statuses carrying job attributes, and responses for the wrong job.
- A purged job with no observed final state reports `unknown` instead of
  claiming successful printing. Missing attributes are retried to the failure cap.
- Serialize cancellation with polling; only an accepted Cancel-Job records
  cancel intent. Refuse cancel for terminal jobs and tracking after unload.
- Match impression progress to impression totals, preserving zero counts.
- Send an explicit `copies: 1` rather than inheriting the printer's default,
  and reject copy counts above the advertised maximum.
- Read the printer's current default paper size for each print with explicit
  sides and send it automatically, without requiring user input,
  fixing HP duplex jobs that otherwise print on separate sheets. Require
  IPP attribute fidelity for explicit print settings so unsupported settings
  are rejected instead of silently substituted.

- Close card subscriptions and timers on disconnect, replacement, and early
  terminal updates; ignore stale progress/cancel callbacks.
- Keep progress for long jobs past 90 seconds, show paused printing with a
  cancel button, use live app auth after healing, and reject oversized files
  before upload.

- Reject duplicate/unexpected multipart fields and invalid cancel IDs;
  cap printer-selection fields and return 400 for malformed upload bodies.
- Bound local file reads even when a file grows after its initial size check;
  refuse special files and preserve extensions when truncating filenames.
- Serialize shared card route/resource registration, load stored Lovelace
  resources before editing them, and close sessions after setup failure or HA stop.
- Use the probed UUID at discovery confirmation; distinguish CUPS queues
  by path and check effective options when detecting duplicate endpoints.

- Avoid a second full-document allocation during IPP submission using a
  sized payload with backpressure. Preserve Content-Length for firmware compatibility.
- Bound printer responses to 1 MiB and reject HTTP redirects instead of
  implicitly replaying jobs against another endpoint.
- Update the vulnerable test-only `source-map-js` dependency; audit is clean.

- Prefer strict image signatures over incidental PDF text in image metadata.
- Prevent manual setup from duplicating legacy entries with host/port IDs;
  unload partially initialized sensor platforms on setup failure.
- Explain when a newer job replaces the card's followed sensor, and scope
  pending cancel requests to the job so they cannot block a later job.

- Explain that a timed-out submission or missing job ID may already have
  printed, so retrying without checking the queue can create duplicates.

### Added
- `config_entry_id` on job events identifies the printer when job IDs overlap.

## [0.4.0] - 2026-10-08

### Added
- **Multiple printers.** Add as many config entries as you have printers;
  each gets its own device and `Current job` sensor (#7).
- `ipp_print.print_file` takes a `target:` (job sensor or device) to pick
  the printer. `POST /api/ipp_print/print` accepts an `entity_id` form
  field and `POST /api/ipp_print/cancel` an `entity_id` JSON key for the
  same purpose. All of these stay optional while only one printer is
  configured; with several they are required (`400`).
- The card uploads to the printer whose job sensor it follows (`entity:`).
  With one printer it finds the sensor on its own; with several it asks
  you to set `entity:`.

### Changed
- The job sensor's entity_id is now derived from the device name
  (`sensor.<printer>_current_job`) instead of being fixed to
  `sensor.printer_current_job`. Existing installs keep their current id
  via the entity registry; new installs get the derived one.

## [0.3.0] - 2026-09-06

### Added
- **`ipp_print.print_file` action.** Print a file from the HA host
  (`www/`, media dirs, or `allowlist_external_dirs`) from any automation,
  with optional `copies`, `sides` (duplex), `job_name`, and
  `document_format`. Returns the job id via `response_variable`.
- **Zeroconf discovery.** Printers advertising `_ipp._tcp` / `_ipps._tcp`
  appear under *Discovered*; host, port, path, and TLS come from the
  advertisement.
- **JPEG and PNG** accepted alongside PDF (card, endpoint, action). Formats
  are checked against the printer's `document-format-supported` when known.
- **Configurable IPP path** (`/ipp/print` default) so CUPS queues
  (`/printers/<name>`) and non-standard printers work.
- **Device** per printer with name, make/model, and a link to its web UI,
  populated from `Get-Printer-Attributes`.
- **Diagnostics** download (redacted config, printer capabilities, current
  job).

### Changed
- Config-flow probe uses `Get-Printer-Attributes` instead of a fake
  `Get-Job-Attributes`; entry title and unique id now come from the printer
  (`printer-info` / `printer-uuid`) with host fallback.
- Card accepts images; theme-aware colors carried over from 0.2.0.

## [0.2.0] - 2026-09-06

### Fixed
- **Non-admin users got no print progress.** The card subscribed with
  `subscribe_trigger`, an admin-only websocket command. Now uses
  `subscribe_entities`, scoped to the job sensor, which any user may call.
- **Options flow crashed on Home Assistant 2024.8–2024.11** (`config_entry`
  property missing on `OptionsFlow`). Minimum supported version is now
  2024.12.
- **Unreachable printer no longer wedges the sensor.** A job whose printer
  stops answering is given up after 10 consecutive failed polls (with
  exponential backoff) and reported as `aborted` /
  `state_reasons: printer-unreachable`.
- **Reload/unload leaves nothing running.** Options changes cancel the old
  poll task and close the old printer session instead of leaking them.
- **Cancel then purge reported as `completed`.** Cancel intent is recorded;
  a job the printer purges right after Cancel-Job now reports `canceled`.
- **Self-healed card instances had no `hass`.** Upload/cancel/progress fall
  back to the app root's live `hass`, and auth-refreshing `fetchWithAuth` is
  preferred over a copied bearer token.
- Non-200 HTTP responses from the printer surface as a clear error
  (`authentication failed (check user/password)` for 401/403) instead of an
  IPP parse failure.
- `%PDF-` magic is accepted anywhere in the first 1024 bytes (per spec).
- Card title updates live when edited in the card editor.
- Upload is refused with 503 before the body is read when no printer is
  configured.

### Changed
- One pooled `aiohttp.ClientSession` per printer with the SSL context built
  once off the event loop — no more TLS handshake per 1.5 s poll.
- Card colors come from the active HA theme (`--primary-color`,
  `--error-color`, `--success-color`) instead of hardcoded mint green.
- Card accepts `entity:` to follow a renamed job sensor.
- Card appears in the Lovelace card picker with a stub config.
- Legacy cipher option uses `SECLEVEL=1` instead of `SECLEVEL=0`.
- Card is served with cache headers (content-hashed URL).
- Config-flow field help moved to `data_description`.
- `hacs.json`: `hide_default_branch` so only tagged releases are offered.
- README rewritten for the HACS default store; `info.md` removed (HACS 2.0
  renders README only).
- Print-Job timeout raised to 300 s; poll timeout lowered to 10 s.

### Added
- `pytest` harness (parser, coordinator, views, config flow), `ruff`, and
  `node --check` in CI.
- `CHANGELOG.md` and a tag-driven release workflow.
- `integration_type: device` in the manifest.

## [0.1.6] - 2026-06-08

### Fixed
- "Nothing happens when I upload a PDF": the card's file input was never
  inserted into the DOM, so modern Chrome/Safari dropped the `change` event.

## [0.1.5] - 2026-05-24

### Fixed
- Narrow-width card layout (container queries) and duplicate error-card
  healing.

## [0.1.4] - 2026-05-24

### Fixed
- Duplicate static-route registration on entry reload.

## [0.1.3] - 2026-05-24

### Fixed
- Bug fixes from integration testing (sister fixes to ha-escl-scan v0.1.5).

## [0.1.2] - 2026-05-24

### Changed
- Branding matched to the sister project.

## [0.1.1] - 2026-05-24

### Fixed
- Slow-reload race in card registration.

## [0.1.0] - 2026-05-24

Initial release.

[0.3.0]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.1.0

[0.4.1]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/wleonhardt/ha-ipp-print/compare/v0.3.0...v0.4.0

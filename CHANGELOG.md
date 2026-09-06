# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semver-ish `0.x`.

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

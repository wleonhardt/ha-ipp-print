# HACS presence, correctness, reach — 2026-09-06

Status: in-progress
Scope: full repo + GitHub/HACS state review, then phased execution.

## Findings (ranked)

### HACS presence
- P1. v0.2.0 in manifest, never tagged/released. HACS users stuck on v0.1.6.
- P2. README install section says "custom repository"; repo is in HACS default store.
- P3. `info.md` dead: HACS 2.0 renders README only.
- P4. No icon in HACS store / HA < 2026.3: not in home-assistant/brands. In-tree `brand/` only works on HA 2026.3+.
- P5. `hacs.json` lacks `hide_default_branch`.
- P6. No release workflow, no CHANGELOG, no issue templates, no dependabot.

### Correctness
- B1. Options flow reads `self.config_entry` on plain `OptionsFlow`; property exists on base class only from HA 2024.12. hacs.json claims 2024.8. Crashes on 2024.8–2024.11.
- B2. Card uses `subscribe_trigger` (admin-only websocket command). Non-admin users get no progress.
- B3. PrintView buffers whole upload before checking integration is configured (503 after 50 MiB).
- B4. Card hardcodes `sensor.printer_current_job`; no `entity:` option.
- B5. Card colors hardcoded; ignore HA theme.
- B6. `SECLEVEL=0` broader than needed (SECLEVEL=1 suffices for non-PFS AES).

### Reach
- R1. No HA service action → automations cannot print.
- R2. PDF only; printers accept jpeg/png/octet-stream.
- R3. Printer path hardcoded `/ipp/print`; CUPS and some printers differ.
- R4. No zeroconf discovery.
- R5. No device (`device_info`), no `Get-Printer-Attributes` (make/model/uuid/formats).
- R6. Config-flow probe uses Get-Job-Attributes job 1; should be Get-Printer-Attributes.
- R7. No print options (copies, sides).
- R8. Card not in picker (`preview: false`, no `getStubConfig`).
- R9. No diagnostics platform.

### Hygiene
- H1. strings.json labels carry help text; use `data_description`.
- H2. `node --check card.js` not in CI; card has no tests.
- H3. Missing `integration_type` in manifest.
- H4. No tests for lovelace sync, `_live_entry`, unload session close, sensor.

## Phases

### Phase 1 — v0.2.0 release — done (v0.2.0 published 2026-09-06) (P1 P2 P3 P5 P6-partial B1 B2 B3 B4 B5 B6 R8 H1 H3 H2-partial)
1. hacs.json: min HA 2024.12.0, hide_default_branch.
2. card.js: subscribe_entities, `entity:` option, theme tokens, getStubConfig.
3. PrintView: configured check before body read.
4. strings: data_description; manifest integration_type.
5. README: badges, My HA install link, drop custom-repo steps; delete info.md.
6. CHANGELOG.md; release workflow (tag → release from CHANGELOG); node --check in CI.
7. Tag v0.2.0, push, release.

### Phase 2 — v0.3.0 reach — in-progress (R1–R7 R9)
1. printer.py: Get-Printer-Attributes, configurable path, rangeOfInteger parse, job-attributes group (copies/sides).
2. config_flow: path field, Get-Printer-Attributes probe, zeroconf step.
3. manifest: zeroconf.
4. sensor: device_info from printer attrs.
5. `ipp_print.print_file` service (path under allowlist, copies, sides, response job_id).
6. PrintView: accept pdf/jpeg/png, check against document-format-supported.
7. diagnostics.py.
8. Tests. Tag v0.3.0, release.

### Phase 3 — hygiene (P4 P6 H2 H4)
1. Issue templates, dependabot, discussions note.
2. Card tests (node:test + jsdom) in CI.
3. Extra Python tests (lovelace sync, unload, sensor).
4. Brands repo PR (custom_integrations/ipp_print).

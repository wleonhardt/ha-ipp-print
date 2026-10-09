# next-up

## Queue

- Shared scan/print rollout in progress. Phase 0 contract/current-host
  experiment and Phase 1 released and installed as print v0.5.0 / scan v0.6.0.
  Physical phone loading confirmed. Phase 2 upload copies/sides and capabilities
  implemented and installed as print v0.6.0 / scan v0.7.0, with subsequent
  card fixes print v0.6.1 / scan v0.7.1. Live API and print jobs pass; physical four-sheet confirmation and release tags pending.
  Phase 3 controls implemented in the compatibility rollout; release gate pending.
  [Printer scope and canonical phased plan](2026-10-08-shared-card-rollout.md).
  [Paired validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-1-validation.md).
  [Phase 2 validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-2-validation.md).
- Compatibility implementation for print 0.7.0 / scan 0.8.0 is pushed and validated.
  All six hosted checks pass for print 74878df; local print tests: 206 Python/35 card.
  Typed IPP, format-specific settings, preflight, scoped queue discovery,
  shared Options dialogs and bridge documentation are implemented.
  [Canonical plan](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/compatibility-rollout-2026-10-08.md).
  [Validation and remaining physical gates](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/compatibility-validation-2026-10-08.md).
  Installed pair: print 0.7.2 / scan 0.8.2. Live card job 368 with explicit
  Letter/automatic tray/monochrome/normal/long-edge duplex completed. User
  confirmed correct one-sheet front/back output; filename cleared. HP requested
  paper-size confirmation on its screen. Scan Letter/grayscale/300 DPI and
  download also pass. Color duplex job 369 printed two numbered sheets; manual
  scanning returned 1F,1B,2F,2B upright with matching downloads. Release tags remain.
  User confirmed both new Options dialogs fit and work on the phone.

## Done

- 2026-10-08 — v0.7.2 paired Options navigation fix installed with scan v0.8.2.
  Back uses HA's dialog manager; disconnection resets the native modal so cached
  cards cannot show settings inline after returning. Done/native-close and focus
  stay synchronized. 206 Python / 40 card tests, Ruff and compileall pass.
  Live HA browser Back/Forward/Done checks pass; physical Android pending.
  [Shared contract](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/decisions/2026-10-08-shared-card-contract.md)
  and [paired deployment/validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/compatibility-validation-2026-10-08.md).

- 2026-10-08 — v0.7.1 label polish from the phone walkthrough. Paper choices
  and loaded-paper text show names plus dimensions, including regional size
  distinctions; tray/color labels are readable too. All 25 HP paper keywords
  remain unchanged as option values; selecting Legal keeps its original wire
  value. Verified the real dialog at 390 x 844, width 356 px without overflow.
  206 Python / 35 card tests, Ruff and compileall pass. Backed up the previous
  component/resources to `/config/.document-card-backups/before-print-labels-v071-20261008.tar.gz`;
  installed and reloaded the print entry (200, require_restart=false).
  Card resource `/ipp_print/card-9a1442e9c6da.js` matches the repository hash.
  No test document was submitted during this display-only check.

- 2026-10-08 — v0.6.1 card fix installed: clear the submitted filename when
  print tracking ends. Initial-completion and stale-update regression checks
  pass; 180 Python / 29 card tests, Ruff and compileall pass. Browser fixture
  verifies filename cleanup with the paired scan v0.7.1 download/capability UI.


- 2026-10-08 — v0.5.0 paired card release installed with scan v0.6.0. Staged
  files, explicit Print, shared theme styling and Sections sizing. Fixed native
  lifecycle cleanup, ambiguous submission handling and HA-owned error recovery.
  135 Python / 29 card tests, Ruff, compileall and hosted validation/release
  workflows pass. User confirmed both cards load correctly on the phone.
  [Paired validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-1-validation.md).

- 2026-10-08 — Thorough code review and v0.4.1 live validation complete.
  [Findings, repairs, verification, and remaining design choices](2026-10-08-code-review.md).
  135 Python tests / 21 card tests and all six final hosted validation jobs pass.
  Live service/card
  jobs completed; cancel and seven rejection checks passed on HP M283fdw / HA
  2026.9.4. Duplex failure repaired; controlled retry confirmed front/back on one
  sheet. Patched HA service job 363 also confirmed on one sheet. Paper size is
  pulled fresh from the printer for each explicit sides job, without user input.
  [Live validation](2026-10-08-v041-live-validation.md).

- 2026-10-08 — v0.4.0: multiple printers (#7). `single_config_entry` dropped; service
  `target:`, `entity_id` on both endpoints, card discovers/sends its sensor; sensor entity_id
  derived from device name. Decision: [decisions/2026-10-08-multiple-printers.md](decisions/2026-10-08-multiple-printers.md).
  Not live-tested with two physical printers.

- 2026-09-06 — Live test of v0.3.0 on HA 2026.9.1 against HP M283fdw (10.11.30.190:631, plain IPP):
  Get-Printer-Attributes parsed (formats incl. pdf/jpeg/octet-stream, both duplex modes, copies 999);
  port 443 needs relaxed ciphers (SECLEVEL=1 works); `ipp_print.print_file` with
  sides=two-sided-long-edge submitted jobs 345/347, both `completed` on the printer;
  device registered with make/model + configuration_url; card served at new hash.
  Not exercised: zeroconf step (entry already existed), card UI in a browser.

- 2026-09-06 — Phases 1-3 of [2026-09-06-hacs-presence-and-reach.md](2026-09-06-hacs-presence-and-reach.md): v0.2.0 (HACS presence, non-admin progress, min HA 2024.12, release workflow) and v0.3.0 (print_file action, zeroconf, images, CUPS paths, device, diagnostics) released; card jsdom tests, issue templates, dependabot.

- 2026-07-20 — Phases 1-4 of [2026-07-20-stability-performance-review.md](2026-07-20-stability-performance-review.md): poll give-up/backoff, clean unload, cancel intent, session+SSL reuse, card hass fallback + scoped subscription + auth refresh, 33-test pytest harness + ruff CI, hygiene sweep. Released as v0.2.0.

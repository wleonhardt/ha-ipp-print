# next-up

## Queue

- Native cards promoted to the main Printer dashboard at the user's request;
  connection tiles, page chip and navigation preserved. Original rollout complete.
  Compatibility follow-up is active: isolated real-HP discovery, card-mod Options
  investigation and device-report coverage. [Follow-up plan](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/compatibility-follow-up-2026-10-09.md).

- Paired activity expansion fixed in both live dashboards using one built-in
  Vertical stack per card. Tile, Mushroom and standalone layouts pass independent
  expansion checks at 320/390/768 px; all 610 tests pass. Examples updated;
  scan 0.12.0 / print 0.11.0 runtime stays unchanged. The user confirmed the
  layout looks good and expansion is smooth on the phone; acceptance is complete.
  [Layout validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/card-independent-expansion-2026-10-09.md).

- Paired alignment/device identity polish installed as print 0.10.3 / scan
  0.11.2; 579 paired tests, hosted checks and narrow real-host layout checks pass.
  The native preview has a device heading. Friendly headings and explicit
  per-printer card names are documented; the user confirmed phone spacing and Back work.
  [Validation and naming decision](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/card-alignment-and-device-names-2026-10-09.md).

- Phase 5 native Tile/Mushroom features accepted: the user confirmed cards and
  navigation work on the phone after print 0.10.1 / scan 0.11.1 fixed the startup
  registry race. Standalone cards stay supported; existing dashboards stay unchanged.
- Print 0.10.2 is released/installed: unsupported PNG now gets format guidance
  instead of a connection error. 220 Python / 62 card tests and hosted checks
  pass; the live rejection and JPEG Validate-Job checks pass without printing.
  The user confirmed their file was JPEG and a retry went through; the first
  failure remains undiagnosed. The PNG fix is independently verified.
  [Validation](2026-10-09-format-rejection.md).
- Phase 6 released/installed: scan 0.12.0 / print 0.11.0. Durable Latest scan,
  ten-job/seven-day print activity, shared core v4 and automatic standalone
  Sections height. 610 tests and hosted/release checks pass. HA restart and
  fresh live cards verified. HP print 373 / scan 8812dcdc7880 survive refresh
  and restart with unchanged metadata, expiry and PDF hash. The user confirmed
  both records and the download on the phone; Phase 6 acceptance is complete. [Validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-6-validation.md).


## Done

- 2026-10-09 — v0.9.1 released and installed after real HP job 371 showed a
  provisional 2/2 impression total during a four-side print. The card now shows
  completed pages/sheets while active, reserving completion for the terminal
  state. 217 Python + 54 card tests, Ruff, compileall, all six hosted checks and
  release workflow pass. Physical paired print/scan and HP off/on recovery checks
  passed; both jobs remain idle, warnings clear and normal polling resumes.
  [Live-test record](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/phase-4-hp-live-tests-2026-10-09.md).

- 2026-10-09 — Phase 4 released and installed as print 0.9.0 / scan 0.10.0.
  Pushed job recovery, submission-scoped cancellation, truthful counters/outcomes,
  native protocol connection sensor and shared presentation core v2. 559 paired
  tests, all hosted checks and release workflows pass. Real read-only HP checks
  and isolated two-tab mobile recovery pass; no physical job was submitted.
  [Paired validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-4-validation.md).

- 2026-10-08 — Phase 3 completed, released and installed as print 0.8.0 / scan 0.9.0.
  Catalog-backed English, regional fallback/plurals, native editor labels/help,
  correct defaults and clearing copies, heading focus and quiet live regions.
  All local checks pass; live native forms, Back/Escape and long labels at
  320 px verified. All six hosted checks and both release workflows passed.
  [Paired validation](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-phase-3-validation.md).
  [Print v0.8.0](https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.8.0).

- 2026-10-08 — v0.7.2 paired Options navigation fix installed with scan v0.8.2.
  Back uses HA's dialog manager; disconnection resets the native modal so cached
  cards cannot show settings inline after returning. Done/native-close and focus
  stay synchronized. 206 Python / 40 card tests, Ruff and compileall pass.
  Live HA browser Back/Forward/Done checks pass; user confirmed the Back fix
  works on the physical phone. All six hosted checks passed on `8ab7703`.
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

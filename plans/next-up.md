# next-up

## Queue

(empty)

## Done

- 2026-09-06 — Live test of v0.3.0 on HA 2026.9.1 against HP M283fdw (10.11.30.190:631, plain IPP):
  Get-Printer-Attributes parsed (formats incl. pdf/jpeg/octet-stream, both duplex modes, copies 999);
  port 443 needs relaxed ciphers (SECLEVEL=1 works); `ipp_print.print_file` with
  sides=two-sided-long-edge submitted jobs 345/347, both `completed` on the printer;
  device registered with make/model + configuration_url; card served at new hash.
  Not exercised: zeroconf step (entry already existed), card UI in a browser.

- 2026-09-06 — Phases 1-3 of [2026-09-06-hacs-presence-and-reach.md](2026-09-06-hacs-presence-and-reach.md): v0.2.0 (HACS presence, non-admin progress, min HA 2024.12, release workflow) and v0.3.0 (print_file action, zeroconf, images, CUPS paths, device, diagnostics) released; card jsdom tests, issue templates, dependabot.

- 2026-07-20 — Phases 1-4 of [2026-07-20-stability-performance-review.md](2026-07-20-stability-performance-review.md): poll give-up/backoff, clean unload, cancel intent, session+SSL reuse, card hass fallback + scoped subscription + auth refresh, 33-test pytest harness + ruff CI, hygiene sweep. Released as v0.2.0.

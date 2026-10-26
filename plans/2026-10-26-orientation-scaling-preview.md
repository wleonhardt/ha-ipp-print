# Orientation, scaling and preview (issue #8)

Status: released as 0.12.0 (2026-10-26)

## Request

[Issue #8](https://github.com/wleonhardt/ha-ipp-print/issues/8) asks for an
orientation option, zoom and a preview.

## Findings

- The HP ColorLaserJet MFP M282-M285 advertises `orientation-requested-supported`
  = 3, 4, 5, 6, 7 (default 3) and `print-scaling-supported` = auto, auto-fit,
  fill, fit, none (default auto). Both are returned for PDF and JPEG probes
  (read-only Get-Printer-Attributes on 2026-10-26).
- IPP has no percentage zoom. `print-scaling` (PWG 5100.13) is the closest
  standard control. Percentage zoom would need client-side rendering, which
  conflicts with the no-build-step, no-dependency card and the bounded payload.
- The capability schema stays at version 1; additions are additive per the
  canonical decision.

## Decision

See [decisions/2026-10-26-orientation-scaling-preview.md](decisions/2026-10-26-orientation-scaling-preview.md).

## Phases

1. Backend: request and parse the two attributes, expose them in the
   capability snapshot, accept `orientation` and `scaling` on the service and
   the upload endpoint, validate against the advertised values, send
   `orientation-requested` and `print-scaling` with fidelity. Tests.
2. Card: Orientation and Scaling selects in Options, same lifecycle as the
   existing paper/tray/color/quality fields. Inline image thumbnail for a
   staged JPEG/PNG and a Preview action that hands the staged file to the
   browser. Card tests.
3. Docs, changelog, version 0.12.0, release, issue reply.

## Validation

- `pytest`, `npm run test:card`, compileall, hosted checks.
- Live (2026-10-26): read-only Validate-Job on the HP accepted JPEG with
  orientation=4 + scaling=fit, PDF with orientation=7 + scaling=none, and
  JPEG with orientation=4 + scaling=fit + duplex + A4, all without warnings.
  No physical job was sent. 302 Python / 69 card tests, hosted checks and the
  release workflow pass.

## HACS installation and card check — 2026-10-26

- Backed up the installed component and HACS tracking to
  `/config/.document-card-backups/before-print-0120-20261026.tar.gz`.
- Installed v0.12.0 through HACS's own download operation after a repository
  refresh. All 20 shipped files match the release tag's SHA-256 hashes.
  `ha core check` passed; one restart with the printer idle. HA stays 2026.10.4.
- After restart the entry is loaded with no ipp_print errors, the update entity
  reports v0.12.0 installed and up to date, and a fresh JPEG capability
  lookup lists orientations 3–7 and scalings auto/auto-fit/fill/fit/none with
  defaults 3 and auto. The card resource serves the new content hash.
- Live card on `/lovelace/printer` (dark theme): a generated JPEG stages with
  its thumbnail, Preview opens a blob URL in a new tab, and Options shows
  Orientation and Scaling with readable labels. Constrained to a 358 px host
  (334 px card body, a 390 px phone's width) nothing overflows: thumbnail
  320 × 160, three 106 px file actions, nine full-width fields, and the Options
  panel scrolls inside its 740 px limit. This was an in-page width constraint,
  not a physical phone; no job was submitted and the staged file was cleared.

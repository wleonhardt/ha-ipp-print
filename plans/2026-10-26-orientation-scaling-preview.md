# Orientation, scaling and preview (issue #8)

Status: released as 0.12.1 and installed (2026-10-26)

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

## Phone check and 0.12.1 — 2026-10-26

Driven over adb on the user's OnePlus (CPH2655, Android 16, companion app
2026.6.5) with rotation locked to portrait during the check and restored after.

- 0.12.0: a JPEG picked through the system picker staged with its thumbnail;
  Preview, Replace and Clear fit side by side. **Defect:** Preview called
  `window.open` on a blob URL, the companion WebView replaced the dashboard
  with a blank page, and Back reloaded the dashboard and lost the chosen file.
- 0.12.1 fix: no navigation. Images keep the thumbnail and no longer show a
  Preview button; a chosen PDF toggles an inline native `object` with fallback
  text where the browser cannot render PDFs. Installed through HACS after the
  hosted checks and release passed; all 20 files match the tag; one restart
  with the printer idle; entry loaded with the new card hash.
- 0.12.1 on the phone: a PDF stages, Preview shows the fallback notice inside
  the card, Hide preview restores the layout, the file stays chosen. Options
  shows all nine fields; the native picker lists the five orientations;
  Landscape selects; Done closes without losing the file. Nothing printed;
  the staged file was cleared and the test files removed from the phone.
- Polish left open: on browsers without a PDF viewer the fallback box keeps
  the 320 px preview height. `navigator.pdfViewerEnabled` could collapse it.

## Compact fallback and 0.12.2 — 2026-10-26

- When `navigator.pdfViewerEnabled === false` the card adds a `fallback`
  class to the preview object and CSS sets `height: auto`, so only the notice
  shows. Every other browser keeps the 320 px inline preview. The shared card
  core is unchanged.
- Two jsdom tests cover the class with the flag false and absent.
  71 card / 302 Python tests, compileall, hosted checks and the release
  workflow pass. Released as v0.12.2 (commit `cc67671`).
- Installed through HACS the same day after a backup to
  `/config/.document-card-backups/before-print-0122-20261026.tar.gz`. All 20
  files match the tag's SHA-256 hashes; `ha core check` passed; one restart
  with the printer idle. Entry loaded, the update entity reports v0.12.2
  installed and up to date, the card resource serves hash `7d0ab5c3f7a5`
  with the new CSS and flag check, and the HA log has no ipp_print errors.
- Desktop (BrowserOS neo, `pdfViewerEnabled` true): no `fallback` class and
  the open preview keeps 320 px.
- Phone (OnePlus, companion app, rotation locked then restored): a 262-byte
  two-page PDF and a 3.15 MB PDF both preview as the notice alone inside a
  compact bordered box; Hide preview restores the layout. Preview stays open
  across the Options dialog (Back closes it), across Home and resume, across
  a cancelled Replace picker and across the Two-sided toggle and Recent
  activity expansion. Replace to a JPEG shows the thumbnail and hides the
  Preview button; Replace to a PDF again starts with the preview closed.
  Three quick Preview taps leave it open (odd count), so no double-toggle
  race. Clear hides everything and returns to Choose file. The system picker
  greys out non-PDF/image files, so the invalid-type path cannot be reached
  from the phone. Staged file cleared, test files removed.
- Real print from the phone with the preview open: the first attempt, a
  hand-written PDF without an xref table, was accepted as job 377 and the HP
  aborted it with `document-format-error`; the card showed the failure and
  cleared the file. A valid one-page PDF went through as job 378: Uploading,
  Printing with Cancel print, then Print complete (1 page). One sheet printed.
  Both jobs appear in Recent activity with the right states.

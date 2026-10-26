# Orientation, scaling and preview (issue #8)

Status: in progress (2026-10-26)

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
- Live: one read-only Validate-Job with orientation=4 and scaling=fit against
  the HP; physical job only if explicitly approved.

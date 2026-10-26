# 2026-10-26 — Orientation, scaling and preview

## Context

Issue #8 asks for orientation, zoom and a preview on the print card.

## Decision

- Add two printer-advertised job options using the existing option pattern:
  `orientation` (IPP `orientation-requested` enum 3 portrait, 4 landscape,
  5 reverse landscape, 6 reverse portrait, 7 none) and `scaling` (IPP
  `print-scaling` keyword auto, auto-fit, fill, fit, none). Each is accepted
  only when the printer lists the value; both are sent with
  `ipp-attribute-fidelity` like every other explicit option.
- Capability snapshot gains `supported.orientations`, `supported.scalings`,
  the two defaults, and two `request_options` entries. Schema version stays 1
  (additive).
- No percentage zoom: IPP does not define one and client-side rendering would
  add a dependency and a build step to the card.
- Preview is browser-native only: an inline thumbnail for a staged JPEG/PNG
  and a Preview action that opens the staged file through an object URL. No
  PDF rendering library. The preview shows the document, not the printer's
  output.
- Scan has no equivalent options; these are print-specific fields under the
  shared card contract. The shared option helper block is unchanged.

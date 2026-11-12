# Issue 8: blank JPEG prints on a Canon G7050 behind CUPS

Status: investigating. Not reproduced. No fix written.

## Report

Reporter jeremypsl, integration 0.12.3, Canon G7050 behind a CUPS server: PDFs print well, JPEG gives a blank page. We have not asked for the CUPS version, the queue's PPD or driverless setup, the CUPS error_log, the card Options in use, or the JPEG's size, DPI, EXIF and color space. No reply has been posted on the issue.

## Lab

Debian trixie container with CUPS 2.4.10 and cups-filters 1.28.17, LogLevel debug. Queues used a generic PDF PPD and a generic PWG-raster PPD, both with a file backend. The integration's own `PrinterClient` (loaded from the repo) sent Get-Printer-Attributes, Validate-Job and Print-Job over HTTP to the container, using the card defaults (copies 1, sides one-sided, media from media-default).

## Evidence so far

- `lp` alone printed every JPEG variant non-blank: 4000x3000 at no DPI, 72, 300 and 600 DPI, EXIF orientation 6, CMYK, grayscale, progressive, an sRGB ICC profile, 640x480, 48 MP and 108 MP.
- The integration with card defaults printed all of those non-blank. The filter chain was `imagetopdf` (PDF queue) or `imagetoraster` (raster queue), each exiting with no errors.
- print-scaling fit, fill, auto, auto-fit and none, and orientation-requested 3 to 6, all printed non-blank. none crops, as expected.
- The only wire difference from PDF is document-format. CUPS received `ipp-attribute-fidelity`, `sides` and `media`, and Validate-Job passed.

Conclusion: on CUPS 2.4.10 with cups-filters 1.28, a CUPS-rendered queue does not produce a blank page from this integration. The integration's JPEG path is not a cause there.

## Not tested

- A driverless (IPP Everywhere) queue. CUPS then forwards the JPEG unfiltered (`cupsFilter2: image/jpeg image/jpeg 0 -`) and the Canon firmware renders it. Sharing a remote queue is not possible in CUPS 2.4, and there is no Canon to test with.
- Canon vendor drivers (cnijfilter2, Gutenprint), CUPS 2.5 or newer, and libcupsfilters 2.x.

## Next step

Ask the reporter for the details listed above, mainly the queue's PPD or driverless setup and the CUPS error_log for a failing job. Wait for the maintainer's go-ahead before replying.

## Second round, 2026-11-12

- Driverless chain tested with `ippeveprinter` as a simulated Canon behind CUPS 2.4.10 (`-m everywhere` queue). CUPS forwards the JPEG bytes unchanged. `lp` forwards only sides, print-color-mode and print-quality.
- The integration with an explicit media adds a `media-col` (size plus 6.35 mm margins, 3.4 mm side margins for A4) that `lp` does not send. This is the only attribute difference found.
- CUPS drops `print-scaling` and `orientation-requested` on a passthrough queue, so the card's scaling and orientation options have no effect there.
- Real HP M283fdw, JPEG sent directly to the firmware with card defaults: a 4000x3000 sRGB JPEG, an EXIF-rotated JPEG and a progressive JPEG completed with 1 sheet each. A CMYK JPEG put the printer into `processing-stopped` / `printer-stopped` with `other-error`; the queued job behind it was held. Both jobs were cancelled; the printer panel needs attention. The user confirmed all three sheets printed an image, so the HP firmware renders ordinary JPEGs sent by the integration with card defaults. A 48 MP JPEG (job 387) also stopped the printer; which of the CMYK and 48 MP files caused the stall is unknown.
- A printer that can stall on a CMYK JPEG makes firmware JPEG decoding a plausible cause for issue 8, but the Canon has not been tested.
- Real HP behind the lab CUPS 2.4.10 driverless queue: `lp` and the integration (card defaults, so CUPS adds `media-col` with margins) both printed an image on the HP, both in grayscale because CUPS sent `print-color-mode=monochrome` from the generated queue defaults. So `media-col` alone does not blank a driverless printer, and `lp` and the integration behave the same there.

## Third round, 2026-11-12: distro and driver stacks

Canon G4000 Gutenprint queues (the closest Canon G-series MegaTank PPD Gutenprint ships; the G7050 is not listed), job output judged by size against a blank-page job (about 42 KB blank versus 13 to 44 MB for a rendered JPEG). `lp` and the integration with card defaults produced identical output sizes unless stated.

- Debian trixie, cups 2.4.10, cups-filters 1.28.17, Gutenprint 5.3.4: all JPEG variants, borderless, A4, print-scaling none, photo media type, and a 108 MP JPEG gave non-trivial output. Rasterizing the 108 MP JPEG under 100 MB of address space still produced the full raster.
- Alpine 3.24 (the stack in the arest HA add-on), cups 2.4.19, cups-filters 1.28.17, Gutenprint 5.3.5: same result, including orientation-requested 4 and print-scaling none.
- Fedora 45, cups 2.4.19, cups-filters 2.0.1, libcupsfilters 2.2.1: ordinary and CMYK JPEGs gave non-trivial output from both `lp` and the integration.
- Alpine's cupsd refuses `file:` device queues ("could not open the output file"); a TCP sink on `socket://` was used instead.

Not tested: Canon's own driver (cnijfilter2 is a licensed vendor download), CUPS 3.x, and Canon firmware.

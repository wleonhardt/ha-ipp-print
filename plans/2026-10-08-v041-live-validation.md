# v0.4.1 live validation — 2026-10-08

Status: verification complete for v0.4.1, including user-confirmed physical duplex.
Initial code under test: `c6f97d9`; duplex fix: `cc9a182`. Paper settings are
refreshed before each explicit sides job; no user-supplied size required.

## Automated gates

- 135 Python tests and 21 card tests passed on the final release candidate
  (126 / 21 initially; 134 / 21 after the first duplex fix).
- compileall, Ruff, npm clean install, card syntax checks passed.
- npm audit reported zero vulnerabilities; no generated files staged.
- [Hosted validation](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37802319364)
  passed Python tests, card tests, Ruff, compileall, hassfest, and HACS.
- [Validation of the duplex fix](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37826611437)
  also passed all six jobs.

- [Final refresh validation](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37828005048)
  passed all six jobs on `f073652`.

## Environment and deployment

- Home Assistant 2026.9.4 / Python 3.14; HP Color LaserJet MFP M283fdw.
- Existing entry uses plain IPP port 631, `/ipp/print`; no connection settings changed.
- Live capability queries passed over IPP 631 and TLS 443 with relaxed ciphers.
  PDF and both duplex modes advertised; maximum copies 999.
- Installed version was 0.3.0. Backed it up outside `custom_components`, deployed
  candidate source, restarted HA, and verified loaded entry and 0.4.1 manifest.
- Initial backup placement under `custom_components` caused a duplicate-domain
  loader conflict. Moved the backup outside discovery and restarted successfully.
  This was a deployment mistake, not a candidate code failure.
- Lovelace resource reconciled to `/ipp_print/card-47b24e6d670d.js` exactly once.
- Used labeled one/two-page test PDFs, never personal documents. Mounted the
  production upload card temporarily in an owned browser tab; no dashboard edits.

## Live jobs

| Job | Submission | Observed result |
|---|---|---|
| 359 | `ipp_print.print_file`, two-page PDF, `copies: 1`, `sides: two-sided-long-edge` | Printer and HA reported completed, 2/2 impressions, `job-completed-successfully`. User confirmed two separate sheets: duplex failure. |
| 360 | Production card upload, one-page PDF | Completed, 1/1 impressions; card showed uploading, queued, printing, then `Print complete ✓ (1 page)`. |
| 361 | Production card upload followed immediately by card cancel | Canceled, zero impressions/sheets, `job-canceled-by-user`; card showed `Cancelling…` then `Print canceled`. |
| 362 | Controlled direct IPP retry with explicit Letter media and attribute fidelity | Completed; user confirmed one sheet, front and back. |
| 363 | Patched HA `print_file` action with copies 1 and long-edge duplex | Completed, 2/2 impressions, one terminal event; user confirmed one sheet. |

Each HA-tracked job emitted one terminal event with matching config-entry
identity. Sensor
returned to idle and card ended its subscription after terminal state. Direct
printer queries confirmed completed/canceled states. A nonexistent job query
returned the expected `JobGoneError`.

The printer omits `copies` and `sides` from Get-Job-Attributes even when explicitly
requested. Acceptance/completion therefore does not prove physical duplex output.
The user confirmed job 359 printed on two sheets, job 362 printed on one
sheet front/back, and job 363 used one sheet. Jobs 359 and 362 both reported two
completed media sheets, so this printer’s counters do not establish physical
duplex output.

## Duplex failure and repair

Strict Validate-Job with `ipp-attribute-fidelity: true` rejected duplex without
media (0x040b, unsupported sides) for PDF, octet-stream, PostScript, PCLm, and URF.
Both duplex modes validated successfully when `media: na_letter_8.5x11in` was
explicit. That size matches the printer’s advertised default and loaded paper.
The original request omitted fidelity, permitting silent substitution to simplex.
[IPP semantics](https://www.rfc-editor.org/rfc/rfc8011#section-4.2.1.1) require
printers to honor explicit job settings or reject them when fidelity is true.

The patch probes current `media-default` before every explicit sides job and
sends that value automatically. It does not require a user-supplied paper size.
If the fresh probe fails, it refuses to submit using stale paper settings.
It requires fidelity for explicit copies, sides, or media. An unsupported-settings
response produces an actionable error without starting tracking. Default uploads
continue to use printer defaults. README explains matching loaded paper; changed
printer defaults are picked up automatically. Paper size is the printer’s configured default, not physical
stock-type detection. Regression tests exercise the real HTTP payload, fidelity placement, missing/A4 defaults, unchanged default
uploads, rejected jobs not starting tracking, refresh after changed defaults,
and probe failure not submitting stale settings.

## Live API and lifecycle checks

All seven rejection checks returned their expected status, without submitting
jobs: boolean cancel ID (400), unknown cancel ID (404), malformed multipart (400),
duplicate file fields (400), oversized selection field (413), unsupported GIF
(415), unauthenticated request (401).

After jobs finished, entry reload returned 200 without requiring a restart. Entry
remained loaded, sensor idle, and exactly one current card resource persisted.
HA logs contained only expected warnings from deliberate invalid-request tests.
The temporary card, observers, and subscriptions were removed after testing.
Temporary PDFs were removed after the final service test. The post-patch restart
loaded the new media-default capability in diagnostics. Job 363 completed through
the HA service; sensor returned to idle, its test subscription closed, and no
IPP Print warnings/errors appeared in the fresh HA log.

After the final refresh change, a fresh live capability query returned Letter
(`na_letter_8.5x11in`). A non-printing Validate-Job built with the production
builder, that default media, copies 1, long-edge duplex, and attribute fidelity
returned successful-ok without creating a job. No additional pages were printed.
Final source was deployed to HA and core restart completed successfully.

## Limits

TLS was probed, not used to submit a live print. Only one physical printer tested;
two printers/CUPS queues, physical resets, huge/long-running jobs, discovery, and
oldest-supported HA remain outside this live check. Unit tests cover malformed
IPP, bounded transfers, cancellation races, setup races, and card lifecycle edges.
The existing printer dashboard view was empty; the temporary production card
verified upload/progress/cancel, not persisted dashboard self-healing.

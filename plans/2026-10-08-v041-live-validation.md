# v0.4.1 live validation — 2026-10-08

Status: candidate installed; release awaits physical duplex confirmation.
Code under test: `c6f97d9`. No v0.4.1 tag published yet.

## Automated gates

- 126 Python tests and 21 card tests passed on the release candidate.
- compileall, Ruff, npm clean install, card syntax checks passed.
- npm audit reported zero vulnerabilities; no generated files staged.
- [Hosted validation](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37802319364)
  passed Python tests, card tests, Ruff, compileall, hassfest, and HACS.

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
| 359 | `ipp_print.print_file`, two-page PDF, `copies: 1`, `sides: two-sided-long-edge` | Printer and HA reported completed, 2/2 impressions, `job-completed-successfully`. Physical sheet count still needs confirmation. |
| 360 | Production card upload, one-page PDF | Completed, 1/1 impressions; card showed uploading, queued, printing, then `Print complete ✓ (1 page)`. |
| 361 | Production card upload followed immediately by card cancel | Canceled, zero impressions/sheets, `job-canceled-by-user`; card showed `Cancelling…` then `Print canceled`. |

Each job emitted one terminal event with matching config-entry identity. Sensor
returned to idle and card ended its subscription after terminal state. Direct
printer queries confirmed completed/canceled states. A nonexistent job query
returned the expected `JobGoneError`.

The printer omits `copies` and `sides` from Get-Job-Attributes even when explicitly
requested. Acceptance/completion therefore does not prove physical duplex output.
The user reported “duplex printed 2 pages”; one sheet versus two sheets is pending
clarification. Do not treat the reported impression count as sheet count.

## Live API and lifecycle checks

All seven rejection checks returned their expected status, without submitting
jobs: boolean cancel ID (400), unknown cancel ID (404), malformed multipart (400),
duplicate file fields (400), oversized selection field (413), unsupported GIF
(415), unauthenticated request (401).

After jobs finished, entry reload returned 200 without requiring a restart. Entry
remained loaded, sensor idle, and exactly one current card resource persisted.
HA logs contained only expected warnings from deliberate invalid-request tests.

## Limits

TLS was probed, not used to submit a live print. Only one physical printer tested;
two printers/CUPS queues, physical resets, huge/long-running jobs, discovery, and
oldest-supported HA remain outside this live check. Unit tests cover malformed
IPP, bounded transfers, cancellation races, setup races, and card lifecycle edges.
The existing printer dashboard view was empty; the temporary production card
verified upload/progress/cancel, not persisted dashboard self-healing.

# Print upload concurrency — 2026-10-09

## Scope

User-approved lean hardening: reproduce concurrent document buffering, bound
it across HTTP uploads and service calls, and ensure failure recovery. No new
settings, dependencies, disk spooling, queues or automatic document resends.

## Findings and fix

- The per-file 50 MiB limit did not bound concurrent files. Four deterministic
  reproductions against the unchanged source at `b4c156c` failed: simultaneous
  HTTP submissions to one/two printers and HTTP/service overlap in both orders.
  The second request read its document or reached Print-Job while the first
  remained active. Small test documents establish the admission gap; no memory
  exhaustion test was run on production.
- One synchronous reservation on HA's event loop now spans preparation through
  submission across every configured printer. Rejections happen before body or
  file reads and explicitly confirm that no job was submitted. Read-only
  capability requests and cancellation remain available. Physical job tracking
  does not retain the slot.
- A stalled incoming body gets a five-minute deadline, independently of the
  existing outgoing printer timeout. Busy and timeout responses close the
  upload connection rather than draining the rejected body for keepalive.
- Entry reload cannot reset the domain-level reservation. Canceled executor
  reads keep it until their worker finishes, because canceling an await cannot
  stop a thread. All exits release it for a new explicit request.

## Validation

22 regression cases cover same/different-printer HTTP concurrency, service/HTTP
overlap, rejection before body read, read-only access, malformed/oversized/
unsupported/validation/ambiguous failures, body disconnect/cancellation, a real
stalled aiohttp upload, separate upload/submission deadlines, repeated service
cancellation during a real worker read (success and failure), file-read errors,
entry reload, and cancellation during HTTP/service submission. Call counts
verify refused requests never reach Print-Job or replay automatically; explicit
subsequent requests succeed. All fault injection uses isolated test fixtures.

Local validation: 292 Python tests and 65 card tests pass (357 total), plus
Ruff, compilation and whitespace checks. `npm ci` reports no vulnerabilities.

## Release and installation

- Source commit `c6714d94bd47455547e1f6a7cfa74ef8782b242d` passed all six
  [hosted checks](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38016215738).
  [Release workflow](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38016327063)
  published [v0.11.4](https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.11.4).
- Installed the tracked component archive on HA 2026.9.4 after confirming both
  document integrations idle. Previous component backed up to
  `/config/.document-card-backups/before-upload-concurrency-v0114-20261009.tar.gz`.
  Installed Python, manifest and unchanged card hashes match the source commit.
  `ha core check` and restart completed successfully.
- Fresh main-dashboard load shows one native Scan feature and one Print feature,
  both controls and activity disclosures. Both integrations are loaded, idle
  and reachable. Diagnostics returns 200 and reports Print 0.11.4. A read-only
  HP JPEG capability lookup succeeds with fresh settings and no recorded failure.
- Latest scan metadata and Recent activity match their pre-restart snapshots.
  Print job 373 remains completed. The existing latest scan is expired with no
  download URL; its state is preserved, not treated as a new download test.
  No Print-Job, Validate-Job or scan was submitted during deployment verification.

Acceptance complete. Concurrent fault cases remain isolated regression tests;
the live HP check confirms installation, connectivity and persistence only.

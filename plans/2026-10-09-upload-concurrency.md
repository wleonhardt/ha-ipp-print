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
Release target: 0.11.4. Hosted and installation results follow.

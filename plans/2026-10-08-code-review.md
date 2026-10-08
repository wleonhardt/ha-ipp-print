# Code review — 2026-10-08

Status: completed locally; fixes prepared as v0.4.1. No release or live-printer
verification performed. Baseline: `89adcc5` (v0.4.0).

Reviewed every integration module, the card, tests, manifest, service schema,
translations, README, project decisions, and validation/release workflows.
The existing architecture remains stdlib + aiohttp, framework-free ES2020,
with early custom-element registration and no build step.

## Findings patched

Priorities reflect the original behavior. Locations point to the repaired
functions rather than the old diff. P1 means misleading outcomes or broken
core behavior; P2 means an edge case, reliability problem, or resource cost.

| Priority | Location | Original problem and repair |
|---|---|---|
| P1 | `coordinator.py:_poll_one_locked` | A purged job without accepted cancel intent was labeled completed, even though it could have failed or been canceled elsewhere. Report `unknown` / `job-outcome-unknown`; only observed completed state claims success. |
| P1 | `coordinator.py:_poll_one_locked` | Two responses lacking job attributes claimed completion. Count these as failed polls, retry with existing backoff, and stop at the failure cap. |
| P1 | `coordinator.py:async_cancel` | Cancel intent was set before the printer accepted it and remained set on rejection/error. Serialize cancel and poll per job and record intent only after success. Terminal jobs cannot be canceled. |
| P1 | `printer.py:PrinterClient.__init__` | Omitting port 80/443 regardless of scheme redirected HTTP on 443 to 80 and HTTPS on 80 to 443; IPP URI default ports also differ from HTTP defaults. Preserve the configured port explicitly in both transport and IPP URIs. Bracket IPv6 literals. |
| P1 | `printer.py:_parse_attributes`, `parse_response` | Truncated names/values, undersized integers, missing end markers, and unrelated bodies could parse as successful responses. Validate bounds, fixed-width types, booleans, versions, and end-of-attributes. |
| P1 | `printer.py:parse_job_attrs_response`, `coordinator.py:_poll_one_locked` | An error response carrying attributes, an invalid state, or attributes for another job could update/complete the tracked job. Reject these instead of applying them. Reject invalid submission job IDs. |
| P1 | `static/card.js:_trackPrintProgress` | An unconditional 90-second timeout unsubscribed healthy long print jobs. Limit the timeout to waiting for a matching sensor snapshot; retain subscriptions for active jobs. |
| P2 | `static/card.js:_stopProgress`, lifecycle callbacks | Disconnects, successive uploads, and terminal messages arriving before the subscription promise resolved leaked subscriptions or allowed old callbacks to overwrite new status. Use generation ownership and dispose late handles; clean up on disconnect and resume on reattachment. |
| P2 | `static/card.js:_cancelJob` | A delayed cancel response could overwrite completion or a new job's status. Scope responses and pending-request ownership to job and tracking generation. |
| P2 | `static/card.js:_trackPrintProgress` | An already-terminal initial sensor snapshot unnecessarily subscribed; `processing-stopped` hid cancel and offered no useful status. Render and finish initial terminal states directly; show paused state and its reason with cancel available. Handle sensor removal. |
| P2 | `static/card.js:_getHass`, `_upload` | A healed card's seeded hass reference prevented the live root fallback; oversized files traveled to HA before rejection. Prefer the live root reference and reject files above 50 MiB before posting. Guard overlapping upload calls. |
| P2 | `static/card.js:_trackPrintProgress` | A newer submission replaced the sensor while the old card continued to claim it was printing. Explain that another job is being tracked, hide stale cancel UI, and bound the wait for the original job to reappear. |
| P2 | `coordinator.py:_fire` | Events from different printers with identical printer-local job IDs were indistinguishable. Include `config_entry_id` on state and terminal events. |
| P2 | `coordinator.py:_apply_attrs` | Sheet counts were divided by impression totals, under-reporting duplex progress; boolean fallback discarded valid zero counts. Prefer impressions when present, preserve zero, and fall back to sheets. Remove unused `last_seen` state. |
| P2 | `printer.py:build_print_job`, `__init__.py:_submit` | Explicit `copies: 1` was omitted, allowing printer defaults to print multiple copies. Send every explicit count, honor the advertised maximum, and retain the maximum across advertised ranges. Keep every job-state reason rather than only the first. |
| P2 | `__init__.py:PrintView.post` | Repeated file fields were concatenated and assigned the last filename. Entity fields were unbounded, and multipart read errors escaped as server errors. Accept exactly one file and at most one bounded entity field; reject duplicate/unexpected fields and return 400 for malformed bodies. |
| P2 | `__init__.py:CancelView.post` | Python treats JSON booleans as integers; invalid/oversized IDs could reach integer encoding. Require an actual integer in the positive signed 32-bit range. |
| P2 | `__init__.py:_read_file_capped`, `_safe_filename` | Files growing after stat bypassed the read cap; special files could block a worker; truncation removed extensions and Windows paths leaked into job names. Bound the actual read, refuse non-regular files, preserve suffixes, and strip both path styles. |
| P2 | `__init__.py:async_setup_entry`, `_sync_lovelace_resource` | Concurrent printer setup could register one static route twice or duplicate resource records. Resources could be edited before persisted records loaded. Serialize each shared operation and load storage before reconciliation. Run the resource wait as a background task. |
| P2 | `__init__.py:async_setup_entry`, `printer.py:async_close` | Setup failures/cancellation could leak clients/platforms; shutdown could race lazy SSL/session creation; late submissions could restart an unloaded poller. Clean partial setup and HA stop, serialize permanent close with initialization, and refuse tracking after unload. |
| P2 | `config_flow.py` | Discovery used advertised/fallback IDs without reconciling the probed UUID; host-only matching blocked separate CUPS queues. Manual setup could duplicate legacy endpoint IDs. Match effective host/port/path including options, distinguish paths in fallback IDs, use probed UUIDs, and recheck at confirmation. Validate port range. |
| P2 | `const.py:sniff_format` | PDF-like text in JPEG/PNG metadata took precedence over the actual image signature. Check strict image prefixes before the permissive PDF preamble search. |
| P2 | `printer.py:_IppDocumentPayload`, `_post_ipp` | Each document was concatenated with its IPP header on the event loop, creating a second document-sized allocation. Use a sized payload holding a memoryview and write 64 KiB chunks with backpressure. Preserve Content-Length, cap printer responses at 1 MiB, reject redirects, and avoid logging response bodies. |
| P2 | `__init__.py:_submit` | Submission timeout/malformed response errors invited retries even when the printer had accepted the document. Explain the ambiguity and tell callers to check the queue before retrying. No automatic retry was added. |
| P2 | `package-lock.json` | The dependency audit reported a high-severity issue in test-only `source-map-js`. Update its compatible patch version; audit now reports zero vulnerabilities. |
| P2 | test harness | Card test windows retained timers and prolonged process exit. Close windows after each test. Copy mutable printer capability fixtures per test to prevent order-dependent leakage. |

## Remaining design choices, ranked

These are limits and future changes, not claims that the corresponding
features were implemented in this review.

1. **Concurrent-job progress deserves a separate contract.** The coordinator
   polls every active job, but the sensor intentionally represents only the
   latest submission. The card now explains replacement instead of showing
   stale progress. For continuous progress on several jobs, choose either a
   per-job status endpoint or a bounded active-job attribute model. Avoid
   adding broad subscriptions to all HA state changes. Existing per-job bus
   events now identify the printer and remain useful to automations.

2. **Persist tracking only with a clear ownership/retention policy.** Reload
   and restart erase in-memory tracking, so still-printing jobs cannot be
   canceled through HA afterward. This is now documented. Persistence needs
   more than an integer job ID: printers can reuse IDs after a reset. Define
   printer identity, job identity, expiry, and stale-job handling before
   adding HA storage. Do not replay Print-Job on recovery.

3. **A per-request cap is not a global memory cap.** The second full-document
   allocation is gone, but N simultaneous uploads still retain roughly N
   document buffers plus networking overhead. A bounded admission semaphore
   should run before body buffering, or uploads should spool to disk in an
   executor. Decide queue length and overload responses explicitly. A lock
   around submission after buffering would not solve the memory issue.

4. **Options currently edit connection settings without reconciling device
   identity.** Redirecting an existing entry to an entirely different printer
   retains its original unique ID, title, and entity history. Duplicate
   endpoint checks now honor options, but replacing a device needs a defined
   reconfigure/replacement flow. Validating every options change against an
   online printer would also prevent offline configuration; choose that
   behavior deliberately rather than adding it incidentally.

5. **The card recovery and Lovelace resource compatibility code are brittle
   boundaries.** They depend on frontend internals, shadow-DOM traversal,
   parent card configuration fields, and several hass.data shapes. Tests
   cover resource loading/reconciliation and card behavior, but actual
   dashboard loading and error-card replacement still need a browser test
   against supported HA releases. Remove compatibility branches only after
   a minimum-version decision and a slow-load test demonstrate that they are
   unnecessary.

6. **Polling cost grows with queue length.** Polls are sequential; an
   unreachable printer can cost up to 10 seconds per job per sweep, before
   backoff. For larger queues, consider bounded concurrency or a printer-level
   failure budget with monotonic elapsed-time limits. Benchmark first: more
   simultaneous requests can overload printer firmware, and the normal
   one/two-job case does not justify unbounded parallelism.

7. **Broaden compatibility verification before release.** Local Python tests
   use HA 2026.2.3 / aiohttp 3.13.3; they do not certify the advertised HA
   2024.12 minimum or every current core release. Add an oldest-supported and
   newer-core test matrix when dependency combinations allow it. Physical
   tests should include two printers, two CUPS queues, TLS with and without
   legacy ciphers, duplex progress, large jobs, cancellation, printer reset,
   and explicit nonstandard ports. Keep ambiguous outcomes visible.

The existing policy allowing authenticated HA users to print, while limiting
cancel to tracked jobs, was preserved in accordance with the project decision.
No framework, protocol library, or new runtime dependency was introduced.

## Verification

- Baseline: 72 Python tests and 11 card tests passed.
- Final: 126 Python tests and 21 card tests passed.
- Python compileall, Ruff, and git diff whitespace checks passed.
- Clean npm install plus card syntax/jsdom tests passed; npm audit: zero vulnerabilities.
- Local HTTP tests verify exact IPP payload bytes, Content-Length without
  chunked transfer, connection reuse, redirect refusal, bounded responses,
  and close during session initialization.
- Regression tests cover cancel/poll races, malformed protocol data, endpoint
  duplicates, malformed/duplicate uploads, growing/special files, shared
  setup/resource races, HA stop, and early/late card subscription lifecycle.
- No bytecode or build artifacts were staged.
- The manifest and matching changelog are prepared for 0.4.1; README documents
  new outcome/event behavior and important lifecycle limits.
- Container-based hassfest/HACS validation was not run: Docker's daemon is
  unavailable on this host. Hosted CI and physical-printer behavior remain
  unverified. No changes were pushed, tagged, or published.

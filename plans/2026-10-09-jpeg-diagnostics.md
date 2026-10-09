# JPEG settings failure diagnostics

Status: released, installed and verified as 0.11.2 on HA 2026.9.4.
The original intermittent JPEG failure remains unexplained; its diagnostic gap
is reproduced and fixed. No new failure was induced on the real HP.

The user approved improving evidence for the intermittent JPEG failure, with no
new settings or dependencies. The original failure's cause is still unknown;
the earlier PNG format-rejection fix does not explain it. See the
[original report](2026-10-09-format-rejection.md).

## Reproduced gap

A format-specific capability lookup can fail before any Validate-Job or
Print-Job request. The cache previously swallowed the cause, retained only
`refresh_failed`, and was absent from the diagnostic download. A successful
retry hid that failure. A JPEG multipart regression reproduced the missing
diagnostic record on the previous implementation.

## Small implementation

- One failure per existing generic/format cache: timestamp, elapsed milliseconds,
  allowlisted category and numeric HTTP/IPP status. Retain the failure on success
  so current freshness and past failure are distinguishable. Preserve IPP status
  using an IppError subclass, not exception-message parsing.
- Include those snapshots and the existing connection snapshot in Download
  diagnostics. Capture one separate snapshot when the shared HTTP/service submit
  path blocks on format/paper settings, with `job_may_exist: false`.
- Store no exception objects, raw messages, documents or filenames. Custom MIME
  labels are reported as `other`. Existing secret redaction remains applied.
- Evidence is in memory only: one generic cache, up to eight format caches and
  one blocked attempt. Reload/restart clears it; cache eviction can discard a
  format failure. Downloading diagnostics does not contact the device.
- Existing card/API errors, capability API schema, backoff, timeout, validation
  and submission behavior stay unchanged. No retry or device workaround is
  justified by the historical JPEG report alone. No Scan runtime changes.

## Validation

Focused checks cover JPEG failure → backoff → successful retry, exactly one
submission, retained evidence, typed IPP rejection, timeout/TLS/auth/HTTP/invalid
data/connection categories, cancellation, per-printer isolation, cache bounds,
redaction and reload. All required local checks pass: 251 Python tests, 65 card
tests after npm ci, Ruff, compileall and diff checks (316 tests total).

## Delivery and live verification

- Commit `e3585fe`: all six [hosted checks](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37992616238)
  passed. The [release workflow](https://github.com/wleonhardt/ha-ipp-print/actions/runs/37992817623)
  published [v0.11.2](https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.11.2).
- Rollback archive:
  `/config/.document-card-backups/before-jpeg-diagnostics-v0112-20261009.tar.gz`.
  Installed tracked release sources, passed HA configuration check and restarted
  with both job sensors idle. All four changed Python modules, manifest and
  unchanged card hashes match the release. Scan remains 0.12.1.
- The real authenticated diagnostic download reports Print 0.11.2, a loaded
  entry, reachable HP and a fresh generic capability cache. Format caches start
  empty, and there is no invented failure or blocked submission record.
- One read-only JPEG capability request succeeds and adds its fresh format cache
  to diagnostics. Two subsequent diagnostic downloads preserve both its attempt
  and success timestamps. No Validate-Job or Print-Job was submitted by this check.
- Both native features render on the main dashboard. Both job sensors remain
  idle. The existing print activity and latest scan metadata are unchanged after
  restart; the old scan is correctly expired at its original deadline.

Failure categories and recovery are verified with isolated tests, not claimed
as reproduced HP failures. If the intermittent problem returns, download
diagnostics before reloading/restarting; do not infer its cause from this
successful read-only query or add speculative retry behavior.

## Bounded settings recovery follow-up — 2026-10-09

The user subsequently approved testing recovery after a failed settings lookup
and fixing reproduced issues, with bounded retries, no automatic print resends,
new settings or dependencies. This changes only the explicit retry policy below;
the cause of the user's historical JPEG failure remains unknown.

Reproduced with the real HA upload endpoint and mocked printer I/O: after a
timeout and printer recovery, a new JPEG request 30 seconds later still returned
502 without contacting the printer. The original five-minute cache backoff also
applied to deliberate print attempts. Before the fix, the upload recovery test
and two focused cache regressions failed; nontransient-failure tests passed.

Print 0.11.3 permits one early settings refresh after a 30-second cooldown for
timeouts, connection errors and HTTP 502/503/504. Only a new per-job `fresh=True`
request can use it. One failed early attempt starts the normal five-minute
backoff, without another early attempt in that interval. Cancellation consumes
the early opportunity. The existing lock serializes access, the 15-second fetch
limit stays in place, and no background recovery timer or submission loop exists.
Authentication, TLS, unsupported IPP operations/formats, malformed responses and
HTTP rate limits retain full backoff. Dashboard GETs retain their existing cache
policy. An error gives the next retry wait; diagnostics also include that wait.

After successful recovery, ordinary format validation, fresh paper selection and
Validate-Job still run before the current request submits once. Ambiguous
Print-Job outcomes still warn that the printer may have accepted the document.
No replay, scanner runtime change, new API parameter, setting or dependency.

Validation:

- All 270 Python and 65 card tests pass (335 total), plus npm ci, Ruff, compileall
  and diff whitespace checks. Added coverage includes early/too-soon retries,
  concurrent failed retries, one-opportunity exhaustion, cancellation, stale
  data and recovery reset, excluded error classes and preserved diagnostics.
- HTTP and service recovery both pass. Service recovery uses the newly returned
  paper default. Read-only dashboard queries cannot consume the early retry.
  Unsupported formats and rejected settings submit zero jobs. A submission
  timeout after recovery sends exactly once and remains an ambiguous outcome,
  including after later read-only requests and diagnostic downloads.
- In an isolated local cache/client, simulated the initial timeout, verified an
  immediate retry was suppressed, waited the actual 30-second cooldown, then
  made one real HP `image/jpeg` capability lookup. It succeeded, the cache became
  fresh and the earlier failure evidence remained. No Validate-Job or Print-Job
  was sent. This proves recovery against the real endpoint after a controlled
  failure; it does not claim the HP naturally timed out or identify the old cause.

Delivery and installed validation:

- Commit `792d1cd`: all six [hosted checks](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38002398900)
  pass. The [release workflow](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38002563015)
  published [v0.11.3](https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.11.3).
- Rollback archive:
  `/config/.document-card-backups/before-settings-recovery-v0113-20261009.tar.gz`.
  Installed tracked release files; hashes of both changed Python modules,
  manifest and unchanged card match. HA configuration check passed and both
  sensors were idle immediately before the core restart.
- HA remains 2026.9.4. Both entries return loaded and the HP is reachable. The
  authenticated diagnostic download returns 200 with manifest 0.11.3 and the new
  retry field, confirming the running code loaded. One normal read-only JPEG
  capability query returns fresh data; its diagnostic retry wait is zero.
- Both native features render on the main dashboard. Latest scan and recent
  print activity metadata match the pre-restart snapshot exactly, including
  the scan's existing expiry. Both job sensors stay idle. No physical print or
  scan, Validate-Job, automatic resend or synthetic production fault was sent.

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

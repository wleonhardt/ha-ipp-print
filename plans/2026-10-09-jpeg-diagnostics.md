# JPEG settings failure diagnostics

Status: implemented for 0.11.2; validation and delivery in progress.

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
Hosted validation, release and installed read-only verification follow.

# Phase 2 capability and upload contract

Use the schema version 1
[canonical decision](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/decisions/2026-10-08-capability-api.md).
Authenticated entity-scoped capabilities use a local bounded cache; uploads and
the existing print_file service share strict copies/sides validation.
Keep the baseline cache policy aligned between projects, with no cross-install
dependency. Preserve the sized document payload and fresh per-job default media.

## Print recovery exception — 2026-10-09

The user approved bounded recovery after a failed settings lookup. Print 0.11.3
allows one early lookup on a new explicit-settings submission, 30 seconds after
a timeout, connection failure or HTTP 502/503/504 response. A failed early lookup
starts the full five-minute backoff, with no further early opportunity until that
window expires. Cancellation consumes the early opportunity. Each call attempts
at most one fetch; there is no retry task, timer or automatic Print-Job resend.

Only the existing `fresh=True` per-job path can use this opportunity. Dashboard
GETs, setup, authentication/TLS/IPP errors and malformed replies retain the
baseline policy. A successful settings refresh still goes through normal format
checks, current paper selection and Validate-Job before its caller submits once.
The Scan runtime does not need this Print-specific exception.

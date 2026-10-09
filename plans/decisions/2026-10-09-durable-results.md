# Phase 6: bounded activity and latest scan

Use the shared [durable results decision](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/decisions/2026-10-09-durable-results.md).

Print stores version-1 private per-entry metadata for ten jobs/seven days. It
never retains uploads or reprints; interrupted tracking restores as unknown.
The shared card core v4 renders collapsed activity with the same presentation
as Latest scan. Existing APIs, active-job semantics and independent releases
remain compatible.

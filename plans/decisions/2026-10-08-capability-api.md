# Phase 2 capability and upload contract

Use the schema version 1
[canonical decision](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/decisions/2026-10-08-capability-api.md).
Authenticated entity-scoped capabilities use a local bounded cache; uploads and
the existing print_file service share strict copies/sides validation.
Keep capability_cache.py policy identical between projects, with no cross-install
dependency. Preserve the sized document payload and fresh per-job default media.

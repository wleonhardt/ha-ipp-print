# Paired documentation overhaul — 2026-10-10

The user requested the same documentation overhaul for Scan and Print. The
[paired scope, corrections and validation record](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/documentation-overhaul-2026-10-10.md)
is maintained in the Scan repository.

Print's README is now a 70-line quick start (previously 593 lines). The matching
[documentation index](../docs/README.md) leads to installation, dashboard,
printing, automations, troubleshooting, compatibility and HTTP API guides.
Development and translation instructions moved to CONTRIBUTING.md. The example
index explains where to paste each configuration.

Corrected the scan-to-print event/path/condition, unknown-outcome guidance, API
field list and multi-printer layout. Options, protocols and compatibility claims
were checked against current code and existing device evidence. No runtime,
dependency, version or production configuration change is included.

Validation: 292 Python tests, 65 card tests after npm ci, Ruff and compilation
pass. Paired documentation link/anchor and YAML/JSON checks pass, including
validation of print-file examples against the actual service schema. Nothing
was physically printed or scanned.

All seven [hosted checks](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38059607551)
pass for `cfeb5e469e60896aef50dc0249c4cdc787cbb732`. Rendered GitHub landing
pages, guide navigation and code/table rendering were checked. Publication
acceptance is complete; production remains on Print 0.11.5 / Scan 0.12.4.

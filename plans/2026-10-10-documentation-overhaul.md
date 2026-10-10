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

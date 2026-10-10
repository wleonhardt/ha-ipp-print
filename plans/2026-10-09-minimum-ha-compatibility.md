# Minimum Home Assistant backend compatibility — 2026-10-09

User-approved isolated compatibility testing with no new settings or runtime
dependencies. The paired [scope, reproduction and validation record](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/minimum-ha-compatibility-2026-10-09.md)
is maintained in the Scan repository.

Print 0.11.4 failed three existing service-target tests on HA 2024.12.0 because
`async_extract_config_entry_ids` requires explicit `hass` there. Print 0.11.5
selects the helper's supported signature before calling it. HA still resolves
targets and validates membership; no submission is retried.

The new minimum-HA CI job pins the real HA 2024.12.0 / Python 3.12 test stack,
asserts it matches `hacs.json`, and runs the existing complete Python suite.
Test-only constructor and setup-cleanup changes let the same assertions run
on both versions without skipped cases or mocked HA service-target helpers.

Local results: 292 Python tests pass on HA 2024.12.0 and 2026.2.3, plus all 65
card tests, Ruff, compilation and whitespace checks. Source commit
`23ffee788c88dc35447448889316deb8acd59432` passed all seven
[hosted checks](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38019032694),
including the minimum job. The successful
[release workflow](https://github.com/wleonhardt/ha-ipp-print/actions/runs/38019157707)
published [v0.11.5](https://github.com/wleonhardt/ha-ipp-print/releases/tag/v0.11.5).

No production HA/device access, restart or physical job occurred. The live
installation remains 0.11.4; isolated compatibility acceptance is complete.

# Shared document card contract

Adopt version 1 of the [shared contract](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/decisions/2026-10-08-shared-card-contract.md).
The scan repository is canonical for shared decisions and paired fixtures.

Keep this integration independently installable, using its existing plain-JS
card type and early registration. Phase 1 vendors the same base styling inside
the already content-hashed card module; no shared runtime asset is introduced.

The print card stages a file locally before explicit Print. Replace and Clear
are unavailable while submitting/following an active job. A canceled file picker
preserves the current selection. Accepted or ambiguous submissions release the
staged file, and ambiguous outcomes tell the user to check the printer queue.
Known validation rejection can retain the selected file. Device routing remains
the sensor entity ID. Copies and sides controls wait for upload API support.

Native Tile/Mushroom hosting remains a later optional release; minimum HA stays
2024.12. Use paired theme/layout fixtures and behavior tests from the canonical
contract, while retaining independent print workflow and network adapters.

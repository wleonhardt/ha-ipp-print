# Shared scan and print card rollout

Status: in-progress, 2026-10-08. Phase 1 released and installed as v0.5.0 with
scan v0.6.0. Physical phone loading confirmed. Phase 2 is next; remaining host
limits are in the canonical validation record linked from `next-up.md`.

Use the same visual and interaction contract as ha-escl-scan: neutral Home
Assistant surfaces, one primary action, a visible Two-sided setting and optional
settings panel. Printing stages the selected document before an explicit Print.
Both integrations remain independently installable, with plain JavaScript,
local assets and compatible existing standalone card types.

The [canonical rollout plan](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/shared-card-rollout-2026-10-08.md)
contains dependencies, detailed acceptance gates, release process and rollback.
Keep cross-project decisions there rather than maintaining two full copies.
The [design review](https://github.com/wleonhardt/ha-escl-scan/blob/main/plans/design-review-2026-10-08.md)
records the rationale and reference designs. Printer baseline: v0.4.1 (`764fe71`).

## Printer work by phase

| Phase | Printer scope | Gate before shipping |
| --- | --- | --- |
| 0 | Shared contract/fixtures and native Tile/current Mushroom Template experiment | Tested host/version boundary; old standalone type retained |
| 1 | Common mobile appearance, Choose file then Print, real cancel control, Sections sizing | Selecting a file submits nothing; explicit Print submits once; existing YAML loads |
| 2 | Idle capability metadata and optional multipart copies/sides | Old uploads work; strict bounded validation; selected printer and fresh sides/media behavior verified |
| 3 | Copies/binding panel, multiple-printer selection and visual editor | Only supported options; freeze target/settings during jobs; consistent defaults |
| 4 | Pushed state before local submission, reconnect, availability and common recovery | Scoped entity/job IDs and stale-reply protection; honest offline/unknown state |
| 5 | Native custom feature with compatible standalone wrapper | Independent installs, mismatched shared-core versions and Android refresh/update work |
| 6 | Bounded recent print activity | Defined metadata lifetime; no uploaded document retention or implicit reprint |

## Printer implementation checklist

- [x] Phase 0 contract and fixtures adopted; current-host experiment recorded.
  Minimum-version and Android native-host runtime checks remain before Phase 5.
- [x] Phase 1 staging and shared mobile layout shipped; phone loading confirmed.
- [ ] Phase 2 capability metadata and upload copies/sides shipped.
- [ ] Phase 3 settings and matching visual editor shipped.
- [ ] Phase 4 state, reconnect, availability and recovery shipped.
- [ ] Phase 5 native feature and migration examples shipped.
- [ ] Phase 6 bounded activity metadata shipped if justified.

Do not show print duplex/copies controls before Phase 2. Preserve omitted-field
API behavior; the new settings UI explicitly requests one copy and one-sided
by default, and exposes long-edge/short-edge when supported. Do not claim that
implicit printer defaults are one-sided before that path exists.

Use sensor entity IDs for selection, progress and cancellation under the
[multiple-printer decision](decisions/2026-10-08-multiple-printers.md). Preserve
`_submit` validation, fresh paper defaults for explicit sides, and the
[bounded payload decision](decisions/2026-10-08-bounded-print-payload.md).
Never retry an ambiguous accepted print automatically. Settings apply to the
next job, freeze after submission, and initially reset to documented defaults
on card reload. Quick-print and remembered presets are separate opt-in work.

Primary edit points at the baseline: `custom_components/ipp_print/static/card.js:29`
for configuration, `:44` for layout, `:203` for cancel; `__init__.py:349` for shared
submission and `:537` for upload parsing; `printer.py:140` for capabilities,
`sensor.py:99` for idle metadata, and `__init__.py:236` for resource registration.

## Release checks

Keep each backend/UI/state/host increment independently usable. Run compileall,
pytest, Ruff and card tests after npm ci, then the hosted validation workflow.
Behavior changes need manifest/changelog/README/examples and a HACS release tag;
this planning change does not. Record tested scan/print release pairs and pinned
shared contract versions without creating a runtime dependency between projects.

Check old YAML, non-admin use, declared minimum/current HA and the physical
Android app. Test 320/390/768px, narrow pairs, light/dark/custom themes, keyboard,
duplicate prevention, external integration jobs and reconnect. Validate copies,
one-sided and both duplex binding modes on the HP. Two physical printers remain
a separate hardware gate where available; automated routing fixtures cover it
until then. Use the canonical plan's idle-install and rollback procedure.

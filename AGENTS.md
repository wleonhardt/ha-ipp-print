# AGENTS.md — ha-ipp-print

Agent operations file. Read before making changes.

## Instruction priority

1. Direct user instruction in the session
2. This file
3. `plans/` (active plans + `plans/decisions/`)
4. Repo conventions inferred from existing code

## Project overview

Home Assistant custom integration (`custom_components/ipp_print/`) that submits
PDFs to IPP network printers and tracks per-job state, plus a vanilla-JS
Lovelace card (`static/card.js`) served by the integration itself at a
content-hashed URL. Distributed via HACS. Sister project: `ha-escl-scan`
(same architecture, scanning).

Stack: Python 3.13+ (HA 2024.8+ APIs, asyncio, aiohttp), hand-rolled IPP
binary protocol (no pyipp), vanilla JS web component (no Lit, no build step).

## Non-negotiable rules

- `python -m compileall -q custom_components/ipp_print` must pass before done.
- CI must stay green: hassfest, HACS validation (`.github/workflows/validate.yml`).
- If a test suite exists (`tests/`), `pytest` must pass before done.
- No new runtime dependencies without a decision record — integration is
  deliberately stdlib+aiohttp only (`manifest.json` has no `requirements`).
- Never do blocking I/O (file reads, SSL context setup, hashing large files)
  on the event loop — use `hass.async_add_executor_job`.
- card.js has no build step; keep it framework-free ES2020. `customElements.define`
  must stay at top of file (HA race — see comment there).
- Check `plans/decisions/` before proposing structural changes.
- Bump `manifest.json` version on user-visible changes (semver-ish 0.x) and
  add a matching `CHANGELOG.md` section; the release workflow refuses tags
  without one.
- Commit after each meaningful change.

## Before-done checklist

- [ ] compileall passes
- [ ] tests pass (if present)
- [ ] version bumped when behavior changed
- [ ] README updated when config/entities/endpoints changed
- [ ] CHANGELOG.md section added when version bumped
- [ ] no `__pycache__`/artifacts staged

## Key commands

```sh
python -m compileall -q custom_components/ipp_print   # syntax gate (CI parity)
node --check custom_components/ipp_print/static/card.js  # card syntax gate
git ls-files | grep -i pyc                            # must be empty
```

## Workspace structure

- `custom_components/ipp_print/__init__.py` — setup, HTTP views (`/api/ipp_print/{print,cancel}`), card static path + lovelace resource sync
- `custom_components/ipp_print/printer.py` — minimal IPP/2.0 wire client (Print-Job, Get-Job-Attributes, Cancel-Job)
- `custom_components/ipp_print/coordinator.py` — per-job poll loop (1.5 s), fires `ipp_print_job_state_changed` / `ipp_print_job_completed`
- `custom_components/ipp_print/sensor.py` — `sensor.printer_current_job` (hardcoded entity_id)
- `custom_components/ipp_print/config_flow.py` — config + options flow
- `custom_components/ipp_print/static/card.js` — Lovelace upload card + self-heal machinery
- `examples/` — dashboard YAML; `assets/` — screenshots

## Context recovery

Lost context mid-task: re-read this file, `plans/next-up.md`, active plan in
`plans/`, then `git log --oneline -15`. Project knowledge belongs in `plans/`,
not agent memory.

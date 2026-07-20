# Stability & performance review — 2026-07-20

Status: planned
Scope: full read of `__init__.py`, `printer.py`, `coordinator.py`, `sensor.py`,
`config_flow.py`, `const.py`, `static/card.js`, manifest/hacs/CI.

Findings ranked by severity, then a phased remediation plan. File:line refs
point at current `main` (a9fc71d).

---

## A. Correctness / stability bugs

### A1. Poll loop never gives up on an unreachable printer — HIGH
`coordinator.py:151-160` — `_poll_one` catches every exception and returns
without changing job state. A job whose printer goes offline (power-off
mid-job, Wi-Fi drop) stays non-terminal forever, so `_poll_loop` spins every
1.5 s indefinitely: log-spam (`Get-Job-Attributes failed` warning per cycle),
a leaked background task, and `sensor.printer_current_job` frozen on
`processing`. `TrackedJob.last_seen` is written but never read — it's the
obvious input for a give-up rule.

**Fix:** track consecutive failures / time since `last_seen`; after a cap
(e.g. 10 failures or 60 s), mark the job terminal with a distinct state
(`"lost"` or `state_reasons="printer-unreachable"`), fire events, stop the
loop. Add exponential backoff between failed polls.

### A2. Coordinator task and client survive entry unload — HIGH
`__init__.py:128-132` — `async_unload_entry` pops `hass.data` but never
cancels `coordinator._poll_task`. Options-flow change triggers reload → old
coordinator keeps polling with the old client config alongside the new one
(duplicate events, wrong printer after host change). Combined with A1 the old
task can spin forever.

**Fix:** spawn the poll loop via
`entry.async_create_background_task(hass, ...)` (auto-cancelled on unload)
instead of `hass.loop.create_task` (`coordinator.py:122`), or add an explicit
`coordinator.async_shutdown()` called from `async_unload_entry`.

### A3. Vanished job always reported "completed" — even after cancel — MEDIUM
`coordinator.py:157-159` — `attrs is None` → `_mark_terminal(job, "completed")`.
Many printers purge a canceled job immediately, so Cancel → next poll →
not-found → card shows "Print complete ✓". Same misreport for jobs the
printer aborts and purges. Also conflates "IPP status not-found" with
"response parsed but attrs missing" (`printer.py:211-218` returns None for
both).

**Fix:** have `parse_job_attrs_response` distinguish not-found status from
parse failure; record cancel intent on the job (`cancel_requested` flag in
`async_cancel`) and report `canceled` when a cancel-requested job vanishes;
consider `unknown` fallback instead of `completed` otherwise.

### A4. Self-healed card instances never receive `hass` — uploads 401 — MEDIUM
`card.js:437-443` — heal path creates the element and calls `setConfig`, but
lovelace's `hui-card` still holds a reference to the old error card, so
subsequent `hass` assignments never reach the fresh node. Result: healed card
renders fine but `this._hass` is undefined → no bearer token → upload/cancel
fail with 401, and progress tracking silently no-ops. The exact devices the
heal targets (slow mobile) get a zombie card.

**Fix:** in `_upload`/`_cancelJob`/`_trackPrintProgress`, fall back to
`document.querySelector('home-assistant')?.hass` when `this._hass` is unset;
optionally assign it during heal.

### A5. Multi-entry setup is silently broken (three ways) — MEDIUM
- `__init__.py:179-187` — `_live_entry` returns the *first* dict entry
  (docstring claims most-recent); with two printers all print/cancel traffic
  goes to whichever entry set up first, and order flips after reloads
  (pop + re-insert moves entries to the end).
- `sensor.py:53` — hardcoded `self.entity_id = "sensor.printer_current_job"`;
  a second entry collides (HA refuses/suffixes the duplicate).
- Card hardcodes the same sensor name (`card.js:278`).

**Fix (short-term, honest):** add `"single_config_entry": true` to
`manifest.json` (HA ≥2024.6) so the UI prevents a second entry; fix the
`_live_entry` docstring. **Long-term:** entry-aware endpoints
(`?entry_id=`), per-device entity naming, card `sensor:`/printer option.
Decision recorded in `plans/open-questions.md`.

### A6. Blocking SSL work on the event loop — MEDIUM
`printer.py:246-267` — `_ssl_context()` runs inside `_post_ipp` on the loop;
`ssl.SSLContext()`/`set_ciphers`/`load_default_certs` do blocking work (HA
2024.x logs "Detected blocking call … inside the event loop" for exactly
this). It's also rebuilt on *every request* — every 1.5 s poll.

**Fix:** build the context once (executor job at client construction or first
use), cache it on the client.

### A7. Non-200 HTTP responses parsed as IPP garbage — LOW
`printer.py:335-342` — logs a warning on non-200 but still returns the body
to the IPP parser. A 401 (bad basic-auth) or an HTML error page becomes
`ValueError: IPP response too short` or nonsense attrs; the user sees
"IPP submission failed: …" instead of "printer rejected credentials".

**Fix:** raise a typed error for non-200 (special-case 401/403 → clear
message), let views map it to a useful status/message.

### A8. `setConfig` after first render ignores config — LOW
`card.js:24-27,37-39` — `_render` early-returns once rendered; editing the
card title in the UI editor does nothing until reload.
**Fix:** when already rendered, update `_titleEl.textContent`.

### A9. PDF magic check rejects legal PDFs with preamble junk — LOW
`__init__.py:233` — spec allows `%PDF-` anywhere in the first 1024 bytes;
scanner/printer-generated files sometimes have leading junk.
**Fix:** `PDF_MAGIC in buf[:1024]`.

### A10. Upload token expiry edge — LOW
`card.js:233-238` — token grabbed from `hass.auth.data.access_token`
internals at click time; normally fine (frontend refreshes), but a suspended
mobile tab can hold a stale token → 401 with no retry.
**Fix:** prefer `hass.fetchWithAuth`-style call (handles refresh), keep
current header path as fallback. Pairs with A4 fallback.

---

## B. Performance

### B1. New ClientSession + TCPConnector + TLS handshake per request — HIGH
`printer.py:308-342` — every poll (1.5 s cadence!) builds a session,
connector, SSL context, does a full TLS handshake, tears it down. Printer TLS
stacks are slow (hundreds of ms) and some rate-limit handshakes. This is the
single biggest efficiency win: keep one session per client with keep-alive,
close it on unload (ties into A2). Poll latency drops, printer load drops,
HA loop churn drops.

### B2. Card subscribes to the global `state_changed` firehose — MEDIUM
`card.js:346` — `subscribeEvents(..., 'state_changed')` receives *every*
entity change in the instance (busy HA = hundreds/sec on a phone browser)
and filters client-side, for the duration of a print job.
**Fix:** use the already-pushed `hass` setter (compare
`hass.states['sensor.printer_current_job']` on assignment — zero extra
subscriptions), or `subscribe_trigger` scoped to the entity.

### B3. 50 MiB uploads double-buffered in RAM — MEDIUM
`__init__.py:224-244` — chunks accumulate into a `bytearray`, then
`bytes(buf)` copies the whole thing again (~100 MiB peak per upload), held
for the entire IPP POST. On an RPi with concurrent uploads this hurts.
**Fix:** cheap: pass `memoryview`/single `bytes` (drop the copy). Better:
stream: spool to a temp file or feed an async generator to aiohttp so the
document never fully resides in memory.

### B4. Content-hashed card URL served with caching disabled — LOW
`__init__.py:116` — `StaticPathConfig(..., cache_headers=False)`, yet the URL
embeds a content hash whose whole point is cache-forever + new-URL-on-change.
Browser refetches card.js on every dashboard load.
**Fix:** flip to `True`.

### B5. Heal machinery runs forever — LOW
`card.js:459-479` — 8 full DOM+shadow-root walks in the first 10 s (fine),
plus a permanent `MutationObserver` over `document.body` subtree. Once this
script has executed, `customElements.define` has run, so "element doesn't
exist" error cards can no longer be created — the observer only pays cost.
**Fix:** `observer.disconnect()` after ~30 s, or drop the observer entirely.

---

## C. Robustness / hygiene

- **C1. `_jobs` never pruned** (`coordinator.py:77,113`) — every job ever
  printed stays in memory until restart. Prune terminal jobs when they leave
  the hold window.
- **C2. 60 s total timeout too tight for big jobs** (`printer.py:283,292`) —
  50 MiB over Wi-Fi to a slow printer can exceed it; the *total* timeout
  covers the upload. Raise for `print_job` (e.g. 300 s) or scale with size.
- **C3. `_sync_lovelace_resource`** (`__init__.py:139-176`) — pokes three
  private `hass.data` shapes, busy-waits up to 60 s, and will raise+log in
  YAML-resource mode (create/delete unsupported → caught, but noisy). Detect
  YAML mode and skip quietly; keep version-proofing comment.
- **C4. Dual registration** — card is injected both via `add_extra_js_url`
  (`__init__.py:118`, loads on *every* frontend page for all users) and via
  lovelace resources. Redundant; pick resources (scoped to dashboards) and
  drop extra_js, or document why both.
- **C5. Any authenticated user can print and cancel any job-id**
  (`__init__.py:199,288`) — including job-ids not submitted via HA. Decide:
  fine (LAN trust) or gate cancel to admin/job-ids the coordinator tracks.
  Logged in `plans/open-questions.md`.
- **C6. Error-detail leakage** — `PrintView` returns raw exception text to
  the client (`__init__.py:254`); acceptable locally, but trim to exception
  class + short message.
- **C7. Stale text** — coordinator docstring says `printer_job_*` events
  (actual: `ipp_print_job_*`, `coordinator.py:9-11`); card description still
  mentions `/media/print_inbox` and "LJ Printer Upload" branding
  (`card.js:392-393`); comment references a legacy `/upload` endpoint that no
  longer exists (`card.js:242-243`).
- **C8. `job_name.encode()[:255]`** (`printer.py:121`) can split a UTF-8
  codepoint (currently unreachable — sanitizer is ASCII-only — but fragile if
  sanitizer loosens). Truncate at a codepoint boundary.
- **C9. Options flow password field is a plain string** (`config_flow.py:109`)
  — rendered as cleartext; use a password selector. Unique_id also goes stale
  when host changes via options (cosmetic).
- **C10. `_attr_device_class = "enum"`** (`sensor.py:45`) — works, but use
  `SensorDeviceClass.ENUM`.

---

## D. Testing gap — the structural risk

CI is hassfest + HACS validation + byte-compile. Zero behavioral tests. The
riskiest code is exactly the most testable:

1. **IPP wire parser** (`printer.py`) — pure functions. Round-trip tests:
   build_* → parse_*; truncated/garbage responses; 1setOf value carry;
   not-found vs malformed (locks in A3's contract).
2. **Coordinator state machine** — fake `PrinterClient`; transitions
   pending→processing→completed; cancel-then-vanish (A3); unreachable printer
   give-up (A1); hold-window clear; event firing.
3. **Views** — `pytest-homeassistant-custom-component` +
   `aiohttp_client`: happy path, missing field, oversize (413), bad magic
   (415), unconfigured (503).
4. **Config flow** — success, cannot_connect, duplicate unique_id.

Add `ruff` (lint) to CI alongside. No new runtime deps — test deps only.

---

## Phased plan

### Phase 1 — stop the bleeding (correctness, ~half day)
1. A2: entry-scoped background task + clean shutdown (unblocks A1/B1 work).
2. A1: give-up rule + backoff in `_poll_one` using `last_seen`.
3. A3: cancel-intent flag + not-found/parse-failure split.
4. A4 (+A10): `home-assistant` element `hass` fallback in card fetch paths.
5. A5 short-term: `single_config_entry: true`; fix `_live_entry` docstring.
6. Bump version, verify with a real printer: submit, cancel, yank power
   mid-job.

### Phase 2 — performance (~half day)
1. B1: persistent `ClientSession` per client, closed on unload; A6: SSL
   context built once off-loop.
2. B2: replace firehose subscription with `hass`-setter diffing.
3. B3: drop the double copy (memoryview); streaming optional later.
4. B4: `cache_headers=True`. B5: disconnect observer after 30 s.

### Phase 3 — test harness (~1 day)
1. `tests/` with `pytest-homeassistant-custom-component`; parser + coordinator
   suites first (they encode Phase 1 fixes), then views + config flow.
2. CI: pytest + ruff jobs in `validate.yml`.

### Phase 4 — polish (opportunistic)
- A7 typed HTTP errors, A8 title update, A9 1 KiB magic scan, C1 pruning,
  C2 timeout scaling, C3 YAML-mode detection, C4 single injection path,
  C6-C10 hygiene sweep.

### Explicitly deferred
- True multi-printer support (entry-aware endpoints + card selector) — behind
  `single_config_entry` until someone asks.
- Non-PDF formats, print options (copies, duplex) — out of scope here.

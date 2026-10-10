# Contributing to IPP Print

[Project overview](README.md) · [User documentation](docs/README.md)

## Report a device or bug

Use the repository's [issue forms](https://github.com/wleonhardt/ha-ipp-print/issues/new/choose).
Successful device reports are useful too. Include model/firmware, integration and
Home Assistant versions, connection route, exact settings, and what was tested.
Attach [diagnostics](docs/troubleshooting.md#collect-diagnostics); redact manually
collected logs and captures before sharing. A private document is not required.

## Run the checks

The normal CI environment uses **Python 3.13** and Node.js 22. From the
repository root:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest tests -q
.venv/bin/ruff check custom_components tests
.venv/bin/python -m compileall -q custom_components/ipp_print
npm ci
npm run test:card
```

The minimum supported Home Assistant is also tested in isolation with Python
3.12 and the pinned minimum-version test stack:

```sh
python3.12 -m venv venv/minimum
venv/minimum/bin/pip install -r requirements_test_minimum.txt
venv/minimum/bin/python -m pytest -q
```

These tests simulate devices or use local test servers. They do not need your
configured printer. Minimum-version pins are test dependencies, not additions
to the runtime integration.

## Find the code

| Location | Purpose |
| --- | --- |
| `custom_components/ipp_print/__init__.py` | Setup, HTTP routes and dashboard resource registration. |
| `config_flow.py` | Discovery, connection setup and integration options. |
| `printer.py` | IPP client and protocol handling. |
| `coordinator.py` | Job lifecycle and state tracking. |
| `sensor.py`, `diagnostics.py` | Home Assistant state and diagnostic output. |
| `static/card.js` | Plain JavaScript card, native feature and visual editor. |
| [Shared presentation core](shared/README.md) | Vendored behavior common to Scan and Print. |
| [Plans and decisions](plans/README.md) | Design rationale, validation records and backlog. |

Code filenames in the table are relative to `custom_components/ipp_print/`.
Keep device I/O asynchronous and blocking file work off the event loop. Preserve
bounded reads, cancellation cleanup and explicit user submission. The cards are
plain ES modules with no framework or required build step. Follow [AGENTS.md](AGENTS.md)
and existing tests when changing behavior.

## Contribute a translation

The card and visual editor currently ship English. They use Home Assistant's
language with region → base language → English fallback for each message.

1. Add a lowercase locale catalog beside `en` in `CARD_TRANSLATIONS` in
   `static/card.js`.
2. Keep semantic keys and `{placeholders}`. Translate whole messages; plural
   messages use `Intl.PluralRules` and must include `other`.
3. Keep protocol values such as `gray`, `Platen` and `two-sided-short-edge`
   unchanged. Render translated text as text, not HTML.
4. Obtain a fluent speaker's review. Check narrow screens, long labels,
   fallback, keyboard navigation and placeholder parity.
5. Update the approved-language assertion, add relevant card tests, and run
   `npm run test:card`.

Device errors, filenames and custom titles remain as supplied. Integration
setup/action translations use `strings.json` and `translations/`. Changes to the
shared card contract must be synchronized and tested in both repositories; see
[the shared core workflow](shared/README.md).

## Maintain the documentation

Keep the main README focused on installation and first use. Put option tables,
protocol details and recovery behavior in the relevant `docs/` page. Link to one
canonical explanation instead of repeating it, and keep the Scan/Print navigation
consistent. Update examples and verify event names/fields against code.

Before publishing, check relative links, heading anchors and fenced YAML/JSON.
Distinguish physical tests, community reports and simulated coverage in the
compatibility guide. Release history belongs in [CHANGELOG.md](CHANGELOG.md);
internal acceptance records belong in `plans/`.

## Release behavior changes

Bump `manifest.json`, add a matching changelog section, and push a `vX.Y.Z` tag.
The release workflow checks the version and publishes the GitHub release from
the changelog. HACS installs releases. Documentation-only edits do not need an
integration release or a Home Assistant restart.

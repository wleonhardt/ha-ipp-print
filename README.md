# IPP Print for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![Release](https://img.shields.io/github/v/release/wleonhardt/ha-ipp-print)](https://github.com/wleonhardt/ha-ipp-print/releases)
[![Validation](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml/badge.svg)](https://github.com/wleonhardt/ha-ipp-print/actions/workflows/validate.yml)

Print a PDF or image from your Home Assistant dashboard. Choose a file, check
your settings, and follow its progress without leaving Home Assistant.

Pairs with [eSCL Scan](https://github.com/wleonhardt/ha-escl-scan) for matching
Scan and Print controls on the same dashboard.

## Before you start

- **Home Assistant 2024.12 or newer.**
- An IPP/2.0 network printer or CUPS queue reachable from Home Assistant. The
  selected endpoint must accept your file format; PDF, JPEG and PNG support varies.

Check [device compatibility](docs/compatibility.md) if you are unsure about your
hardware or use a USB device, bridge or separate network.

## Installation

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=wleonhardt&repository=ha-ipp-print&category=integration)

1. Open **HACS**, search for **IPP Print**, and select **Download**.
   It is in the default store; no custom repository is needed.
2. Restart Home Assistant.
3. Open **Settings → Devices & services** and configure the discovered printer.
   If it does not appear, choose **Add integration → IPP Print** and enter its
   connection details.

[Manual installation, connection settings and updates →](docs/installation.md)

## Adding the card to a dashboard

1. Edit your dashboard and add a **Tile** card.
2. Select the printer's **Current job** sensor from this integration.
3. In **Features**, add **IPP Print**. Set **Features position** to **Bottom**.
4. In a Sections dashboard, leave **Rows** set to **Auto** so messages can expand.

The card is included and registered automatically. No separate card download,
resource entry or styling code is needed.

[Dashboard examples, side-by-side cards and other card types →](docs/dashboard.md)

## Print your first document

1. Press **Choose file** and select a PDF, JPEG or PNG supported by your printer.
2. Set **Two-sided** if needed. Open the sliders button for copies, binding,
   paper, tray, color and quality.
3. Press **Print**. Choosing a file alone does not send it to the printer.

**Recent activity** keeps the last ten job outcomes per printer for seven days,
including after a refresh or restart. It stores job details, not the documents.

If a submission's outcome is uncertain, check the printer queue before trying
again to avoid a duplicate print. See [printing and recovery](docs/printing.md).

## Guides and help

| I want to… | Read |
| --- | --- |
| Adjust print settings or understand job status | [Printing](docs/printing.md) |
| Build an automation | [Actions, entities and events](docs/automations.md) |
| Fix a problem | [Troubleshooting](docs/troubleshooting.md) |
| Use a bridge or check tested hardware | [Compatibility](docs/compatibility.md) |
| Build a client or contribute | [HTTP API](docs/api.md) · [Contributing](CONTRIBUTING.md) |

[All documentation](docs/README.md) · [Report a problem](https://github.com/wleonhardt/ha-ipp-print/issues/new/choose) · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)

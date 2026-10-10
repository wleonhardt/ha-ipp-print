# YAML examples

[Documentation](../docs/README.md) · [Dashboard guide](../docs/dashboard.md)

Replace sample sensor IDs, paths and notification actions with your own. Each
file's top-level structure determines where to paste it: a single card, a card
list, a complete view, or one automation. Paired examples require both
[eSCL Scan](https://github.com/wleonhardt/ha-escl-scan) and
[IPP Print](https://github.com/wleonhardt/ha-ipp-print).

| Example | Use it for |
| --- | --- |
| [automation-print-file.yaml](automation-print-file.yaml) | Scheduled printing of a file on the Home Assistant host. |
| [compatibility-options.yaml](compatibility-options.yaml) | Standalone card defaults for scan/print options. |
| [dashboard-card.yaml](dashboard-card.yaml) | Standalone card. |
| [dashboard-multiple-printers.yaml](dashboard-multiple-printers.yaml) | One named native card per printer. |
| [dashboard-mushroom.yaml](dashboard-mushroom.yaml) | One current Mushroom Template card hosting the native feature. |
| [dashboard-native-tile.yaml](dashboard-native-tile.yaml) | One native Tile with the integration feature (recommended). |
| [dashboard-sections.yaml](dashboard-sections.yaml) | Side-by-side standalone Scan/Print in Sections, with independent expansion. |
| [dashboard-with-scan.yaml](dashboard-with-scan.yaml) | Standalone Print/Scan pair in a Horizontal stack. |

For adjacent cards, keep each in its own Vertical stack and use **Rows: Auto**.
The Mushroom example requires Mushroom; Tile and standalone examples do not.

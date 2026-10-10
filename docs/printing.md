# Printing and recent activity

[Documentation](README.md) · [Dashboard setup](dashboard.md)

## Print a document

1. Press **Choose file** and select a supported PDF, JPEG or PNG.
2. Check the filename. **Replace** selects a different file; **Clear** removes it.
3. Set **Two-sided**, or open the sliders button for more options.
4. Press **Print** and follow the reported progress.

Choosing a file does not upload or print it. The selection stays in that browser
card until you press Print; canceling the file picker preserves the previous
selection. The browser releases the selected file after acceptance. Known
validation errors keep it available for correction.

Files must be **50 MiB or smaller**. The printer or queue must advertise support
for the actual format. Renaming a PNG to `.jpg` does not convert it. The integration
does not render documents into a printer language; use an appropriately configured
[CUPS queue or Printer Application](compatibility.md) if conversion is required.

## Choose print settings

Choose a file before opening format-specific options. The printer may offer
different settings for PDF and images.

| Option | What to choose |
| --- | --- |
| Copies | 1–99, within the printer's advertised maximum. |
| Two-sided | Off for one-sided printing; on if supported by this printer. |
| Binding | Long edge for book-style turning; short edge for the other binding direction. Check the result for your document orientation. |
| Paper | Device default or a supported size, shown with a readable name and dimensions. |
| Tray | Device default or an advertised paper source. |
| Color | Device default or an advertised mode. |
| Quality | Device default or an advertised draft, normal or best setting. |

The card starts with **one copy and one-sided printing** unless you change its
[defaults](dashboard.md#card-defaults). Selecting another file or printer
revalidates the available choices. Controls lock while submitting or printing.

Explicit options are checked before document upload using IPP Validate-Job.
If the printer explicitly does not implement that operation, the integration
requests strict attribute handling on submission and shows a warning. Rejected
settings submit nothing; reported substitutions are shown as warnings.

For an explicit sides request, the integration refreshes the printer's default
paper size when no paper was chosen. This helps devices that ignore duplex
without a paper size. Load paper matching the printer's own size/tray settings;
a paper confirmation prompt can still require action at the device.

## Follow progress and cancel

The card reports the printer's completed pages or sheets. Some printers change
their estimated total while rendering, so a growing page count is not proof
of completion. Only the final job state confirms the outcome.

Use **Cancel** while an integration-tracked job is active. Cancellation depends
on the printer accepting the request and cannot retrieve pages already printed.

| Status | Meaning |
| --- | --- |
| Pending / Held | The printer accepted the job but has not started it. |
| Processing | The printer is working on the job. |
| Stopped | The printer reports a pause; check its screen or queue for the reason. |
| Completed | The printer reported completion. |
| Canceled / Aborted | The job ended without normal completion. |
| Unknown | The final result could not be confirmed. Check the printer before resending. |

## Recent activity and restarts

Expand **Recent activity** to see up to **ten outcomes per printer**, retained
for **seven days from submission**. Each record includes the filename, reported
outcome, completed count and timestamps. It survives a dashboard refresh or Home
Assistant restart. Documents are not retained and there is no reprint action.

The card reconnects to jobs still tracked by the running integration. Restarting
Home Assistant or reloading the integration stops active tracking; it does not
cancel printer-side jobs. If no final outcome was recorded, restored activity
says **Outcome unknown — check the printer**. No job is automatically resent.
Removing an integration entry removes that printer's activity metadata.

## Multiple printers and simultaneous requests

Each printer has its own device, Current job sensor and activity list. Use a
[native card for each printer](dashboard.md#put-scan-and-print-beside-each-other)
to keep destinations clear. The standalone card can choose a printer in Options.

Only **one document can be prepared or submitted at a time** across all printers,
services and uploads. A second request gets a busy message; there is no queue or
automatic retry. Once submission finishes, another document can be sent even if
the first printer is still physically printing. The sensor/card follows its
printer's newest job; events continue for other jobs still being tracked.

## If submission fails

- **No print job was submitted:** correct the reported settings/connection
  problem, then make a new explicit attempt when allowed.
- **The job may have printed / outcome unknown:** inspect the printer queue
  and output before sending anything again.

A transient settings lookup can be retried by a new print attempt once after
30 seconds; another failure returns to the five-minute backoff. Follow the wait
time in the error. This only retries the settings lookup, never the document.

[More troubleshooting and diagnostic collection →](troubleshooting.md)

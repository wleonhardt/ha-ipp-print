# Unsupported image format reported as a connection error

Status: fixed for print 0.10.2; local validation passed, deployment verification pending.

The user confirmed the paired native cards and navigation work on the physical
phone, then reported a print failure for a file named with a `.jpg` extension.
The displayed message said current format/paper settings could not be read.

The HP M283fdw is reachable. Read-only native IPP queries accept JPEG and PDF,
advertise both, and reject PNG with `client-error-document-format-not-supported`
(`0x040a`). Its generic format list excludes PNG despite advertising octet-stream
auto-sensing. HA's JPEG cache was fresh at 14:54:08 UTC; its failed PNG probe was
at 14:54:10, matching the reported attempt. This suggests PNG content with JPEG
metadata; the user's original image has not been provided, so that exact file
has not been inspected.

An end-to-end reproduction uploaded a tiny PNG with a `.jpg` filename and
`image/jpeg` MIME metadata, plus the card's copies=1 and sides=one-sided
defaults. The installed 0.10.1 endpoint returned the identical 502 connection
message with `job_may_exist=false`. No device job was submitted. The backend
correctly detected PNG bytes, but tried the format-specific probe before checking
the already-known supported-format list; its rejected probe became a generic
capability error.

The shared HTTP/service submit path now checks fresh generic format support
before that probe, retains the post-probe check, and lets fresh scoped data
override stale generic data. A mismatch returns 415, names the detected format,
suggests only advertised upload formats, explains filename conversion, and
confirms no job was submitted. Native bytes are never silently converted or
sent as octet-stream. Embedded rendering remains a separate proposal.

Validation: 220 Python tests, 62 card tests after npm ci, Ruff, compileall and
shared-core parity pass. New tests cover mislabeled PNG with/without explicit
card defaults, no capability/validation/print calls after a known mismatch, and
stale generic exclusions followed by fresh supported-format data. Existing
JPEG/PNG/PDF upload, unknown capability and transport-failure tests still pass.

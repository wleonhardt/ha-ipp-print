# Unsupported image format reported as a connection error

Status: released and installed as print 0.10.2; local, hosted and live endpoint
validation pass. The user confirmed their file was JPEG and a retry went through.
The cause of their first failure remains unconfirmed.

The user confirmed the paired native cards and navigation work on the physical
phone, then reported a print failure for a file named with a `.jpg` extension.
The displayed message said current format/paper settings could not be read.

The HP M283fdw is reachable. Read-only native IPP queries accept JPEG and PDF,
advertise both, and reject PNG with `client-error-document-format-not-supported`
(`0x040a`). Its generic format list excludes PNG despite advertising octet-stream
auto-sensing. HA's JPEG cache was fresh at 14:54:08 UTC; a failed PNG probe was
at 14:54:10. An initial hypothesis linked that timing to the user's file, but
timing alone does not establish its format. The user subsequently confirmed it
was JPEG. The original file has not been independently inspected, and the PNG
probe must not be treated as a diagnosis of their failed attempt.

A separate end-to-end test uploaded a tiny PNG with a `.jpg` filename and
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

Release `v0.10.2`, commit `2bebacf`: all six hosted jobs passed in validation
`37948785826`; release `37948788648` published successfully. Backed up the prior
integration to `/config/.document-card-backups/before-print-format-fix-v0102-20261009.tar.gz`.
Both job sensors were confirmed idle, then HA was restarted to load the backend
change. Installed __init__.py SHA-256 matches source:
`8271144a322c9b226e9d66037f3483bfc4400904acaaa9a2083fdacb1c6bc11a`.

After restart, the same mislabeled tiny PNG upload returns 415, identifies PNG,
offers PDF/JPEG, and reports `job_may_exist=false`; the job sensor stays idle.
A direct JPEG Validate-Job check with copies=1, one-sided, and the fresh Letter
default returned success with no warning. Validate-Job contains no document and
does not submit a print job. This is not a physical print of the user's file.

User follow-up: “it was a jpeg it just went through now after trying again”.
Record this as a successful JPEG retry reported by the user, without attributing
it to the PNG patch or claiming independently verified job completion/output.
A transient settings lookup failure is possible but unconfirmed. If it recurs,
capture the failed capability request and error category before assigning a
cause; conversion is not indicated by this report.

# 2026-10-08 — Send IPP documents without another full-size copy

## Context

The HTTP view already buffers up to 50 MiB. `build_print_job` concatenates
that buffer with the protocol header, allocating another document-sized
object on the event loop. Concurrent prints multiply that memory pressure.
Some printer firmware does not accept chunked HTTP requests, so a bare async
generator would trade memory savings for compatibility failures.

## Decision

Keep the capped input buffer, but send a sized aiohttp Payload containing
the small IPP header and a memoryview of the existing document. Write the
document in 64 KiB pieces with backpressure. A known payload size preserves
Content-Length and avoids chunked transfer without a new runtime dependency.
The public pure wire builder remains available for unit tests and small uses.

Bound printer responses to 1 MiB, which is generous for the requested
attribute subset. Do not follow HTTP redirects: a Print-Job must stay bound
to its configured endpoint and must not be replayed elsewhere implicitly.

## Consequences

Removes the second document-sized allocation and the full-size concatenation
from the production submission path. Uploads still buffer one document in
memory; disk spooling or a global concurrency limit remains a separate
future decision. Validate the sized payload against an HTTP test server,
including exact bytes, Content-Length, no chunking, and session reuse.

## Accepted follow-up — 2026-10-09

The user approved upload concurrency hardening. Reserve one HA-wide document
slot before multipart parsing or service file reading, through submission.
Reject competing requests immediately instead of queueing their documents.
Keep it in domain-level state so config-entry reload cannot reset it. Physical
job tracking does not hold the slot; printer routing remains unchanged.

Bound the incoming HTTP body to five minutes. Reject busy and timed-out uploads
with a closed connection, actionable 409/408 messages and `job_may_exist: false`.
Do not shorten the outgoing Print-Job timeout or retry ambiguous submissions.
Cancellation of an executor-backed service read retains the slot until the
worker finishes, including repeated cancellation and read failures.

This bounds admitted document buffers, not all HTTP/transport overhead. The
50 MiB file limit and sized outgoing payload remain unchanged. No disk spool,
queue, configuration option or dependency. [Reproduction and validation](../2026-10-09-upload-concurrency.md).

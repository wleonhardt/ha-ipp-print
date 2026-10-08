# Open questions

## Open

## Resolved

- Multi-printer support: implemented in v0.4.0; routing uses job-sensor entity IDs. See [decision](decisions/2026-10-08-multiple-printers.md). (2026-10-08)
- Endpoint authorization: any authenticated user may print (LAN-trust, matches HA norms); cancel restricted to coordinator-tracked job-ids so arbitrary printer jobs can't be cancelled through HA. (2026-07-20)

# Open questions

## Open

## Resolved

- Multi-printer support: declared `single_config_entry: true`; entry-aware endpoints deferred until requested. (2026-07-20)
- Endpoint authorization: any authenticated user may print (LAN-trust, matches HA norms); cancel restricted to coordinator-tracked job-ids so arbitrary printer jobs can't be cancelled through HA. (2026-07-20)

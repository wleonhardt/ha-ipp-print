# Open questions

## Open

- Multi-printer support: declare `single_config_entry: true` (honest, simple) or make endpoints/sensor entry-aware (card needs a printer selector)? Review plan assumes single-instance short-term. (2026-07-20)
- Should `/api/ipp_print/{print,cancel}` be admin-only, or is any authenticated user fine? Currently any user can print and cancel arbitrary printer job-ids. (2026-07-20)

## Resolved

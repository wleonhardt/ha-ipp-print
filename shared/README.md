# Document card presentation core v4

Canonical source: `ha-escl-scan/shared/card-core.js`. This identical vendored copy
owns localization, base styles, safe status details, the native Options dialog,
native feature adapters, and bounded activity presentation. Its scan download
helper uses the domain-owned authenticated transport and stale-request guard.
Domain-specific job state, options, capabilities and transport remain in card.js.
Each card registers its main element first and includes the core inline. There
is no runtime dependency, additional fetch or required build step for installation.

To update, edit the canonical file, copy it to the sister repository, and run
`node tools/sync-card-core.mjs --write` in both repositories. Review both diffs,
run `npm run test:card` in both, and record the tested release pair. Bump the
contract markers for intentional contract changes. CI checks the local source
against the inline copy; compare the two vendored files when releasing a pair.
Domain-specific dialog tags allow independently upgraded integrations to coexist.

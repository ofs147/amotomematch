# AOMatch testing: current product vs legacy

## Current product signal

Tests marked `current` protect the behavior served by the present AOMatch UI.
The authoritative selectable-character source is `load_tag_characters()` with:

- `data/core_xp_tags_v6.csv`
- `data/core_xp_tags_v6_2_review.csv`
- `data/character_display_names_zh.csv`
- `data/series_display_names_zh.csv`

The current baseline is 478 unique selectable character IDs. Tests derive
identity membership from this production path; only the single top-level
contract keeps 478 as a deliberate release baseline.

Run current product tests:

```powershell
python -m pytest -m current -q
```

## Legacy tests

Tests marked `legacy` cover historical migrations, snapshots, and superseded
v2-v6 workflows. Fixed counts such as 90, 291, or 303 remain valid when they
describe an isolated historical artifact. They must not be used as the current
public pool size.

Run legacy coverage:

```powershell
python -m pytest -m legacy -q
```

## Roster and environment tests

Canonical roster CSVs can be protected by the host environment. Current UI
tests use the public Tag-first loader instead. Historical tests that genuinely
cross the protected roster boundary are marked `environment` and `integration`;
the markers classify them but do not silently skip them.

```powershell
python -m pytest -m environment -q
python -m pytest -m integration -q
```

Pytest temporary files and cache are directed to writable project-local
`.pytest-tmp` and `.pytest-cache-local` directories. Product data directories
are never used for temporary test output.

## AI tests

Dynamic AI output is checked structurally: schema, allowed IDs and tags,
recommendation counts, non-empty copy, diversity, and safe fallback. Exact text
is retained only for deterministic fixed-copy behavior.

The AI validator derives its expected high-match and exploration counts from
the upstream fallback selection result. Normal output remains 5+3, while a
quality-filtered two-card exploration result is accepted only when upstream
actually established that reduced contract.

## Full repository

```powershell
python -m pytest -q
```

The full repository includes legacy and environment tests. A failure there must
be interpreted by marker and ownership; it does not automatically mean the
current public product is broken.

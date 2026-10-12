# external/ — private data submodules

## `wbi-ebird-data` (private)

`UBC-FRESH/wbi-ebird-data` is the **private** DataLad/git-annex store for raw eBird
extracts and derived tables. It is wired here as a submodule so the engine can
consume the data without any copy entering this public repository.

**Terms of Use (binding).** Raw eBird data are non-commercial research/education
use only and **must not be publicly distributed**. The store's Arbutus S3 special
remote is configured **private (`public=no`)** — anonymous access is denied. Never
commit raw content, observer identifiers, or annex objects here.

**CI never initialises this submodule** (workflows use `actions/checkout` without
`submodules: true`), and tests that need it skip cleanly. Only the submodule
pointer and `.gitmodules` are public.

### Use

```bash
git submodule update --init external/wbi-ebird-data
datalad get -r external/wbi-ebird-data     # needs Arbutus S3 credentials in the env
```

Contents: `raw/ebd/`, `raw/sed/`, `derived/`, `checksums/` (see the store README).

### Legacy benchmark

`scripts/benchmark_legacy_rbnu.py` fits the reconstructed legacy RBNU design
matrix with the native Python regression and compares against the 2019 R
reference (`tests/fixtures/legacy_rbnu_reference.json`). It exits non-zero if the
private data is missing.

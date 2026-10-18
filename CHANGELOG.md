# Changelog

## [0.0.5]

### Added
- breakthrough curve `c/c0(t)` from the Rosen solution + chart in the UI
- comparison matrix of breakthrough times for all refrigerant / zeolite pairs (`GET /api/matrix`)
- bed height, column diameter and any breakthrough criterion (slider) as inputs
- pytest suite (values checked against the thesis tables)

### Changed
- backend split into `app/core` modules, material data moved to `app/data/*.json`
- `E(c/c0)` from `scipy.special.erfinv` instead of the lookup table (Tab. 12)
- all endpoints under `/api`, frontend uses the dev-server proxy

## [0.0.1]

- first version: Python port of the thesis spreadsheets + simple Angular form

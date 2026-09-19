# Copilot instructions for SeaGarden DST

## Project shape

This repository is a Python decision-support app for SeaGarden. The important split is:

- `app/` is the Shiny front end and wiring layer.
- `src/seagarden_dst/` is the analytical core and model logic.
- `params/` holds data-driven parameter files (YAML) rather than hard-coded coefficients.
- `tests/` covers the analytical core; `app/tests/` covers app smoke checks.

The dependency direction is intentionally one-way: `app/` imports `seagarden_dst`, never the reverse. Keep model code framework-free and reusable outside the UI.

## Local setup and validation

Do **not** create a virtual environment (`venv`, `virtualenv`, conda env) in this
directory. All Python work uses the existing micromamba environment `shiny`:

```bash
micromamba activate shiny
pip install -e ".[app,dev]"      # editable install into `shiny`; pip is only for this repo
```

Or run a single command without activating:

```bash
micromamba run -n shiny pytest -q
```

Install new third-party packages with `micromamba install -n shiny <package>`; fall back
to `pip install` only when a package is not on conda-forge. `shiny_deckgl` (the map layer)
is conda-only and must never be added as a pip dependency. There is no global Python on
PATH; micromamba is the sole distribution.

Run the default validation suite:

```bash
pytest
ruff check .
```

Run a single test file or single test target:

```bash
pytest tests/test_api.py -q
pytest app/tests/test_app_smoke.py -q
pytest tests/test_params.py -q -k regulatory
```

Run the app from the repo root with:

```bash
shiny run app.app
```

Important: run `app.app`, not `app/app.py`. The package layout intentionally makes `app/` importable from the repo root and `pythonpath` is configured in `pyproject.toml` to include both `src` and `.`.

## CI and test matrix

The project is tested in CI on Python 3.11 and 3.13. The default test selection deliberately excludes optional marker groups:

- `engines`
- `e2e`
- `spatial`

This is configured in `pyproject.toml` via `pytest` markers and `addopts`.

If you need to run those optional groups explicitly, use:

```bash
pytest -m engines -q
pytest -m spatial tests/ -q
pytest -m e2e -q
```

Do not assume optional extras are installed unless the task explicitly targets them.

## High-level architecture

The core model is structured around a single public entry point, `seagarden_dst.api.assess_site()`. The UI should call that entry point and render the returned assessment object, rather than reaching into model modules directly.

Key focus areas:

- `src/seagarden_dst/api.py` — public site assessment entry point.
- `src/seagarden_dst/contracts.py` — model contracts, context objects, and exported result objects.
- `src/seagarden_dst/params.py` — parameter loading and validation.
- `src/seagarden_dst/forcing.py` — the `ForcingSource` protocol and reading vocabulary (`SiteReading`, coverage, aggregation); placeholder and seasonal sources live here too.
- `src/seagarden_dst/gridded.py` — `GriddedForcing`: reads the forcing artifact that package C builds. **The only module outside `refresh/` allowed to import xarray**; the core and app must import cleanly without the `spatial` extra.
- `src/seagarden_dst/artifact/` — artifact manifest, grid, and pair contracts (pydantic + stdlib + numpy only, no xarray).
- `src/seagarden_dst/refresh/` — the offline refresh tooling that fetches source layers (Copernicus, EMODnet, HELCOM) and writes the artifact. Never imported by the app at runtime.
- `src/seagarden_dst/calibration.py` — calibration tier registry (spec §7.4); the tier travels with every number to the UI.
- `src/seagarden_dst/regulatory.py` — regulatory record schema (spec §9); schema only, content is produced in-project later.
- `src/seagarden_dst/scenarios.py` — side-by-side scenario comparison (spec §5.4).
- `src/seagarden_dst/growth.py`, `shellfish.py`, `nutrients.py`, `suitability.py` — core model logic.
- `src/seagarden_dst/bowtie_adapter.py`, `eutropy_adapter.py` — optional engine adapters.
- `app/app.py` — app wiring and stale-assessment invalidation.
- `app/modules/` — one UI/server pair per panel (`site`, `catalogue`, `results`, `report`, `user_mode`). `user_mode` implements the four spec §4 entry points as one mode selector; `app/doors.py` is its deprecated predecessor and should not be extended.
- `params/` — data files that define coefficients, species, and regulatory logic.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — package design documents and their implementation plans; `docs/runbooks/` holds release and deploy runbooks. Package letters (A0, A, B, C, D, G) refer to those documents; read the relevant one before changing the corresponding module.

A useful mental model for this repo is: the app is a thin UI around a model core that is meant to be reusable from notebooks and scripts, not just the Shiny app.

## Core model guidance (tightened)

Treat `src/seagarden_dst/` as the durable analytical layer and keep the app UI thin.

- The public entry point is `seagarden_dst.api.assess_site()`. If a change affects ranking, suitability, or result formatting, trace it through the assessment object returned by that function before changing the UI.
- Do not bypass `contracts.py`. Site context, species options, and assessment output are intentionally typed and exported through the contract layer. If a new result field is needed, add it to the contract and preserve the `to_dict()`/report path rather than constructing ad hoc UI-only structures.
- Keep coefficients in `params/`, not in model code. This repository explicitly expects recalibration to happen as data changes, not as code releases. If a number appears in a Python module and is not a numerical algorithm, it is likely a design smell.
- Preserve the calibration/tier story. Results are not just values; they carry provenance and caveats. A downgraded or contraindicated result must remain visible to the user and never be silently normalized into a clean number.
- Suitability is a minimum-of-constraints decision, not a weighted score. A fatal constraint or legal exclusion should block the verdict; do not mask it behind a composite metric.
- Optional engines are adapters, not hard dependencies. `bowtiepy` and EUTROPY integrations should degrade to "not computed" when absent, never crash the whole assessment.
- Prefer adding or updating tests in `tests/` around the affected invariant, especially for the rules already encoded in the repository: calibration enforcement, legal blocking, pressure-never-folded-into-ranking, and report caveats.

## Repository conventions and gotchas

- Keep model logic in `src/seagarden_dst/` and keep UI concerns in `app/`.
- Treat `params/` as source data, not as Python code; prefer updating YAML or parameter sets over editing constants in model modules.
- Preserve the provenance and caveat model: many results carry calibration/tier metadata and should expose limitations in the result, not hide them in logs.
- The app should degrade gracefully when optional sibling engines or spatial inputs are unavailable. Do not make the app fail hard on missing optional dependencies.
- Prefer the smallest targeted test command to validate a change instead of running the whole suite unnecessarily.
- The repo is intentionally designed to avoid runtime dependency on a database or heavy platform services; keep that durability premise in mind when adding new integrations.

## App/UI guidance (tightened)

Treat `app/` as the presentation and orchestration layer; it should coordinate results, not reimplement the model.

- The app entry points are in `app/app.py` and `app/shell.py`. Keep the app shell responsible for branding, layout, and user affordances, not for analytical decisions.
- State is kept in `app/state.py`; use the existing reactive/default structure instead of inventing new ad hoc state patterns. The repository explicitly treats `AppState` and `_DEFAULTS` as the source of truth for session state.
- `app/modules/` is organized as one panel per concern (`site`, `catalogue`, `results`, `report`, etc.). Keep that separation intact and avoid mixing unrelated UI logic into a single module.
- Stale-assessment invalidation is a core app behavior. If a user changes site or specification inputs, the app should invalidate stale results before showing them. Do not allow an old assessment to remain attached to a new label or query.
- Keep result rendering close to the assessment object. The UI should present contract output and caveats in the same form the analytical core returns, rather than reconstructing transformed values in the widgets.
- Do not add UI-only business rules that duplicate model logic. If a rule affects the decision outcome, it belongs in `src/seagarden_dst/`.
- App smoke tests in `app/tests/` are intentionally small but important. If a change touches app wiring, interaction flows, or screen outputs, update or add the smallest relevant smoke test.

## Change expectations

When modifying the model or the UI:

1. Check the relevant `tests/` or `app/tests/` coverage first.
2. Prefer data-driven changes in `params/` when the issue is calibration or scenario behavior.
3. Keep the UI logic thin and let core functions own business logic.
4. Validate with the relevant targeted pytest invocation before broadening scope.

## Existing project guidance incorporated

This repo already documents the following important constraints in the root `README.md` and `pyproject.toml`:

- Use `shiny run app.app` from the repo root.
- Keep `app/` and `src/seagarden_dst/` separated.
- Maintain the optional-dependency pattern: app/core remains functional without optional engines and spatial extras.
- Use `pythonpath = ["src", "."]` and keep imports aligned with that layout.

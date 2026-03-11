# Enrichment-Scoring

LP prospect enrichment, scoring, persistence, and reporting pipeline for the PaceZero interview challenge.

## What This Project Does

This project ingests a CSV of prospect contacts, deduplicates them at the organization level, enriches each organization with public evidence, scores each contact across the required 4 dimensions, stores the results in a lightweight database, and exports a report that a fundraising team can review.

The pipeline supports two enrichment modes:

- Offline heuristic mode: runs without external APIs and keeps the project runnable in a local environment.
- Live AI-powered web enrichment mode: uses the OpenAI Responses API with `web_search` to gather public information, cite sources, and populate the enrichment fields with real web-backed evidence.

## How To Run

### 1. Create and activate a virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

The pipeline, offline enrichment mode, and the full `unittest` suite use only the Python standard library.

No extra packages are required to run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts\run_pipeline.py
```

If you also want the FastAPI server, install the optional API dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
```

### 3. Put the input CSV in place

Expected input file:

```text
data/incoming/challenge_contacts.csv
```

### 4. Run the pipeline

```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py
```

Outputs will be written to:

- `storage/db/prospects.sqlite3`
- `data/processed/<run_id>_results.json`
- `data/exports/<run_id>_leaderboard.csv`
- `data/exports/<run_id>_run_summary.csv`
- `data/exports/<run_id>_cost_breakdown.csv`
- `data/exports/<run_id>_cost_projections.csv`
- `data/exports/<run_id>_report.html`
- `storage/state/<run_id>.json`

The CLI prints all of these artifact paths when the run completes, plus the estimated API cost and the enrichment-mode mix for the leaderboard export.

### 5. Run the API

```powershell
.\.venv\Scripts\python.exe scripts\run_api.py
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Live Web Enrichment Setup

To enable the real AI-powered web enrichment path, set these environment variables before running the pipeline:

```powershell
$env:OPENAI_API_KEY="your_openai_key"
$env:PACEZERO_ENABLE_LIVE_ENRICHMENT="true"
```

To keep the key out of source files, you can store it in a local PowerShell env file:

```powershell
. .\local.env.ps1
.\.venv\Scripts\python.exe scripts\run_pipeline.py
```

Notes:

- `local.env.ps1` is ignored by git
- create or edit `local.env.ps1` locally with:

  ```powershell
  $env:OPENAI_API_KEY="your_openai_key"
  $env:PACEZERO_ENABLE_LIVE_ENRICHMENT="true"
  ```

- the leading `. ` loads the environment variables into the current PowerShell session

Optional settings:

```powershell
$env:PACEZERO_OPENAI_MODEL="gpt-4.1-mini"
$env:PACEZERO_OPENAI_TIMEOUT_SECONDS="45"
```

Notes:

- If live enrichment is disabled, the project still runs using the offline heuristic provider.
- If the live call fails, the provider falls back to the offline path and records the error in the enrichment payload.
- A live run can still contain a small number of heuristic fallback rows if individual enrichment calls fail.
- The easiest verification step is to check the exported leaderboard CSV and confirm `enrichment_mode` contains `live_openai_web_search`.

## Stack

### Core runtime

- Python 3
- Standard library only for the main pipeline runtime
- `unittest` for tests
- `sqlite3` for default persistence

### Optional API layer

- FastAPI
- Uvicorn

### Live enrichment

- OpenAI Responses API
- OpenAI `web_search` tool
- No OpenAI Python SDK is required; the project uses the Python standard library HTTP client

### Outputs

- SQLite database
- CSV leaderboard export
- Static HTML report
- JSON processed output
- Optional FastAPI endpoints for triggering and reviewing runs

## Database

The application database is SQLite by default.

Default database file:

```text
storage/db/prospects.sqlite3
```

Tables:

- `pipeline_runs`
  - one row per pipeline execution
  - stores total prospect count, org count, and cost summary JSON
- `prospects`
  - one row per scored contact per run
  - stores flat score fields plus `enrichment_json` and `score_json`

Important note:

- The `supabase/` directory is only local Supabase project scaffolding.
- The scoring application itself is not currently wired to Supabase/Postgres.
- If you want Supabase as the real backend, the persistence layer needs to be upgraded from SQLite to Postgres.

## How The Pipeline Works

1. `scripts/run_pipeline.py` loads settings and logging, then starts the pipeline.
2. `src/ingest/csv_loader.py` loads `data/incoming/challenge_contacts.csv`.
3. `src/dedup/org_registry.py` groups contacts by normalized organization name.
4. `src/enrichment/provider.py` enriches one organization at a time.
   - In offline mode it uses conservative heuristics and challenge calibration anchors.
   - In live mode it calls OpenAI Responses API with `web_search`, requests JSON-only output, filters noisy sources, and stores citations.
5. `src/scoring/engine.py` scores each contact using the required weighted formula.
6. `src/validation/rules.py` flags suspicious or low-confidence outcomes.
7. `src/persistence/repository.py` stores the run and scored prospects in SQLite.
8. `src/dashboard/service.py` exports:
   - leaderboard CSV
   - static HTML report
9. `src/orchestration/state.py` writes resumable run manifests to `storage/state/`.
10. `src/api.py` exposes the pipeline and results over HTTP if you want an application layer.

## Requirement Coverage

### Must Have

#### 1. AI-powered web enrichment

Implemented in [src/enrichment/provider.py](src/enrichment/provider.py).

What it researches:

- organization type
- external fund allocations
- sustainability / impact / ESG / climate mandate
- AUM
- brand / halo signal
- emerging manager evidence

How it works:

- Uses OpenAI Responses API with `web_search` when live enrichment is enabled
- Requests structured JSON with per-dimension citations
- Rejects noisy sources with a source policy
- Marks insufficient evidence instead of guessing
- Falls back to the offline path if live enrichment is disabled or fails

Status:

- Implemented
- Live web-backed enrichment only runs when the required environment variables are set

#### 2. Structured scoring output

Implemented in [src/scoring/engine.py](src/scoring/engine.py) and [src/models/entities.py](src/models/entities.py).

Each prospect gets:

- numeric scores from `1-10`
- rationale per dimension
- confidence level
- insufficient-evidence signaling

#### 3. Composite scoring and tiering

Implemented in [src/scoring/engine.py](src/scoring/engine.py).

Formula:

```text
composite = (sector_fit * 0.35)
          + (relationship_depth * 0.30)
          + (halo_value * 0.20)
          + (emerging_fit * 0.15)
```

Tiers:

- `PRIORITY CLOSE`
- `STRONG FIT`
- `MODERATE FIT`
- `WEAK FIT`

#### 4. Data persistence

Implemented in [src/persistence/repository.py](src/persistence/repository.py).

Results are stored in SQLite, not just printed to the console.

#### 5. Visualization / BI layer

Implemented in [src/dashboard/service.py](src/dashboard/service.py) and [src/api.py](src/api.py).

Available views:

- static HTML report
- leaderboard CSV
- FastAPI endpoints

This is enough for:

- local review
- spreadsheet analysis
- Power BI import
- a simple internal web workflow

#### 6. Cost estimation

Implemented in [src/costing/tracker.py](src/costing/tracker.py).

The pipeline tracks:

- estimated cost per run
- cost per contact
- cost per organization
- cache hit rate
- avoided cost
- operation-level cost breakdown
- scale projections for larger prospect volumes

### Should Have

#### 1. Accuracy / validation layer

Implemented in [src/validation/rules.py](src/validation/rules.py).

Examples of flags:

- service-provider-like org scored too high
- allocator-like org scored unexpectedly low
- high composite built on low-confidence dimensions
- strong-fit score with insufficient evidence

#### 2. Org-level deduplication

Implemented in [src/dedup/org_registry.py](src/dedup/org_registry.py) and [src/enrichment/cache.py](src/enrichment/cache.py).

Multiple contacts from the same organization share one enrichment record.

#### 3. Scalability considerations

Implemented in the current single-process design through:

- request pacing via [src/control/rate_limiter.py](src/control/rate_limiter.py)
- enrichment cache reuse
- org-level deduplication
- resumable run state via [src/orchestration/state.py](src/orchestration/state.py)
- cost-aware projections

Current limitation:

- the pipeline is still single-process and mostly serial
- it is rate-limited and restart-safe, but not yet a distributed worker system

### Nice To Have

The project also includes several nice-to-have items:

- CSV import via `data/incoming/challenge_contacts.csv`
- confidence scoring per dimension
- insufficient-evidence signaling
- estimated check size from AUM and org type in [src/scoring/check_size.py](src/scoring/check_size.py)

## Scoring Model

The pipeline uses the challenge formula and calibration anchors encoded in [src/scoring/engine.py](src/scoring/engine.py).

Dimensions:

- Sector & Mandate Fit: `35%`
- Relationship Depth: `30%`
- Halo & Strategic Value: `20%`
- Emerging Manager Fit: `15%`

Plain-language meaning of the key dimensions:

- `Sector & Mandate Fit` asks whether the organization looks like the right kind of LP for PaceZero's strategy. A high score requires evidence that the prospect behaves like an allocator into external managers and also has sustainability, impact, ESG, climate, or mission-aligned investment language that fits PaceZero's fundraising target.
- `Halo & Strategic Value` asks whether winning the prospect would create signaling value with other LPs. A high score means the name is institutionally credible, visible, and likely to help validate PaceZero with other allocators during fundraising.

The engine also encodes important rubric rules:

- LPs are not the same as GPs, brokers, lenders, or service providers
- high Sector & Mandate Fit requires both allocator evidence and sustainability-aligned mandate evidence
- insufficient evidence is marked explicitly rather than hidden

## Insufficient Evidence Convention

When the system cannot form a confident score for a dimension, it does not silently guess.

This is implemented through:

- `insufficient_evidence` on each score dimension
- rationale text that says insufficient evidence was available
- metadata field `insufficient_evidence_dimensions`
- validation flags for strong scores that still contain evidence gaps

## Estimated Check Size

If AUM is available, the engine estimates a likely commitment range using the org-type convention from the challenge.

Implemented in [src/scoring/check_size.py](src/scoring/check_size.py).

Allocation ranges:

- Pension / Insurance: `0.5%-2%`
- Endowment / Foundation: `1%-3%`
- Fund of Funds / Multi-Family Office: `2%-5%`
- Single Family Office / HNWI: `3%-10%`
- Asset Manager / RIA/FIA / Private Capital Firm: `0.5%-3%`

## Files That Matter Most

### Entry points

- [scripts/run_pipeline.py](scripts/run_pipeline.py)
- [scripts/run_api.py](scripts/run_api.py)

### Core pipeline

- [src/orchestration/pipeline.py](src/orchestration/pipeline.py)
- [config/settings.py](config/settings.py)

### Enrichment

- [src/enrichment/provider.py](src/enrichment/provider.py)
- [prompts/enrichment/system.txt](prompts/enrichment/system.txt)
- [prompts/enrichment/organization_research.txt](prompts/enrichment/organization_research.txt)

### Scoring

- [src/scoring/engine.py](src/scoring/engine.py)
- [src/scoring/check_size.py](src/scoring/check_size.py)

### Persistence and reporting

- [src/persistence/repository.py](src/persistence/repository.py)
- [src/dashboard/service.py](src/dashboard/service.py)
- [src/api.py](src/api.py)

## Environment Variables

### Runtime controls

- `PACEZERO_ENRICHMENT_RPM`
- `PACEZERO_SCORING_RPM`
- `PACEZERO_WEBHOOK_URLS`
- `PACEZERO_WEBHOOK_TIMEOUT_SECONDS`

### API

- `PACEZERO_API_HOST`
- `PACEZERO_API_PORT`
- `PACEZERO_API_KEY`

### Live enrichment

- `OPENAI_API_KEY`
- `PACEZERO_ENABLE_LIVE_ENRICHMENT`
- `PACEZERO_OPENAI_BASE_URL`
- `PACEZERO_OPENAI_MODEL`
- `PACEZERO_OPENAI_TIMEOUT_SECONDS`

## Testing

Run the full test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

This validates:

- scoring logic
- pipeline persistence
- cost tracker behavior
- rate limiter
- webhooks
- API boot path
- live provider parsing and fallback logic

## Operator Notes

- Malformed CSV rows are skipped rather than crashing the whole run. A row must include the required fields and a valid `Relationship Depth` between `1` and `10`.
- The scoring engine is deterministic local Python. Only the live enrichment step generates API cost.
- Cost exports are written per run so BI tools can track total API spend, cost per contact, cache savings, and scale projections over time.

## How The Results Are Viewed

### HTML report

The static HTML report includes:

- summary cards
- tier mix
- cost breakdown
- scale projections
- research methodology
- top prospects
- flagged prospects

### CSV leaderboard

The leaderboard export includes flat fields that are easy to review in Excel or Power BI:

- dimension scores
- composite
- tier
- confidence indicators
- insufficient-evidence dimensions
- check-size estimate
- validation flags
- enrichment mode, researched org type, AUM, and source-quality fields
- repeated run-level cost fields so a BI tool can join prospect rows to run economics without extra SQL

### Run-level BI cost files

Each run also exports:

- `data/exports/<run_id>_run_summary.csv`
- `data/exports/<run_id>_cost_breakdown.csv`
- `data/exports/<run_id>_cost_projections.csv`

These are intended for BI/reporting use cases where you want:

- total API cost per run
- billable API request count vs local scoring call count
- enrichment cost vs local scoring activity
- cache hit rate and avoided cost
- effective cost per contact / per organization
- scale projections for `100`, `1000`, and `5000` contacts

## Power BI

The easiest Power BI integration is the leaderboard CSV export.

Recommended file:

```text
data/exports/<run_id>_leaderboard.csv
```

You can also use:

- `storage/db/prospects.sqlite3`
- `data/processed/<run_id>_results.json`
- `data/exports/<run_id>_run_summary.csv`
- `data/exports/<run_id>_cost_breakdown.csv`
- `data/exports/<run_id>_cost_projections.csv`

## Security and Operational Notes

- The API can be protected with `PACEZERO_API_KEY`
- Webhooks are validated so non-local endpoints must use HTTPS
- Source filtering in the live enrichment path blocks noisy domains
- Run state files are written atomically
- Existing heuristic cache entries are refreshed automatically when live enrichment is enabled

## Current Known Limitations

- Default persistence is SQLite, not Postgres/Supabase
- Supabase project files exist, but the app is not yet wired to Supabase
- Live web enrichment requires a valid OpenAI API key
- The current execution model is single-process rather than distributed

## Verified Commands

The following commands have been verified in this repository:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts\run_pipeline.py
.\.venv\Scripts\python.exe scripts\run_api.py
```

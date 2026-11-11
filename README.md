# AgriCare AI — Unified Smart Agriculture Platform

This package upgrades the existing AgriCare AI FastAPI application in place. It keeps the HTML/CSS/vanilla-JavaScript frontend and the Python FastAPI backend, and adds database-backed farm analytics, crop records, historical mandi-price storage/import, structured crop-health guidance, and a multilingual Farmer Assistant.

## What's included

- Existing AgriCare modules retained: fertilizer screening, pest/image upload route, market provider route, digital-twin scenario, weather, irrigation and dashboard.
- Monthly revenue/expense analytics in INR, net profit/loss by month, selected period, averages, crop/state/district/season/date filters, category expense percentages and donut/bar visualisations.
- Transaction create/edit/delete with account ownership.
- Crop record create/edit/delete with cultivated area, season, dates, production, yield, price verification/source, actual vs estimated revenue status, expenses and profit.
- Historical mandi price table with daily/monthly granularity kept separate, source attribution, filters, pagination, date coverage, monthly/state/mandi comparisons and CSV export.
- CSV import utility for official Agmarknet/data.gov.in daily exports and CEDA monthly exports.
- Structured disease and crop-growing guidance. This is general agricultural information, not a confirmed disease diagnosis or a district-verified prescription.
- Farmer Assistant conversation endpoint with English/Hindi/Telugu language locking, persisted follow-up history, voice input/output in the browser, and routing to weather, historical market, disease guidance and signed-in financial summaries when relevant.
- Optional PlantNet image screening and optional OpenAI-backed conversational responses. API credentials stay on the backend.

## Important data-integrity status

**No historical FY 2025–26 mandi dataset is bundled in this ZIP.** The database starts empty by design. The application does not invent records, interpolate missing prices, or substitute current prices for FY 2025–26 history. Import a verified source export before expecting historical charts to show data.

The importer accepts:
- Daily records from the official data.gov.in/Agmarknet variety-wise daily market-price resource.
- Monthly aggregates from CEDA Agri-Market, stored as `monthly` granularity and never merged into the daily series.

Official sources:
- data.gov.in variety-wise daily prices: https://data.gov.in/resource/variety-wise-daily-market-prices-data-commodity
- data.gov.in current daily mandi-price catalog (use for schema/current data only, not as a replacement for FY 2025–26 history): https://data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi
- CEDA Agri-Market portal: https://ceda.ashoka.edu.in/data-portal/
- CEDA Data Portal API registration: https://api.ceda.ashoka.edu.in/

Check the actual downloaded file's coverage, date range, fields, source and licence before import. The CSV importer preserves source dates and granularity and skips rows it cannot parse; it does not manufacture missing values. CEDA API access requires registration, and its terms require appropriate CEDA credit/logo and limit use to non-commercial purposes; verify the current terms before publishing or commercialising an application that uses CEDA data.

## Local setup (Windows / macOS / Linux)

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Generate a unique authentication secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated value in `AGRICARE_AUTH_SECRET`. Never commit `.env` or API keys. Start the app:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and API documentation at http://127.0.0.1:8000/docs.

### Farmer accounts and private financial records

Create an account in the Analytics page. Passwords are stored using PBKDF2-HMAC-SHA256; signed bearer tokens expire after 12 hours. Financial transactions and crop records are scoped to the signed-in farmer. Set a strong, stable `AGRICARE_AUTH_SECRET` before creating accounts; changing it invalidates active sessions.

Local development uses SQLite at `app/agricare.db` (or `AGRICARE_DB_PATH`) and does not delete it during startup. **Vercel production requires managed PostgreSQL**: set `DATABASE_URL` to a TLS-enabled Neon/Supabase PostgreSQL URL. If `VERCEL=1` and no `DATABASE_URL` is configured, the homepage still starts and `/api/health` reports `status: degraded` / `database: unconfigured`; database-backed operations return HTTP 503 with a clear configuration message. The app never falls back to ephemeral `/tmp` SQLite. After setting a persistent PostgreSQL URL, redeploy and confirm `/api/health` reports `status: ok` / `database: postgresql`.

## Import historical mandi records

1. Download the official daily CSV export for the required period, or obtain a CEDA monthly export. Verify the columns and date coverage.
2. Place the file somewhere local (do not commit large private datasets unless licensing allows it).
3. Run the importer from the project root:

```bash
python scripts/import_mandi_prices.py --csv path/to/agmarknet-fy2025-26.csv --source "data.gov.in Agmarknet" --granularity daily --start-date 2025-04-01 --end-date 2026-03-31
```

For CEDA monthly aggregates:

```bash
python scripts/import_mandi_prices.py --csv path/to/ceda-fy2025-26.csv --source "CEDA Agri-Market" --granularity monthly --start-date 2025-04-01 --end-date 2026-03-31
```

The source label is saved with each record. Keep original reporting dates. Daily and monthly records are stored and queried separately. The UI shows an empty state until data is imported.

## Optional integrations

- `OPENAI_API_KEY`: enables the LLM response provider. Without it, the assistant uses conservative, language-specific guided responses and never claims to have generated an AI diagnosis or live price.
- `OPENAI_MODEL`: defaults to `gpt-4o-mini`.
- `PLANTNET_API_KEY`: enables optional plant/disease image screening. Without it, image analysis returns a clear unavailable response; symptom-based guidance remains available.
- `DATA_GOV_IN_API_KEY` and `AGMARKNET_RESOURCE_ID`: used by the legacy current-price endpoint. These do not replace the historical CSV import pipeline.

## API overview

### Authentication
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Farm analytics (Bearer token required)
- `POST /api/analytics/transactions`
- `GET /api/analytics/transactions`
- `PUT /api/analytics/transactions/{id}`
- `DELETE /api/analytics/transactions/{id}`
- `GET /api/analytics/overview`
- `GET /api/analytics/crops`
- `POST /api/analytics/crops`
- `PUT /api/analytics/crops/{id}`
- `DELETE /api/analytics/crops/{id}`
- `GET /api/analytics/crop-performance`

### Historical mandi intelligence
- `GET /api/market/historical/filters?granularity=daily|monthly`
- `GET /api/market/historical?start_date=2025-04-01&end_date=2026-03-31&commodity=Tomato&state=Telangana`
- `GET /api/market/historical/export?...`

### Farmer and crop health
- `POST /api/assistant`
- `POST /api/disease/guidance`
- `POST /api/pest/detect` (requires `PLANTNET_API_KEY`)
- `GET /api/weather/current?latitude=17.385&longitude=78.487`
- `GET /api/irrigation/advice?moisture=35`

## Farmer Assistant source review and integration notes

The public `Abhishekpendyala06/Farmer-Assistant-Multilingual-Chatbot` repository (https://github.com/Abhishekpendyala06/Farmer-Assistant-Multilingual-Chatbot) was inspected. The AgriCare source repository is https://github.com/soha2023786/AgriCare-AIML. Its chat intent/response logic lives primarily in browser-side `chatbot.js` and the English/Hindi/Telugu JSON response dictionaries; its Flask `server.py` exposes `/api/disease`, `/api/price` and `/api/health`, rather than a standalone backend chat endpoint. AgriCare keeps FastAPI and provides one integrated `/api/assistant` conversation endpoint, language-locked responses, stored follow-up history, voice support, and links to the unified weather/market/disease/financial services. The PlantNet and data.gov.in capabilities are backend integrations, not an iframe to the Farmer Assistant deployment.

See `integrations/FARMER_ASSISTANT_SOURCE_AUDIT.md` for the source-route mapping. The original repository's entire static response dictionary and every original UI feature (for example its full crop wizard, feedback controls and PDF export) have **not** been copied wholesale into this version. The integrated assistant covers the main agricultural conversation domains and the three languages, but this is a scoped port rather than a byte-for-byte merge of the two frontends.

## Known limitations — do not mistake these for completed model functionality

- The FY 2025–26 mandi data must be downloaded/obtained and imported; no historical dataset is bundled because source coverage/access must be verified first.
- CEDA's API requires registration for an API key. If no suitable API export is available, the UI correctly remains empty rather than inventing values.
- PlantNet image screening is optional and requires a valid key and provider access. It is a screening prediction, not a definitive diagnosis.
- Disease guidance is general advisory content. It does not prescribe pesticide dosages and must be checked with the local KVK/State Agricultural University.
- Fertilizer screening remains a rule-based preliminary screen, not a laboratory recommendation.
- The digital-twin calculation remains an illustrative rule-based scenario, not a calibrated crop-growth model or yield forecast.
- Local development and unit tests use SQLite. Vercel production uses the PostgreSQL adapter and refuses to start without `DATABASE_URL`; the actual managed database still must be configured and restart-tested.
- This package does not include a newly trained pest/disease model or claim that one has been trained and evaluated.

## Testing

Run:

```bash
python -m pytest -q
node --check app/static/app.js
python -m compileall -q app scripts
```

The 16 tests cover recorded financial totals, transaction and crop CRUD/owner isolation, authenticated API access, local SQLite persistence across a separate Python process, Vercel startup/health behaviour without a database and refusal to fall back to ephemeral SQLite, verified vs estimated crop revenue, official encoded CSV headings, large transaction aggregation, and historical mandi CSV import/filter/export. They do not certify a live PostgreSQL connection, hosted Vercel restart/redeployment persistence, live third-party API availability, or mobile-browser behaviour.

## Deployment

For Vercel, follow `VERCEL_DEPLOYMENT_GUIDE.md` and configure managed PostgreSQL through `DATABASE_URL`, plus a stable `AGRICARE_AUTH_SECRET`. For Render, the included `render.yaml` can use its persistent disk and SQLite path. Run `/api/health` and `/docs` after deployment.

If you have existing SQLite data to carry over, first back up the file, create the PostgreSQL schema by starting the app against the new `DATABASE_URL`, then run `scripts/migrate_sqlite_to_postgres.py` with `AGRICARE_SQLITE_SOURCE` and `DATABASE_URL`. The script copies records and stable farmer IDs without modifying the source database.


## Historical mandi price import

The Market Intelligence dashboard reads genuine records from `mandi_prices`; it does not generate prices. Download an official FY 2025–26 export and import it with `scripts/import_mandi_prices.py`. See `PROJECT_AUDIT_AND_UPGRADE_NOTES.md` and `data/mandi_import_template.csv` for the accepted fields and exact command. Empty dashboard results mean no imported observations match the selected filters.

## Audit and known deployment constraints

See `PROJECT_AUDIT_AND_UPGRADE_NOTES.md` for inspected root causes, changes, test results, and incomplete production requirements. Vercel deployments require PostgreSQL. The PostgreSQL adapter and additive schema setup are included in this build; production persistence still must be verified against the actual configured managed database using the restart checklist in `VERCEL_DEPLOYMENT_GUIDE.md`.

### Dashboard filter controls

Analytics and Market Intelligence each provide a **Clear filters** action. Both dashboards reject reversed date ranges before requesting data. Market Intelligence resets to the FY 2025–26 period (1 April 2025–31 March 2026), daily records and the default page size. Geographic fields are optional exact-match filters; leave them blank for all India/all districts/all mandis. Historical prices are never fabricated: import a permitted source export before expecting records or charts.

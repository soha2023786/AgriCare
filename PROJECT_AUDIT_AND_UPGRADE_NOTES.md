# AgriCare AI — Code Audit and Upgrade Notes

## Inspected source snapshot

This update modifies the saved `AgriCare-AI-upgraded.zip` project snapshot in place. It retains FastAPI and the static HTML/CSS/JavaScript frontend. Local development remains SQLite-backed; Vercel production now requires managed PostgreSQL through `DATABASE_URL`. The GitHub branch was not committed or deployed as part of this file update.

## Root causes found

1. **Market Intelligence showed empty values because the database was not populated.** The historical endpoint queried `mandi_prices`, but the project contained no historical FY 2025–26 dataset and no automatic historical downloader. The existing importer was a command-line CSV importer. Empty values were therefore an honest result, not a chart-rendering issue alone.
2. **Historical import validation was too permissive.** The importer could count malformed/incomplete observations as imported and did not reject inconsistent min/max/modal price ranges. This upgrade validates date and price fields, reports skipped rows, and retains source-attributed idempotent upserts.
3. **Market comparison data was incomplete.** State/mandi aggregates did not include minimum, maximum, latest observation date, or a text search. The API now includes those aggregate fields and supports searching historical rows.
4. **The Market Intelligence page had no record-search control.** Added search and page-size controls and retained the existing filters, pagination, and CSV export.
5. **The page layout could prevent access to lower content.** Added document-level vertical scrolling, overflow-safe table wrappers, and a compact mobile layout.
6. **Analytics summary previously loaded at most 1,000 transactions.** The overview service now allows up to 100,000 records for calculations, rather than silently calculating from only the newest 1,000.
7. **Vercel SQLite persistence was unsafe.** The previous `/tmp/agricare.db` default is removed. Vercel now requires `DATABASE_URL`, uses a psycopg PostgreSQL adapter, creates additive/idempotent schema migrations, and reports the active backend from `/api/health`. Missing `DATABASE_URL` causes a clear startup failure instead of silent ephemeral storage.
8. **Farmer registration lacked a name field.** Added name to the existing registration UI, API schema and farmer account table, with an additive migration for existing SQLite/PostgreSQL databases.
9. **Private dashboard content remained visible after sign-out.** Logout now clears the financial and crop summary UI. Analytics date filters now default to all dates so older saved records are not hidden on first sign-in.
10. **Official CSV column names may be encoded.** Import now decodes Excel/data export `_x0020_` headings (for example `Min_x0020_Price`). Market Apply Filters resets pagination to page 1.

## Existing capabilities confirmed in the uploaded snapshot

- Name/email/password registration and login with PBKDF2 password hashing and signed bearer tokens.
- User ownership is applied to financial transaction and crop-record CRUD queries.
- Analytics overview, transaction CRUD, crop CRUD, and historical market query/export endpoints exist.
- Existing tests cover account token validation, farmer data isolation, financial totals, crop revenue handling, historical imports, and assistant history.

## Important features not complete in this snapshot

These are not claimed as implemented by this upgrade:

- Phone and farm-location profile fields are not implemented; the farmer name and email are persisted.
- Forgot-password / reset-password flow is not implemented. A secure reset requires a verified email-delivery provider and token lifecycle.
- Vercel PostgreSQL support is implemented, but a real managed `DATABASE_URL` was not available in this environment. Do not claim production persistence until the hosted restart/login test passes. Local SQLite restart persistence was tested separately.
- The import process is still a CLI CSV workflow; there is no authenticated browser upload for CSV/XLSX in this patch.
- No genuine FY 2025–26 mandi dataset was included in the uploaded archive. No prices have been generated or bundled. Market Intelligence will remain empty until a permitted official export is imported.
- Automated import from Agmarknet/data.gov.in/CEDA has not been verified. API access, dataset resource identifiers, terms, and availability must be confirmed before enabling scheduled downloads.
- Full deployment end-to-end testing against a hosted PostgreSQL database and real FY 2025–26 source file was not possible in this environment.

## Import genuine FY 2025–26 records

1. Download an official Agmarknet/data.gov.in or permitted CEDA export covering **2025-04-01 through 2026-03-31**.
2. Ensure the file has columns matching `data/mandi_import_template.csv` (the importer also accepts common aliases such as `date`, `commodity`, `mandi`, `minimum_price`, and `maximum_price`).
3. From the project root, run:

```bash
python scripts/import_mandi_prices.py --csv path/to/official_export.csv --source "data.gov.in Agmarknet" --granularity daily --start-date 2025-04-01 --end-date 2026-03-31
```

For a monthly CEDA aggregate, use `--granularity monthly` and an exact source label. Daily and monthly data are intentionally stored and queried separately. The importer never fills missing days or creates prices.

## Validation performed

- Python compilation: `python -m compileall -q app scripts tests`.
- Frontend JavaScript syntax: `node --check app/static/app.js`.
- Unit/API tests: 15 tests passed, including market import/filter/export, analytics calculations, transaction and crop ownership checks, unauthenticated API rejection, and the Vercel no-SQLite-fallback guard.
- Local SQLite persistence test across two separate Python processes: farmer registration/login, financial transaction persistence, and crop record persistence all passed.
- FastAPI TestClient multi-farmer test: Farmer B could not list, update, or delete Farmer A's transaction/crop records; Farmer A's records remained unchanged.
- SQLite connection lifecycle now explicitly closes connections after commit/rollback; the previous unclosed-connection ResourceWarnings no longer appear.
- Not performed: live PostgreSQL connection, Vercel cold-start/redeployment persistence, hosted market CSV import, browser automation, or mobile-device testing.

## Follow-up dashboard control pass — 11 November 2026

Applied to the supplied `AgriCare-AI-Deployment-Diagnostic-Update.zip` snapshot:

- Added **Clear filters** controls to Analytics and Market Intelligence. Analytics clears month/date/crop/location/season/financial-year selections; Market Intelligence restores the FY 2025–26 date window, daily granularity, default page size, and clears search/geographic/commodity filters.
- Added client-side date-range validation to both dashboards so a reversed From/To range is rejected before an API request.
- Corrected the historical-results loading row to span all ten table columns and reset the summary metrics while a new query is loading, avoiding stale values being mistaken for the new selection.
- Clarified that blank geographic fields mean All India/all districts/all mandis; typing the words “All India” would otherwise be treated as an exact state filter.

Validation after this pass:

- `node --check app/static/app.js` — passed.
- `python -m compileall -q app scripts tests` — passed.
- `PYTHONPATH=. python -m pytest -q` — 16 passed.

The automated tests use local SQLite and controlled test records. They do not prove that a production PostgreSQL database is configured, that the official FY 2025–26 mandi export has been imported, or that the hosted Vercel deployment has been browser-tested. Market Intelligence therefore continues to show an honest empty state until genuine source-attributed records are imported.

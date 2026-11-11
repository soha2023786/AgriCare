# AgriCare AI deployment guide

## Recommended: Render with persistent disk

1. Push the contents of this project folder to a GitHub repository.
2. In Render, choose **New → Blueprint** and connect the repository.
3. Review the `render.yaml` service, persistent disk mount and generated `AGRICARE_AUTH_SECRET`.
4. Add optional `OPENAI_API_KEY`, `PLANTNET_API_KEY` and `DATA_GOV_IN_API_KEY` values in the Render dashboard.
5. Deploy and open `/api/health` and `/docs`.
6. Create a farmer account, add a test transaction and verify account isolation.
7. Import the verified FY 2025–26 mandi CSV using `scripts/import_mandi_prices.py` after the deployment has a secure database import workflow or by running the script against the mounted database in an authorised maintenance environment.

## Local smoke test

```bash
pip install -r requirements.txt
# Copy .env.example to .env and set AGRICARE_AUTH_SECRET first.
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Test:
- `/` — dashboard
- `/api/health` — service health
- `/docs` — interactive API documentation
- Analytics account registration/login and private records
- Historical market empty state before import, then filters and CSV export after import

## Vercel

Vercel is suitable for a preview deployment, but its ephemeral serverless filesystem is not durable storage for farmer accounts, financial transactions or imported historical data. Use a managed persistent database or a host with a persistent disk before production use.

# AgriCare AI — Vercel deployment with persistent PostgreSQL

The project root contains `main.py`, which exports the FastAPI instance as `app`; this is a supported zero-configuration FastAPI entrypoint on Vercel. A custom `vercel.json` rewrite is not required for this backend layout. See the current [Vercel FastAPI deployment guide](https://vercel.com/docs/frameworks/backend/fastapi).

Vercel Functions have an ephemeral filesystem. **Do not use SQLite for deployed farmer data.** This build requires a managed PostgreSQL database for persistent farmer and mandi records. If `DATABASE_URL` is missing or unreachable, the app now still starts so the homepage and `/api/health` remain available; health reports `status: degraded`, and database-backed operations return HTTP 503 with a configuration explanation. It never silently creates an ephemeral SQLite database on Vercel.

## 1. Create the production database

1. Create a managed PostgreSQL database with Neon or Supabase.
2. Copy the provider's PostgreSQL runtime/pooled connection string. Use TLS (`sslmode=require`).
3. Keep the database in a region close to the Vercel deployment.
4. Do not commit the connection string to GitHub.

## 2. Configure Vercel environment variables

In **Vercel → Project → Settings → Environment Variables**, add the following to Production (and Preview if needed):

- `DATABASE_URL` — managed PostgreSQL connection string.
- `AGRICARE_AUTH_SECRET` — one random secret generated once with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it unchanged between deployments; rotating it signs out existing sessions.
- Any optional provider keys such as `OPENAI_API_KEY` or `PLANTNET_API_KEY` only if those features are enabled.

Do not set `AGRICARE_DB_PATH` on Vercel. Redeploy after adding variables.

## 3. Safe schema migration

The application runs additive, idempotent `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and index creation at startup. It never drops tables or deletes records. Schema version 2 is recorded in `agricare_schema_migrations`. Back up the database before deploying schema changes.

## 4. Verify the actual deployment

1. Open `/api/health`; before database setup it should report `status: degraded` and `database: unconfigured`. After setup it must report `status: ok` and `database: postgresql`.
2. Register a test farmer, add a small test revenue record and a crop record.
3. Record the test account email (never the password) and the displayed values.
4. Trigger a new Vercel deployment or wait for a new serverless instance, then sign in again.
5. Confirm the same transaction and crop remain.
6. Register a second farmer and confirm their lists are empty and the first farmer's record IDs cannot be read, edited or deleted with the second token.

A local SQLite restart test is not proof of Vercel persistence. Complete this test against the production PostgreSQL database before claiming deployment persistence.

## 5. Backup and restore

Use the database provider's scheduled backups/PITR where available. Also take a manual logical backup before releases:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=agricare-backup.dump
```

Restore to a new/empty database (do not overwrite production blindly):

```bash
createdb agricare_restore_test
pg_restore --dbname="$RESTORE_DATABASE_URL" --clean --if-exists agricare-backup.dump
```

After validating the restored app against the test database, update `DATABASE_URL` only during a planned maintenance window. Keep backup files encrypted and access-restricted. Never place credentials in the repository.

## Local development

Without `DATABASE_URL`, the app uses SQLite at `app/agricare.db` (or `AGRICARE_DB_PATH` if set). The file is not recreated or deleted at startup. Copy `.env.example` to `.env`, set a stable `AGRICARE_AUTH_SECRET`, install requirements, and run `uvicorn main:app --reload` from the project root.

-- PostgreSQL persistent-storage schema (safe to re-run; additive only).
CREATE TABLE IF NOT EXISTS farmer_accounts (
  id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL
);
ALTER TABLE farmer_accounts ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS farm_transactions (
  id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
  transaction_type TEXT NOT NULL CHECK (transaction_type IN ('revenue','expense')),
  crop TEXT NOT NULL, category TEXT NOT NULL DEFAULT '', amount_inr DOUBLE PRECISION NOT NULL CHECK (amount_inr >= 0),
  quantity_quintals DOUBLE PRECISION, season TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '',
  transaction_date TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT
);
ALTER TABLE farm_transactions ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE farm_transactions ADD COLUMN IF NOT EXISTS updated_at TEXT;
CREATE INDEX IF NOT EXISTS idx_farm_tx_owner_date ON farm_transactions(owner_id,transaction_date);
CREATE TABLE IF NOT EXISTS farm_crops (
  id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL, crop TEXT NOT NULL, area_acres DOUBLE PRECISION NOT NULL,
  season TEXT NOT NULL, sowing_date TEXT, harvest_date TEXT, production_kg DOUBLE PRECISION,
  selling_price_inr_per_quintal DOUBLE PRECISION, price_verified INTEGER NOT NULL DEFAULT 0,
  price_source TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '', soil_type TEXT DEFAULT '',
  notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_farm_crops_owner ON farm_crops(owner_id,crop,season);
CREATE TABLE IF NOT EXISTS mandi_prices (
  id BIGSERIAL PRIMARY KEY, granularity TEXT NOT NULL CHECK (granularity IN ('daily','monthly')),
  source TEXT NOT NULL, source_record_id TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '',
  market TEXT DEFAULT '', commodity TEXT NOT NULL, variety TEXT DEFAULT '', grade TEXT DEFAULT '', report_date TEXT NOT NULL,
  min_price DOUBLE PRECISION, max_price DOUBLE PRECISION, modal_price DOUBLE PRECISION, arrivals DOUBLE PRECISION,
  unit TEXT NOT NULL DEFAULT 'INR/quintal', imported_at TEXT NOT NULL,
  UNIQUE(source,granularity,state,district,market,commodity,variety,grade,report_date)
);
CREATE INDEX IF NOT EXISTS idx_mandi_date ON mandi_prices(granularity,report_date,commodity);
CREATE INDEX IF NOT EXISTS idx_mandi_geo ON mandi_prices(state,district,market,commodity);
CREATE TABLE IF NOT EXISTS assistant_conversations (
  id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL, conversation_key TEXT NOT NULL,
  language TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_history ON assistant_conversations(owner_id,conversation_key,id);
CREATE TABLE IF NOT EXISTS agricare_schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO agricare_schema_migrations(version) VALUES (2) ON CONFLICT(version) DO NOTHING;

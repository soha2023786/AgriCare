"""Copy existing AgriCare SQLite data into PostgreSQL without deleting either copy.

Required environment:
  AGRICARE_SQLITE_SOURCE=/absolute/path/to/agricare.db
  DATABASE_URL=postgresql://... (TLS-enabled managed PostgreSQL URL)
Run after creating the PostgreSQL schema with the app's startup migration.
"""
import os
import sqlite3
import sys

TABLES = (
    "farmer_accounts",
    "farm_transactions",
    "farm_crops",
    "mandi_prices",
    "assistant_conversations",
)
SERIAL_TABLES = ("farm_transactions", "farm_crops", "mandi_prices", "assistant_conversations")


def main():
    source = os.getenv("AGRICARE_SQLITE_SOURCE")
    target = os.getenv("DATABASE_URL")
    if not source or not target:
        raise SystemExit("Set AGRICARE_SQLITE_SOURCE and DATABASE_URL before running this migration.")
    if not os.path.isfile(source):
        raise SystemExit(f"SQLite source file not found: {source}")
    import psycopg
    from psycopg import sql

    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    copied = {}
    with psycopg.connect(target, sslmode="require") as dst:
        with dst.cursor() as cur:
            for table in TABLES:
                exists = src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not exists:
                    copied[table] = 0
                    continue
                source_cols = [r["name"] for r in src.execute(f'PRAGMA table_info("{table}")')]
                target_cols = [r[0] for r in cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position",
                    (table,),
                ).fetchall()]
                cols = [c for c in source_cols if c in target_cols]
                if not cols:
                    copied[table] = 0
                    continue
                rows = src.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in cols)} FROM "{table}"').fetchall()
                if rows:
                    stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, cols)),
                        sql.SQL(",").join(sql.Placeholder() for _ in cols),
                    )
                    cur.executemany(stmt, [tuple(row[c] for c in cols) for row in rows])
                copied[table] = len(rows)
            for table in SERIAL_TABLES:
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                sequence = cur.fetchone()[0]
                if sequence:
                    cur.execute(sql.SQL("SELECT COALESCE(MAX(id), 0) FROM {}").format(sql.Identifier(table)))
                    maximum = cur.fetchone()[0]
                    if maximum:
                        cur.execute("SELECT setval(%s, %s, true)", (sequence, maximum))
        dst.commit()
    src.close()
    for table, count in copied.items():
        print(f"{table}: {count} source rows considered (existing destination conflicts skipped)")
    print("Migration copy complete. Source SQLite file was not modified or deleted.")


if __name__ == "__main__":
    main()

"""Database-backed farm analytics and historical mandi-price services.

Daily Agmarknet records and monthly CEDA aggregates are stored separately so
records with different granularity are never silently combined.
"""
from __future__ import annotations
import os, sqlite3, json, urllib.parse, urllib.request, csv, io
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
# Vercel functions are ephemeral: never silently fall back to SQLite for deployed data.
# Missing production configuration must not crash module import (which causes a Vercel 500);
# database-backed endpoints instead return a clear 503 while the homepage and health check load.
VERCEL_RUNTIME = bool(os.getenv('VERCEL'))
STORAGE_CONFIGURED = bool(DATABASE_URL) or not VERCEL_RUNTIME
DB_PATH = Path(os.getenv('AGRICARE_DB_PATH', str(BASE_DIR / 'agricare.db'))) if not DATABASE_URL else None
EXPENSE_CATEGORIES = ['Seeds','Fertilizers','Pesticides','Labour','Irrigation','Equipment','Machinery','Transportation','Electricity','Land preparation','Storage','Other expenses']

class _PostgresConnection:
    # Compatibility adapter for the existing SQLite-style queries.
    def __init__(self, conn): self.conn = conn
    def __enter__(self): self.conn.__enter__(); return self
    def __exit__(self, typ, value, tb): return self.conn.__exit__(typ, value, tb)
    def execute(self, sql, params=()): return self.conn.execute(sql.replace('?', '%s'), params)
    def commit(self): return self.conn.commit()
    def close(self): return self.conn.close()

class _SQLiteConnection:
    # sqlite3.Connection's context manager commits/rolls back but does not close.
    # Close explicitly so server processes and tests do not leak file handles.
    def __init__(self, conn): self.conn = conn
    def __enter__(self): self.conn.__enter__(); return self
    def __exit__(self, typ, value, tb):
        try:
            return self.conn.__exit__(typ, value, tb)
        finally:
            self.conn.close()
    def execute(self, sql, params=()): return self.conn.execute(sql, params)
    def commit(self): return self.conn.commit()
    def close(self): return self.conn.close()
    def __getattr__(self, name): return getattr(self.conn, name)

def _connect():
    if VERCEL_RUNTIME and not DATABASE_URL:
        raise RuntimeError('Persistent storage is not configured. Add DATABASE_URL (PostgreSQL) in Vercel Project Settings → Environment Variables, then redeploy. No temporary SQLite database was created.')
    if DATABASE_URL:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError('Install psycopg[binary] to use DATABASE_URL PostgreSQL storage.') from exc
        return _PostgresConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10, sslmode='require'))
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return _SQLiteConnection(conn)

def database_backend(): return 'postgresql' if DATABASE_URL else ('unconfigured' if VERCEL_RUNTIME else 'sqlite')

def check_database():
    with _connect() as db: db.execute('SELECT 1').fetchone()
    return True

def init_db():
    if DATABASE_URL:
        statements = [
          "CREATE TABLE IF NOT EXISTS farmer_accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL)",
          "ALTER TABLE farmer_accounts ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
          "CREATE TABLE IF NOT EXISTS farm_transactions (id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local', transaction_type TEXT NOT NULL CHECK(transaction_type IN ('revenue','expense')), crop TEXT NOT NULL, category TEXT NOT NULL DEFAULT '', amount_inr DOUBLE PRECISION NOT NULL CHECK(amount_inr >= 0), quantity_quintals DOUBLE PRECISION, season TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '', transaction_date TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT)",
          "ALTER TABLE farm_transactions ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local'",
          "ALTER TABLE farm_transactions ADD COLUMN IF NOT EXISTS updated_at TEXT",
          "CREATE INDEX IF NOT EXISTS idx_farm_tx_owner_date ON farm_transactions(owner_id,transaction_date)",
          "CREATE TABLE IF NOT EXISTS farm_crops (id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL, crop TEXT NOT NULL, area_acres DOUBLE PRECISION NOT NULL, season TEXT NOT NULL, sowing_date TEXT, harvest_date TEXT, production_kg DOUBLE PRECISION, selling_price_inr_per_quintal DOUBLE PRECISION, price_verified INTEGER NOT NULL DEFAULT 0, price_source TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '', soil_type TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT)",
          "CREATE INDEX IF NOT EXISTS idx_farm_crops_owner ON farm_crops(owner_id,crop,season)",
          "CREATE TABLE IF NOT EXISTS mandi_prices (id BIGSERIAL PRIMARY KEY, granularity TEXT NOT NULL CHECK(granularity IN ('daily','monthly')), source TEXT NOT NULL, source_record_id TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '', market TEXT DEFAULT '', commodity TEXT NOT NULL, variety TEXT DEFAULT '', grade TEXT DEFAULT '', report_date TEXT NOT NULL, min_price DOUBLE PRECISION, max_price DOUBLE PRECISION, modal_price DOUBLE PRECISION, arrivals DOUBLE PRECISION, unit TEXT NOT NULL DEFAULT 'INR/quintal', imported_at TEXT NOT NULL, UNIQUE(source,granularity,state,district,market,commodity,variety,grade,report_date))",
          "CREATE INDEX IF NOT EXISTS idx_mandi_date ON mandi_prices(granularity,report_date,commodity)",
          "CREATE INDEX IF NOT EXISTS idx_mandi_geo ON mandi_prices(state,district,market,commodity)",
          "CREATE TABLE IF NOT EXISTS assistant_conversations (id BIGSERIAL PRIMARY KEY, owner_id TEXT NOT NULL, conversation_key TEXT NOT NULL, language TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)",
          "CREATE INDEX IF NOT EXISTS idx_assistant_history ON assistant_conversations(owner_id,conversation_key,id)",
          "CREATE TABLE IF NOT EXISTS agricare_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
          "INSERT INTO agricare_schema_migrations(version,applied_at) VALUES (2, CURRENT_TIMESTAMP) ON CONFLICT(version) DO NOTHING"
        ]
        with _connect() as db:
            for statement in statements: db.execute(statement)
        return
    with _connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS farm_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL DEFAULT 'local',
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('revenue','expense')),
            crop TEXT NOT NULL, category TEXT NOT NULL DEFAULT '', amount_inr REAL NOT NULL CHECK(amount_inr >= 0),
            quantity_quintals REAL, season TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '',
            transaction_date TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT
        )''')
        cols={r['name'] for r in db.execute('PRAGMA table_info(farm_transactions)')}
        if 'owner_id' not in cols: db.execute("ALTER TABLE farm_transactions ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'")
        if 'updated_at' not in cols: db.execute('ALTER TABLE farm_transactions ADD COLUMN updated_at TEXT')
        db.execute('CREATE INDEX IF NOT EXISTS idx_farm_tx_owner_date ON farm_transactions(owner_id,transaction_date)')
        db.execute('''CREATE TABLE IF NOT EXISTS farm_crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, crop TEXT NOT NULL,
            area_acres REAL NOT NULL, season TEXT NOT NULL, sowing_date TEXT, harvest_date TEXT,
            production_kg REAL, selling_price_inr_per_quintal REAL, price_verified INTEGER NOT NULL DEFAULT 0,
            price_source TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '', soil_type TEXT DEFAULT '',
            notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_farm_crops_owner ON farm_crops(owner_id,crop,season)')
        db.execute('''CREATE TABLE IF NOT EXISTS mandi_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, granularity TEXT NOT NULL CHECK(granularity IN ('daily','monthly')),
            source TEXT NOT NULL, source_record_id TEXT DEFAULT '', state TEXT DEFAULT '', district TEXT DEFAULT '',
            market TEXT DEFAULT '', commodity TEXT NOT NULL, variety TEXT DEFAULT '', grade TEXT DEFAULT '',
            report_date TEXT NOT NULL, min_price REAL, max_price REAL, modal_price REAL, arrivals REAL,
            unit TEXT NOT NULL DEFAULT 'INR/quintal', imported_at TEXT NOT NULL,
            UNIQUE(source,granularity,state,district,market,commodity,variety,grade,report_date)
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_mandi_date ON mandi_prices(granularity,report_date,commodity)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_mandi_geo ON mandi_prices(state,district,market,commodity)')
        db.execute('''CREATE TABLE IF NOT EXISTS assistant_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, conversation_key TEXT NOT NULL,
            language TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_assistant_history ON assistant_conversations(owner_id,conversation_key,id)')
        db.execute("CREATE TABLE IF NOT EXISTS farmer_accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL)")
        cols={r['name'] for r in db.execute('PRAGMA table_info(farmer_accounts)')}
        if 'name' not in cols: db.execute("ALTER TABLE farmer_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        db.execute('CREATE TABLE IF NOT EXISTS agricare_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO agricare_schema_migrations(version,applied_at) VALUES (2,CURRENT_TIMESTAMP)')

def _owner_clause(owner_id): return owner_id or 'local'

def add_transaction(data, owner_id='local'):
    init_db(); now=datetime.now(timezone.utc).isoformat()
    dt=data['transaction_date'].isoformat() if hasattr(data['transaction_date'],'isoformat') else str(data['transaction_date'])
    with _connect() as db:
        cur=db.execute('''INSERT INTO farm_transactions
          (owner_id,transaction_type,crop,category,amount_inr,quantity_quintals,season,state,district,transaction_date,notes,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id''',
          (_owner_clause(owner_id),data['transaction_type'],data['crop'].strip(),data.get('category',''),data['amount_inr'],
           data.get('quantity_quintals'),data.get('season',''),data.get('state',''),data.get('district',''),dt,data.get('notes',''),now,now))
        return dict(db.execute('SELECT * FROM farm_transactions WHERE id=?',(cur.fetchone()['id'],)).fetchone())


def update_transaction(record_id,data,owner_id='local'):
    init_db(); now=datetime.now(timezone.utc).isoformat()
    dt=data['transaction_date'].isoformat() if hasattr(data['transaction_date'],'isoformat') else str(data['transaction_date'])
    with _connect() as db:
        cur=db.execute('''UPDATE farm_transactions SET transaction_type=?,crop=?,category=?,amount_inr=?,quantity_quintals=?,season=?,state=?,district=?,transaction_date=?,notes=?,updated_at=? WHERE id=? AND owner_id=?''',
          (data['transaction_type'],data['crop'].strip(),data.get('category',''),data['amount_inr'],data.get('quantity_quintals'),data.get('season',''),data.get('state',''),data.get('district',''),dt,data.get('notes',''),now,record_id,_owner_clause(owner_id)))
        if not cur.rowcount: return None
        return dict(db.execute('SELECT * FROM farm_transactions WHERE id=?',(record_id,)).fetchone())


def delete_transaction(record_id,owner_id='local'):
    init_db()
    with _connect() as db:
        cur=db.execute('DELETE FROM farm_transactions WHERE id=? AND owner_id=?',(record_id,_owner_clause(owner_id)))
        return cur.rowcount>0


def list_transactions(start_date=None,end_date=None,crop=None,state=None,district=None,owner_id='local',season=None,limit=500):
    init_db(); clauses=['owner_id=?']; args=[_owner_clause(owner_id)]
    for col,val,op in [('transaction_date',start_date,'>='),('transaction_date',end_date,'<='),('crop',crop,'='),('state',state,'='),('district',district,'='),('season',season,'=')]:
        if val: clauses.append(f'{col} {op} ?'); args.append(val)
    args.append(max(1,min(int(limit),100000)))
    with _connect() as db: return [dict(r) for r in db.execute('SELECT * FROM farm_transactions WHERE '+' AND '.join(clauses)+' ORDER BY transaction_date DESC,id DESC LIMIT ?',args).fetchall()]


def overview(start_date=None,end_date=None,crop=None,state=None,district=None,owner_id='local',season=None):
    rows=list_transactions(start_date,end_date,crop,state,district,owner_id,season,100000)
    revenue=sum(r['amount_inr'] for r in rows if r['transaction_type']=='revenue')
    expenses=sum(r['amount_inr'] for r in rows if r['transaction_type']=='expense')
    by_crop={}; by_month={}; by_category={}; by_season={}
    for r in rows:
        c=r['crop'] or 'Unspecified'; by_crop.setdefault(c,{'revenue':0.0,'expenses':0.0})
        by_crop[c]['revenue' if r['transaction_type']=='revenue' else 'expenses']+=r['amount_inr']
        month=r['transaction_date'][:7]; by_month.setdefault(month,{'revenue':0.0,'expenses':0.0})
        by_month[month]['revenue' if r['transaction_type']=='revenue' else 'expenses']+=r['amount_inr']
        season_name=r['season'] or 'Unspecified'; by_season[season_name]=by_season.get(season_name,0)+ (r['amount_inr'] if r['transaction_type']=='expense' else 0)
        if r['transaction_type']=='expense': by_category[r['category'] or 'Other expenses']=by_category.get(r['category'] or 'Other expenses',0)+r['amount_inr']
    crops=[{'crop':k,'revenue_inr':round(v['revenue'],2),'expenses_inr':round(v['expenses'],2),'profit_inr':round(v['revenue']-v['expenses'],2)} for k,v in sorted(by_crop.items())]
    months=[{'month':k,'revenue_inr':round(v['revenue'],2),'expenses_inr':round(v['expenses'],2),'profit_inr':round(v['revenue']-v['expenses'],2)} for k,v in sorted(by_month.items())]
    categories=[{'category':k,'amount_inr':round(v,2),'percentage':round(v/expenses*100,2) if expenses else 0} for k,v in sorted(by_category.items(),key=lambda x:x[1],reverse=True)]
    return {'currency':'INR','currency_symbol':'₹','record_count':len(rows),'total_revenue_inr':round(revenue,2),'total_expenses_inr':round(expenses,2),
      'net_profit_inr':round(revenue-expenses,2),'average_monthly_revenue_inr':round(revenue/max(1,len(months)),2),
      'average_monthly_expenses_inr':round(expenses/max(1,len(months)),2),'selected_period':{'start_date':start_date,'end_date':end_date},
      'crop_performance':crops,'monthly_trends':months,'expense_breakdown':categories,
      'season_expenses':[{'season':k,'amount_inr':round(v,2)} for k,v in by_season.items()],
      'highest_expense_category':categories[0] if categories else None,'records':rows,'data_status':'recorded_farm_data',
      'message':None if rows else 'No farm records match these filters. Add actual revenue and expense records to populate analytics.'}


def _crop_row(row, owner_id='local'):
    d=dict(row); production_q=d['production_kg']/100 if d.get('production_kg') is not None else None
    price=d.get('selling_price_inr_per_quintal'); verified=bool(d.get('price_verified'))
    calculated=round(production_q*price,2) if production_q is not None and price is not None else None
    d['production_quintals']=round(production_q,3) if production_q is not None else None
    d['yield_kg_per_acre']=round(d['production_kg']/d['area_acres'],2) if d.get('production_kg') is not None and d['area_acres'] else None
    d['revenue_inr']=calculated if verified else None
    d['estimated_revenue_inr']=calculated if (not verified and calculated is not None) else None
    d['revenue_status']='actual_verified_price' if verified and calculated is not None else ('estimate_unverified_price' if calculated is not None else 'unavailable')
    clauses=["owner_id=?","crop=?","transaction_type='expense'"]; args=[owner_id,d['crop']]
    for col,val in [('season',d.get('season')),('state',d.get('state')),('district',d.get('district'))]:
        if val: clauses.append(col+'=?'); args.append(val)
    if d.get('sowing_date'): clauses.append('transaction_date>=?'); args.append(d['sowing_date'])
    if d.get('harvest_date'): clauses.append('transaction_date<=?'); args.append(d['harvest_date'])
    with _connect() as db:
        tx=db.execute('SELECT COALESCE(SUM(amount_inr),0) n FROM farm_transactions WHERE '+' AND '.join(clauses),args).fetchone()['n']
    d['expenses_inr']=round(tx,2)
    d['profit_inr']=round(calculated-tx,2) if verified and calculated is not None else None
    d['performance_status']='Profitable' if d['profit_inr'] is not None and d['profit_inr']>0 else ('Loss' if d['profit_inr'] is not None else 'Awaiting verified price')
    return d


def add_crop(data,owner_id='local'):
    init_db(); now=datetime.now(timezone.utc).isoformat()
    data=dict(data)
    for k in ('sowing_date','harvest_date'):
        if hasattr(data.get(k),'isoformat'): data[k]=data[k].isoformat()
    with _connect() as db:
        cur=db.execute('''INSERT INTO farm_crops(owner_id,crop,area_acres,season,sowing_date,harvest_date,production_kg,selling_price_inr_per_quintal,price_verified,price_source,state,district,soil_type,notes,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id''',(_owner_clause(owner_id),data['crop'].strip(),data['area_acres'],data['season'],data.get('sowing_date'),data.get('harvest_date'),data.get('production_kg'),data.get('selling_price_inr_per_quintal'),int(data.get('price_verified',False)),data.get('price_source',''),data.get('state',''),data.get('district',''),data.get('soil_type',''),data.get('notes',''),now,now))
        row=db.execute('SELECT * FROM farm_crops WHERE id=?',(cur.fetchone()['id'],)).fetchone()
    return _crop_row(row,_owner_clause(owner_id))


def list_crops(owner_id='local',crop=None,season=None,state=None,district=None,start_date=None,end_date=None):
    init_db(); clauses=['owner_id=?']; args=[_owner_clause(owner_id)]
    for col,val in [('crop',crop),('season',season),('state',state),('district',district)]:
        if val: clauses.append(col+'=?'); args.append(val)
    if start_date: clauses.append("COALESCE(harvest_date,sowing_date,'')>=?"); args.append(start_date)
    if end_date: clauses.append("COALESCE(harvest_date,sowing_date,'')<=?"); args.append(end_date)
    with _connect() as db: rows=db.execute('SELECT * FROM farm_crops WHERE '+' AND '.join(clauses)+' ORDER BY COALESCE(sowing_date,created_at) DESC',args).fetchall()
    return [_crop_row(r,_owner_clause(owner_id)) for r in rows]


def update_crop(record_id,data,owner_id='local'):
    init_db(); now=datetime.now(timezone.utc).isoformat()
    data=dict(data)
    for k in ('sowing_date','harvest_date'):
        if hasattr(data.get(k),'isoformat'): data[k]=data[k].isoformat()
    fields=['crop','area_acres','season','sowing_date','harvest_date','production_kg','selling_price_inr_per_quintal','price_verified','price_source','state','district','soil_type','notes']
    vals=[data.get(k) for k in fields]; vals[7]=int(bool(vals[7]))
    with _connect() as db:
        cur=db.execute('UPDATE farm_crops SET '+','.join(f'{k}=?' for k in fields)+',updated_at=? WHERE id=? AND owner_id=?',(*vals,now,record_id,_owner_clause(owner_id)))
        if not cur.rowcount:return None
        row=db.execute('SELECT * FROM farm_crops WHERE id=?',(record_id,)).fetchone()
    return _crop_row(row,_owner_clause(owner_id))


def delete_crop(record_id,owner_id='local'):
    init_db()
    with _connect() as db:return db.execute('DELETE FROM farm_crops WHERE id=? AND owner_id=?',(record_id,_owner_clause(owner_id))).rowcount>0


def import_mandi_rows(rows,source,granularity='daily'):
    """Import source-attributed observations; reject malformed dates/prices."""
    if granularity not in ('daily','monthly'):
        raise ValueError('granularity must be daily or monthly')
    if not str(source or '').strip():
        raise ValueError('A source label is required for every historical import.')
    init_db(); now=datetime.now(timezone.utc).isoformat()
    accepted=skipped=0
    aliases={'state':['state'],'district':['district'],'market':['market','mandi'],
      'commodity':['commodity','crop'],'variety':['variety'],'grade':['grade'],
      'report_date':['arrival_date','date','report_date','month'],
      'min_price':['min_price','minimum_price'],'max_price':['max_price','maximum_price'],
      'modal_price':['modal_price','modal'],'arrivals':['arrivals','arrival_quantity','quantity']}
    with _connect() as db:
        for raw in rows:
            r={__import__('re').sub(r'_x([0-9a-f]{4})_',lambda m:chr(int(m.group(1),16)),str(k).strip().lower()).replace(' ','_'):v for k,v in raw.items()}
            def get(key):
                for alias in aliases[key]:
                    if alias in r and r[alias] not in ('',None): return str(r[alias]).strip()
                return ''
            commodity=get('commodity'); raw_date=get('report_date')
            if not commodity or not raw_date:
                skipped+=1; continue
            try:
                if '/' in raw_date: dt=datetime.strptime(raw_date,'%d/%m/%Y').date().isoformat()
                elif len(raw_date)==10 and raw_date[2]=='-': dt=datetime.strptime(raw_date,'%d-%m-%Y').date().isoformat()
                elif len(raw_date)==7 and raw_date[4]=='-': dt=raw_date+'-01'
                else:
                    try: dt=datetime.fromisoformat(raw_date[:10]).date().isoformat()
                    except ValueError:
                        parsed=None
                        for fmt in ('%b-%Y','%B %Y','%Y %b'):
                            try: parsed=datetime.strptime(raw_date,fmt).date(); break
                            except ValueError: pass
                        if parsed is None: raise ValueError('unsupported date')
                        dt=parsed.isoformat()
            except Exception:
                skipped+=1; continue
            def num(key):
                value=get(key)
                if not value: return None
                try:
                    n=float(value.replace(',',''))
                    return n if 0<=n<1e12 else None
                except (ValueError,AttributeError): return None
            lo,hi,modal=num('min_price'),num('max_price'),num('modal_price')
            if lo is None and hi is None and modal is None:
                skipped+=1; continue
            if lo is not None and hi is not None and lo>hi:
                skipped+=1; continue
            if modal is not None and ((lo is not None and modal<lo) or (hi is not None and modal>hi)):
                skipped+=1; continue
            values=(granularity,str(source).strip(),get('state'),get('district'),get('market'),
              commodity,get('variety'),get('grade'),dt,lo,hi,modal,num('arrivals'),
              'INR/quintal',now)
            db.execute("""INSERT INTO mandi_prices(granularity,source,state,district,market,commodity,variety,grade,report_date,min_price,max_price,modal_price,arrivals,unit,imported_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(source,granularity,state,district,market,commodity,variety,grade,report_date)
              DO UPDATE SET min_price=excluded.min_price,max_price=excluded.max_price,
              modal_price=excluded.modal_price,arrivals=excluded.arrivals,imported_at=excluded.imported_at""",values)
            accepted+=1
    return {'imported_or_updated':accepted,'skipped_invalid':skipped,
      'source':str(source).strip(),'granularity':granularity}


def mandi_filters(granularity='daily'):
    init_db()
    with _connect() as db:
        def vals(col):return [r[col] for r in db.execute(f'SELECT DISTINCT {col} FROM mandi_prices WHERE granularity=? AND {col}<>\'\' ORDER BY {col}',(granularity,)).fetchall()]
        return {'commodities':vals('commodity'),'states':vals('state'),'districts':vals('district'),'markets':vals('market')}


def query_mandi(start_date='2025-04-01',end_date='2026-03-31',commodity=None,state=None,district=None,market=None,granularity='daily',page=1,page_size=100,search=None):
    init_db(); clauses=['granularity=?','report_date>=?','report_date<=?']; args=[granularity,start_date,end_date]
    for col,val in [('commodity',commodity),('state',state),('district',district),('market',market)]:
        if val: clauses.append(col+'=?'); args.append(val)
    if search and search.strip():
        term='%'+search.strip().replace('%','\\%').replace('_','\\_')+'%'
        clauses.append("(state LIKE ? OR district LIKE ? OR market LIKE ? OR commodity LIKE ? OR variety LIKE ?)")
        args.extend([term]*5)
    where=' AND '.join(clauses); page=max(1,int(page)); page_size=max(1,min(int(page_size),500))
    with _connect() as db:
        total=db.execute('SELECT COUNT(*) n FROM mandi_prices WHERE '+where,args).fetchone()['n']
        rows=[dict(r) for r in db.execute('SELECT * FROM mandi_prices WHERE '+where+' ORDER BY report_date, state,district,market LIMIT ? OFFSET ?',(*args,page_size,(page-1)*page_size)).fetchall()]
        stats=db.execute('''SELECT MIN(min_price) min_price,MAX(max_price) max_price,AVG(min_price) avg_min,AVG(max_price) avg_max,AVG(modal_price) avg_modal,COUNT(*) n,MAX(report_date) last_date,MIN(report_date) first_date FROM mandi_prices WHERE '''+where,args).fetchone()
        monthly=db.execute('''SELECT substr(report_date,1,7) period,AVG(modal_price) avg_modal,MIN(min_price) min_price,MAX(max_price) max_price,COUNT(*) records FROM mandi_prices WHERE '''+where+''' GROUP BY substr(report_date,1,7) ORDER BY period''',args).fetchall()
        states=db.execute('''SELECT state,AVG(modal_price) avg_modal,MIN(min_price) min_price,MAX(max_price) max_price,MAX(report_date) last_date,COUNT(*) records FROM mandi_prices WHERE '''+where+''' GROUP BY state ORDER BY avg_modal DESC''',args).fetchall()
        markets=db.execute('''SELECT market,state,district,AVG(modal_price) avg_modal,MIN(min_price) min_price,MAX(max_price) max_price,MAX(report_date) last_date,COUNT(*) records FROM mandi_prices WHERE '''+where+''' GROUP BY market,state,district ORDER BY avg_modal DESC LIMIT 100''',args).fetchall()
        distinct_dates=[r['report_date'] for r in db.execute('SELECT DISTINCT report_date FROM mandi_prices WHERE '+where+' ORDER BY report_date',args).fetchall()]
    missing=[]
    if granularity=='daily' and distinct_dates:
        from datetime import date,timedelta
        cur=date.fromisoformat(start_date); last=date.fromisoformat(end_date); present=set(distinct_dates)
        while cur<=last and len(missing)<1000:
            if cur.isoformat() not in present: missing.append(cur.isoformat())
            cur+=timedelta(days=1)
    return {'period':{'start_date':start_date,'end_date':end_date},'granularity':granularity,'total_records':total,'page':page,'page_size':page_size,'pages':(total+page_size-1)//page_size,
      'summary':dict(stats),'coverage':{'first_report_date':stats['first_date'],'last_report_date':stats['last_date'],'missing_reporting_dates':missing,'missing_date_count':len(missing),'missing_dates_truncated':len(missing)>=1000},'monthly': [dict(x) for x in monthly],'states':[dict(x) for x in states],'markets':[dict(x) for x in markets],'records':rows,
      'source_note':'Historical wholesale mandi observations. Daily and monthly-granularity records are queried separately. Prices are INR per quintal. Mean modal price is an unweighted mean across returned observations, not a volume-weighted all-India average.'}


def export_mandi_csv(params):
    data=query_mandi(**params,page=1,page_size=500)
    # Export all pages without loading a large result into a browser.
    rows=data['records']; pages=data['pages']
    for p in range(2,pages+1): rows.extend(query_mandi(**params,page=p,page_size=500)['records'])
    out=io.StringIO(); fields=['report_date','state','district','market','commodity','variety','grade','min_price','max_price','modal_price','arrivals','unit','source','granularity']
    w=csv.DictWriter(out,fieldnames=fields); w.writeheader(); w.writerows({k:r.get(k) for k in fields} for r in rows)
    return out.getvalue()


def save_assistant_message(owner_id,conversation_key,language,role,content):
    init_db()
    with _connect() as db:db.execute('INSERT INTO assistant_conversations(owner_id,conversation_key,language,role,content,created_at) VALUES(?,?,?,?,?,?)',(_owner_clause(owner_id),conversation_key,language,role,content,datetime.now(timezone.utc).isoformat()))


def get_assistant_history(owner_id,conversation_key,limit=12):
    init_db()
    with _connect() as db:rows=db.execute('SELECT role,content,language FROM assistant_conversations WHERE owner_id=? AND conversation_key=? ORDER BY id DESC LIMIT ?',(_owner_clause(owner_id),conversation_key,limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def weather_current(latitude: float,longitude: float):
    params=urllib.parse.urlencode({'latitude':latitude,'longitude':longitude,'current':'temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m,weather_code','daily':'temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max','forecast_days':5,'timezone':'auto'})
    req=urllib.request.Request('https://api.open-meteo.com/v1/forecast?'+params,headers={'User-Agent':'AgriCareAI/1.0'})
    with urllib.request.urlopen(req,timeout=12) as response:payload=json.loads(response.read().decode())
    c=payload.get('current',{}); d=payload.get('daily',{})
    return {'source':'Open-Meteo','latitude':latitude,'longitude':longitude,'timezone':payload.get('timezone'),'updated_at':c.get('time'),
      'current':{'temperature_c':c.get('temperature_2m'),'humidity_percent':c.get('relative_humidity_2m'),'precipitation_mm':c.get('precipitation'),'rain_mm':c.get('rain'),'wind_speed_kmh':c.get('wind_speed_10m'),'weather_code':c.get('weather_code')},
      'forecast':[{'date':d.get('time',[None]*5)[i],'max_temp_c':(d.get('temperature_2m_max') or [None]*5)[i],'min_temp_c':(d.get('temperature_2m_min') or [None]*5)[i],'precipitation_mm':(d.get('precipitation_sum') or [None]*5)[i],'rain_probability_percent':(d.get('precipitation_probability_max') or [None]*5)[i]} for i in range(len(d.get('time',[])))],
      'advisory':weather_advisory(c,d)}


def weather_advisory(current,daily):
    temp=current.get('temperature_2m'); rain=current.get('precipitation',0) or 0; probability=max(daily.get('precipitation_probability_max') or [0]) if daily else 0; tips=[]
    if temp is not None and temp>=38:tips.append('High-temperature conditions: check crop-specific heat stress and irrigate during cooler hours if soil moisture is low.')
    if probability>=60:tips.append('Rain is likely in the forecast: reassess irrigation scheduling and avoid unnecessary watering.')
    if rain>=5:tips.append('Recent precipitation is reported: check root-zone moisture before the next irrigation.')
    if not tips:tips.append('No threshold-based weather alert was triggered. Check field soil moisture and crop stage before making irrigation decisions.')
    return {'rules_based_advisory':tips,'disclaimer':'General weather screening only; not a crop-yield prediction or a substitute for local agronomy advice.'}

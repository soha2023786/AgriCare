#!/usr/bin/env python3
"""Import an official Agmarknet/data.gov.in or CEDA CSV export.

Daily Agmarknet files and monthly CEDA files are stored with separate
`granularity` values. This script never fabricates or interpolates prices.
"""
import argparse, csv, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.analytics import import_mandi_rows

p=argparse.ArgumentParser(description='Import historical Indian mandi price CSV records')
p.add_argument('--csv',required=True,help='Path to the downloaded source CSV')
p.add_argument('--source',required=True,help='Exact source label, e.g. data.gov.in Agmarknet or CEDA Agri-Market')
p.add_argument('--granularity',choices=['daily','monthly'],default='daily')
p.add_argument('--start-date',default='2025-04-01')
p.add_argument('--end-date',default='2026-03-31')
a=p.parse_args()
path=Path(a.csv)
if not path.is_file(): raise SystemExit(f'CSV not found: {path}')
with path.open('r',encoding='utf-8-sig',newline='') as f:
    rows=[]
    for row in csv.DictReader(f):
        # Filter to the requested FY without changing the source date granularity.
        import re
        normalized={re.sub(r'_x([0-9a-f]{4})_',lambda m:chr(int(m.group(1),16)),str(k).strip().lower()).replace(' ','_'):v for k,v in row.items()}
        date_value=(normalized.get('arrival_date') or normalized.get('date') or normalized.get('report_date') or normalized.get('month') or '').strip()
        if not date_value: continue
        from datetime import datetime
        try:
            if '/' in date_value: d=datetime.strptime(date_value,'%d/%m/%Y').date().isoformat()
            elif len(date_value)==10 and date_value[2]=='-': d=datetime.strptime(date_value,'%d-%m-%Y').date().isoformat()
            elif len(date_value)==7: d=date_value+'-01'
            else:
                try: d=datetime.fromisoformat(date_value[:10]).date().isoformat()
                except ValueError:
                    parsed=None
                    for fmt in ('%b-%Y','%B %Y','%Y %b'):
                        try: parsed=datetime.strptime(date_value,fmt).date(); break
                        except ValueError: pass
                    if parsed is None: raise
                    d=parsed.isoformat()
        except Exception: continue
        if a.start_date<=d<=a.end_date: rows.append(row)
result=import_mandi_rows(rows,a.source,a.granularity)
print({**result,'requested_period':[a.start_date,a.end_date],'input_file':str(path)})

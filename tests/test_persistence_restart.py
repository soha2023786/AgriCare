import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from app.services import analytics, auth

class PersistenceRestartTests(unittest.TestCase):
    def test_sqlite_records_and_login_survive_a_new_python_process(self):
        with tempfile.TemporaryDirectory(prefix='agricare_restart_') as directory:
            db_path = Path(directory) / 'agricare.sqlite3'
            old_path = analytics.DB_PATH
            old_secret = os.environ.get('AGRICARE_AUTH_SECRET')
            analytics.DB_PATH = db_path
            os.environ['AGRICARE_AUTH_SECRET'] = 'restart-test-secret-long-enough-123456789'
            try:
                user = auth.register('Restart Farmer', 'restart@example.test', 'strong-password-123')
                analytics.add_transaction({
                    'transaction_type': 'revenue', 'crop': 'Rice', 'category': 'Sale',
                    'amount_inr': 9876, 'transaction_date': date(2026, 11, 10), 'notes': ''
                }, user['farmer_id'])
                analytics.add_crop({
                    'crop': 'Rice', 'area_acres': 1.5, 'season': 'Kharif',
                    'sowing_date': date(2026, 6, 1), 'state': 'Telangana', 'district': 'Warangal'
                }, user['farmer_id'])

                env = os.environ.copy()
                env['AGRICARE_DB_PATH'] = str(db_path)
                env.pop('DATABASE_URL', None)
                env.pop('POSTGRES_URL', None)
                code = """import json
from app.services import analytics, auth
analytics.init_db(); auth.init_auth()
user=auth.login('restart@example.test','strong-password-123')
rows=analytics.list_transactions(owner_id=user['farmer_id']) if user else []
crops=analytics.list_crops(owner_id=user['farmer_id']) if user else []
print(json.dumps({'login':bool(user),'transactions':len(rows),'crops':len(crops),'amount':rows[0]['amount_inr'] if rows else None}))
"""
                result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1], env=env,
                                        text=True, capture_output=True, check=True)
                observed = json.loads(result.stdout.strip().splitlines()[-1])
                self.assertEqual(observed, {'login': True, 'transactions': 1, 'crops': 1, 'amount': 9876.0})
            finally:
                analytics.DB_PATH = old_path
                if old_secret is None: os.environ.pop('AGRICARE_AUTH_SECRET', None)
                else: os.environ['AGRICARE_AUTH_SECRET'] = old_secret


    def test_vercel_without_database_keeps_home_and_health_available(self):
        env = os.environ.copy()
        env['VERCEL'] = '1'
        env['AGRICARE_AUTH_SECRET'] = 'health-test-secret-long-enough-123456789'
        env.pop('DATABASE_URL', None)
        env.pop('POSTGRES_URL', None)
        code = """from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
assert c.get('/').status_code == 200
h=c.get('/api/health')
assert h.status_code == 200 and h.json()['status'] == 'degraded'
assert h.json()['database'] == 'unconfigured'
assert c.get('/api/market/historical').status_code == 503
"""
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1], env=env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_vercel_mode_imports_without_creating_ephemeral_sqlite_fallback(self):
        env = os.environ.copy()
        env['VERCEL'] = '1'
        env.pop('DATABASE_URL', None)
        env.pop('POSTGRES_URL', None)
        code = "from app.services import analytics; assert analytics.database_backend() == 'unconfigured'; analytics._connect()"
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1], env=env,
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Persistent storage is not configured', result.stderr)

if __name__ == '__main__': unittest.main()

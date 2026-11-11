import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.services import analytics
from app.main import app

class FarmerApiSecurityTests(unittest.TestCase):
    def setUp(self):
        self.old_path = analytics.DB_PATH
        self.old_secret = os.environ.get('AGRICARE_AUTH_SECRET')
        self.path = Path(tempfile.gettempdir()) / f'agricare_api_security_{os.getpid()}.sqlite3'
        if self.path.exists(): self.path.unlink()
        analytics.DB_PATH = self.path
        os.environ['AGRICARE_AUTH_SECRET'] = 'test-only-secret-that-is-long-enough-123456'
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        if self.path.exists(): self.path.unlink()
        analytics.DB_PATH = self.old_path
        if self.old_secret is None: os.environ.pop('AGRICARE_AUTH_SECRET', None)
        else: os.environ['AGRICARE_AUTH_SECRET'] = self.old_secret

    def _register(self, email, name):
        response = self.client.post('/api/auth/register', json={
            'name': name, 'email': email, 'password': 'strong-test-password-123'
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['access_token']

    def test_two_farmers_cannot_list_or_mutate_each_others_records(self):
        token_a = self._register('farmer-a@example.test', 'Farmer A')
        token_b = self._register('farmer-b@example.test', 'Farmer B')
        headers_a = {'Authorization': f'Bearer {token_a}'}
        headers_b = {'Authorization': f'Bearer {token_b}'}

        tx = self.client.post('/api/analytics/transactions', headers=headers_a, json={
            'transaction_type': 'revenue', 'crop': 'Rice', 'category': 'Sale',
            'amount_inr': 25000, 'transaction_date': '2026-11-01', 'season': 'Kharif'
        })
        self.assertEqual(tx.status_code, 200, tx.text)
        tx_id = tx.json()['id']

        crop = self.client.post('/api/analytics/crops', headers=headers_a, json={
            'crop': 'Rice', 'area_acres': 2, 'season': 'Kharif',
            'sowing_date': '2026-06-01', 'state': 'Telangana', 'district': 'Warangal'
        })
        self.assertEqual(crop.status_code, 200, crop.text)
        crop_id = crop.json()['id']

        self.assertEqual(self.client.get('/api/analytics/transactions', headers=headers_b).json()['records'], [])
        self.assertEqual(self.client.get('/api/analytics/crops', headers=headers_b).json()['records'], [])
        self.assertEqual(self.client.put(f'/api/analytics/transactions/{tx_id}', headers=headers_b, json={
            'transaction_type': 'expense', 'crop': 'Rice', 'category': 'Tampering',
            'amount_inr': 1, 'transaction_date': '2026-11-02'
        }).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/analytics/transactions/{tx_id}', headers=headers_b).status_code, 404)
        self.assertEqual(self.client.put(f'/api/analytics/crops/{crop_id}', headers=headers_b, json={
            'crop': 'Wheat', 'area_acres': 1, 'season': 'Rabi'
        }).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/analytics/crops/{crop_id}', headers=headers_b).status_code, 404)

        self.assertEqual(self.client.get('/api/analytics/transactions', headers=headers_a).json()['records'][0]['amount_inr'], 25000)
        self.assertEqual(self.client.get('/api/analytics/crops', headers=headers_a).json()['records'][0]['crop'], 'Rice')

    def test_private_analytics_requires_authentication(self):
        self.assertEqual(self.client.get('/api/analytics/overview').status_code, 401)

if __name__ == '__main__': unittest.main()

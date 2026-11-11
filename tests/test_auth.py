import os
import tempfile
import unittest
from pathlib import Path
from app.services import analytics, auth

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.old_path=analytics.DB_PATH
        self.old_secret=os.environ.get('AGRICARE_AUTH_SECRET')
        analytics.DB_PATH=Path(tempfile.gettempdir())/'agricare_auth_test.sqlite3'
        if analytics.DB_PATH.exists():analytics.DB_PATH.unlink()
        os.environ['AGRICARE_AUTH_SECRET']='unit-test-secret-long-random-value'
        auth.init_auth()

    def tearDown(self):
        if analytics.DB_PATH.exists():analytics.DB_PATH.unlink()
        analytics.DB_PATH=self.old_path
        if self.old_secret is None:os.environ.pop('AGRICARE_AUTH_SECRET',None)
        else:os.environ['AGRICARE_AUTH_SECRET']=self.old_secret

    def test_password_hash_login_and_signed_token(self):
        user=auth.register('farmer@example.com','strong-password-123')
        self.assertIsNotNone(auth.login('farmer@example.com','strong-password-123'))
        self.assertIsNone(auth.login('farmer@example.com','wrong-password-123'))
        token=auth.issue_token(user)
        self.assertEqual(auth.verify_token(token)['farmer_id'],user['farmer_id'])
        self.assertIsNone(auth.verify_token(token+'tampered'))

if __name__=='__main__':unittest.main()

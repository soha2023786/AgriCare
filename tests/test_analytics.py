import tempfile
import unittest
from datetime import date
from pathlib import Path
from app.services import analytics

class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.old_path = analytics.DB_PATH
        analytics.DB_PATH = Path(tempfile.gettempdir()) / 'agricare_unit_test.sqlite3'
        if analytics.DB_PATH.exists(): analytics.DB_PATH.unlink()

    def tearDown(self):
        if analytics.DB_PATH.exists(): analytics.DB_PATH.unlink()
        analytics.DB_PATH = self.old_path

    def test_inr_totals_and_crop_profit(self):
        common={'crop':'Rice','season':'Kharif','state':'Telangana','district':'Hyderabad','notes':''}
        analytics.add_transaction({**common,'transaction_type':'revenue','category':'Crop sale','amount_inr':125000,'transaction_date':date(2026,11,1)})
        analytics.add_transaction({**common,'transaction_type':'expense','category':'Seeds','amount_inr':35000,'transaction_date':date(2026,11,2)})
        data=analytics.overview()
        self.assertEqual(data['total_revenue_inr'],125000)
        self.assertEqual(data['total_expenses_inr'],35000)
        self.assertEqual(data['net_profit_inr'],90000)
        self.assertEqual(data['crop_performance'][0]['profit_inr'],90000)


    def test_transaction_crud_and_owner_isolation(self):
        common={'crop':'Tomato','season':'Kharif','state':'Telangana','district':'Warangal','notes':''}
        a=analytics.add_transaction({**common,'transaction_type':'expense','category':'Seeds','amount_inr':1200,'transaction_date':date(2025,6,1)},'farmer-a')
        self.assertEqual(len(analytics.list_transactions(owner_id='farmer-a')),1)
        self.assertEqual(len(analytics.list_transactions(owner_id='farmer-b')),0)
        updated=analytics.update_transaction(a['id'],{**common,'transaction_type':'expense','category':'Seeds','amount_inr':1500,'transaction_date':date(2025,6,2)},'farmer-a')
        self.assertEqual(updated['amount_inr'],1500)
        self.assertFalse(analytics.delete_transaction(a['id'],'farmer-b'))
        self.assertTrue(analytics.delete_transaction(a['id'],'farmer-a'))

    def test_crop_verified_revenue_and_estimate_separation(self):
        analytics.add_transaction({'crop':'Tomato','season':'Kharif','state':'Telangana','district':'Warangal','transaction_type':'expense','category':'Labour','amount_inr':3000,'transaction_date':date(2025,6,15),'notes':''},'farmer-a')
        base={'crop':'Tomato','area_acres':2,'season':'Kharif','sowing_date':date(2025,4,1),'harvest_date':date(2025,7,1),'production_kg':1000,'selling_price_inr_per_quintal':2000,'price_source':'sale receipt','state':'Telangana','district':'Warangal','soil_type':'Red','notes':''}
        actual=analytics.add_crop({**base,'price_verified':True},'farmer-a')
        estimated=analytics.add_crop({**base,'price_verified':False},'farmer-a')
        self.assertEqual(actual['revenue_inr'],20000)
        self.assertEqual(actual['expenses_inr'],3000)
        self.assertEqual(actual['profit_inr'],17000)
        self.assertIsNone(estimated['revenue_inr'])
        self.assertEqual(estimated['estimated_revenue_inr'],20000)

    def test_historical_mandi_import_filter_and_export(self):
        rows=[
          {'State':'Telangana','District':'Warangal','Market':'Warangal','Commodity':'Tomato','Variety':'Local','Arrival_Date':'05/06/2025','Min_Price':'1000','Max_Price':'2000','Modal_Price':'1500'},
          {'State':'Telangana','District':'Warangal','Market':'Warangal','Commodity':'Tomato','Variety':'Local','Arrival_Date':'05/06/2026','Min_Price':'1200','Max_Price':'2200','Modal_Price':'1700'},
        ]
        result=analytics.import_mandi_rows(rows,'data.gov.in Agmarknet','daily')
        self.assertEqual(result['imported_or_updated'],2)
        data=analytics.query_mandi('2025-04-01','2026-03-31',commodity='Tomato',state='Telangana')
        self.assertEqual(data['total_records'],1)
        self.assertEqual(data['summary']['avg_modal'],1500)
        self.assertEqual(data['records'][0]['report_date'],'2025-06-05')
        exported=analytics.export_mandi_csv({'start_date':'2025-04-01','end_date':'2026-03-31','commodity':'Tomato','state':'Telangana','granularity':'daily'})
        self.assertIn('1500',exported)


    def test_historical_import_rejects_invalid_prices_and_supports_search(self):
        rows=[
          {'State':'Telangana','District':'Nalgonda','Market':'Miryalaguda','Commodity':'Rice','Arrival_Date':'2025-08-10','Min_Price':'1000','Max_Price':'2000','Modal_Price':'1500'},
          {'State':'Telangana','District':'Nalgonda','Market':'Miryalaguda','Commodity':'Rice','Arrival_Date':'2025-08-11','Min_Price':'2500','Max_Price':'1000','Modal_Price':'1500'},
          {'State':'Telangana','District':'Nalgonda','Market':'Miryalaguda','Commodity':'Rice','Arrival_Date':'not-a-date','Min_Price':'1000','Max_Price':'2000','Modal_Price':'1500'},
          {'State':'Telangana','District':'Nalgonda','Market':'Miryalaguda','Commodity':'Rice','Arrival_Date':'2025-08-12','Min_Price':'','Max_Price':'','Modal_Price':''},
        ]
        result=analytics.import_mandi_rows(rows,'Official source','daily')
        self.assertEqual(result['imported_or_updated'],1)
        self.assertEqual(result['skipped_invalid'],3)
        found=analytics.query_mandi('2025-04-01','2026-03-31',search='Miryalaguda')
        self.assertEqual(found['total_records'],1)
        self.assertEqual(found['markets'][0]['min_price'],1000)


    def test_encoded_official_csv_headers_are_normalized(self):
        rows=[{'State':'Telangana','District':'Warangal','Market':'Warangal','Commodity':'Rice','Variety':'Sona','Arrival_Date':'2025-06-05','Min_x0020_Price':'1000','Max_x0020_Price':'2000','Modal_x0020_Price':'1500'}]
        result=analytics.import_mandi_rows(rows,'data.gov.in Agmarknet','daily')
        self.assertEqual(result['imported_or_updated'],1)
        self.assertEqual(result['skipped_invalid'],0)

    def test_overview_includes_more_than_one_thousand_transactions(self):
        for i in range(1005):
            analytics.add_transaction({'crop':'Rice','transaction_type':'revenue','category':'Sale','amount_inr':1,'transaction_date':date(2026,1,1),'notes':''},'large-farmer')
        self.assertEqual(analytics.overview(owner_id='large-farmer')['total_revenue_inr'],1005)

    def test_assistant_conversation_history_persistence(self):
        analytics.save_assistant_message('farmer-a','thread-1','Telugu','user','నా టమాటా ఆకులు పసుపు రంగులో ఉన్నాయి')
        analytics.save_assistant_message('farmer-a','thread-1','Telugu','assistant','లక్షణాలను మరింత వివరించండి')
        history=analytics.get_assistant_history('farmer-a','thread-1')
        self.assertEqual([x['role'] for x in history],['user','assistant'])
        self.assertEqual(history[0]['language'],'Telugu')
        self.assertEqual(analytics.get_assistant_history('farmer-b','thread-1'),[])

if __name__ == '__main__': unittest.main()

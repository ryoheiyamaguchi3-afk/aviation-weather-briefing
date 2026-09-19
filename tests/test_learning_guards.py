import unittest
from briefing.demo import demo_record, DEMO_TEXT
from briefing.pipeline import learning_guards
from briefing.schema import validate_report

class LearningGuardTests(unittest.TestCase):
    def fixture(self, issued='2026-09-19T03:40:00+09:00'):
        from datetime import datetime, timedelta
        rec=demo_record()
        for i, slot in enumerate(rec['report']['timeline']):
            slot['date_jst']=(datetime.fromisoformat(issued).date()+timedelta(days=i==4)).isoformat()
        return rec['report']

    def test_horizontal_shear_is_not_llws_and_wind_is_not_crosswind(self):
        report=self.fixture()
        for item in report['aviation']:
            item['assessment']={'text':'確定した航空現象','label':'資料記載','evidence':[{'page':1,'quote':DEMO_TEXT}]}
        result=learning_guards(report,[DEMO_TEXT],'2026-09-19T03:40:00+09:00')
        for item in result['aviation']:
            if item['code'] in ['LLWS','TURB','CROSSWIND','CB','VIS','CEILING']:
                self.assertEqual(item['assessment']['label'],'追加資料確認推奨')
                self.assertNotIn('確定した航空現象',str(item))
        validate_report(result,[DEMO_TEXT],'2026-09-19T03:40:00+09:00')

    def test_tomorrow_night_not_moved_to_tonight(self):
        pages=[DEMO_TEXT+'19日夜には強い台風となり、20日夜から進路を東よりに変える。']
        result=learning_guards(self.fixture(),pages,'2026-09-19T03:40:00+09:00')
        self.assertIn('20日夜から',result['timeline'][3]['outlook']['text'])
        self.assertEqual(result['timeline'][4]['outlook']['label'],'追加資料確認推奨')
        validate_report(result,pages,'2026-09-19T03:40:00+09:00')

    def test_day_number_boundary_and_past_slots(self):
        pages=[DEMO_TEXT+'21日朝には雨が弱まる。']
        result=learning_guards(self.fixture('2026-09-01T03:40:00+09:00'),pages,'2026-09-01T03:40:00+09:00')
        self.assertEqual(result['timeline'][0]['outlook']['label'],'追加資料確認推奨')
        result=learning_guards(self.fixture('2026-09-21T15:40:00+09:00'),pages,'2026-09-21T15:40:00+09:00')
        self.assertEqual(result['timeline'][0]['outlook']['label'],'追加資料確認推奨')

if __name__=='__main__': unittest.main()

import unittest
from urllib.error import HTTPError
from briefing.demo import demo_record, DEMO_TEXT
from briefing.pipeline import quarantine_unverified_claims, safe_error_code, response_schema
from briefing.schema import validate_report, normalize

class RecoveryTests(unittest.TestCase):
    def test_quote_catalog_contains_only_real_source_spans(self):
        pages=['原資料に存在する引用です。次の文も実際の文章です。', '二ページ目の文章を照合します。']
        fields=response_schema(pages)['$defs']['Evidence']['properties']
        self.assertEqual(fields['page']['enum'],[1,2])
        self.assertGreaterEqual(len(fields['quote']['enum']),3)
        for quote in fields['quote']['enum']:
            self.assertTrue(any(normalize(quote) in normalize(p) for p in pages))
            self.assertTrue(6<=len(quote)<=160)

    def test_empty_source_cannot_create_a_quote_catalog(self):
        with self.assertRaisesRegex(ValueError,'source_quote_catalog_limit'):
            response_schema([''])

    def test_unverified_claim_is_discarded_not_relabelled(self):
        rec=demo_record()
        rec['report']['summary'][0]['text']='UNSUPPORTED CLAIM'
        rec['report']['summary'][0]['evidence'][0]['quote']='存在しない引用文字列'
        result=quarantine_unverified_claims(rec['report'],[DEMO_TEXT])
        claim=result['summary'][0]
        self.assertNotIn('UNSUPPORTED',str(result))
        self.assertEqual(claim['label'],'追加資料確認推奨')
        self.assertEqual(claim['evidence'],[])
        self.assertIn('要確認表示',result['limitations'][-1])
        validate_report(result,[DEMO_TEXT],rec['source']['issued_at'])

    def test_widespread_bad_evidence_still_fails_closed(self):
        rec=demo_record()
        def corrupt(node):
            if isinstance(node, dict):
                if {'text','label','evidence'} <= node.keys():
                    node['label']='資料記載'
                    node['evidence']=[]
                for value in node.values(): corrupt(value)
            elif isinstance(node,list):
                for value in node: corrupt(value)
        corrupt(rec['report'])
        with self.assertRaisesRegex(ValueError,'unmatched_evidence'):
            quarantine_unverified_claims(rec['report'],['異なる資料'])

    def test_valid_report_is_unchanged(self):
        rec=demo_record()
        self.assertEqual(quarantine_unverified_claims(rec['report'],[DEMO_TEXT]),rec['report'])

    def test_diagnostic_does_not_expose_exception_text(self):
        secret='SECRET_SENTINEL'
        for exc in [RuntimeError(secret),ValueError(secret),HTTPError('https://example.test',401,secret,None,None)]:
            self.assertNotIn(secret,safe_error_code(exc))

if __name__=='__main__': unittest.main()

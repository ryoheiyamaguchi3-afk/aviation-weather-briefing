import copy
from datetime import datetime, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from briefing import pipeline, render, source
from briefing.demo import demo_record, DEMO_TEXT
from briefing.schema import Report, validate_report
from briefing.security import audit_public

class SourceTests(unittest.TestCase):
    def test_discover_uses_official_anchor(self):
        url, related=source.discover('<a href="https://www.data.jma.go.jp/new.pdf">短期予報解説資料</a><a href="/bosai/numericmap/">高層天気図</a>')
        self.assertEqual(url,'https://www.data.jma.go.jp/new.pdf')
        self.assertFalse(related[0]['analyzed'])
    def test_changed_link_fails_closed(self):
        with self.assertRaises(ValueError): source.discover('<a href="missing.pdf">別資料</a>')
    def test_external_and_lookalike_urls_rejected(self):
        for url in ['https://jma.go.jp.evil.test/a','http://www.jma.go.jp/a','https://example.com/a','https://user@www.jma.go.jp/a','https://www.jma.go.jp:444/a']:
            with self.subTest(url=url), self.assertRaises(ValueError): source.official_url(url)
    def test_redirect_is_checked(self):
        with self.assertRaises(ValueError): source.OfficialRedirect().redirect_request(None,None,302,'',{},'https://evil.test/a')
    def test_pdf_heading_full_width_and_editions(self):
        class Page:
            def extract_text(self): return '短期予報解説資料１ ２０２６年９月１８日１５時４０分発表 気象庁'
        class Reader:
            is_encrypted=False
            pages=[Page()]
        with patch.object(source,'PdfReader',return_value=Reader()):
            meta,pages=source.inspect_pdf(b'%PDF-fixture','https://www.jma.go.jp/file.pdf',datetime(2026,9,18,16,tzinfo=source.JST))
        self.assertEqual(meta['issued_at'],'2026-09-18T15:40:00+09:00')
        self.assertEqual(meta['name'],'短期予報解説資料1')
        self.assertIn('夕方',meta['edition'])
    def test_non_pdf_and_future_header_fail(self):
        with self.assertRaises(ValueError): source.inspect_pdf(b'<html>down</html>','https://www.jma.go.jp/a')
        class Reader:
            is_encrypted=False
            pages=[type('Page',(),{'extract_text':lambda s:'短期予報解説資料 2099年1月1日03時40分発表'})()]
        with patch.object(source,'PdfReader',return_value=Reader()),self.assertRaises(ValueError):
            source.inspect_pdf(b'%PDF-test','https://www.jma.go.jp/a')

class EvidenceTests(unittest.TestCase):
    def setUp(self): self.rec=demo_record()
    def validate(self): return validate_report(self.rec['report'],[DEMO_TEXT],self.rec['source']['issued_at'])
    def test_valid_schema_and_citations(self): self.validate()
    def test_false_quote_is_rejected(self):
        self.rec['report']['summary'][0]['evidence'][0]['quote']='存在しない根拠の文章'
        with self.assertRaises(ValueError): self.validate()
    def test_fact_requires_quote(self):
        self.rec['report']['summary'][0]['evidence']=[]
        with self.assertRaises(ValueError): self.validate()
    def test_page_out_of_bounds(self):
        self.rec['report']['summary'][0]['evidence'][0]['page']=2
        with self.assertRaises(ValueError): self.validate()
    def test_next_morning_date_and_slot_order(self):
        self.rec['report']['timeline'][-1]['date_jst']='2026-01-01'
        with self.assertRaises(ValueError): self.validate()
    def test_duplicate_hazard_rejected(self):
        self.rec['report']['aviation'][1]['code']='TS'
        with self.assertRaises(ValueError): self.validate()
    def test_no_unknown_fields(self):
        self.rec['report']['html']='<script>alert(1)</script>'
        with self.assertRaises(ValueError): self.validate()

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.state={'version':1,'documents':{},'monthly_requests':{}}
        self.meta={'id':'x','sha256':'hash','issued_at':'2026-09-18T03:40:00+09:00'}
        self.now=datetime(2026,9,18,5,tzinfo=source.JST)
    def reserve(self,**kw): return pipeline.reserve(self.state,self.meta,now=self.now,**kw)
    def test_crash_reservation_blocks_paid_repeat(self):
        self.assertTrue(self.reserve()[0]); self.assertEqual(self.reserve(),(False,'retry_required'))
        self.assertEqual(self.state['monthly_requests']['2026-09'],1)
    def test_completed_never_reanalyzed_even_retry(self):
        self.reserve(); self.state['documents']['hash']['status']='complete'
        self.assertEqual(self.reserve(retry=True),(False,'unchanged'))
    def test_retry_once_only(self):
        self.reserve(); self.assertTrue(self.reserve(retry=True)[0]); self.assertEqual(self.reserve(retry=True),(False,'attempt_limit'))
    def test_monthly_limit_survives_restarts(self):
        self.state['monthly_requests']['2026-09']=70
        self.assertEqual(self.reserve(),(False,'budget_limit'))
    def test_revision_new_hash_is_new_document(self):
        self.reserve(); self.meta={**self.meta,'sha256':'corrected','id':'y'}
        self.assertTrue(self.reserve()[0])

class PipelineTests(unittest.TestCase):
    def test_native_pdf_vision_request_and_structured_result(self):
        rec=demo_record()
        body={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(rec['report'])}]}],
              'usage':{'input_tokens':100,'output_tokens':200,'total_tokens':300}}
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return json.dumps(body).encode()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'unit-test-placeholder'}),patch('urllib.request.urlopen',return_value=Response()) as req:
            report,usage=pipeline.api_request(rec['source'],b'%PDF-test',[DEMO_TEXT],'gpt-4.1-mini')
        payload=json.loads(req.call_args.args[0].data)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['input'][0]['content'][1]['type'],'input_file')
        self.assertEqual(payload['input'][0]['content'][1]['detail'],'high')
        self.assertTrue(payload['text']['format']['strict'])
        self.assertEqual(usage['total_tokens'],300)
        self.assertEqual(req.call_count,1)
    def test_timeout_has_no_automatic_paid_retry(self):
        rec=demo_record()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'unit-test-placeholder'}),patch('urllib.request.urlopen',side_effect=TimeoutError) as req:
            with self.assertRaises(TimeoutError): pipeline.api_request(rec['source'],b'%PDF-test',[DEMO_TEXT],'gpt-4.1-mini')
            self.assertEqual(req.call_count,1)
    def test_incomplete_response_never_published(self):
        rec=demo_record()
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return b'{"status":"incomplete"}'
        with patch.dict('os.environ',{'OPENAI_API_KEY':'unit-test-placeholder'}),patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'incomplete_response'):
                pipeline.api_request(rec['source'],b'%PDF-test',[DEMO_TEXT],'gpt-4.1-mini')
    def test_analyze_failure_preserves_previous_report_and_durable_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data'; work=Path(tmp)/'work'; d=data/'documents'/'x'; d.mkdir(parents=True)
            (d/'source.pdf').write_bytes(b'%PDF-fixture')
            pipeline.write_json(d/'source.json',{'id':'x','issued_at':'2026-01-01T03:40:00+09:00'})
            pipeline.write_json(d/'text.json',[DEMO_TEXT])
            pipeline.write_json(data/'reports'/'old.json',{'keep':True})
            pipeline.write_json(data/'state.json',{'documents':{'h':{'status':'reserved','attempts':[{'status':'reserved'}]}}})
            pipeline.write_json(work/'pending.json',{'id':'x','sha256':'h','model':'test'})
            def fail(*args): raise RuntimeError('sensitive upstream error')
            with patch.object(pipeline,'DATA',data),patch.object(pipeline,'WORK',work),self.assertRaisesRegex(RuntimeError,'^analysis_failed$'):
                pipeline.analyze(fail)
            self.assertEqual(pipeline.read_json(data/'reports'/'old.json'),{'keep':True})
            self.assertEqual(pipeline.read_json(data/'state.json')['documents']['h']['status'],'failed')
            self.assertNotIn('sensitive',(data/'status.json').read_text())
    def test_missing_key_does_not_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta={'id':'x','sha256':'h','issued_at':source.now_jst().isoformat()}
            with patch.object(pipeline,'DATA',Path(tmp)/'data'),patch.object(pipeline,'WORK',Path(tmp)/'work'),patch.dict('os.environ',{},clear=True):
                self.assertFalse(pipeline.prepare(fetcher=lambda:(meta,[DEMO_TEXT],b'%PDF-fixture')))
                self.assertFalse((Path(tmp)/'data'/'state.json').exists())

class RenderingTests(unittest.TestCase):
    def test_generated_html_escapes_untrusted_text(self):
        r=demo_record(); r['report']['headline']='<script>alert("X")</script>'
        html=render.document(r,{'code':'demo'},[],[])
        self.assertNotIn('<script>alert',html); self.assertIn('&lt;script&gt;',html)
    def test_demo_is_labeled_and_not_current(self):
        html=render.document(demo_record(),{},[],[])
        self.assertIn('架空の学習例',html); self.assertIn('data-demo="true"',html)
        self.assertIn('APIで生成した結果でもありません',html)
    def test_empty_state_never_fabricates_report(self):
        html=render.document(None,{},[],[])
        self.assertIn('ブリーフィングは未生成',html); self.assertNotIn('前線が',html)
    def test_all_requested_sections(self):
        html=render.document(demo_record(),{},[],[])
        for ident in ['overview','synoptic','upper','phenomena','rain','aviation','timeline','why','source']:
            self.assertIn('id="'+ident+'"',html)
        self.assertEqual(html.count('class="hazard"'),14)

class PublicationTests(unittest.TestCase):
    def test_unexpected_secret_file_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'.env').write_text('private',encoding='utf-8')
            with self.assertRaises(ValueError): audit_public(Path(tmp))
    def test_key_pattern_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'index.html').write_text('sk-'+'x'*40,encoding='utf-8')
            with self.assertRaises(ValueError): audit_public(Path(tmp))
    def test_clean_artifact_is_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'index.html').write_text('<html>safe</html>',encoding='utf-8')
            audit_public(Path(tmp))

if __name__=='__main__': unittest.main()

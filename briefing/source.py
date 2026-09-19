"""Discover the latest PDF through the JMA official expert index, never guessed URLs."""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import re
import unicodedata
import urllib.request
from urllib.parse import urljoin, urlparse
from pypdf import PdfReader

JST = timezone(timedelta(hours=9))
INDEX_URL = 'https://www.jma.go.jp/jma/kishou/know/expert/'
MAX_PDF = 8 * 1024 * 1024

def now_jst(): return datetime.now(JST)

def official_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or not (p.hostname == 'jma.go.jp' or p.hostname.endswith('.jma.go.jp')) or p.username or p.password or p.port not in (None, 443):
        raise ValueError('non_jma_url')
    return url

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download(url, limit):
    official_url(url)
    req = urllib.request.Request(url, headers={'User-Agent':'AviationWeatherLearning/1.0', 'Cache-Control':'no-cache'})
    with urllib.request.build_opener(OfficialRedirect()).open(req, timeout=45) as response:
        official_url(response.url)
        data = response.read(limit+1)
        if len(data) > limit: raise ValueError('download_too_large')
        return data, response.url

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.items=[]; self.href=None; self.label=[]
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.href=dict(attrs).get('href'); self.label=[]
    def handle_data(self, data):
        if self.href: self.label.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.items.append((''.join(self.label).strip(), self.href)); self.href=None

def discover(html, base=INDEX_URL):
    parser=Links(); parser.feed(html)
    candidates=[official_url(urljoin(base, u)) for label,u in parser.items if label.strip()=='短期予報解説資料']
    if len(set(candidates)) != 1: raise ValueError('jma_link_changed')
    related=[]
    for label,u in parser.items:
        if label in ['高層天気図','FAX天気図']:
            related.append({'name':label,'url':official_url(urljoin(base,u)), 'analyzed':False})
    return candidates[0], related

def inspect_pdf(data, source_url, fetched_at=None):
    if not data.startswith(b'%PDF-'): raise ValueError('not_pdf')
    reader=PdfReader(BytesIO(data))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 4: raise ValueError('unsupported_pdf')
    pages=[p.extract_text() or '' for p in reader.pages]
    first=unicodedata.normalize('NFKC',pages[0])
    header=re.sub(r'\s+','',first[:500])
    if '短期予報解説資料' not in header: raise ValueError('wrong_document')
    match=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})時(?:(\d{1,2})分)?発表',header)
    if not match: raise ValueError('issue_date_unreadable')
    parts=[int(x or 0) for x in match.groups()]
    issued=datetime(*parts,tzinfo=JST)
    fetched=fetched_at or now_jst()
    if issued > fetched+timedelta(minutes=15): raise ValueError('future_issue')
    sha=hashlib.sha256(data).hexdigest()
    edition='朝版（05時予報向け）' if issued.hour<12 else '夕方版（17時予報向け）'
    # Stop before the issuance year: removing whitespace otherwise joins 1 + 2026.
    title_match=re.search(r'短期予報解説資料\d*',header[:match.start()])
    meta={'name':title_match.group(), 'issued_at':issued.isoformat(), 'edition':edition,
          'source_url':official_url(source_url),'index_url':INDEX_URL,'fetched_at':fetched.isoformat(),
          'sha256':sha,'id':issued.strftime('%Y%m%dT%H%M')+'-'+sha[:12], 'pages':len(pages)}
    return meta,pages

def fetch_latest():
    html,base=download(INDEX_URL,2*1024*1024)
    url,related=discover(html.decode('utf-8'),base)
    data,actual_url=download(url,MAX_PDF)
    meta,pages=inspect_pdf(data,actual_url)
    meta['related']=related
    return meta,pages,data

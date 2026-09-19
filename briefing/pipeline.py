"""Durable prepare/reserve -> analyze -> build stages, also callable locally."""
import argparse
import base64
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from .schema import Report, validate_report
from .source import fetch_latest, now_jst

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
WORK=ROOT/'work'

def safe_error_code(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return 'http_' + str(int(exc.code))
    known = {'missing_api_key','response_too_large','secret_in_response',
             'incomplete_response','model_refusal','upper_levels','aviation_codes',
             'timeline_slots','timeline_date','missing_evidence','unmatched_evidence'}
    if type(exc) is ValueError and exc.args and exc.args[0] in known:
        return exc.args[0]
    if isinstance(exc, TimeoutError): return 'timeout'
    return 'response_validation_or_processing_error'

def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def status(code, **fields):
    write_json(DATA/'status.json', {'checked_at':now_jst().isoformat(),'code':code,**fields})

def reserve(state, meta, retry=False, limit=70, now=None):
    now=now or now_jst()
    sha=meta['sha256']
    old=state['documents'].get(sha)
    if old and old['status']=='complete': return False,'unchanged'
    if old and not retry: return False,'retry_required'
    if old and len(old['attempts'])>=2: return False,'attempt_limit'
    month=now.strftime('%Y-%m')
    if state['monthly_requests'].get(month,0)>=limit: return False,'budget_limit'
    item=old or {'id':meta['id'],'attempts':[]}
    item.update(status='reserved',issued_at=meta['issued_at'])
    item['attempts'].append({'reserved_at':now.isoformat(),'status':'reserved'})
    state['documents'][sha]=item
    state['monthly_requests'][month]=state['monthly_requests'].get(month,0)+1
    return True,'reserved'

def prepare(retry=False, fetcher=fetch_latest):
    WORK.mkdir(exist_ok=True)
    pending=WORK/'pending.json'
    if pending.exists(): pending.unlink()
    meta,pages,pdf=fetcher()
    write_json(DATA/'latest_source.json',meta)
    state=read_json(DATA/'state.json',{'version':1,'documents':{},'monthly_requests':{}})
    # Refuse a rollback; an older cache cannot overwrite the active source or report.
    latest=max((x['issued_at'] for x in state['documents'].values()),default='')
    if latest and meta['issued_at']<latest:
        status('source_rollback',source=meta); return False
    docdir=DATA/'documents'/meta['id']; docdir.mkdir(parents=True,exist_ok=True)
    (docdir/'source.pdf').write_bytes(pdf)
    write_json(docdir/'source.json',meta)
    write_json(docdir/'text.json',pages)
    if now_jst()-datetime.fromisoformat(meta['issued_at'])>timedelta(hours=30):
        status('source_stale',source=meta); return False
    if not os.environ.get('OPENAI_API_KEY'):
        status('needs_api_key',source=meta); return False
    model=os.environ.get('OPENAI_MODEL','gpt-4.1-mini')
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,100}',model): raise ValueError('invalid_model')
    allowed,code=reserve(state,meta,retry,int(os.environ.get('MAX_MONTHLY_REQUESTS','70')))
    if allowed:
        write_json(DATA/'state.json',state)
        write_json(pending,{'id':meta['id'],'sha256':meta['sha256'],'model':model})
    status(code,source=meta)
    print('Source checked. '+code)
    return allowed

def api_request(meta,pdf,pages,model):
    key=os.environ.get('OPENAI_API_KEY')
    if not key: raise ValueError('missing_api_key')
    prompt=(ROOT/'briefing'/'prompt.txt').read_text(encoding='utf-8')
    context={'source':meta,'extracted_pages':pages}
    payload={'model':model,'store':False,'max_output_tokens':int(os.environ.get('MAX_OUTPUT_TOKENS','12000')),
             'instructions':prompt,
             'input':[{'role':'user','content':[
                 {'type':'input_text','text':json.dumps(context,ensure_ascii=False)},
                 {'type':'input_file','filename':'short-range-forecast.pdf','detail':'high',
                  'file_data':'data:application/pdf;base64,'+base64.b64encode(pdf).decode('ascii')}
             ]}],
             'text':{'format':{'type':'json_schema','name':'aviation_weather_briefing',
                               'strict':True,'schema':Report.model_json_schema()}}}
    request=urllib.request.Request('https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode(),method='POST',
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    # No implicit retry: an ambiguous timeout may already have been billed.
    # A durable reservation is committed before this function runs in Actions.
    with urllib.request.urlopen(request,timeout=240) as response:
        raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024: raise ValueError('response_too_large')
        if key.encode() in raw: raise ValueError('secret_in_response')
        result=json.loads(raw)
    usage=result.get('usage') or {}
    write_json(DATA/'diagnostics'/(meta['id']+'.json'), {
        'usage':{k:int(usage.get(k,0)) for k in ['input_tokens','output_tokens','total_tokens']},
        'completed':result.get('status')=='completed',
        'output_limit_reached':(result.get('incomplete_details') or {}).get('reason')=='max_output_tokens'})
    if result.get('status')!='completed': raise ValueError('incomplete_response')
    parts=[]
    for item in result.get('output',[]):
        if item.get('type')=='message':
            for part in item.get('content',[]):
                if part.get('type')=='refusal': raise ValueError('model_refusal')
                if part.get('type')=='output_text': parts.append(part['text'])
    report=validate_report(json.loads(''.join(parts)),pages,meta['issued_at'])
    usage=result.get('usage') or {}
    return report.model_dump(),{k:int(usage.get(k,0)) for k in ['input_tokens','output_tokens','total_tokens']}

def analyze(requester=api_request):
    pending=read_json(WORK/'pending.json')
    if not pending:
        print('No new analysis queued.'); return
    state=read_json(DATA/'state.json')
    item=state['documents'][pending['sha256']]
    if item['status']!='reserved': raise ValueError('reservation_not_pending')
    docdir=DATA/'documents'/pending['id']
    meta=read_json(docdir/'source.json'); pages=read_json(docdir/'text.json')
    try:
        report,usage=requester(meta,(docdir/'source.pdf').read_bytes(),pages,pending['model'])
        # Validate again at the boundary; test doubles cannot bypass validation.
        report=validate_report(report,pages,meta['issued_at']).model_dump()
        record={'source':meta,'generated_at':now_jst().isoformat(),'model':pending['model'],
                'usage':usage,'report':report,'demo':False,'prompt_version':'1.0'}
        write_json(DATA/'reports'/(meta['id']+'.json'),record)
        item['status']='complete'; item['attempts'][-1]['status']='complete'
        status('ok',source=meta)
    except Exception as exc:
        # Never print exception strings or HTTP bodies: they can contain secrets.
        code=safe_error_code(exc)
        print('Analysis diagnostic: '+code, file=sys.stderr)
        item['status']='failed'; item['attempts'][-1]['status']='failed'
        status('analysis_failed',source=meta,diagnostic=code)
        raise RuntimeError('analysis_failed') from None
    finally:
        write_json(DATA/'state.json',state)
        (WORK/'pending.json').unlink(missing_ok=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['prepare','analyze','build','fetch-only'])
    parser.add_argument('--retry',action='store_true')
    args=parser.parse_args()
    try:
        if args.stage=='prepare': prepare(args.retry)
        elif args.stage=='fetch-only':
            # Explicitly never calls OpenAI or consumes the request ledger.
            meta,pages,pdf=fetch_latest()
            d=DATA/'documents'/meta['id']; d.mkdir(parents=True,exist_ok=True)
            (d/'source.pdf').write_bytes(pdf)
            write_json(d/'source.json',meta); write_json(d/'text.json',pages)
            write_json(DATA/'latest_source.json',meta); status('not_analyzed',source=meta)
            print('Official PDF fetched and dated: '+meta['issued_at'])
        elif args.stage=='analyze': analyze()
        else:
            from .render import build
            build()
    except Exception:
        if args.stage in ['prepare','fetch-only']: status('fetch_failed')
        print('Processing failed ('+args.stage+'). Details are suppressed to protect secrets.',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__': main()

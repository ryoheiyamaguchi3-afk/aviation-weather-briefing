"""Static, escaped HTML. Only allowlisted public files enter site/."""
from datetime import datetime
from html import escape
from pathlib import Path
import json
import shutil
import pypdfium2 as pdfium
from .pipeline import ROOT, DATA, read_json, write_json
from .demo import demo_record
from .schema import Report, validate_report
from .source import official_url

SITE=ROOT/'site'
STATUS_TEXT={
    'ok':'解析済み', 'unchanged':'同じ資料を確認・再解析なし', 'reserved':'解析準備中',
    'needs_api_key':'OpenAI API未設定・未解析', 'not_analyzed':'原資料を取得済み・AI解析は未実行',
    'analysis_failed':'解析に失敗・直近の正常なレポートを保持', 'retry_required':'前回処理が未完了・手動再試行が必要',
    'source_stale':'配信資料が古いため解析を停止', 'source_rollback':'古い版の取得を検知',
    'budget_limit':'月間の解析回数上限に到達', 'attempt_limit':'この資料の再試行上限に到達',
    'fetch_failed':'気象庁資料の取得に失敗・直近のデータを保持'}

def e(value): return escape(str(value),quote=True)
def datefmt(value):
    return datetime.fromisoformat(value).strftime('%Y.%m.%d %H:%M JST') if value else '—'

def claim(c):
    labels={'資料記載':'fact','気象学的解釈':'interpret','追加資料確認推奨':'check'}
    kind=labels[c['label']]
    evidence=''
    if c['evidence']:
        quotes=''.join(f'<blockquote><small>原資料 p.{x["page"]}</small><p>{e(x["quote"])}</p></blockquote>' for x in c['evidence'])
        evidence=f'<details class="evidence"><summary>根拠を読む</summary>{quotes}</details>'
    return f'<div class="claim"><span class="badge {kind}">{e(c["label"])}</span><p>{e(c["text"])}</p>{evidence}</div>'

def section(id, num, title, body, subtitle=''):
    return f'<section id="{id}" class="section"><div class="section-head"><span class="section-number">{num}</span><div><h2>{title}</h2><p>{subtitle}</p></div></div>{body}</section>'

def topics(items):
    result=[]
    for t in items:
        rows=''.join(f'<div class="topic-row"><b>{label}</b>{claim(t[key])}</div>' for key,label in [('what','WHAT'),('why','WHY'),('where','WHERE'),('when','WHEN')])
        result.append(f'<article class="topic-card"><h3>{e(t["title"])}</h3>{rows}<div class="focus"><span>天気図のどこを見る？</span>{claim(t["chart_focus"])}</div></article>')
    return '<div class="topic-grid">'+''.join(result)+'</div>'

def report_body(r):
    summary='<ol class="summary-list">'+''.join(f'<li>{claim(c)}</li>' for c in r['summary'])+'</ol>'
    summary+='<aside class="key-phenomenon"><span class="eyebrow">TODAY’S FOCUS</span><h3>今日一番注目すべき現象</h3>'+claim(r['key_phenomenon'])+'</aside>'
    html=section('overview','01','30秒でわかる今日の気象',summary,'まず全体像をつかみ、根拠へ。')
    html+=section('synoptic','02','総観場',topics(r['synoptic']),'位置 → 移動 → 天気への影響')
    levels=''.join(f'<article class="level"><h3>{e(x["level"])}</h3><div>{claim(x["analysis"])}<div class="connection"><span>地上とのつながり</span>{claim(x["vertical_connection"])}</div></div></article>' for x in r['upper_air'])
    html+=section('upper','03','上空から、立体的に読む',f'<div class="levels">{levels}</div>','上空の場・鉛直運動・下層の暖湿気・地上現象')
    html+=section('phenomena','04','今日の重要現象',topics(r['phenomena']))
    html+=section('rain','05','降水・対流','<div class="paper">'+''.join(claim(x) for x in r['precipitation'])+'</div>','なぜ、その場所で雨雲が強まるのか。')
    hazards=[]
    for x in r['aviation']:
        hazards.append(f'<details class="hazard"><summary><strong>{e(x["code"])}</strong><span class="hazard-label">{e(x["assessment"]["label"])}</span><span class="plus">＋</span></summary><div>{claim(x["assessment"])}{claim(x["region_time"])}<p class="required"><b>追加確認</b> {e(x["additional_checks"])}</p></div></details>')
    html+=section('aviation','06','✈ AVIATION WEATHER','<p class="section-note">学習上の着目点です。未記載は「現象なし」を意味しません。</p><div class="hazards">'+''.join(hazards)+'</div>','運航判断に必要な追加資料を、切り分ける。')
    timeline=''.join(f'<li><div class="time-label"><small>{e(x["date_jst"])}</small><h3>{e(x["slot"])}</h3></div>{claim(x["outlook"])}</li>' for x in r['timeline'])
    html+=section('timeline','07','一日の変化を追う','<ol class="timeline">'+timeline+'</ol>','発表日から翌朝まで。情報がない時間帯は補完しません。')
    lessons=[]
    for x in r['why_lessons']:
        chain='<ol class="causal-chain">'+''.join('<li>'+claim(c)+'</li>' for c in x['chain'])+'</ol>'
        lessons.append(f'<article class="lesson"><span class="eyebrow">ASK WHY</span><h3>{e(x["question"])}</h3>{chain}<div class="focus"><span>天気図と照らし合わせる</span>{claim(x["chart_focus"])}</div><p class="caveat">{e(x["caveat"])}</p></article>')
    html+=section('why','08','今日の「なぜ？」',''.join(lessons),'点で覚えず、因果関係でつなぐ。')
    html+=section('limits','09','この解説の限界','<ul class="limitations">'+''.join('<li>'+e(x)+'</li>' for x in r['limitations'])+'</ul>')
    return html

def copy_source(meta):
    ident=meta['id']
    source=DATA/'documents'/ident/'source.pdf'
    if not source.exists(): return []
    target=SITE/'sources'/ident; target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target/'source.pdf')
    result=[]
    with pdfium.PdfDocument(source) as doc:
        for i in range(len(doc)):
            page=doc[i]
            scale=min(2.8,1800/page.get_width())
            bitmap=page.render(scale=scale)
            im=bitmap.to_pil(); path=target/f'page-{i+1}.jpg'; im.save(path,quality=88)
            im.close(); bitmap.close(); page.close()
            result.append(f'sources/{ident}/page-{i+1}.jpg')
    return result

def source_panel(meta,images,demo=False):
    if not meta: return '<div class="paper"><p>まだ資料を取得していません。</p></div>'
    if demo:
        from .demo import DEMO_TEXT
        return '<div class="paper"><h3>架空資料の本文</h3><p>'+e(DEMO_TEXT)+'</p><p>画面の動作確認用です。気象庁の実資料ではありません。</p></div>'
    url=official_url(meta['source_url'])
    body=f'<p class="source-credit">出典：気象庁「{e(meta["name"])}」。AIによる解説は当アプリが作成し、気象庁の公式見解ではありません。</p>'
    body+=f'<div class="source-meta"><span>発表 {e(datefmt(meta["issued_at"]))}</span><span>取得 {e(datefmt(meta["fetched_at"]))}</span></div>'
    if images:
        body+='<div class="source-images">'+''.join(f'<button class="chart-open" data-src="{e(path)}" aria-label="原資料の{i+1}ページを拡大"><img src="{e(path)}" alt="短期予報解説資料 {i+1}ページ" loading="lazy"><span>p.{i+1} ↗ 拡大して読む</span></button>' for i,path in enumerate(images))+'</div>'
        body+=f'<a class="button secondary" href="sources/{e(meta["id"])}/source.pdf" target="_blank" rel="noopener">この版のPDFを開く ↗</a> '
    body+=f'<a class="text-link" href="{e(url)}" target="_blank" rel="noopener">気象庁の最新PDF ↗</a><p class="muted">最新PDFのURLは更新されるため、このレポートの原資料と内容が異なる場合があります。</p>'
    related=meta.get('related',[])
    if related:
        body+='<h3>関連する公式資料</h3><p class="muted">Phase 1ではリンクの案内のみ。生成時に取得・解析していません。</p><div class="related">'+''.join(f'<a href="{e(official_url(x["url"]))}" target="_blank" rel="noopener">{e(x["name"])} ↗</a>' for x in related)+'</div>'
    body+=f'<details class="evidence"><summary>取得元・資料識別情報</summary><p>取得元：<a href="{e(url)}">{e(url)}</a></p><p>SHA-256: <code>{e(meta["sha256"])}</code></p></details>'
    return body

def document(record,state,history,images,archive=False):
    demo=bool(record and record.get('demo'))
    meta=record['source'] if record else state.get('source')
    issued=meta.get('issued_at','') if meta else ''
    report=record.get('report') if record else None
    heading=report['headline'] if report else '空の変化を、理由から理解する。'
    badge='表示デモ・実際の予報ではありません' if demo else STATUS_TEXT.get(state.get('code'),'取得待ち')
    if archive and not demo: badge='保存された過去のレポート'
    demo_notice='<div class="demo-banner" role="note">DEMO ／ 架空の学習例です。最新の天気でも、OpenAI APIで生成した結果でもありません。</div>' if demo else ''
    report_notice=''
    latest=state.get('source')
    if not demo and not archive and record and latest and latest['id'] != meta['id']:
        report_notice='<p class="alert">別の版を取得しましたが解析は未完了です。下記は直近の解析済み資料です。資料の発表日時を確認してください。</p>'
    options='<option value="index.html">最新の状態</option><option value="demo.html"'+(' selected' if demo else '')+'>画面サンプル（架空）</option>'
    for x in history:
        selected=' selected' if archive and record and record['source']['id']==x['source']['id'] else ''
        options+=f'<option value="{e(x["source"]["id"])}.html"{selected}>{e(datefmt(x["source"]["issued_at"]))} · {e(x["source"]["edition"])}</option>'
    if report: content=report_body(report)
    else:
        content=section('overview','01','ブリーフィングは未生成です',
          '<div class="empty"><span class="empty-icon">↗</span><h3>原資料から、次の学びへ。</h3><p>気象庁PDFの取得とAI解析は別の処理です。解析済みレポートがないため、気象の要約や航空への影響はまだ表示していません。</p><p>下の原資料を読むか、画面サンプルで構成を確認できます。</p><a class="button" href="demo.html">画面サンプルを見る →</a></div>')
    content+=section('source','SOURCE','原資料と照らし合わせる',source_panel(meta,images,demo))
    nav=[('overview','概要'),('synoptic','総観場'),('upper','上空'),('aviation','航空'),('timeline','時系列'),('why','なぜ？'),('source','原資料')] if report else [('overview','概要'),('source','原資料')]
    generated=datefmt(record.get('generated_at')) if record else '未生成'
    model=record.get('model','未使用') if record else '未使用'
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<meta name="description" content="気象庁の短期予報解説資料を、理由・天気図・航空気象の着目点につなげる学習用ブリーフィング。">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex,nofollow">
<title>{'デモ | ' if demo else ''}航空気象デイリーブリーフィング</title><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="style.css"><script src="app.js" defer></script></head>
<body data-issued="{e(issued)}" data-demo="{str(demo).lower()}" data-checked="{e(state.get('checked_at',''))}" data-archive="{str(archive).lower()}">
<a class="skip" href="#main">本文へ移動</a>{demo_notice}
<header class="header"><a class="brand" href="index.html"><span class="brand-icon">↗</span><span>AVIATION WEATHER<small>航空気象デイリーブリーフィング</small></span></a><span class="header-note">日々の空を、学びに。</span></header>
<main id="main"><div class="topline"><span class="eyebrow">DAILY WEATHER BRIEFING</span><label class="edition-select">資料を選ぶ<select id="edition-select">{options}</select></label></div>
<div class="hero"><div><p class="edition">{e(meta['edition'] if meta else '取得待ち')} <span>／ {e(datefmt(issued))}</span></p><h1>{e(heading)}</h1><p class="hero-sub">何が起きるか。なぜ起きるか。<br class="mobile-break">天気図と、航空の視点でつなぐ。</p></div><div class="hero-mark" aria-hidden="true"><span>WX</span><i>READ THE SKY</i></div></div>
<div class="statusbar"><span class="status-dot"></span><strong>{e(badge)}</strong><span>確認 {e(datefmt(state.get('checked_at')))}</span></div>{report_notice}<p id="freshness" class="alert" hidden></p>
<div class="learning-note"><b>学習補助専用</b><span>実際の運航判断・公式ブリーフィングの代替にはできません。最新の公式航空気象情報を確認してください。</span></div>
<nav class="section-nav" aria-label="レポート内の目次">{''.join(f'<a href="#{a}">{b}</a>' for a,b in nav)}</nav>
<div class="legend"><span class="badge fact">資料記載</span><span>原文の事実</span><span class="badge interpret">気象学的解釈</span><span>条件付きの説明</span><span class="badge check">追加資料確認推奨</span><span>まだ判断できないこと</span></div>
{content}
<footer><b>航空気象デイリーブリーフィング</b><p>AIの解説には誤りが含まれる可能性があります。原資料と照合しながら学習してください。</p><p>生成 {e(generated)} ／ モデル {e(model)}</p><p>資料記載の引用は抽出テキストとの一致を検証しています。解釈の正しさを保証する検証ではありません。</p></footer></main>
<dialog id="chart-dialog" aria-label="原資料の拡大表示"><div class="dialog-toolbar"><strong>原資料</strong><div><button id="zoom-out" aria-label="縮小">−</button><button id="zoom-reset">リセット</button><button id="zoom-in" aria-label="拡大">＋</button><button id="chart-close">閉じる ×</button></div></div><div class="chart-viewport"><img id="chart-image" alt="原資料の拡大画像"></div></dialog>
</body></html>'''

def build():
    SITE.mkdir(exist_ok=True)
    for name in ['style.css','app.js','favicon.svg']:
        shutil.copyfile(ROOT/'web'/name,SITE/name)
    (SITE/'.nojekyll').write_text('',encoding='utf-8')
    state=read_json(DATA/'status.json',{'code':'waiting'})
    if not state.get('source'):
        state['source']=read_json(DATA/'latest_source.json')
    records=[]
    for path in (DATA/'reports').glob('*.json'):
        rec=read_json(path)
        if rec.get('demo'): continue
        pages=read_json(DATA/'documents'/rec['source']['id']/'text.json')
        validate_report(rec['report'],pages,rec['source']['issued_at'])
        records.append(rec)
    records.sort(key=lambda x:(x['source']['issued_at'],x['generated_at']),reverse=True)
    # Bounded published history; durable ledger remains intact.
    history=records[:60]
    latest=history[0] if history else None
    meta=latest['source'] if latest else state.get('source')
    images=copy_source(meta) if meta else []
    (SITE/'index.html').write_text(document(latest,state,history,images),encoding='utf-8')
    for rec in history:
        imgs=images if latest is rec else copy_source(rec['source'])
        (SITE/(rec['source']['id']+'.html')).write_text(document(rec,state,history,imgs,archive=True),encoding='utf-8')
        write_json(SITE/'reports'/(rec['source']['id']+'.json'),rec)
    write_json(SITE/'status.json',state)
    demo=demo_record()
    (SITE/'demo.html').write_text(document(demo,{'code':'demo'},history,[],archive=True),encoding='utf-8')
    from .security import audit_public
    audit_public(SITE)
    print(f'Static site built: {len(history)} validated reports; fictional demo is separate.')

"""Clearly fictional layout fixture. Never a current weather report."""
from .schema import HAZARDS, SLOTS

DEMO_TEXT='前線が本州付近に停滞。前線に向かって暖かく湿った空気が流れ込む。'

def demo_record():
    def c(text,label='気象学的解釈',quote=None):
        return {'text':text,'label':label,'evidence':[{'page':1,'quote':quote}] if quote else []}
    unknown=lambda t:c(t,'追加資料確認推奨')
    fact=c('前線付近への暖湿気の流入に注目。','資料記載',DEMO_TEXT)
    def topic(title,what,why,where):
        return {'title':title,'what':c(what),'why':c(why),'where':c(where),
                'when':unknown('時間帯別の変化は、この架空資料だけでは判断できません。'),
                'chart_focus':unknown('地上天気図で前線位置を確認し、850hPaの風向と湿潤域を重ねて読みます。')}
    frontal=topic('前線と暖湿気の関係','前線付近では雲や降水が生じる可能性があります。',
                 '暖湿気の流入に収束や上昇が重なると、水蒸気が凝結しやすくなります。',
                 '前線近傍が着目域。ただし雨域の位置は前線線上と一致するとは限りません。')
    convection=topic('雨雲が強まる条件','対流の発達条件を順に確かめます。',
                    '水蒸気だけでなく、不安定度、持ち上げる仕組み、抑制の強さが関係します。',
                    '下層の収束域や風上側の斜面が候補。今日の発生場所を示すものではありません。')
    wind=topic('風の変化を読む','前線の両側で風向・風速が変わる可能性があります。',
               '異なる気団の境界と気圧場の変化が、地上付近の風に関わります。',
               '空港の風は地形と局地循環も関係するため、総観場だけで決められません。')
    checks={
        'TS':'雷監視・レーダー・METAR/SPECI・TAF・SIGMET', 'CB':'衛星・レーダー・SIGMET・航空気象図',
        'TURB':'SIGMET・乱気流予想図・鉛直風分布', 'ICE':'着氷予想図・凍結高度・雲水と温度の鉛直分布',
        'WIND':'METAR/SPECI・TAF・地上天気図', 'CROSSWIND':'滑走路方位・METAR/SPECI・TAFの風向風速',
        'LLWS':'低層ウィンドシア情報・下層風の鉛直分布', 'VIS':'METAR/SPECI・TAF',
        'CEILING':'METAR/SPECI・TAF・雲底情報', 'FRONT':'地上天気図・レーダー・風と気温の時系列',
        'HEAVY RAIN':'降水短時間予報・レーダー・警報', 'SNOW':'地上気温・湿球温度・降雪予報',
        'MOUNTAIN WAVE':'山越え風と安定度の鉛直分布・SIGMET', 'JET STREAM':'高層天気図・航空気象図・SIGMET'}
    report={
        'headline':'前線・暖湿気・上昇流を、ひとつの流れで読む。',
        'summary':[fact,c('暖湿気は材料。雨雲を強めるには持ち上げる仕組みも必要です。'),
                   unknown('上空のトラフの位置と移動は、高層天気図の追加確認が必要です。'),
                   unknown('空港別の雷・視程・雲底は、この資料だけでは判断できません。')],
        'key_phenomenon':c('暖湿気が流れ込む場所と、上昇が重なる場所。'),
        'synoptic':[frontal],
        'upper_air':[
            {'level':'500hPa','analysis':unknown('この架空資料には解析がありません。トラフ、寒気、移流の分布を追加確認します。'),
             'vertical_connection':c('上空の力学的な上昇の場と、下層の水蒸気の分布が重なるかが学習の着目点です。')},
            {'level':'700hPa','analysis':unknown('湿潤域や鉛直流の資料が必要です。上昇域の位置を断定できません。'),
             'vertical_connection':c('中層の湿潤度は雲の発達や乾燥空気の混入を考える材料になります。')},
            {'level':'850hPa','analysis':unknown('暖湿気流入は記載されていますが、850hPaの具体的な風・温度・水蒸気量は不明です。'),
             'vertical_connection':c('下層からの水蒸気供給と収束を確認し、地上の雨域との対応を考えます。')}],
        'phenomena':[frontal,convection,wind],
        'precipitation':[c('暖湿気が同じ場所に流れ込み続け、収束や地形による上昇も続くと、降水が持続する可能性があります。'),
                         unknown('TS・CBの発生や雨量は、不安定度・レーダー・雷監視などで追加確認します。')],
        'aviation':[{'code':code,'assessment':unknown('この資料だけでは発生・強度・空港別の影響を判断できません。'),
                     'region_time':unknown('場所と時間の特定には追加資料が必要です。'),
                     'additional_checks':checks[code]} for code in HAZARDS],
        'timeline':[{'slot':s,'date_jst':'2026-01-02' if i==4 else '2026-01-01',
                     'outlook':unknown('時刻を特定する情報がないため、この時間帯の変化は判断できません。')} for i,s in enumerate(SLOTS)],
        'why_lessons':[{'question':'なぜ、暖湿気だけでは大雨と言い切れない？',
                        'chain':[fact,c('収束・前線・地形などによる持ち上げ'),c('冷却・凝結による雲の形成'),
                                 c('不安定度や持続性などの条件がそろうと降水が発達')],
                        'chart_focus':unknown('850hPaの風と湿潤域、地上の前線、レーダーの雨域を比べます。'),
                        'caveat':'これは条件を整理する概念図です。実際の降水量・雷の有無を予測するものではありません。'}],
        'limitations':['表示確認用の架空の学習例です。実在の日の予報でもOpenAI APIの生成結果でもありません。',
                       '関連天気図は未取得・未解析です。']}
    return {'demo':True,'source':{'id':'demo','name':'架空の学習資料（表示例）','issued_at':'2026-01-01T03:40:00+09:00',
            'edition':'朝版の表示例','fetched_at':None,'source_url':'https://www.jma.go.jp/jma/kishou/know/expert/',
            'sha256':'','pages':1,'related':[]},'generated_at':None,'model':'デモ（API未使用）','usage':{},'report':report}

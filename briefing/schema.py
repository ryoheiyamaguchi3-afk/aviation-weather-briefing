"""Strict output schema and local, evidence-aware validation."""
from datetime import datetime, timedelta
from typing import Literal
import re
import unicodedata
from pydantic import BaseModel, ConfigDict, Field

LABELS = ['資料記載', '気象学的解釈', '追加資料確認推奨']
HAZARDS = ['TS', 'CB', 'TURB', 'ICE', 'WIND', 'CROSSWIND', 'LLWS', 'VIS',
           'CEILING', 'FRONT', 'HEAVY RAIN', 'SNOW', 'MOUNTAIN WAVE', 'JET STREAM']
SLOTS = ['朝', '昼', '夕方', '夜', '翌朝']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Strict):
    page: int = Field(ge=1, le=4)
    quote: str = Field(min_length=6, max_length=160)

class Claim(Strict):
    text: str = Field(min_length=1, max_length=700)
    label: Literal['資料記載', '気象学的解釈', '追加資料確認推奨']
    evidence: list[Evidence] = Field(max_length=3)

class Topic(Strict):
    title: str = Field(min_length=1, max_length=80)
    what: Claim
    why: Claim
    where: Claim
    when: Claim
    chart_focus: Claim

class Level(Strict):
    level: Literal['500hPa', '700hPa', '850hPa']
    analysis: Claim
    vertical_connection: Claim

class Aviation(Strict):
    code: Literal['TS','CB','TURB','ICE','WIND','CROSSWIND','LLWS','VIS','CEILING',
                  'FRONT','HEAVY RAIN','SNOW','MOUNTAIN WAVE','JET STREAM']
    assessment: Claim
    region_time: Claim
    additional_checks: str = Field(min_length=1, max_length=350)

class TimeSlot(Strict):
    slot: Literal['朝','昼','夕方','夜','翌朝']
    date_jst: str
    outlook: Claim

class Lesson(Strict):
    question: str = Field(min_length=1, max_length=120)
    chain: list[Claim] = Field(min_length=3, max_length=6)
    chart_focus: Claim
    caveat: str = Field(min_length=1, max_length=400)

class Report(Strict):
    headline: str = Field(min_length=1, max_length=100)
    summary: list[Claim] = Field(min_length=3, max_length=5)
    key_phenomenon: Claim
    synoptic: list[Topic] = Field(min_length=1, max_length=5)
    upper_air: list[Level] = Field(min_length=3, max_length=3)
    phenomena: list[Topic] = Field(min_length=3, max_length=5)
    precipitation: list[Claim] = Field(min_length=1, max_length=4)
    aviation: list[Aviation] = Field(min_length=14, max_length=14)
    timeline: list[TimeSlot] = Field(min_length=5, max_length=5)
    why_lessons: list[Lesson] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(min_length=1, max_length=8)

def normalize(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))

def validate_report(payload, pages, issued_at):
    report = Report.model_validate(payload)
    if [x.level for x in report.upper_air] != ['500hPa','700hPa','850hPa']:
        raise ValueError('upper_levels')
    if {x.code for x in report.aviation} != set(HAZARDS):
        raise ValueError('aviation_codes')
    if [x.slot for x in report.timeline] != SLOTS:
        raise ValueError('timeline_slots')
    day = datetime.fromisoformat(issued_at).date()
    for i, slot in enumerate(report.timeline):
        if slot.date_jst != (day + timedelta(days=i == 4)).isoformat():
            raise ValueError('timeline_date')
    def walk(node):
        if isinstance(node, dict):
            if {'text','label','evidence'} <= node.keys():
                if node['label'] == '資料記載' and not node['evidence']:
                    raise ValueError('missing_evidence')
                for e in node['evidence']:
                    if e['page'] > len(pages) or normalize(e['quote']) not in normalize(pages[e['page']-1]):
                        raise ValueError('unmatched_evidence')
            for value in node.values(): walk(value)
        elif isinstance(node, list):
            for value in node: walk(value)
    walk(report.model_dump())
    # Evidence occurrence can be checked; entailment / meteorological truth cannot be proved mechanically.
    return report

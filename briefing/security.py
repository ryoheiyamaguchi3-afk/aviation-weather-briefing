"""Fail publication if an unexpected file or a recognizable secret enters the artifact."""
import os
from pathlib import Path
import re

ROOT_FILES={'index.html','demo.html','style.css','app.js','favicon.svg','status.json','.nojekyll'}
DOC=r'\d{8}T\d{4}-[a-f0-9]{12}'

def audit_public(directory):
    key=os.environ.get('OPENAI_API_KEY','')
    for path in Path(directory).rglob('*'):
        if not path.is_file(): continue
        name=path.relative_to(directory).as_posix()
        allowed=(name in ROOT_FILES or re.fullmatch(DOC+r'\.html',name)
                 or re.fullmatch(r'reports/'+DOC+r'\.json',name)
                 or re.fullmatch(r'sources/'+DOC+r'/(source\.pdf|page-[1-4]\.jpg)',name))
        if not allowed: raise ValueError('unexpected_public_file')
        raw=path.read_bytes()
        if key and key.encode() in raw: raise ValueError('secret_in_artifact')
        if path.suffix in {'.html','.js','.css','.json','.svg'}:
            if re.search(rb'sk-(?:proj-)?[A-Za-z0-9_-]{20,}',raw): raise ValueError('key_pattern_in_artifact')
            if b'-----BEGIN PRIVATE KEY-----' in raw: raise ValueError('private_key_in_artifact')

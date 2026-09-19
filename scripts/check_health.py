import json
from pathlib import Path
import sys
p=Path('data/status.json')
code=json.loads(p.read_text(encoding='utf-8')).get('code') if p.exists() else 'no_status'
ok=code in ['ok','unchanged']
print('Pipeline health: '+str(code))
sys.exit(0 if ok else 1)

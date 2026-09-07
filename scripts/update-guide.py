#!/usr/bin/env python3
"""Refresh the public explorer's embedded skill instructions from shared source."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
path = ROOT / 'docs/proposals/workcell-next.html'
text = path.read_text()
start = text.index('const skills=') + len('const skills=')
end = text.index(';\nfunction showSkill', start)
skills = json.loads(text[start:end])
for skill in skills:
    source = (ROOT / 'skills' / skill['name'] / 'SKILL.md').read_text()
    skill['instructions'] = source.split('---', 2)[2].strip()
updated = text[:start] + json.dumps(skills, ensure_ascii=False).replace('<', '\\u003c') + text[end:]
if args.check:
    if updated != text:
        parser.exit(1, 'Embedded skill instructions are stale; run scripts/update-guide.py\n')
else:
    path.write_text(updated)

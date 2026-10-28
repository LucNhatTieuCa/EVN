"""Validate the shareable tree without importing Home Assistant or contacting EVN."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from html.parser import HTMLParser

parser=argparse.ArgumentParser();parser.add_argument('--preparation',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1];component=root/'custom_components/npc';errors=[];pending=[]
for path in component.rglob('*.py'):
    try:ast.parse(path.read_text(),filename=str(path))
    except SyntaxError as error:errors.append(str(error))
for path in root.rglob('*.json'):
    if '__pycache__' not in path.parts:
        try:json.loads(path.read_text())
        except ValueError:errors.append('Invalid JSON: '+str(path.relative_to(root)))
for path in (component/'webui/assets/js').glob('*.js'):
    result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True)
    if result.returncode:errors.append(result.stderr)
for path in root.rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts:continue
    if path.suffix in {'.db','.pdf','.fernet'} or path.name in {'credentials.json','secrets.yaml','hassTokens'}:errors.append('Private artifact: '+str(path.relative_to(root)))
    if path.suffix in {'.py','.json','.html','.js','.md','.yml'} and 'vendor' not in path.parts:
        text=path.read_text()
        if re.search(r'PC02KK\d+|haos\.hongan\.io\.vn|192\.168\.\d+\.\d+|AIza[\w-]{25,}',text):errors.append('Site-specific data: '+str(path.relative_to(root)))
class LocalAssets(HTMLParser):
    def __init__(self,file):super().__init__();self.file=file
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key not in {'src','href'} or not value or value.startswith(('http','/','#','data:','blob:')):continue
            target=self.file.parent/value.split('?')[0]
            if not target.exists():errors.append('Missing local asset: '+str(target.relative_to(root)))
for file in (component/'webui').glob('*.html'):LocalAssets(file).feed(file.read_text())
manifest=json.loads((component/'manifest.json').read_text())
for key in ('documentation','issue_tracker'):
    if not manifest.get(key):pending.append('Set destination repository metadata: '+key)
result={'code_checks':'PASS' if not errors else 'FAIL','errors':errors,'publication_pending':pending,'strict_release_ready':not errors and not pending}
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(1 if errors or (pending and not args.preparation) else 0)

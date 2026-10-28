"""Set public repository metadata once the destination is chosen. Does not push."""
import argparse
import json
from pathlib import Path
import re

parser=argparse.ArgumentParser();parser.add_argument('repository',help='owner/repository');args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',args.repository):parser.error('Expected owner/repository')
root=Path(__file__).resolve().parents[1];path=root/'custom_components/evn/manifest.json'
data=json.loads(path.read_text());url='https://github.com/'+args.repository
data['documentation']=url+'#readme';data['issue_tracker']=url+'/issues';data['codeowners']=['@'+args.repository.split('/')[0]]
path.write_text(json.dumps(data,indent=2)+'\n')
print('Updated metadata only; no GitHub operation performed.')

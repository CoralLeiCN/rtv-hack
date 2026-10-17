"""Copy the VM provenance index into this checkout; run on the laptop."""
import argparse
from pathlib import Path
import collections, json, os, shlex, subprocess, tempfile
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--host", default="bc-iverson930g")
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "data/external-videos.json")
args = parser.parse_args()
remote = "from pathlib import Path; print((Path.home()/'data/ceda/external-videos.json').read_text(), end='')"
r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20',args.host,'python3 -c '+shlex.quote(remote)],capture_output=True,text=True,check=True)
index=json.loads(r.stdout)
p=args.output.expanduser()
p.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.external-videos-',dir=p.parent)
with os.fdopen(fd,'w') as f: f.write(json.dumps(index,indent=2)+'\n')
os.replace(tmp,p)
clips=[v for v in index['videos'] if v.get('source_video_id')]
print(json.dumps({'batch_status':index['ingest_batches'][0]['status'],'clip_states':dict(collections.Counter(c['ingestion']['status'] for c in clips)),'updated_at_utc':index['updated_at_utc']}))

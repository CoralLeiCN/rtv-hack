import argparse
argparse.ArgumentParser(description="CEDA batch status").parse_args()
import collections,json,os,urllib.parse,urllib.request
from pathlib import Path
base=os.environ['INGRESS_URL'].rstrip('/')
body=json.dumps({'username':os.environ['USERNAME'],'password':os.environ['PASSWORD']}).encode()
req=urllib.request.Request(base+'/api/v1/auth/login',data=body,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=40) as r: token=json.load(r)['access_token']
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token}),timeout=60) as r: return json.load(r)
get('/api/v1/auth/me')
d=get('/api/v1/dashboard/stats?scope=mine')
index=json.loads((Path.home()/'data/ceda/external-videos.json').read_text())
keys={v['ingestion'].get('object_key') for v in index['videos'] if v.get('source_video_id')}
recent=[]
for v in d.get('recent_videos',[]):
    if urllib.parse.unquote(urllib.parse.urlsplit(v.get('original_video','')).path).lstrip('/') in keys:
        recent.append({k:v.get(k) for k in ('filename','unique_segments','expected_segments','indexed_clips','segment_rows','duplicate_rows')})
print(json.dumps({'login':'ok','dashboard':'ok','overview':d.get('overview'),'quality':d.get('quality'),'pipeline_alignment':d.get('pipeline_alignment'),'s3_inventory':{key:d.get('s3_inventory',{}).get(key) for key in ('chunks_mp4','segments_mp4','segmenter_output_mp4')},'batch_recent':recent,'note':'Recent videos is a limited sample; pipeline totals may include other content.'}))

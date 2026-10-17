import argparse
argparse.ArgumentParser(description="CEDA batch verify_uploads").parse_args()
import json,os,sys,urllib.parse
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
from pathlib import Path
try:
 import boto3
 from botocore.config import Config
except ImportError:
 print('S3 SDK unavailable; no installation attempted.');sys.exit(0)
s3=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT'],aws_access_key_id=os.environ['ACCESS_KEY'],aws_secret_access_key=os.environ['SECRET_KEY'],verify=False,config=Config(retries={'max_attempts':0},signature_version='s3v4',connect_timeout=15,read_timeout=30,s3={'addressing_style':'path'}))
d=json.loads((Path.home()/'data/ceda/external-videos.json').read_text())
clips=[v for v in d['videos'] if v.get('source_video_id')]
rows=[]
for clip in clips:
 key=clip['ingestion']['object_key']
 try:
  head=s3.head_object(Bucket=os.environ['S3_CHUNKS_BUCKET'],Key=key)
  prefix='segments/'+Path(key).stem+'_segment_'
  count=sum(1 for page in s3.get_paginator('list_objects_v2').paginate(Bucket=os.environ['S3_SEGMENTS_BUCKET'],Prefix=prefix) for obj in page.get('Contents',[]) if obj['Key'].endswith('.mp4'))
  meta=head.get('Metadata',{})
  rows.append({'clip':clip['sequence'],'stored_bytes':head['ContentLength'],'size_matches':head['ContentLength']==clip['size_bytes'],'private_matches':meta.get('is-public','').lower()=='false','allowed_users_matches':meta.get('allowed-users','')==os.environ['USERNAME'],'prompt_matches':urllib.parse.unquote(meta.get('custom-prompt',''))==d['ingest_batches'][0]['settings']['custom_prompt'],'tags_match':set(meta.get('tags','').split(','))==set(d['ingest_batches'][0]['settings']['tags']),'capture_type_matches':meta.get('capture-type')=='general','location_matches':meta.get('location')==d['ingest_batches'][0]['settings']['location'],'original_filename_matches':meta.get('original-filename')==clip['filename'],'camera_id_omitted':not meta.get('camera-id'),'segment_objects':count,'last_modified':head['LastModified'].isoformat()})
 except Exception as e: rows.append({'clip':clip['sequence'],'error_type':type(e).__name__})
out={'checked_files':len(rows),'matching_files':{key:sum(r.get(key) is True for r in rows) for key in ('size_matches','private_matches','allowed_users_matches','prompt_matches','tags_match','capture_type_matches','location_matches','original_filename_matches','camera_id_omitted')},'clips_with_segments':sum(r.get('segment_objects',0)>0 for r in rows),'segment_objects':sum(r.get('segment_objects',0) for r in rows),'errors':[{'clip':r['clip'],'error_type':r['error_type']} for r in rows if 'error_type' in r]}
print(json.dumps(out))
(Path.home()/'data/ceda/ceda-upload-verification.json').write_text(json.dumps(out,indent=2)+'\n')

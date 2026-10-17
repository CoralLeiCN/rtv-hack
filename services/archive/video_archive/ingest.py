import hashlib
import json
import math
import os
import subprocess
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .models import embedding_identity


def run_media(args):
    # FFmpeg diagnostics can contain local paths. Caller reports a fixed error.
    return subprocess.run(args, check=True, capture_output=True, timeout=600).stdout


def duration(path):
    probe = json.loads(run_media(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=duration', '-of', 'json', str(path)]))
    if not probe.get('streams'):
        raise ValueError('Source contains no video stream')
    reported = probe['streams'][0].get('duration')
    if reported in (None, 'N/A'):
        # WebM and some other containers omit per-stream duration. Measure only
        # decoded video, never fall back to a potentially longer audio timeline.
        progress = run_media(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
                              '-map', '0:v:0', '-an', '-vf', 'setpts=PTS-STARTPTS',
                              '-fps_mode', 'passthrough', '-progress', 'pipe:1', '-stats_period', '600',
                              '-f', 'null', '-'])
        times = [float(line.split(b'=', 1)[1]) / 1_000_000 for line in progress.splitlines()
                 if line.startswith(b'out_time_us=') and not line.endswith(b'N/A')]
        value = max(times, default=0)
    else:
        value = float(reported)
    if not math.isfinite(value) or value <= 0 or value > 86400:
        raise ValueError('Unsupported video duration')
    return value


def validate_video(path):
    # A successful transcode can still produce an audio-only or empty MP4.
    frames = run_media(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
                        '-map', '0:v:0', '-frames:v', '1', '-f', 'framemd5', '-'])
    if not any(line.strip() and not line.startswith(b'#') for line in frames.splitlines()):
        raise ValueError('Segment contains no decodable video frames')


def intervals(seconds, length):
    return [(start, min(start + length, seconds)) for start in range(0, math.ceil(seconds), length)]


def enqueue(repo, store, settings, source, dataset_id, tags, segment_seconds=10, captions=None):
    if not dataset_id.strip() or len(dataset_id) > 200 or not 1 <= segment_seconds <= 60:
        raise ValueError('Provide a dataset ID and segment length from 1 to 60 seconds')
    if len(tags) > 32 or any(not tag.strip() or len(tag) > 100 for tag in tags):
        raise ValueError('Invalid tags')
    if captions is not None and (not isinstance(captions, list) or not captions or
            any(not isinstance(c, str) or not c.strip() or len(c) > 16000 for c in captions)):
        raise ValueError('Captions must be a nonempty list of nonblank strings')
    checksum, key = store.import_video(source)
    seconds = duration(store.path(key))
    if captions is not None and len(captions) != len(intervals(seconds, segment_seconds)):
        raise ValueError('Caption count must match the number of segments')
    options = {'dataset_id': dataset_id, 'tags': sorted(set(tags)), 'segment_seconds': segment_seconds,
               'duration': seconds, 'captions': captions, 'embedding_identity': embedding_identity(settings),
               'cosmos_model': settings.cosmos_model, 'cosmos_revision': settings.cosmos_revision,
               'pipeline_version': 2}
    video_id = uuid5(NAMESPACE_URL, checksum)
    config_hash = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
    job_id = uuid5(video_id, config_hash)
    return repo.enqueue(video_id, checksum, key, job_id, options)


def process_job(job, repo, store, index, embedder, captioner, settings):
    repo.assert_worker()
    attempt_id = uuid4()
    options = job['settings']
    if options['embedding_identity'] != embedding_identity(settings):
        raise ValueError('Queued embedding configuration differs from the active model')
    if options['captions'] is None and (options['cosmos_model'] != settings.cosmos_model or options['cosmos_revision'] != settings.cosmos_revision):
        raise ValueError('Queued Cosmos configuration differs from the active model')
    parent = repo.video(job['video_id'])
    source = store.path(parent['storage_key'])
    for number, (start, end) in enumerate(intervals(options['duration'], options['segment_seconds'])):
        repo.assert_worker()
        segment_id = uuid5(UUID(str(job['id'])), str(number))
        existing = repo.segment(segment_id)
        # An obsolete worker may finish an in-flight external write after losing
        # its session. Give each attempt isolated files and vector point IDs.
        key = (existing['storage_key'] if existing and store.path(existing['storage_key']).is_file()
               else f'segments/{segment_id}/{attempt_id}.mp4')
        target = store.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            temporary = target.with_suffix('.partial.mp4')
            try:
                run_media(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(start), '-i', str(source),
                           '-t', str(end-start), '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264',
                           '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                           '-movflags', '+faststart', str(temporary)])
                validate_video(temporary)
                repo.assert_worker()
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            validate_video(target)
        caption = existing['caption'] if existing else (options['captions'][number] if options['captions'] is not None else captioner.caption(target))
        row = {'id': segment_id, 'index_id': uuid5(attempt_id, str(segment_id)),
               'job_id': job['id'], 'video_id': job['video_id'], 'storage_key': key,
               'caption': caption, 'start_sec': start, 'end_sec': end, 'dataset_id': options['dataset_id'],
               'tags': options['tags'], 'embedding_identity': options['embedding_identity']}
        repo.save_segment(row)
        vector = embedder.encode(caption)
        repo.assert_worker()
        index.upsert(row, vector)
        repo.mark_indexed(segment_id)


def work_once(repo, store, index, embedder, captioner, settings):
    with repo.worker_lock() as repo:
        job = repo.next_job()
        if job is None:
            return False
        try:
            process_job(job, repo, store, index, embedder, captioner, settings)
        except Exception:
            # Persist only a safe code; model/DB errors may contain credentials.
            repo.finish(job['id'], 'ingestion_failed')
            return True
        repo.finish(job['id'])
        return True

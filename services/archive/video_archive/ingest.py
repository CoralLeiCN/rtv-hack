import hashlib
from fractions import Fraction
import json
import logging
import math
import os
import subprocess
import tempfile
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .models import embedding_identity


def run_media(args):
    # FFmpeg diagnostics can contain local paths. Caller reports a fixed error.
    return subprocess.run(args, check=True, capture_output=True, timeout=600).stdout


def decoded_duration(path, time_base):
    # Progress timestamps can mark the START of the final frame. Decode the
    # video timeline and include that frame's duration instead. Spool per-frame
    # metadata to disk so long videos do not require an unbounded Python buffer.
    with tempfile.TemporaryFile() as frames:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_frames', '-show_entries',
            'frame=best_effort_timestamp,duration,pkt_duration:frame_side_data=',
            '-of', 'compact=p=0:nk=0', str(path)],
            stdout=frames, stderr=subprocess.PIPE, check=True, timeout=600)
        if result.stderr:
            raise ValueError('Cannot decode video timeline')
        frames.seek(0)
        first, last, end, last_duration, step = None, None, None, None, None
        constant_step = True
        for line in frames:
            if not line.strip():
                continue
            fields = dict(field.split(b'=', 1) for field in line.strip().split(b'|'))
            timestamp = int(fields[b'best_effort_timestamp'])
            # FFprobe 5 exposes pkt_duration; newer releases expose duration.
            reported = fields.get(b'duration', fields.get(b'pkt_duration', b'0'))
            frame_duration = 0 if reported == b'N/A' else int(reported)
            if frame_duration < 0:
                raise ValueError('Invalid video frame duration')
            if last is not None:
                delta = timestamp - last
                constant_step = constant_step and delta > 0 and (step is None or delta == step)
                step = delta
            first = timestamp if first is None else min(first, timestamp)
            end = timestamp + frame_duration if end is None else max(end, timestamp + frame_duration)
            if last is None or timestamp >= last:
                last, last_duration = timestamp, frame_duration
    if first is None:
        raise ValueError('Source contains no decodable video frames')
    if not last_duration:
        # Some containers omit frame durations as well. A constant decoded
        # cadence establishes the final frame's length without using audio or
        # an average frame rate that would be wrong for variable-rate footage.
        if not constant_step or step is None or step <= 0:
            raise ValueError('Final video frame duration is unavailable')
        end = max(end, last + step)
    return float((end - first) * Fraction(time_base))


def duration(path):
    probe = json.loads(run_media(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=duration,time_base', '-of', 'json', str(path)]))
    if not probe.get('streams'):
        raise ValueError('Source contains no video stream')
    reported = probe['streams'][0].get('duration')
    if reported in (None, 'N/A'):
        # Never use the container duration: it can include an audio-only tail.
        value = decoded_duration(path, probe['streams'][0]['time_base'])
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
        if existing:
            repo.assert_worker()
            try:
                index.delete([existing['index_id']])
            except Exception:
                # Publication already succeeded. Retrying the job just because
                # cleanup failed would create more obsolete points.
                logging.getLogger(__name__).warning('Vector cleanup deferred; run cleanup-vectors.')


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

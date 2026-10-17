import { useEffect, useRef, useState } from 'react';
import type { Candidate } from '../api';
import { eligibilityNote, isEligible, mmss, segmentTime, type Stage } from '../demo';

function PlayIcon({ playing = false }: { playing?: boolean }) {
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">{playing
    ? <><rect x="3" y="2" width="4" height="12" fill="currentColor" /><rect x="9" y="2" width="4" height="12" fill="currentColor" /></>
    : <polygon points="3,2 14,8 3,14" fill="currentColor" />}</svg>;
}

export function ReferenceCard({ candidate, rank, selected, onSelect }: { candidate: Candidate; rank: number; selected: boolean; onSelect: () => void }) {
  const p = candidate.provenance;
  return <button className={`card ${selected ? 'sel' : ''}`} onClick={onSelect} aria-pressed={selected}>
    <div className="ir reference-thumb" aria-hidden="true">
      <span className="mono thumb-cam">REF</span>
      <span className="mono thumb-time">{segmentTime(p.segment_start_sec)}</span>
      <span className="display thumb-rank">{String(rank).padStart(2, '0')}</span>
    </div>
    <div className="reference-copy">
      <div className="badge-row"><span className={`badge ${candidate.review_status === 'reviewed' ? 'rev' : 'unrev'}`}>
        {candidate.review_status === 'reviewed' ? `Reviewed · ${candidate.reviewed_behavior ?? 'behavior'}` : candidate.review_status === 'stale' ? 'Review outdated' : 'Unreviewed'}
      </span><span className="mono similarity">sim {candidate.similarity == null ? '—' : candidate.similarity.toFixed(2)}</span></div>
      <div className="clamp2 caption">{candidate.caption || 'No model caption available.'}</div>
      <div className="mono source-summary">{p.source_label} · {segmentTime(p.segment_start_sec)}–{segmentTime(p.segment_end_sec)}</div>
    </div>
  </button>;
}

export function ReferencePanel({ candidate, stage, simulatorReady, onCopy, onRetry, actionError }: {
  candidate: Candidate;
  stage: Stage;
  simulatorReady: boolean;
  onCopy: () => void;
  onRetry: () => void;
  actionError: string | null;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  // Preserve the existing search app's clearResults behavior when evidence
  // selection changes: release the old stream instead of leaving it buffering.
  useEffect(() => {
    const element = video.current;
    return () => {
      if (!element) return;
      element.pause();
      element.removeAttribute('src');
      element.load();
    };
  }, []);
  const eligible = isEligible(candidate);
  const p = candidate.provenance;
  const archiveTime = p.segment_start_sec == null ? null : p.segment_start_sec + position;
  const seek = (value: number) => { if (video.current && Number.isFinite(value)) video.current.currentTime = value; };
  const togglePlay = async () => {
    if (!video.current) return;
    if (!video.current.paused) video.current.pause();
    else {
      if (video.current.ended) video.current.currentTime = 0;
      try { await video.current.play(); setVideoError(null); }
      catch { setVideoError('The segment could not play. Retry playback or run the search again if this reference has expired.'); }
    }
  };
  const retryVideo = async () => {
    if (!video.current) return;
    setVideoError(null);
    video.current.load();
    await togglePlay();
  };
  const copyLabel = stage === 'imitating' ? `Imitating · ${candidate.action?.primitive}` : stage === 'complete' ? 'Imitation complete' : eligible ? 'Copy this behavior' : 'Copy unavailable';
  let copyNote = 'Copy runs one bounded primitive through the existing controller. Completion is observed, not timed.';
  if (!eligible) copyNote = 'Copy unavailable: only a reviewed reference returned by this search can move the duck.';
  else if (!simulatorReady) copyNote = 'Waiting for the Microduck physics controller to become ready.';
  else if (stage === 'imitating') copyNote = `Waiting for the controller to complete ${candidate.action!.primitive} and return to its normal mode.`;
  else if (stage === 'complete') copyNote = 'Controller completion observed. Choose another reviewed reference or Reset.';

  return <div className="selection-panel">
    <div className="selection-heading"><span className="label">Selected reference</span><span className="mono secondary small">{p.dataset ?? 'Archive segment'}</span></div>
    <div className="ir video-frame">
      <video ref={video} src={candidate.video_url} preload="metadata" playsInline
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
        onTimeUpdate={() => setPosition(video.current?.currentTime ?? 0)}
        onLoadedMetadata={() => setDuration(Number.isFinite(video.current?.duration) ? video.current!.duration : 0)}
        onDurationChange={() => setDuration(Number.isFinite(video.current?.duration) ? video.current!.duration : 0)}
        onError={() => setVideoError('This segment is unavailable or has expired. Run the search again to get a fresh reference.')}
        aria-label={`Wildlife reference: ${candidate.caption || p.source_label}`} />
      <span className="hud video-top-left"><span className={`dot ${playing ? 'live' : ''}`} aria-hidden="true" /> ARCHIVE · {playing ? 'PLAY' : 'PAUSED'}</span>
      <span className="hud video-bottom-left">ARCHIVE {mmss(archiveTime)}</span>
      <span className="hud video-bottom-right">SEG {mmss(position)} / {mmss(duration || null)}</span>
      {!playing && !videoError && <button className="video-play" aria-label="Play segment" onClick={() => void togglePlay()}><PlayIcon /></button>}
    </div>
    <div className="video-controls">
      <button className="iconbtn" onClick={() => void togglePlay()} aria-label={playing ? 'Pause segment' : 'Play segment'}><PlayIcon playing={playing} /></button>
      <button className="iconbtn" onClick={() => { video.current?.pause(); seek(0); }} aria-label="Back to segment start"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2" width="2" height="12" fill="currentColor" /><polygon points="14,2 5,8 14,14" fill="currentColor" /></svg></button>
      <input className="video-seek" aria-label="Segment position" aria-valuetext={`${mmss(position)} of ${mmss(duration)}`} type="range" min="0" max={duration || 1} value={Math.min(position, duration || 1)} step="0.05" disabled={!duration} onChange={event => seek(Number(event.target.value))} />
      <span className="mono segment-time">{segmentTime(p.segment_start_sec)}–{segmentTime(p.segment_end_sec)}</span>
    </div>
    {videoError && <div className="alert compact" role="alert"><span>{videoError}</span><div className="alert-actions"><button className="seg" onClick={() => void retryVideo()}>Retry video</button><button className="seg" onClick={onRetry}>Search again</button></div></div>}
    <div className="behavior-panel">
      <div className="badge-row spread"><span className="label">Reviewed behavior → duck move</span><span className={`badge ${eligible ? 'rev' : 'hot'}`}>{eligible ? 'Reviewed · eligible' : 'Copy unavailable'}</span></div>
      {eligible ? <div className="behavior-mapping">
        <div><span className="label secondary">Observed in footage</span><span className="behavior-name">{candidate.reviewed_behavior}</span><span className="body-note">{candidate.review_reason ?? 'Recorded in the reviewed reference manifest.'}</span></div>
        <div className="allowed-primitive"><span className="label secondary">Allowed primitive</span><span className="mono primitive">{candidate.action!.primitive}</span><span className="body-note">{candidate.action!.primitive === 'ground_pick' ? 'One complete beak-dip cycle' : candidate.action!.primitive === 'short_walk' ? 'Slow movement · 2 seconds maximum' : candidate.action!.primitive === 'stand_hold' ? 'Neutral standing · 3 seconds maximum' : 'One bounded controller action'} · {(candidate.action!.max_duration_ms / 1000).toFixed(0)} s cancellation limit</span></div>
      </div> : <div className="ineligible-note">{eligibilityNote(candidate)}</div>}
      <button className="btn primary copy-button" onClick={onCopy} disabled={!eligible || stage !== 'ready' || !simulatorReady}>{copyLabel}</button>
      {stage === 'imitating' && <div className="action-running mono" role="status"><span className="dot live" aria-hidden="true" /> Controller action in progress</div>}
      {actionError && <div className="action-error" role="alert">{actionError}</div>}
      <div className="mono copy-note">{copyNote}</div>
      <button className="seg details-toggle" onClick={() => setDetailsOpen(value => !value)} aria-expanded={detailsOpen}>{detailsOpen ? 'Hide evidence details' : 'Evidence details'}</button>
      {detailsOpen && <dl className="kv mono">
        <dt>model caption</dt><dd>{candidate.caption || 'none available'}</dd>
        <dt>caption hash</dt><dd>{candidate.caption_hash ?? 'not supplied by this backend'}</dd>
        <dt>reviewed label</dt><dd className="teal">{candidate.animal && candidate.reviewed_behavior ? `${candidate.animal} · ${candidate.reviewed_behavior}` : 'none recorded'}</dd>
        <dt>review reason</dt><dd>{candidate.review_reason ?? 'none recorded'}</dd>
        <dt>eligibility</dt><dd>{candidate.eligibility_reason}</dd>
        <dt>source</dt><dd>{p.source_label}</dd>
        <dt>parent video</dt><dd>{p.parent_id || 'unresolved'}</dd>
        <dt>segment</dt><dd>{segmentTime(p.segment_start_sec)}–{segmentTime(p.segment_end_sec)} · source-relative</dd>
        <dt>clip id</dt><dd>{candidate.clip_id}</dd>
        <dt>provenance</dt><dd>{p.dataset ?? 'not supplied'}</dd>
      </dl>}
    </div>
  </div>;
}

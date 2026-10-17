import { useEffect, useRef, useState } from 'react';
import type { Candidate } from '../api';
import { eligibilityNote, isEligible, mmss, segmentTime, type Stage } from '../demo';

function PlayIcon({ playing = false }: { playing?: boolean }) {
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">{playing
    ? <><rect x="3" y="2" width="4" height="12" fill="currentColor" /><rect x="9" y="2" width="4" height="12" fill="currentColor" /></>
    : <polygon points="3,2 14,8 3,14" fill="currentColor" />}</svg>;
}

export function ReferenceCard({ candidate, rank, selected, sequenceState, onSelect }: { candidate: Candidate; rank: number; selected: boolean; sequenceState?: string; onSelect: () => void }) {
  const p = candidate.provenance;
  const inferred = candidate.action_basis === 'video_caption';
  return <button className={`card ${selected ? 'sel' : ''}`} onClick={onSelect} aria-pressed={selected} title="Pause the loop and inspect this reference">
    <div className="ir reference-thumb" aria-hidden="true">
      <span className="mono thumb-cam">REF</span>
      <span className="mono thumb-time">{segmentTime(p.segment_start_sec)}</span>
      <span className="display thumb-rank">{String(rank).padStart(2, '0')}</span>
    </div>
    <div className="reference-copy">
      <div className="badge-row"><span className={`badge ${inferred ? 'inferred' : candidate.review_status === 'reviewed' ? 'rev' : 'unrev'}`}>
        {inferred ? 'Caption-inferred' : candidate.review_status === 'reviewed' ? `Reviewed · ${candidate.reviewed_behavior ?? 'behavior'}` : candidate.review_status === 'stale' ? 'Review outdated' : 'No supported action'}
      </span><span className="mono similarity">sim {candidate.similarity == null ? '—' : candidate.similarity.toFixed(2)}</span>{sequenceState && <span className={`mono rank-state ${sequenceState}`}>{sequenceState}</span>}</div>
      <div className="clamp2 caption">{candidate.caption || 'No model caption available.'}</div>
      <div className="mono source-summary">{p.source_label} · {segmentTime(p.segment_start_sec)}–{segmentTime(p.segment_end_sec)}</div>
    </div>
  </button>;
}

export function ReferencePanel({ candidate, stage, autoPlaying, sequenceLabel, onRetry, actionError }: {
  candidate: Candidate;
  stage: Stage;
  autoPlaying: boolean;
  sequenceLabel: string;
  onRetry: () => void;
  actionError: string | null;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);
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
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    let cancelled = false;
    if (autoPlaying) {
      element.muted = true;
      if (element.readyState >= 1) element.currentTime = 0;
      void element.play().then(() => { if (!cancelled) setAutoplayBlocked(false); }).catch(error => {
        if (!cancelled && error?.name !== 'AbortError') setAutoplayBlocked(true);
      });
    } else element.pause();
    return () => { cancelled = true; };
  }, [autoPlaying]);
  const eligible = isEligible(candidate);
  const inferred = candidate.action_basis === 'video_caption';
  const behavior = candidate.inferred_behavior ?? candidate.reviewed_behavior;
  const actionReason = candidate.action_reason ?? candidate.review_reason;
  const p = candidate.provenance;
  const archiveTime = p.segment_start_sec == null ? null : p.segment_start_sec + position;
  const seek = (value: number) => { if (video.current && Number.isFinite(value)) video.current.currentTime = value; };
  const togglePlay = async () => {
    if (!video.current) return;
    if (!video.current.paused) video.current.pause();
    else {
      if (video.current.ended) video.current.currentTime = 0;
      try { await video.current.play(); setVideoError(null); setAutoplayBlocked(false); }
      catch (error) {
        // Pause, Stop, Rewind, and changing the source intentionally interrupt
        // a pending play request; they are not failures of the archive clip.
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setVideoError('The segment could not play. Retry playback or run the search again if this reference has expired.');
      }
    }
  };
  const retryVideo = async () => {
    if (!video.current) return;
    setVideoError(null);
    video.current.load();
    await togglePlay();
  };
  const primitiveLabel = candidate.action?.primitive === 'head_scan' ? 'Bounded head movement' : candidate.action?.primitive === 'ground_pick' ? 'One complete beak-dip cycle' : candidate.action?.primitive === 'short_walk' ? 'Short forward movement' : 'Neutral standing hold';
  const evidenceNote = inferred
    ? 'Caption-inferred approximation using a pretrained duck movement. This label has not been visually reviewed.'
    : 'Visually reviewed evidence mapped to a pretrained duck movement.';

  return <div className="selection-panel">
    <div className="selection-heading"><span className="label">Current reference</span><span className="mono secondary small">{p.dataset ?? 'Archive segment'}</span></div>
    <div className="ir video-frame">
      <video ref={video} src={candidate.video_url} preload="metadata" playsInline muted autoPlay={autoPlaying} loop={autoPlaying}
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
    {autoplayBlocked && !videoError && <div className="body-note">Automatic playback was blocked. Press Play to watch this segment.</div>}
    {videoError && <div className="alert compact" role="alert"><span>{videoError}</span><div className="alert-actions"><button className="seg" onClick={() => void retryVideo()}>Retry video</button><button className="seg" onClick={onRetry}>Search again</button></div></div>}
    <div className="behavior-panel">
      <div className="badge-row spread"><span className="label">Video behavior → duck move</span><span className={`badge ${eligible ? inferred ? 'inferred' : 'rev' : 'hot'}`}>{eligible ? inferred ? 'Caption-inferred' : 'Reviewed' : 'Skipped'}</span></div>
      {eligible ? <div className="behavior-mapping">
        <div><span className="label secondary">{inferred ? 'Inferred from caption' : 'Reviewed in footage'}</span><span className="behavior-name">{behavior ?? 'Supported interaction'}</span><span className="body-note">{actionReason ?? 'Mapped from the returned video evidence.'}</span></div>
        <div className="allowed-primitive"><span className="label secondary">Duck approximation</span><span className="mono primitive">{candidate.action!.primitive}</span><span className="body-note">{primitiveLabel} · {(candidate.action!.max_duration_ms / 1000).toFixed(1).replace(/\.0$/, '')} s motion window</span></div>
      </div> : <div className="ineligible-note">{eligibilityNote(candidate)}</div>}
      <div className={`automatic-action display ${autoPlaying ? 'active' : ''}`}>{autoPlaying ? 'Automatic loop running' : stage === 'paused' ? 'Loop stopped' : 'No supported action'}</div>
      {actionError && <div className="action-error" role="alert">{actionError}</div>}
      <div className="mono copy-note">{eligible ? evidenceNote : 'This rank stays in place and is skipped. Lower-ranked results are not promoted.'} {autoPlaying ? 'Use Stop to pause.' : sequenceLabel}</div>
      <button className="seg details-toggle" onClick={() => setDetailsOpen(value => !value)} aria-expanded={detailsOpen}>{detailsOpen ? 'Hide evidence details' : 'Evidence details'}</button>
      {detailsOpen && <dl className="kv mono">
        <dt>model caption</dt><dd>{candidate.caption || 'none available'}</dd>
        <dt>caption hash</dt><dd>{candidate.caption_hash ?? 'not supplied by this backend'}</dd>
        <dt>action basis</dt><dd>{candidate.action_basis ?? 'none'}</dd>
        <dt>inferred label</dt><dd>{candidate.inferred_behavior ?? 'none'}</dd>
        <dt>interaction pair</dt><dd>{candidate.animal ?? 'unresolved'} · {candidate.interaction_partner ?? 'unresolved'}</dd>
        <dt>action reason</dt><dd>{candidate.action_reason ?? 'none recorded'}</dd>
        <dt>evidence id</dt><dd>{candidate.action?.evidence_id ?? 'none'}</dd>
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

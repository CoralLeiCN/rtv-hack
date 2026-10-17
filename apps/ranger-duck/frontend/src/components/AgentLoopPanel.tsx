import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { ApiError, getHealth, type Health } from '../api';
import { checkActive, loopRequest, playAndReact, reactionState, runAgentLoop, runRoleActions, type AgentCycle, type ReactionOutcome } from '../agentLoop';
import type { MicroduckSceneHandle } from '../simulator/MicroduckScene';

type Props = { duck: RefObject<MicroduckSceneHandle>; ready: boolean; health: Health | null; onSearching(value: boolean): void;
  animal: 'cat' | 'deer'; onAnimalChange(animal: 'cat' | 'deer'): void };
export function AgentLoopPanel({ duck, ready, health, onSearching, animal, onAnimalChange }: Props) {
  const [prompt, setPrompt] = useState('Meet a curious deer');
  const [running, setRunning] = useState(false);
  const [settling, setSettling] = useState(false);
  const [status, setStatus] = useState('Enter a prompt, then enable Loop mode.');
  const [error, setError] = useState<string | null>(null);
  const [cycle, setCycle] = useState<AgentCycle | null>(null);
  const [outcome, setOutcome] = useState<ReactionOutcome | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const video = useRef<HTMLVideoElement>(null);
  const active = useRef<AbortController | null>(null);
  const saved = useRef<{ id: string; prompt: string; animal: string } | null>(null);
  const cleanupRequest = useRef<Promise<unknown>>(Promise.resolve());
  const starting = useRef<Promise<unknown> | null>(null);
  const mounted = useRef(true);

  const pause = useCallback((message = 'Loop off. Resume makes a fresh search using the previous context.') => {
    active.current?.abort(); active.current = null;
    video.current?.pause(); duck.current?.stop();
    onSearching(false);
    if (mounted.current) { setRunning(false); setBlocked(false); setStatus(message); setSettling(true); }
    const id = saved.current?.id;
    const cleanup = (starting.current ?? Promise.resolve()).catch(() => undefined)
      .then(() => id ? loopRequest(`/${id}/pause`).catch(() => undefined) : undefined);
    cleanupRequest.current = cleanup;
    void cleanup.finally(() => { if (mounted.current && cleanupRequest.current === cleanup) setSettling(false); });
  }, [duck, onSearching]);

  useEffect(() => {
    mounted.current = true;
    const hidden = () => { if (document.hidden && active.current) pause('Paused while the tab is hidden. Resume when ready.'); };
    document.addEventListener('visibilitychange', hidden);
    return () => { mounted.current = false; document.removeEventListener('visibilitychange', hidden); pause(); };
  }, [pause]);

  const start = async () => {
    if (!ready || !health || active.current || settling || !prompt.trim() || document.hidden) return;
    const controller = new AbortController(); active.current = controller;
    const current = () => mounted.current && active.current === controller && !controller.signal.aborted;
    setRunning(true); setError(null); setBlocked(false); setOutcome(null);
    try {
      await cleanupRequest.current;
      checkActive(controller.signal);
      const existing = saved.current;
      if (!existing || existing.prompt !== prompt.trim() || existing.animal !== animal) {
        // A reset must also recover an expired cookie or a restarted backend.
        await getHealth(controller.signal);
        checkActive(controller.signal);
        const id = crypto.randomUUID();
        saved.current = { id, prompt: prompt.trim(), animal };
        setHistory([]); setCycle(null);
        // Let start finish so a concurrent stop can always cancel the created session.
        try {
          starting.current = loopRequest('', { session_id: id, prompt: prompt.trim(), animal });
          await starting.current;
        } catch (failure) {
          if (saved.current?.id === id) saved.current = null;
          throw failure;
        } finally { starting.current = null; }
        if (!current()) { await loopRequest(`/${id}/pause`).catch(() => undefined); return; }
      } else await loopRequest(`/${existing.id}/resume`, undefined, controller.signal);
      checkActive(controller.signal);
      const id = saved.current!.id;
      setStatus('Preparing the duck…');
      await duck.current!.prepareCycle();
      checkActive(controller.signal);
      setStatus('Facing and approaching the animal…');
      await duck.current!.ensureInteraction();
      checkActive(controller.signal);
      await runAgentLoop({
        signal: controller.signal,
        onSearch: attempt => { if (current()) { setStatus(`Codex is searching${attempt > 1 ? ` · attempt ${attempt}/3` : ''}…`); onSearching(true); } },
        next: async () => {
          const timeout = setTimeout(() => controller.abort('deadline'), (health.loop_cycle_timeout_ms ?? 180000) + 5000);
          try { return await loopRequest<AgentCycle>(`/${id}/next`, undefined, controller.signal); }
          finally { clearTimeout(timeout); }
        },
        execute: async next => {
          checkActive(controller.signal);
          setCycle(next); setOutcome(null); setBlocked(false); onSearching(false);
          setStatus(`Cycle ${next.cycle} · playing clip and responding`);
          let completed = false;
          let companionStatus: ReactionOutcome['companion']['status'] = 'cancelled';
          try {
            setStatus(`Cycle ${next.cycle} · facing and approaching the animal`);
            await duck.current!.ensureInteraction();
            checkActive(controller.signal);
            setStatus(`Cycle ${next.cycle} · playing clip and responding`);
            await playAndReact(video.current!, next, controller.signal,
              () => runRoleActions(next.role_plan, controller.signal,
                async () => {
                  try {
                    await duck.current!.performCompanion({ behavior: next.role_plan.companion_behavior, durationMs: next.role_plan.companion_duration_ms });
                    companionStatus = 'completed';
                  } catch (error) { companionStatus = controller.signal.aborted ? 'cancelled' : 'failed'; throw error; }
                },
                () => duck.current!.perform({ primitive: next.action.primitive, evidenceId: next.action.evidence_id, maxDurationMs: next.action.max_duration_ms })),
              () => { if (current()) { setBlocked(true); setStatus('Press Play clip to allow playback.'); } });
            completed = true;
          } catch (failure) {
            checkActive(controller.signal);
            if (current()) setError(failure instanceof Error ? failure.message : 'The reaction failed.');
          } finally { duck.current?.stopCompanion(); }
          checkActive(controller.signal);
          const state = reactionState(duck.current!.telemetry());
          if (!completed) duck.current!.stop();
          const report: ReactionOutcome = { cycle_id: next.cycle_id, primitive: next.action.primitive,
            status: completed ? 'completed' : 'failed', playback: video.current!.ended ? 'ended' : 'failed', state,
            companion: { behavior: next.role_plan.companion_behavior, status: companionStatus } };
          if (current()) { setOutcome(report); setHistory(previous => [`${next.cycle}. ${next.action.primitive} · ${report.status}`, ...previous].slice(0, 5)); }
          return report;
        },
        report: async report => {
          await loopRequest(`/${id}/outcome`, report, controller.signal);
          checkActive(controller.signal);
          if (report.status === 'completed') {
            setStatus('Facing the animal before the next search…');
            await duck.current!.ensureInteraction();
            checkActive(controller.signal);
          }
        },
      });
    } catch (failure) {
      if (current() || (active.current === controller && controller.signal.reason === 'deadline')) {
        setError(controller.signal.reason === 'deadline' ? 'The agent deadline was reached.' : failure instanceof ApiError || failure instanceof Error ? failure.message : 'The loop could not continue.');
        pause('Paused. Retry resumes with a fresh search.');
      }
    }
  };
  const reset = () => { pause('Reset. Enter a prompt to start a new interaction.'); saved.current = null; setCycle(null); setHistory([]); setOutcome(null); setError(null); };
  const available = ready && !!health?.live_configured && health.loop_agent_available !== false;

  return <aside className="archive-column agent-loop-panel" aria-label="Agent Loop mode">
    <div className="archive-heading"><h2 className="display">Loop mode</h2><span className="badge">Caption-grounded animal behavior</span></div>
    <form className="box loop-form" onSubmit={event => { event.preventDefault(); void start(); }}>
      <label className="label" htmlFor="loop-prompt">Initial prompt</label>
      <textarea id="loop-prompt" maxLength={1000} value={prompt} disabled={running} onChange={event => setPrompt(event.target.value)} />
      <label htmlFor="loop-animal">Animal scope</label>
      <select id="loop-animal" value={animal} disabled={running} onChange={event => onAnimalChange(event.target.value as 'cat' | 'deer')}><option value="deer">Deer</option><option value="cat">Cat</option></select>
      <div className="alert-actions"><button type="button" className={`btn ${running ? '' : 'primary'}`} role="switch" aria-checked={running} disabled={!running && (!available || !prompt.trim() || settling)} onClick={() => running ? pause() : void start()}>{running ? 'Loop on · turn off' : saved.current ? 'Resume loop' : 'Turn loop on'}</button><button type="button" className="btn" onClick={reset}>Reset</button></div>
      <div role="status">{settling ? 'Stopping the previous cycle…' : status}</div>
      {!health?.live_configured && <p className="body-note">Configure archive access on the backend to start.</p>}
      {health?.loop_agent_available === false && <p className="body-note">Codex CLI is unavailable on the backend host. Install it and sign in there.</p>}
    </form>
    {error && <div className="alert" role="alert">{error}</div>}
    {cycle && <div className="box"><div className="label">Cycle {cycle.cycle} · original result rank {cycle.clip.rank}</div><p className="mono">{cycle.query}</p><p>{cycle.query_reason}</p></div>}
    <video ref={video} hidden={!cycle} className="loop-video" controls playsInline muted preload="none" aria-label="Agent-selected reference clip" />
    {blocked && <button className="btn primary" onClick={() => { void video.current?.play().then(() => setBlocked(false)).catch(() => setError('Playback is still blocked. Check browser media permissions.')); }}>Play clip</button>}
    {cycle && <details className="box"><summary>Search results · {cycle.candidates.length} clips</summary>
      <ol>{cycle.candidates.map(candidate => <li key={candidate.candidate_id} value={candidate.rank}>
        <p>{candidate.caption || 'No caption available.'}</p>
        {candidate.unavailable_reason && <p className="body-note">Unavailable for this cycle: {candidate.unavailable_reason.replaceAll('_', ' ')}</p>}
      </li>)}</ol>
    </details>}
    {cycle && <div className="box"><div className="label">{cycle.clip.evidence_basis === 'reviewed' ? 'Reviewed interaction' : 'Inferred from archive caption'}</div><p>{cycle.clip.caption}</p>{cycle.clip.dataset_id && <dl className="kv mono"><dt>dataset id</dt><dd>{cycle.clip.dataset_id}</dd></dl>}<div className="label">{cycle.role_plan.grounding === 'caption_roles' ? 'Two video roles · caption-inferred approximation' : cycle.role_plan.grounding === 'single_behavior' ? 'Individual behavior · duck imitation' : 'Insufficient role evidence · neutral fallback'}</div>
      {cycle.role_plan.grounding === 'single_behavior' ? <p>Scene companion: standing nearby. No second video role is inferred.</p> : <p>Companion: {cycle.role_plan.companion.subject} → {cycle.role_plan.companion_behavior}</p>}
      {cycle.role_plan.companion.evidence && <blockquote>{cycle.role_plan.companion.evidence}</blockquote>}
      <p>Duck: {cycle.role_plan.duck.subject} → {cycle.action.primitive}</p>
      {cycle.role_plan.duck.evidence && <blockquote>{cycle.role_plan.duck.evidence}</blockquote>}
      <p>Order: {cycle.role_plan.timing.replaceAll('_', ' ')}</p><p>{cycle.response_reason}</p><p className="body-note">The companion uses scripted animation; the duck uses supported physics movements. These are approximations of caption-described roles, not motion capture.</p>{outcome && <p className="mono">Actual outcome: {outcome.status} · companion {outcome.companion.status} · controller {outcome.state.status} · position {outcome.state.position.map(n => n.toFixed(2)).join(', ')}</p>}</div>}
    {!!history.length && <div className="box"><div className="label">Recent reactions</div>{history.map((item, index) => <p className="mono" key={index}>{item}</p>)}</div>}
  </aside>;
}

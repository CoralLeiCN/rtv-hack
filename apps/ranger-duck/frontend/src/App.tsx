import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ApiError, getEncounters, getHealth, type Encounter, type Health } from './api';
import { motionLabel, type Stage } from './demo';
import { ReferenceCard, ReferencePanel } from './components/ReferencePanel';
import { MicroduckScene, type MicroduckSceneHandle } from './simulator/MicroduckScene';
import { SessionController, sessionLabel, type SessionPhase } from './session';
import { sessionApi } from './sessionApi';

const stages = ['Encounter', 'Agent search', 'Actions ready', 'Imitating', 'Round complete'];
const stageIndex: Record<SessionPhase, number> = { idle: -1, starting: 0, planning: 1, searching: 1, approaching: 2, playback: 2, acting: 3, reporting: 3, complete: 4, paused: 3, empty: 1, failed: 1 };

export default function App() {
  const duck = useRef<MicroduckSceneHandle>(null);
  const video = useRef<HTMLVideoElement>(null);
  const healthRef = useRef<Health | null>(null);
  const runner = useRef<SessionController | null>(null);
  if (!runner.current) runner.current = new SessionController({
    api: () => { if (!healthRef.current) throw new Error('The backend is not connected.'); return sessionApi(healthRef.current); },
    scene: () => duck.current, video: () => video.current,
  });
  const controller = runner.current;
  const run = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<Encounter[]>([]);
  const [scenarioId, setScenarioId] = useState('');
  const [intent, setIntent] = useState('');
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [bootAttempt, setBootAttempt] = useState(0);
  const [simulatorReady, setSimulatorReady] = useState(false);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);
  const [movementError, setMovementError] = useState<string | null>(null);
  const [duckStatus, setDuckStatus] = useState('loading');
  const [navigationStatus, setNavigationStatus] = useState('idle');
  const [control, setControl] = useState<ReturnType<MicroduckSceneHandle['telemetry']> | null>(null);
  const [clock, setClock] = useState(Date.now());
  const lastConfig = useRef('');
  const scenario = scenarios.find(item => item.id === scenarioId) ?? null;
  const currentScenario = run.currentScenario ?? scenario;
  const species = [...new Set(scenarios.map(item => item.animal))].sort();
  const speciesScenarios = scenarios.filter(item => item.animal === scenario?.animal);
  const configKey = JSON.stringify([scenarioId, intent.trim()]);
  const configChanged = !!run.runId && configKey !== lastConfig.current;
  const searching = ['planning', 'searching'].includes(run.phase);
  const selected = run.round?.queue.find(item => item.candidate.clip_id === run.selectedId) ?? null;
  const elapsed = run.startedAt == null ? run.elapsedMs : clock - run.startedAt;
  const label = sessionLabel(run);
  const canStart = !run.running && !run.stopping && !!health?.live_configured && !!scenario && simulatorReady && health.encounter_agent_available !== false;
  const canResume = canStart && !!run.runId && !configChanged;
  const pendingToggle = !!run.round && run.adaptive !== run.roundAdaptive;

  useEffect(() => {
    const abort = new AbortController();
    setBootstrapError(null);
    Promise.all([getHealth(abort.signal), getEncounters(abort.signal)]).then(([service, catalog]) => {
      if (abort.signal.aborted) return;
      if (!catalog.length) throw new Error('No encounter scenarios are configured.');
      healthRef.current = service; setHealth(service); setScenarios(catalog);
      setScenarioId(previous => catalog.some(item => item.id === previous) ? previous : catalog[0].id);
    }).catch(error => { if (!abort.signal.aborted) setBootstrapError(error instanceof ApiError || error instanceof Error ? error.message : 'The demo backend is unavailable.'); });
    return () => abort.abort();
  }, [bootAttempt]);
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(Date.now());
      if (simulatorReady) try { setControl(duck.current?.telemetry() ?? null); } catch { /* Scene is still loading. */ }
    }, 250);
    return () => clearInterval(timer);
  }, [simulatorReady]);
  useEffect(() => {
    const visibility = () => controller.visibility(document.hidden);
    document.addEventListener('visibilitychange', visibility);
    return () => { document.removeEventListener('visibilitychange', visibility); controller.pause(); };
  }, [controller]);

  const start = (broaden = false) => {
    if (!canStart || !scenario) return;
    const id = crypto.randomUUID();
    lastConfig.current = configKey;
    setMovementError(null);
    // Stop the previous owner before queuing the animal. Planning starts
    // independently of the animal's appearance and automatic approach.
    controller.start({ run_id: id, animal: scenario.animal === 'cat' ? 'cat' : 'deer', scenario_id: scenario.id, intent: intent.trim(), adaptive: run.adaptive }, broaden);
    duck.current?.startEncounter({ id, animal: scenario.animal === 'cat' ? 'cat' : 'deer', interaction_partner: 'microduck', behavior_hint: scenario.behavior_hint, preservePose: true });
  };
  const reset = () => { controller.reset(); duck.current?.reset(); setMovementError(null); lastConfig.current = ''; };
  const onReady = useCallback(() => { setSimulatorReady(true); setSimulatorError(null); }, []);
  const onError = useCallback((message: string) => { controller.pause('Simulator unavailable.'); setSimulatorReady(false); setSimulatorError(message); setDuckStatus('failed'); }, [controller]);
  const onStatus = useCallback((status: string) => { setDuckStatus(status); if (status === 'ready' || status === 'complete') setMovementError(null); }, []);
  const onNavigation = useCallback((status: string) => setNavigationStatus(status), []);
  const onMovementError = useCallback((message: string) => setMovementError(message), []);
  const navigationLabel = control?.primitive ? motionLabel(control.primitive as Parameters<typeof motionLabel>[0]) : navigationStatus === 'approaching' ? 'Turning and approaching the animal' : navigationStatus === 'settling' ? 'Settling for the next action' : control?.target && Math.abs(control.target.facing_error) < 0.18 && duckStatus === 'ready' ? 'Facing the animal · ready' : 'Movement paused';
  const panelStage: Stage = run.phase === 'acting' ? 'imitating' : ['paused', 'failed'].includes(run.phase) ? 'paused' : run.phase === 'complete' ? 'complete' : 'ready';

  return <div className="app-shell unified-experience">
    <header className="app-header">
      <div className="brand"><div className="logo" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 28 28" fill="none"><circle cx="12" cy="16" r="8" fill="#101018" /><circle cx="17" cy="9" r="5" fill="#101018" /><path d="M21 9 L27 11 L21 13 Z" fill="#FF7A2F" /><circle cx="18.5" cy="8" r="1.2" fill="#FFD23F" /></svg></div><div><h1 className="display">Ranger Duck</h1><div className="label brand-subtitle">Field unit AV-1 · retrieval-guided imitation</div></div></div>
      <div className="species-tabs"><span className="label">Species</span><div className="tabs" role="group" aria-label="Animal species">{species.map(animal => <button key={animal} className={`tab ${scenario?.animal === animal ? 'on' : ''}`} aria-pressed={scenario?.animal === animal} disabled={run.running || run.stopping} onClick={() => { const first = scenarios.find(item => item.animal === animal); if (first) { setScenarioId(first.id); setIntent(''); } }}>{animal}</button>)}</div></div>
      <div className="encounter-tabs"><span className="label">Interaction preset</span><div className="tabs" role="group" aria-label="Encounter scenario">{speciesScenarios.map(item => <button key={item.id} className={`tab ${scenarioId === item.id ? 'on' : ''}`} aria-pressed={scenarioId === item.id} disabled={run.running || run.stopping} onClick={() => { setScenarioId(item.id); setIntent(''); }}>{item.label}</button>)}{!scenarios.length && <span className="mono secondary small">Connecting…</span>}</div></div>
      <div className="header-actions"><button className={`seg adaptive-toggle ${run.adaptive ? 'on' : ''}`} role="switch" aria-checked={run.adaptive} aria-label="Loop: refresh search after each round" onClick={() => controller.setAdaptive(!run.adaptive)}>Loop {run.adaptive ? 'on' : 'off'}</button><button className="btn primary" disabled={!canStart} onClick={() => start()}>{configChanged ? 'Start new run' : 'Start'}</button><button className="btn loop-control" disabled={!run.running && !canResume} onClick={() => run.running ? controller.pause() : controller.resume()}>{run.running ? 'Pause' : 'Resume'}</button><button className="btn" onClick={reset}>Reset</button></div>
    </header>
    <main className="main">
      <section aria-label="Shared simulation scene" className="scene-column">
        <div className="scene">
          <MicroduckScene ref={duck} onReady={onReady} onError={onError} onStatus={onStatus} onNavigation={onNavigation} onMovementError={onMovementError} searching={searching} />
          {searching && <div className="scan" aria-hidden="true" />}
          <div className="hud scene-hud-top"><span className={`dot ${simulatorReady ? 'live' : ''}`} aria-hidden="true" /><span>SIM · MuJoCo WASM · pretrained policy</span></div>
          <div className="hud scene-clock">{new Date(clock).toLocaleDateString('sv-SE')} {new Date(clock).toLocaleTimeString('en-GB')}</div>
          <div className="hud scene-hud-bottom"><span>Encounter {currentScenario?.label ?? '—'}</span><span>{run.runId ? `RUN ${run.runId.slice(0, 8)}` : 'Awaiting Start'}</span></div>
          {run.runId && <div className={`hud scene-navigation ${navigationStatus}`}><span className="label">Duck control · {control?.primitive ? 'evidence action' : 'navigation'}</span><span>{navigationLabel}</span>{control?.commands && <span className="mono control-command">Forward {control.commands.forward.toFixed(2)} · turn {control.commands.yaw.toFixed(2)}{control.target && navigationStatus === 'approaching' ? ` · ${control.target.distance.toFixed(2)} m to animal` : ''}</span>}</div>}
          <div className="sticker mono duck-status"><span className="label">duck.status()</span><span>{duckStatus}</span></div>
          {simulatorError && <div className="sim-error alert" role="alert"><strong className="display">Simulator unavailable</strong><span>{simulatorError}</span><span className="small">Load the pinned simulator assets and reload this page.</span></div>}
        </div>
        <div className="encounter-details"><div className="encounter-description"><div className="label">One animal · continuous duck physics</div><div className="scene-caption">{run.running ? `${currentScenario?.label ?? 'Encounter'}: Microduck faces the ${currentScenario?.animal ?? 'animal'} and imitates caption-grounded video behavior.` : 'Choose an encounter, then Start. The agent finds interactions or similar individual behavior for the duck to imitate.'}</div><div className="body-note">{run.adaptive ? 'Loop on: the animal chooses a different interaction after each completed round; a fresh query and action queue follow.' : 'Loop off: repeat the same query and up to three actions, without another search.'}{pendingToggle && ' This change applies at the round boundary.'}</div></div></div>
        {configChanged && <div className="body-note">The preset or intent changed. Start a new run to apply it; the duck keeps its physical position.</div>}
        {movementError && <div className="alert compact" role="alert">Navigation: {movementError}</div>}
        {bootstrapError && <div className="alert compact" role="alert"><span>{bootstrapError}</span><button className="seg" onClick={() => setBootAttempt(value => value + 1)}>Reconnect backend</button></div>}
        {health && !health.live_configured && <div className="setup-note mono">Live archive access is not configured on the backend.</div>}
        {health?.encounter_agent_available === false && <div className="setup-note mono">The agent runtime is unavailable. Connect the backend agent runtime to start.</div>}
      </section>
      <aside aria-label="Archive agent and reference queue" className={`archive-column ${selected && !searching ? 'has-selection' : ''}`}>
        <div className="archive-heading"><h2 className="display">{searching && <span className="dot live" aria-hidden="true" />}Archive agent</h2><span className={`badge ${run.replay ? 'hot' : ''}`}>{run.replay ? 'Saved round replay' : 'Live archive'}</span></div>
        <details className="intent-editor"><summary className="label">Intent · {intent.trim() ? 'custom' : scenario?.label ?? 'choose a preset'}</summary><label className="label" htmlFor="run-intent">Optional intent</label><textarea id="run-intent" maxLength={1000} value={intent} placeholder={scenario?.description ?? 'Describe an interaction or individual behavior'} disabled={run.running || run.stopping} onChange={event => setIntent(event.target.value)} /><p className="body-note">The preset supplies the starting context. Pause before editing.</p></details>
        <div className="current-interaction"><span className="label">Current interaction{run.plan ? ` · round ${run.plan.round}` : run.round ? ` · round ${run.round.round}` : ""}</span><span className="mono">{currentScenario?.label ?? "Awaiting preset"}</span><span className="body-note">Scripted animal context · {searching ? "guides this query" : "video evidence authorizes each duck action"}</span></div>
        <div className="box"><div className="query-heading"><span className="label">Agent query</span><span className={`label request-status ${run.phase}`} role="status">{run.stopping ? 'Stopping…' : run.phase === 'planning' ? 'Generating query' : run.phase === 'searching' ? 'Search + action plan' : run.replay ? 'Recorded decisions' : run.round ? `Round ${run.round.round} · pass ${run.pass}` : 'Ready'}</span></div><div className="mono query-text">{run.plan?.query ?? (run.phase === 'planning' ? 'Agent is composing a query…' : run.round?.query ?? '—')}</div><div className="query-footer"><span className="mono request-route">{run.replay ? 'Saved result · no new agent or search call' : `${scenario?.animal ?? 'Animal'} interactions or individual behavior`}</span><span className="mono elapsed">{run.startedAt != null || run.round ? `${(elapsed / 1000).toFixed(2)} s` : '— s'}</span></div>{(run.plan?.query_reason ?? (!searching && run.round?.query_reason)) && <div className="agent-query-reason body-note">{run.plan?.query_reason ?? run.round?.query_reason}</div>}{!searching && run.round?.agent_plan?.summary && <div className="agent-plan-summary body-note"><span className="label">Agent action plan</span> {run.round.agent_plan.summary}</div>}{(run.plan?.timings ?? (!searching && run.round?.timings)) && <div className="mono stage-timings">{([["Query", "query_agent_ms"], ["VSS", "vss_search_ms"], ["Actions", "action_agent_ms"]] as const).map(([name, key]) => { const value = (run.plan?.timings ?? run.round?.timings)?.[key]; return <span key={key}>{name} {typeof value === "number" ? `${(value / 1000).toFixed(2)} s` : "—"}</span>; })}</div>}{run.replay && <div className="mono replay-note">Replaying saved decisions{run.round?.recorded_at ? ` from ${new Date(run.round.recorded_at).toLocaleTimeString('en-GB')}` : ''}. Replay outcomes do not update the live agent.</div>}</div>
        <div className="results-section"><div className="results-heading"><span className="label">Active actions · {!searching && run.round ? `${run.round.queue.length} of up to 3` : 'awaiting search'}</span><span className="label secondary">{!searching && run.round ? `${run.round.candidates.length} references searched` : 'original archive order'}</span></div><div className="results-list">
          {searching ? <div className="empty">{run.phase === 'planning' ? 'The agent is generating a query…' : 'Searching the archive and mapping supported active actions…'}</div> : run.round?.queue.length ? run.round.queue.map((item, index) => <ReferenceCard key={item.action_id} candidate={item.candidate} rank={index + 1} sourceRank={item.candidate.rank ?? index + 1} selected={run.selectedId === item.candidate.clip_id} sequenceState={run.rankStates[item.action_id] ?? 'queued'} onSelect={() => controller.inspect(item.candidate.clip_id)} />) : run.phase === 'empty' ? <div className="alert"><div className="display alert-title">No active supported motion</div><div className="body-note">Head scans and standing holds are excluded. Try another intent or broaden the behavior.</div><button className="btn small-button" disabled={!canStart} onClick={() => start(true)}>Other interactions</button></div> : <div className="empty">{run.phase === 'starting' ? 'Preparing the animal encounter and agent session…' : 'Choose a preset and press Start.'}</div>}
        </div></div>
        {run.runId && <div className={`sequence-status mono ${run.running ? 'running' : ''}`} role="status">{label}{run.note && <div className="body-note">{run.note}</div>}</div>}
        {run.error && <div className="alert compact" role="alert"><span>{run.error}</span><button className="seg" disabled={!canResume} onClick={() => controller.resume()}>Resume</button></div>}
        {run.playbackBlocked && <div className="alert compact"><span>Playback needs permission. The action is waiting.</span><button className="btn small-button" onClick={() => { void video.current?.play().catch(() => undefined); }}>Play clip</button></div>}
        {!searching && run.round?.warnings.length ? <div className="search-warnings mono">{run.round.warnings.map((warning, index) => <div key={index}>{warning}</div>)}</div> : null}
        {selected && !searching && <ReferencePanel key={`${run.round?.round_id}:${selected.candidate.clip_id}`} candidate={selected.candidate} stage={panelStage} autoPlaying={run.running} controlled videoRef={video} rolePlan={selected.role_plan} onPauseRun={() => controller.pause()} actionActive={run.phase === 'acting' && run.execution?.action_id === selected.action_id} actionElapsedMs={run.actionStartedAt == null ? 0 : Math.max(0, clock - run.actionStartedAt)} sequenceLabel={label} onRetry={() => controller.pause('Paused. Resume retries the current reference.')} actionError={null} />}
        {(run.history.length > 0 || run.round) && <details className="session-history"><summary className="label">Agent history · {run.history.length} recent outcomes</summary>{run.round && <button className="seg" disabled={run.stopping || !simulatorReady} onClick={() => controller.replay()}>Replay saved round</button>}{run.history.map(item => <div className="history-entry" key={item.attemptId}><div className="label">{item.replay ? 'Replay · ' : ''}Round {item.round} · {item.interaction} · pass {item.pass} · source #{item.sourceRank}</div><div className="mono">{item.primitive} · {item.status}</div><p>{item.query}</p><p className="body-note">{item.queryReason}</p></div>)}</details>}
      </aside>
    </main>
    <footer className="stage-footer"><ol className="stage-list" aria-label="Demo progress">{stages.map((name, index) => <li key={name} className={`step ${index === 1 && ['empty', 'failed'].includes(run.phase) ? 'bad' : index < stageIndex[run.phase] ? 'done' : index === stageIndex[run.phase] ? 'cur' : ''}`} aria-current={index === stageIndex[run.phase] ? 'step' : undefined}><span className="mono step-number">{String(index + 1).padStart(2, '0')}</span>{name}</li>)}</ol><span className="mono end-tape">{run.adaptive ? 'New encounter + query after the round' : 'Same queue · continuous physics'}</span></footer>
  </div>;
}

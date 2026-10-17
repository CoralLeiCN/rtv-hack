import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, getEncounters, getHealth, searchArchive, type Encounter, type Health, type SearchMode, type SearchResult } from './api';
import { responseIsCurrent, searchDeadlineMs, runReferenceLoop, sequenceSlots, motionLabel, loopPhaseLabel, STAGE_INDEX, STAGES, visibleCandidates, type LoopProgress, type Stage } from './demo';
import { ReferenceCard, ReferencePanel } from './components/ReferencePanel';
import { MicroduckScene, type MicroduckSceneHandle } from './simulator/MicroduckScene';

type Rehearsal = 'nomatch' | 'timeout' | null;
type ActiveLoop = { response: SearchResult; cycle: number };
const idLabel = (number: number) => `encounter-${String(number).padStart(3, '0')}`;

export default function App() {
  const duck = useRef<MicroduckSceneHandle>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<Encounter[]>([]);
  const [scenarioId, setScenarioId] = useState('');
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [bootAttempt, setBootAttempt] = useState(0);
  const [simulatorReady, setSimulatorReady] = useState(false);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);
  const [duckStatus, setDuckStatus] = useState('loading');
  const [stage, setStage] = useState<Stage>('idle');
  const [encounterId, setEncounterId] = useState(idLabel(1));
  const [mode, setMode] = useState<SearchMode>('live');
  const [broadened, setBroadened] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loopRunning, setLoopRunning] = useState(false);
  const [loopProgress, setLoopProgress] = useState<LoopProgress | null>(null);
  const [loopNote, setLoopNote] = useState<string | null>(null);
  const [rankStates, setRankStates] = useState<Record<number, string>>({});
  const [actionStartedAt, setActionStartedAt] = useState<number | null>(null);
  const [rehearsal, setRehearsal] = useState<Rehearsal>(null);
  const [replayKeys, setReplayKeys] = useState<Set<string>>(new Set());
  const [clock, setClock] = useState(new Date());
  const sequence = useRef(1);
  const activeEncounter = useRef(encounterId);
  const requestGeneration = useRef(0);
  const actionGeneration = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const loopController = useRef<AbortController | null>(null);
  const activeLoop = useRef<ActiveLoop | null>(null);
  const visibilityResume = useRef<ActiveLoop | null>(null);
  const currentStage = useRef<Stage>('idle');
  const scenario = scenarios.find(item => item.id === scenarioId) ?? null;
  const selected = result?.candidates.find(item => item.clip_id === selectedId) ?? null;
  const species = [...new Set(scenarios.map(item => item.animal))].sort();
  const speciesScenarios = scenarios.filter(item => item.animal === scenario?.animal);
  const replayAvailable = replayKeys.has(`${scenarioId}:${broadened}`);
  const setCurrentStage = useCallback((value: Stage) => { currentStage.current = value; setStage(value); }, []);

  useEffect(() => {
    const controller = new AbortController();
    setBootstrapError(null);
    setHealth(null);
    Promise.all([getHealth(controller.signal), getEncounters(controller.signal)]).then(([service, catalog]) => {
      if (controller.signal.aborted) return;
      if (!catalog.length) throw new Error('No encounter scenarios are configured.');
      setHealth(service);
      setScenarios(catalog);
      setScenarioId(previous => catalog.some(item => item.id === previous) ? previous : catalog[0].id);
    }).catch(error => {
      if (!controller.signal.aborted) setBootstrapError(error instanceof ApiError ? error.message : 'The demo backend is unavailable. Start the backend, then reconnect.');
    });
    return () => controller.abort();
  }, [bootAttempt]);
  useEffect(() => { const timer = setInterval(() => setClock(new Date()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => () => { pending.current?.abort(); loopController.current?.abort(); duck.current?.stop(); }, []);

  const stopMotion = useCallback(() => {
    loopController.current?.abort();
    loopController.current = null;
    activeLoop.current = null;
    actionGeneration.current += 1;
    duck.current?.stop();
    setLoopRunning(false);
    setActionStartedAt(null);
  }, []);

  const pauseLoop = useCallback((message = 'Stopped. Resume continues from rank 1 without resetting the duck.') => {
    visibilityResume.current = null;
    pending.current?.abort();
    pending.current = null;
    requestGeneration.current += 1;
    stopMotion();
    setLoopNote(message);
    setActionError(null);
    setRankStates(previous => Object.fromEntries(Object.entries(previous).map(([rank, value]) => [rank, ['running', 'waiting'].includes(value) ? 'paused' : value])));
    if (currentStage.current !== 'idle') setCurrentStage('paused');
  }, [stopMotion, setCurrentStage]);

  const pauseForVisibility = useCallback(() => {
    // Abort the sequence before stopping physics so intentional cancellation
    // cannot become a stale movement failure or leave a running rank behind.
    if (activeLoop.current) visibilityResume.current = { ...activeLoop.current, cycle: activeLoop.current.cycle + 1 };
    if (!visibilityResume.current) return;
    stopMotion();
    setActionError(null);
    setRankStates(previous => Object.fromEntries(Object.entries(previous).map(([rank, value]) => [rank, ['running', 'waiting'].includes(value) ? 'paused' : value])));
    setLoopNote('Paused while this tab is hidden. The loop resumes when you return.');
    setCurrentStage('paused');
  }, [stopMotion, setCurrentStage]);

  const invalidate = useCallback(() => {
    visibilityResume.current = null;
    pending.current?.abort();
    pending.current = null;
    requestGeneration.current += 1;
    stopMotion();
    const id = idLabel(++sequence.current);
    activeEncounter.current = id;
    setEncounterId(id);
    setResult(null);
    setSelectedId(null);
    setElapsed(0);
    setSearchError(null);
    setActionError(null);
    setLoopProgress(null);
    setLoopNote(null);
    setRankStates({});
    return id;
  }, [stopMotion]);

  const startLoop = useCallback((response: SearchResult, firstCycle = 1) => {
    if (response.encounter_id !== activeEncounter.current || !duck.current) return;
    visibilityResume.current = null;
    stopMotion();
    setSelectedId(visibleCandidates(response.candidates)[0]?.candidate.clip_id ?? null);
    if (!sequenceSlots(response.candidates).some(slot => slot.supported)) {
      setLoopNote('All three ranks are skipped: no supported video actions were returned.');
      setCurrentStage(visibleCandidates(response.candidates).length ? 'ready' : 'nomatch');
      return;
    }
    if (document.hidden) {
      visibilityResume.current = { response, cycle: firstCycle };
      setLoopNote('Paused while this tab is hidden. The loop resumes when you return.');
      setCurrentStage('paused');
      return;
    }
    const controller = new AbortController();
    loopController.current = controller;
    activeLoop.current = { response, cycle: firstCycle };
    const generation = ++actionGeneration.current;
    const isCurrent = () => !controller.signal.aborted && generation === actionGeneration.current && response.encounter_id === activeEncounter.current;
    setLoopRunning(true);
    setActionError(null);
    setLoopNote(null);
    void runReferenceLoop({
      candidates: response.candidates,
      signal: controller.signal,
      firstCycle,
      prepareCycle: () => duck.current!.prepareCycle(),
      status: () => duck.current?.status() ?? 'failed',
      perform: action => duck.current!.perform({ primitive: action.primitive, evidenceId: action.evidence_id, maxDurationMs: action.max_duration_ms }),
      onProgress: progress => {
        if (!isCurrent()) return;
        activeLoop.current = { response, cycle: progress.cycle };
        setLoopProgress(progress);
        setActionStartedAt(progress.phase === 'running' ? Date.now() : null);
        if (progress.rank != null) setSelectedId(progress.candidate?.clip_id ?? null);
        if (progress.phase === 'preparing') setRankStates({});
        if (progress.rank != null) setRankStates(previous => ({ ...previous, [progress.rank!]: progress.phase }));
        setCurrentStage(progress.phase === 'cycle_complete' ? 'complete' : 'imitating');
      },
    }).catch(error => {
      if (!isCurrent()) return;
      if (document.hidden) { pauseForVisibility(); return; }
      stopMotion();
      setRankStates(previous => Object.fromEntries(Object.entries(previous).map(([rank, value]) => [rank, ['running', 'waiting'].includes(value) ? 'failed' : value])));
      setActionError(error instanceof Error ? error.message : 'The controller could not continue. Reset before resuming.');
      setLoopNote('The loop stopped before another action could begin.');
      setCurrentStage('paused');
    }).finally(() => {
      if (loopController.current === controller) { loopController.current = null; setLoopRunning(false); }
    });
  }, [stopMotion, setCurrentStage, pauseForVisibility]);

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.hidden) { pauseForVisibility(); return; }
      const queued = visibilityResume.current;
      visibilityResume.current = null;
      if (queued && queued.response.encounter_id === activeEncounter.current) startLoop(queued.response, queued.cycle);
    };
    document.addEventListener('visibilitychange', visibilityChanged);
    return () => document.removeEventListener('visibilitychange', visibilityChanged);
  }, [pauseForVisibility, startLoop]);

  const reset = useCallback(() => {
    invalidate();
    duck.current?.reset();
    setCurrentStage('idle');
    setRehearsal(null);
    setBroadened(false);
    setMode('live');
  }, [invalidate, setCurrentStage]);

  const beginSearch = useCallback(async (id: string, broad = false, requestedMode: SearchMode = mode) => {
    if (!scenario || !health || id !== activeEncounter.current) return;
    pending.current?.abort();
    stopMotion();
    const controller = new AbortController();
    pending.current = controller;
    const generation = ++requestGeneration.current;
    setResult(null); setSelectedId(null); setSearchError(null); setActionError(null); setElapsed(0); setBroadened(broad); setMode(requestedMode);
    setCurrentStage('searching');
    const started = performance.now();
    const isCurrent = () => id === activeEncounter.current && generation === requestGeneration.current;
    const tick = setInterval(() => { if (isCurrent()) setElapsed(performance.now() - started); }, 80);
    // Follow the backend's advertised budget, with time to receive its result.
    const timeout = setTimeout(() => controller.abort('deadline'), searchDeadlineMs(health.search_timeout_ms));
    try {
      const response = await searchArchive({ encounter_id: id, scenario_id: scenario.id, mode: requestedMode, broaden: broad }, controller.signal);
      if (!responseIsCurrent(response, id, activeEncounter.current, generation, requestGeneration.current)) return;
      setResult(response);
      setElapsed(response.elapsed_ms);
      setMode(response.mode);
      if (response.mode === 'live') setReplayKeys(previous => new Set([...previous, `${scenario.id}:${broad}`]));
      setCurrentStage(visibleCandidates(response.candidates).length ? 'ready' : 'nomatch');
      startLoop(response);
    } catch (error) {
      if (!isCurrent()) return;
      setElapsed(performance.now() - started);
      setSearchError(controller.signal.aborted ? 'The search deadline was reached. No cached result was substituted.' : error instanceof ApiError ? error.message : 'The demo service could not be reached. Check the connection and retry.');
      if (error instanceof ApiError && error.code === 'replay_unavailable') setReplayKeys(previous => { const next = new Set(previous); next.delete(`${scenario.id}:${broad}`); return next; });
      setCurrentStage('failed');
    } finally { clearInterval(tick); clearTimeout(timeout); }
  }, [scenario, health, mode, setCurrentStage, startLoop, stopMotion]);

  const onEncounterReady = useCallback((id: string) => {
    if (id !== activeEncounter.current || currentStage.current !== 'encounter') return;
    void beginSearch(id, broadened, mode);
  }, [beginSearch, mode, broadened]);
  const onSimulatorReady = useCallback(() => { setSimulatorReady(true); setSimulatorError(null); }, []);
  const onSimulatorError = useCallback((message: string) => { pauseLoop('Simulator unavailable.'); setSimulatorReady(false); setSimulatorError(message); setDuckStatus('failed'); }, [pauseLoop]);
  const onSimulatorStatus = useCallback((status: string) => { setDuckStatus(status); }, []);

  const start = () => {
    if (!scenario || !health || !simulatorReady || !(stage === 'idle' || (stage === 'paused' && !result))) return;
    const id = invalidate();
    setRehearsal(null);
    setCurrentStage('encounter');
    duck.current?.startEncounter({ id, animal: scenario.animal === 'cat' ? 'cat' : 'deer', interaction_partner: 'microduck', behavior_hint: scenario.behavior_hint });
  };
  const chooseScenario = (id: string) => { if (id !== scenarioId) { reset(); setScenarioId(id); setMode('live'); } };
  const chooseSpecies = (animal: string) => { const first = scenarios.find(item => item.animal === animal); if (first) chooseScenario(first.id); };
  const chooseMode = (value: SearchMode) => {
    if (value !== mode || rehearsal) {
      const retainedScope = broadened;
      reset();
      setBroadened(retainedScope);
      setMode(value);
    }
  };
  const select = (id: string) => {
    if (!result || !visibleCandidates(result.candidates).some(item => item.candidate.clip_id === id)) return;
    pauseLoop('Paused for reference inspection. Resume restarts the top-three loop.');
    setSelectedId(id);
    setActionError(null);
  };
  const resume = () => {
    if (!result || rehearsal || !simulatorReady) return;
    startLoop(result, (loopProgress?.cycle ?? 0) + 1);
  };
  const rehearse = (kind: Exclude<Rehearsal, null>) => {
    invalidate(); duck.current?.reset(); setRehearsal(kind); setBroadened(false);
    setCurrentStage(kind === 'nomatch' ? 'nomatch' : 'failed');
    setSearchError(kind === 'timeout' ? 'Rehearsal: the deadline reached state. No archive request was made.' : null);
  };
  const retry = (requestedMode: SearchMode = mode, broad = broadened) => {
    setRehearsal(null);
    const id = invalidate();
    void beginSearch(id, broad, requestedMode);
  };
  const currentIndex = STAGE_INDEX[stage];
  const results = visibleCandidates(result?.candidates ?? []);
  const statusText = rehearsal ? 'UI rehearsal · no request' : stage === 'idle' ? 'idle' : stage === 'encounter' ? 'waiting for encounter zone' : stage === 'searching' ? mode === 'replay' ? 'replaying saved run' : 'live request in flight' : stage === 'nomatch' ? 'no supported match' : stage === 'failed' ? 'search did not finish' : `${result?.mode ?? mode} · ${result?.candidates.length ?? 0} candidates`;
  const timeLabel = stage === 'idle' || stage === 'encounter' || rehearsal ? '— s' : `${(elapsed / 1000).toFixed(2)} s`;
  const canStart = (stage === 'idle' || (stage === 'paused' && !result)) && !!health && !!scenario && simulatorReady;
  const slots = sequenceSlots(result?.candidates ?? []);
  const canResume = !!result && result.encounter_id === activeEncounter.current && slots.some(slot => slot.supported) && simulatorReady;
  const canStop = loopRunning || stage === 'encounter' || stage === 'searching';
  const loopLabel = loopRunning && loopProgress ? `Cycle ${loopProgress.cycle} · ${loopProgress.rank ? `rank ${loopProgress.rank}/3 · ` : ''}${loopPhaseLabel(loopProgress.phase)}${loopProgress.candidate?.action && loopProgress.phase === 'running' ? ` · ${motionLabel(loopProgress.candidate.action.primitive)}` : ''}` : loopNote ?? 'Top-three actions run automatically after search.';
  const eventJson = scenario && stage !== 'idle' ? JSON.stringify({ encounter_id: encounterId, scenario_id: scenario.id, input_mode: 'scripted_scene', animal: scenario.animal, scene_partner: 'microduck', archive_interaction_partner: scenario.interaction_partner ?? scenario.animal, interaction: scenario.interaction ?? scenario.behavior_hint }, null, 2) : '{ awaiting Start }';

  return <div className="app-shell">
    <header className="app-header">
      <div className="brand"><div className="logo" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 28 28" fill="none"><circle cx="12" cy="16" r="8" fill="#101018" /><circle cx="17" cy="9" r="5" fill="#101018" /><path d="M21 9 L27 11 L21 13 Z" fill="#FF7A2F" /><circle cx="18.5" cy="8" r="1.2" fill="#FFD23F" /></svg></div><div><h1 className="display">Ranger Duck</h1><div className="label brand-subtitle">Field unit AV-1 · retrieval-guided imitation</div></div></div>
      <div className="species-tabs"><span className="label">Species</span><div className="tabs" role="group" aria-label="Animal species">{species.map(animal => <button key={animal} className={`tab ${scenario?.animal === animal ? 'on' : ''}`} aria-pressed={scenario?.animal === animal} onClick={() => chooseSpecies(animal)}>{animal}</button>)}</div></div>
      <div className="encounter-tabs"><span className="label">Interaction</span><div className="tabs" role="group" aria-label="Encounter scenario">{speciesScenarios.map(item => <button key={item.id} className={`tab ${scenarioId === item.id ? 'on' : ''}`} aria-pressed={scenarioId === item.id} onClick={() => chooseScenario(item.id)}>{item.label}</button>)}{!scenarios.length && <span className="mono secondary small">Connecting…</span>}</div></div>
      <div className="header-actions"><div className="mono encounter-id">{encounterId}</div><button className="btn primary" disabled={!canStart} onClick={start}>Start</button><button className="btn loop-control" disabled={!canStop && !canResume} onClick={() => canStop ? pauseLoop() : resume()}>{canStop || !canResume ? 'Stop' : 'Resume'}</button><button className="btn" onClick={reset}>Reset</button></div>
    </header>
    <main className="main">
      <section aria-label="Shared simulation scene" className="scene-column">
        <div className="scene">
          <MicroduckScene ref={duck} onReady={onSimulatorReady} onError={onSimulatorError} onStatus={onSimulatorStatus} onEncounterReady={onEncounterReady} searching={stage === 'searching'} />
          {stage === 'searching' && <div className="scan" aria-hidden="true" />}
          <div className="hud scene-hud-top"><span className={`dot ${simulatorReady ? 'live' : ''}`} aria-hidden="true" /><span>SIM · MuJoCo WASM · pretrained policy</span></div>
          <div className="hud scene-clock">{clock.toLocaleDateString('sv-SE')} {clock.toLocaleTimeString('en-GB')}</div>
          <div className="hud scene-hud-bottom"><span>Scenario {scenario?.behavior_hint ?? '—'}</span><span>{encounterId}</span></div>
          <div className="sticker mono duck-status"><span className="label">duck.status()</span><span>{duckStatus}</span></div>
          {simulatorError && <div className="sim-error alert" role="alert"><strong className="display">Simulator unavailable</strong><span>{simulatorError}</span><span className="small">Load the pinned simulator assets and reload this page.</span></div>}
        </div>
        <div className="encounter-details"><div className="encounter-description"><div className="label">Encounter event · supplied by the simulation</div><div className="scene-caption">{stage === 'idle' ? scenario ? `Press Start. One ${scenario.animal} faces Microduck. The duck responds using the top three archive references.` : 'Connecting to the encounter catalog.' : scenario ? `A ${scenario.animal} faces Microduck in a scripted ${scenario.label.toLowerCase()} encounter.` : ''}</div><div className="body-note">One scripted animal · continuous duck physics · video-guided loop</div></div><pre className="mono encounter-json">{eventJson}</pre></div>
        {bootstrapError && <div className="alert compact" role="alert"><span>{bootstrapError}</span><button className="seg" onClick={() => setBootAttempt(value => value + 1)}>Reconnect backend</button></div>}
        {health && !health.live_configured && <div className="setup-note mono">Live archive credentials are not configured on this backend. The simulator can load; live searches will report setup required.</div>}
        {health && health.reviewed_reference_count === 0 && <div className="setup-note mono">Caption-inferred actions are labeled separately from visually reviewed evidence.</div>}
      </section>
      <aside aria-label="Live archive search" className={`archive-column ${selected ? 'has-selection' : ''}`}>
        <div className="archive-heading"><h2 className="display">{stage === 'searching' && <span className="dot live" aria-hidden="true" />}Archive search</h2><div role="group" aria-label="Search mode" className="mode-group"><button className={`seg ${mode === 'live' ? 'on' : ''}`} aria-pressed={mode === 'live'} onClick={() => chooseMode('live')}>Live</button><button className={`seg ${mode === 'replay' ? 'on' : ''}`} aria-pressed={mode === 'replay'} disabled={!replayAvailable && mode !== 'replay'} title={replayAvailable ? 'Replay the previous live search for this encounter' : 'Run this encounter live to save a replay first'} onClick={() => chooseMode('replay')}>Replay</button></div></div>
        <div className="box"><div className="query-heading"><span className="label">Query</span><span className={`label request-status ${stage}`} role="status">{statusText}</span></div><div className="mono query-text">{result?.query ?? (stage === 'idle' ? '—' : rehearsal ? 'UI state rehearsal — no query sent' : (broadened ? scenario?.broader_query : scenario?.query) ?? 'Awaiting query from archive search…')}</div><div className="query-footer"><span className="mono request-route">{mode === 'replay' ? 'Saved live run · current browser session' : `Live archive · ${scenario?.animal === 'cat' ? 'cat–cat' : 'deer–deer'} interactions · server-ranked segments`}</span><span className="mono elapsed">{timeLabel}</span></div>{broadened && <div className="mono broadened-note">Other interactions · same species pair</div>}{result?.mode === 'replay' && <div className="mono replay-note">Replaying a saved result{result.recorded_at ? ` from ${new Date(result.recorded_at).toLocaleTimeString('en-GB')}` : ''}{result.original_elapsed_ms != null ? ` · original live search ${(result.original_elapsed_ms / 1000).toFixed(2)} s` : ''}.</div>}</div>
        <div className="results-section"><div className="results-heading"><span className="label">Top three · {result ? `${results.length} video references` : 'awaiting search'}</span><span className="label secondary">ranked references</span></div><div className="results-list">
          {result && result.candidates.length > 0 ? slots.map(slot => slot.candidate ? <ReferenceCard key={slot.rank} candidate={slot.candidate} rank={slot.rank} selected={selectedId === slot.candidate.clip_id} sequenceState={slot.supported ? rankStates[slot.rank] ?? 'queued' : 'skipped'} onSelect={() => select(slot.candidate!.clip_id)} /> : <div className="missing-reference mono" key={slot.rank}>Rank {slot.rank} · skipped · no usable segment returned</div>) : stage === 'nomatch' ? <div className="alert"><div className="display alert-title">No supported imitation found</div><div className="body-note">{rehearsal ? 'Rehearsal only. No archive request was made. Microduck holds its pose.' : 'No usable reference segments were returned. Microduck holds its pose.'}</div><button className="btn small-button" disabled={!health || broadened} onClick={() => retry('live', true)}>Other interactions</button></div> : stage === 'failed' ? <div className="alert"><div className="display alert-title">Search did not finish</div><div className="body-note">{searchError}</div><div className="alert-actions"><button className="btn small-button" disabled={!health} onClick={() => retry('live')}>Retry live</button><button className="btn small-button" disabled={!replayAvailable} onClick={() => retry('replay')}>Use replay</button></div></div> : <div className="empty">{stage === 'searching' ? mode === 'replay' ? 'Loading the saved archive results…' : 'Ranking archive segments…' : stage === 'encounter' ? 'Animal entering the encounter zone. Search starts on arrival.' : 'Choose an encounter and press Start.'}</div>}
          {result?.status === 'no_supported_imitation' && <div className="unsupported-summary"><span className="label pink">No supported imitation found</span><span className="body-note">These clips can be watched. No supported action was returned for these interaction references.</span>{!broadened && <button className="seg" onClick={() => retry('live', true)}>Other interactions</button>}</div>}
        </div></div>
        {result && <div className={`sequence-status mono ${loopRunning ? 'running' : ''}`} role="status">{loopLabel}</div>}
        {result?.warnings.length ? <div className="search-warnings mono">{result.warnings.map((warning, index) => <div key={index}>{warning}</div>)}</div> : null}
        {selected ? <ReferencePanel key={`${result?.search_id}:${selected.clip_id}`} candidate={selected} stage={stage} autoPlaying={loopRunning} actionActive={loopRunning && loopProgress?.phase === 'running' && loopProgress.candidate?.clip_id === selected.clip_id} actionElapsedMs={actionStartedAt == null ? 0 : Math.max(0, clock.getTime() - actionStartedAt)} sequenceLabel={loopLabel} onRetry={() => retry('live')} actionError={actionError} /> : results.length ? <div className="empty">{loopLabel}</div> : null}
      </aside>
    </main>
    <footer className="stage-footer"><ol className="stage-list" aria-label="Demo progress">{STAGES.map((label, index) => <li key={label} className={`step ${index === 1 && (stage === 'nomatch' || stage === 'failed') ? 'bad' : index < currentIndex ? 'done' : index === currentIndex ? 'cur' : ''}`} aria-current={index === currentIndex ? 'step' : undefined}><span className="mono step-number">{String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol><div className="rehearsal-controls"><span className="label secondary">Rehearse UI</span><button className="seg" onClick={() => rehearse('nomatch')}>No match</button><button className="seg" onClick={() => rehearse('timeout')}>Timeout</button><span className="mono end-tape">End of tape · be kind, rewind</span></div></footer>
  </div>;
}

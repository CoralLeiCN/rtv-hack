import { ApiError, readResponse, type Primitive, type SearchScope } from './api';
import type { CompanionBehavior } from './simulator/clearing';
import type { DuckStatus } from './simulator/adapter';
import { isActiveImitation } from './demo';

export interface LoopCandidate {
  candidate_id: string; rank: number; caption: string;
  observed_behavior: string | null; evidence_basis: string | null;
  allowed_actions: Primitive[]; unavailable_reason: string | null;
}
export interface RolePlan {
  grounding: 'caption_roles' | 'single_behavior' | 'insufficient_evidence';
  companion: { subject: string; evidence: string };
  duck: { subject: string; evidence: string };
  duck_behavior: 'still' | 'looking' | 'moving' | 'feeding' | 'nodding' | 'sitting' | 'unknown';
  companion_behavior: CompanionBehavior; companion_duration_ms: number;
  timing: 'together' | 'companion_first' | 'duck_first';
}
export interface AgentCycle {
  session_id: string; cycle_id: string; cycle: number;
  query: string; query_reason: string; response_reason: string;
  search_scope?: SearchScope;
  candidates: LoopCandidate[]; role_plan: RolePlan;
  action: { primitive: Primitive; max_duration_ms: number; evidence_id: string };
  clip: { clip_id: string; video_url: string; caption: string; rank: number;
    dataset?: string | null; dataset_id?: string | null;
    observed_behavior: string; evidence_basis: string; start_sec: number; end_sec: number };
}
export interface ReactionOutcome {
  cycle_id: string; primitive: Primitive; status: 'completed' | 'failed' | 'cancelled';
  playback: 'ended' | 'failed' | 'cancelled';
  companion: { behavior: CompanionBehavior; status: 'completed' | 'failed' | 'cancelled' };
  state: { status: DuckStatus; position: number[]; head_yaw: number; simulation_time: number };
}
export function reactionState(telemetry: ReactionOutcome['state']): ReactionOutcome['state'] {
  const { status, position, head_yaw, simulation_time } = telemetry;
  // Live control telemetry also includes navigation; the outcome API retains
  // its strict, stable state contract.
  return { status, position, head_yaw, simulation_time };
}
export async function loopRequest<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return readResponse(await fetch(`/demo-api/loop${path}`, {
    method: 'POST', credentials: 'same-origin', signal: signal ?? AbortSignal.timeout(10000),
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }));
}
export function checkActive(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException('Loop stopped.', 'AbortError');
}
function requireActiveMotion(cycle: AgentCycle) {
  if (!isActiveImitation(cycle.action?.primitive)) throw new ApiError('passive_behavior_excluded', 'No active supported motion was selected. Head scans and standing holds are excluded. Try another search.', true);
}
export function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    checkActive(signal);
    const abort = () => { clearTimeout(timer); reject(new DOMException('Loop stopped.', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}

/** Serialized coordinator; no next search until playback, physics, and outcome acknowledgement finish. */
export async function runAgentLoop(options: {
  signal: AbortSignal; next(): Promise<AgentCycle>;
  execute(cycle: AgentCycle): Promise<ReactionOutcome>;
  report(outcome: ReactionOutcome): Promise<unknown>;
  onSearch(attempt: number): void;
  retryDelayMs?: number;
}) {
  let failures = 0;
  while (true) {
    checkActive(options.signal);
    options.onSearch(failures + 1);
    let cycle: AgentCycle;
    try { cycle = await options.next(); }
    catch (error) {
      checkActive(options.signal);
      // Configuration, cancellation, and schema failures require intervention.
      if (++failures >= 3 || !(error instanceof ApiError) || !['no_loop_match', 'invalid_agent_action', 'invalid_agent_query', 'upstream_timeout', 'upstream_error', 'loop_timeout'].includes(error.code)) throw error;
      await delay(options.retryDelayMs ?? 1000, options.signal);
      continue;
    }
    checkActive(options.signal);
    requireActiveMotion(cycle);
    const outcome = await options.execute(cycle);
    checkActive(options.signal);
    await options.report(outcome);
    checkActive(options.signal);
    if (outcome.status !== 'completed') throw new Error('Playback or the duck action did not complete. The loop is paused.');
    failures = 0;
  }
}

/** Both video roles must finish; cancellation cannot start a delayed second role. */
export async function runRoleActions(plan: RolePlan, signal: AbortSignal,
  companion: () => Promise<void>, duck: () => Promise<void>) {
  checkActive(signal);
  if (plan.timing === 'together') await Promise.all([companion(), duck()]);
  else {
    await (plan.timing === 'companion_first' ? companion() : duck());
    checkActive(signal);
    await (plan.timing === 'companion_first' ? duck() : companion());
  }
  checkActive(signal);
}

/** Playback starts the action; both must finish, with bounded waiting and abort cleanup. */
export async function playAndReact(video: HTMLVideoElement, cycle: AgentCycle, signal: AbortSignal,
  perform: () => Promise<void>, onBlocked: () => void) {
  checkActive(signal);
  requireActiveMotion(cycle);
  let cleanup = () => {};
  let action: Promise<void> | null = null;
  const finished = new Promise<void>((resolve, reject) => {
    let ended = false, reacted = false;
    const complete = () => { if (ended && reacted) resolve(); };
    const playing = () => {
      if (action || signal.aborted) return;
      action = perform();
      action.then(() => { reacted = true; complete(); }, reject);
    };
    const onEnded = () => { ended = true; complete(); };
    const failed = () => reject(new Error('Reference playback failed.'));
    const aborted = () => reject(new DOMException('Loop stopped.', 'AbortError'));
    const timer = setTimeout(() => reject(new Error('Playback did not complete within two minutes.')), 130000);
    video.addEventListener('playing', playing);
    video.addEventListener('ended', onEnded);
    video.addEventListener('error', failed);
    signal.addEventListener('abort', aborted, { once: true });
    cleanup = () => {
      clearTimeout(timer);
      video.removeEventListener('playing', playing); video.removeEventListener('ended', onEnded);
      video.removeEventListener('error', failed); signal.removeEventListener('abort', aborted);
      video.pause();
    };
    video.muted = true;
    video.src = cycle.clip.video_url;
    video.load();
    video.play().catch(error => {
      if (signal.aborted) return;
      if (error instanceof DOMException && error.name === 'NotAllowedError') onBlocked();
      else reject(new Error('Reference playback could not start.'));
    });
  });
  try { await finished; } finally { cleanup(); }
}

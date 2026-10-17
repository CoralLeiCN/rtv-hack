import { ApiError, readResponse, type Candidate, type Health, type SearchResult, type SearchScope } from './api';
import type { ReactionOutcome, RolePlan } from './agentLoop';

export interface RunInput { run_id: string; animal: 'cat' | 'deer'; scenario_id: string; intent: string; adaptive: boolean; }
export interface Execution { action_id: string; attempt_id: string; }
export interface RunScenario {
  id: string; label: string; animal: 'cat' | 'deer'; behavior_hint: string;
  interaction: string; description: string; interaction_partner?: string;
}
export interface RunCursor {
  run_id: string;
  status: 'ready' | 'needs_plan' | 'paused';
  adaptive: boolean;
  round_id: string | null;
  round: number;
  pass: number;
  execution: Execution | null;
}
export interface RunPlan {
  run_id: string; round_id: string; round: number; plan_id: string;
  scenario: RunScenario;
  query: string; query_reason: string; search_scope?: SearchScope;
  timings?: { query_agent_ms?: number; [key: string]: number | undefined };
}
export interface QueueAction { action_id: string; candidate: Candidate; role_plan: RolePlan; }
export interface RunRound extends SearchResult {
  run_id: string; round_id: string; round: number; pass: number;
  scenario: RunScenario;
  queue: QueueAction[]; execution: Execution | null;
  run_status: 'ready' | 'paused';
  adaptive?: boolean;
  timings?: { query_agent_ms?: number; [key: string]: number | undefined };
}
export type RunOutcome = Omit<ReactionOutcome, 'cycle_id'> & { round_id: string; action_id: string; attempt_id: string };
export interface SessionApi {
  create(input: RunInput, signal: AbortSignal): Promise<RunCursor>;
  plan(id: string, broaden: boolean, signal: AbortSignal): Promise<RunPlan>;
  search(id: string, planId: string, signal: AbortSignal): Promise<RunRound>;
  outcome(id: string, outcome: RunOutcome, signal: AbortSignal): Promise<RunCursor>;
  pause(id: string): Promise<RunCursor>;
  resume(id: string, signal: AbortSignal): Promise<RunCursor>;
  adaptive(id: string, adaptive: boolean): Promise<RunCursor>;
  replay(id: string, signal: AbortSignal): Promise<RunRound>;
}

export function runDeadline(value: unknown, maximum: number): number {
  return (typeof value === 'number' && Number.isFinite(value) && value >= 1000 && value <= maximum ? value : maximum) + 5000;
}
async function request<T>(path: string, body: unknown, signal: AbortSignal | undefined, timeout: number): Promise<T> {
  const bounded = new AbortController();
  const abort = () => bounded.abort();
  if (signal?.aborted) throw new DOMException('Run paused.', 'AbortError');
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => bounded.abort('deadline'), timeout);
  try {
    const response = await fetch(`/demo-api/runs${path}`, {
      method: 'POST', credentials: 'same-origin', signal: bounded.signal,
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await readResponse<T>(response);
    if (signal?.aborted) throw new DOMException('Run paused.', 'AbortError');
    return result;
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Run paused.', 'AbortError');
    if (bounded.signal.reason === 'deadline') throw new ApiError('run_timeout', 'The agent or archive request reached its deadline. Resume to retry.', true);
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}

export function sessionApi(health: Health): SessionApi {
  const path = (id: string, operation: string) => `/${encodeURIComponent(id)}/${operation}`;
  return {
    create: (input, signal) => request('', input, signal, 15000),
    plan: (id, broaden, signal) => request(path(id, 'plan'), { broaden }, signal, runDeadline(health.encounter_plan_timeout_ms, 60000)),
    search: (id, plan_id, signal) => request(path(id, 'search'), { plan_id }, signal, runDeadline(health.encounter_timeout_ms, 180000)),
    outcome: (id, body, signal) => request(path(id, 'outcome'), body, signal, 15000),
    pause: id => request(path(id, 'pause'), undefined, undefined, 15000),
    resume: (id, signal) => request(path(id, 'resume'), undefined, signal, 15000),
    adaptive: (id, adaptive) => request(path(id, 'adaptive'), { adaptive }, undefined, 15000),
    replay: (id, signal) => request(path(id, 'replay'), undefined, signal, 15000),
  };
}

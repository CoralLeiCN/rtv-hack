import { ApiError, planEncounter, searchArchive, type EncounterPlan, type Health, type SearchMode } from './api';
import { searchDeadlineMs } from './demo';

export function encounterDeadlineMs(value: number | undefined, phase: 'plan' | 'search'): number {
  const maximum = phase === 'plan' ? 60000 : 180000;
  return (typeof value === 'number' && Number.isFinite(value) && value >= 1000 && value <= maximum ? value : maximum) + 5000;
}

function check(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException('Encounter request cancelled.', 'AbortError');
}
async function bounded<T>(request: (signal: AbortSignal) => Promise<T>, signal: AbortSignal, milliseconds: number, phase: string): Promise<T> {
  check(signal);
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => controller.abort('deadline'), milliseconds);
  try {
    const value = await request(controller.signal);
    check(signal);
    if (controller.signal.aborted) throw new ApiError('encounter_timeout', `${phase} reached its deadline. Retry to create a new plan.`, true);
    return value;
  } catch (error) {
    check(signal);
    if (controller.signal.reason === 'deadline') throw new ApiError('encounter_timeout', `${phase} reached its deadline. Retry to create a new plan.`, true);
    throw error;
  } finally { clearTimeout(timer); signal.removeEventListener('abort', cancel); }
}

/** Publish the real generated query before the archive/action-planning request. */
export async function searchEncounter(input: { encounter_id: string; scenario_id: string; mode: SearchMode; broaden: boolean }, options: {
  signal: AbortSignal;
  health: Health;
  onPlan(plan: EncounterPlan): void;
}) {
  const { signal, health } = options;
  let plan: EncounterPlan | undefined;
  if (input.mode === 'live') {
    plan = await bounded(requestSignal => planEncounter({ encounter_id: input.encounter_id, scenario_id: input.scenario_id, broaden: input.broaden }, requestSignal),
      signal, encounterDeadlineMs(health.encounter_plan_timeout_ms, 'plan'), 'Agent query planning');
    if (plan.encounter_id !== input.encounter_id || typeof plan.plan_id !== 'string' || !plan.plan_id || typeof plan.query !== 'string' || !plan.query.trim()) throw new ApiError('invalid_encounter_plan', 'The agent returned an invalid encounter plan. Retry to create a new plan.', true);
    check(signal);
    options.onPlan(plan);
  }
  check(signal);
  return bounded(requestSignal => searchArchive({ ...input, ...(plan ? { plan_id: plan.plan_id } : {}) }, requestSignal), signal,
    input.mode === 'replay' ? searchDeadlineMs(health.search_timeout_ms) : encounterDeadlineMs(health.encounter_timeout_ms, 'search'), 'Archive search and agent action planning');
}

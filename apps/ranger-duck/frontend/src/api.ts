export type SearchMode = 'live' | 'replay';
export type Primitive = 'ground_pick' | 'short_walk' | 'stand_hold' | 'head_scan' | 'head_nod' | 'sit_cycle';
export interface SearchScope {
  tags: string[];
  requested_dataset_id?: string;
  dataset_filter_applied?: boolean;
}

export interface Health {
  status: string;
  api_version: string;
  live_configured: boolean;
  reviewed_reference_count: number;
  search_timeout_ms?: number;
  loop_agent_available?: boolean;
  loop_cycle_timeout_ms?: number;
  encounter_agent_available?: boolean;
  encounter_plan_timeout_ms?: number;
  encounter_timeout_ms?: number;
}
export interface Encounter {
  id: string;
  label: string;
  animal: string;
  interaction_partner?: string;
  interaction?: string;
  behavior_hint: string;
  description: string;
  input_mode: 'scripted_scene';
  query?: string;
  broader_query?: string;
}
export interface Candidate {
  rank?: number;
  clip_id: string;
  video_url: string;
  caption: string;
  caption_hash?: string;
  similarity: number | null;
  review_status: 'reviewed' | 'unreviewed' | 'stale';
  eligibility_reason: string;
  animal: string | null;
  reviewed_behavior: string | null;
  review_reason?: string | null;
  action_basis?: 'reviewed' | 'video_caption' | null;
  action_reason?: string | null;
  action_planner?: 'agent';
  agent_reason?: string | null;
  evidence_excerpt?: string | null;
  inferred_behavior?: string | null;
  interaction_partner?: string | null;
  provenance: {
    dataset: string | null;
    dataset_id?: string | null;
    source_label: string;
    parent_id: string | null;
    segment_start_sec: number | null;
    segment_end_sec: number | null;
  };
  action: null | { primitive: Primitive; evidence_id: string; max_duration_ms: number };
}
export interface SearchResult {
  encounter_id: string;
  search_id: string;
  mode: SearchMode;
  status: 'ok' | 'no_supported_imitation' | 'no_results';
  query: string;
  query_basis?: 'agent';
  query_reason?: string;
  action_planner?: 'agent';
  agent_plan?: { summary: string };
  search_scope?: SearchScope;
  match_type?: 'species' | 'broader_category' | 'species_interaction' | 'broader_behavior';
  elapsed_ms: number;
  original_elapsed_ms?: number;
  recorded_at?: string;
  candidates: Candidate[];
  warnings: string[];
}
export interface EncounterPlan {
  encounter_id: string;
  plan_id: string;
  query: string;
  query_reason: string;
  query_basis: 'agent';
  search_scope?: SearchScope;
}
export class ApiError extends Error {
  constructor(public code: string, message: string, public retryable = false) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function readResponse<T>(response: Response): Promise<T> {
  let body;
  try { body = await response.json(); }
  catch { throw new ApiError('invalid_response', 'The demo service returned an unreadable response. Please retry.', true); }
  if (!response.ok) {
    throw new ApiError(body?.error?.code ?? 'request_failed', body?.error?.message ?? 'The demo request failed. Please retry.', body?.error?.retryable ?? true);
  }
  return body as T;
}
export async function getHealth(signal?: AbortSignal): Promise<Health> {
  return readResponse(await fetch('/demo-api/health', { credentials: 'same-origin', signal }));
}
export async function getEncounters(signal?: AbortSignal): Promise<Encounter[]> {
  const response = await readResponse<{ encounters: Encounter[] }>(await fetch('/demo-api/encounters', { credentials: 'same-origin', signal }));
  return response.encounters;
}
export async function searchArchive(input: {
  encounter_id: string;
  scenario_id: string;
  mode: SearchMode;
  broaden: boolean;
  plan_id?: string;
}, signal: AbortSignal): Promise<SearchResult> {
  return readResponse(await fetch('/demo-api/search', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  }));
}
export async function planEncounter(input: { encounter_id: string; scenario_id: string; broaden: boolean }, signal: AbortSignal): Promise<EncounterPlan> {
  return readResponse(await fetch('/demo-api/encounter-plan', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input), signal,
  }));
}
export async function cancelEncounter(encounterId: string): Promise<void> {
  await fetch(`/demo-api/encounters/${encodeURIComponent(encounterId)}/cancel`, {
    method: 'POST', credentials: 'same-origin', signal: AbortSignal.timeout(10000),
  });
}

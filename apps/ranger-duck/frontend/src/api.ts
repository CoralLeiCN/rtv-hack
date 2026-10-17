export type SearchMode = 'live' | 'replay';
export type Primitive = 'ground_pick' | 'short_walk' | 'stand_hold' | 'sit' | 'head_scan';

export interface Health {
  status: string;
  api_version: string;
  live_configured: boolean;
  reviewed_reference_count: number;
}
export interface Encounter {
  id: string;
  label: string;
  animal: string;
  behavior_hint: string;
  description: string;
  input_mode: 'scripted_scene';
  query?: string;
  broader_query?: string;
}
export interface Candidate {
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
  provenance: {
    dataset: string | null;
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
  match_type?: 'species' | 'broader_category';
  elapsed_ms: number;
  original_elapsed_ms?: number;
  recorded_at?: string;
  candidates: Candidate[];
  warnings: string[];
}
export class ApiError extends Error {
  constructor(public code: string, message: string, public retryable = false) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readResponse<T>(response: Response): Promise<T> {
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
}, signal: AbortSignal): Promise<SearchResult> {
  return readResponse(await fetch('/demo-api/search', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  }));
}

import type { Candidate, SearchResult } from './api';

export type Stage = 'idle' | 'encounter' | 'searching' | 'ready' | 'imitating' | 'complete' | 'nomatch' | 'failed';
export const STAGES = ['Encounter', 'Searching', 'Reference ready', 'Imitating', 'Complete'];
export const STAGE_INDEX: Record<Stage, number> = { idle: -1, encounter: 0, searching: 1, ready: 2, imitating: 3, complete: 4, nomatch: 1, failed: 1 };

export function searchDeadlineMs(backendBudget: unknown): number {
  const validBudget = typeof backendBudget === 'number' && Number.isFinite(backendBudget) && backendBudget >= 1000 && backendBudget <= 60000;
  // Leave time for the backend's bounded search to return its structured error.
  // Older backends omit the field; malformed values must not cause early aborts.
  return (validBudget ? backendBudget : 30000) + 5000;
}

export function isEligible(candidate: Candidate | null | undefined): candidate is Candidate & { action: NonNullable<Candidate['action']> } {
  return !!candidate && candidate.review_status === 'reviewed' && candidate.eligibility_reason === 'reviewed_match' && !!candidate.action;
}
// Keep the original ranking visible, while making a reviewed result beyond the
// first three reachable. Returning its original rank avoids a false rank claim.
export function visibleCandidates(candidates: Candidate[]): { candidate: Candidate; rank: number }[] {
  const list = candidates.slice(0, 3).map((candidate, i) => ({ candidate, rank: i + 1 }));
  if (!list.some(({ candidate }) => isEligible(candidate))) {
    const index = candidates.findIndex(isEligible);
    if (index >= 3) list[2] = { candidate: candidates[index], rank: index + 1 };
  }
  return list;
}
export function responseIsCurrent(result: SearchResult, encounterId: string, activeEncounterId: string, generation: number, activeGeneration: number): boolean {
  return result.encounter_id === encounterId && encounterId === activeEncounterId && generation === activeGeneration;
}
export function mmss(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const value = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}
// Adapted from the existing search app's web/api.js formatTime: round to
// milliseconds before splitting fields so short archive intervals stay visible.
// Keep this design's zero-padded minutes rather than the search app's m:ss.
export function segmentTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const milliseconds = Math.round(seconds * 1000);
  const whole = Math.floor(milliseconds / 1000);
  const hours = Math.floor(whole / 3600);
  const minutes = String(Math.floor((whole % 3600) / 60)).padStart(2, '0');
  const secs = String(whole % 60).padStart(2, '0');
  const fraction = milliseconds % 1000;
  const suffix = fraction ? `.${String(fraction).padStart(3, '0').replace(/0+$/, '')}` : '';
  return `${hours ? `${hours}:` : ''}${minutes}:${secs}${suffix}`;
}
export function eligibilityNote(candidate: Candidate): string {
  const reasons: Record<string, string> = {
    not_reviewed: 'This segment has no visual review. Copy stays unavailable until its animal and behavior have been checked.',
    reference_changed: 'The reference changed after review. A new visual review is needed before Copy is available.',
    incomplete_metadata: 'The source identity or segment timing is incomplete. Playback may be available, but this result cannot authorize imitation.',
    unsupported_behavior: 'The reviewed behavior has no supported duck movement.',
    species_mismatch: 'The reviewed animal does not match this encounter. It can be watched, but it cannot authorize imitation.',
  };
  return reasons[candidate.eligibility_reason] ?? 'Only a current, reviewed reference returned by this search can move the duck.';
}

import type { Candidate, Primitive, SearchResult } from './api';

export type Stage = 'idle' | 'encounter' | 'searching' | 'ready' | 'imitating' | 'complete' | 'paused' | 'nomatch' | 'failed';
export const STAGES = ['Encounter', 'Searching', 'Top three ready', 'Auto imitation', 'Repeat'];
export const STAGE_INDEX: Record<Stage, number> = { idle: -1, encounter: 0, searching: 1, ready: 2, imitating: 3, complete: 4, paused: 3, nomatch: 1, failed: 1 };

export function searchDeadlineMs(backendBudget: unknown): number {
  const validBudget = typeof backendBudget === 'number' && Number.isFinite(backendBudget) && backendBudget >= 1000 && backendBudget <= 60000;
  // Leave time for the backend's bounded search to return its structured error.
  // Older backends omit the field; malformed values must not cause early aborts.
  return (validBudget ? backendBudget : 30000) + 5000;
}

export function isEligible(candidate: Candidate | null | undefined): candidate is Candidate & { action: NonNullable<Candidate['action']> } {
  if (!candidate?.action || typeof candidate.action.evidence_id !== 'string' || !candidate.action.evidence_id.trim()) return false;
  if (!['ground_pick', 'short_walk', 'stand_hold', 'head_scan'].includes(candidate.action.primitive)) return false;
  if (!Number.isFinite(candidate.action.max_duration_ms) || candidate.action.max_duration_ms <= 0) return false;
  return (candidate.action_basis === 'video_caption' && candidate.eligibility_reason === 'caption_interaction_match') ||
    ((candidate.action_basis === 'reviewed' || candidate.action_basis == null) && candidate.review_status === 'reviewed' && candidate.eligibility_reason === 'reviewed_match');
}
// The automatic sequence is exactly the first three ranked results. A later
// eligible result must never silently replace an unsupported top-three entry.
export function visibleCandidates(candidates: Candidate[]): { candidate: Candidate; rank: number }[] {
  return candidates.map((candidate, i) => ({ candidate, rank: candidate.rank ?? i + 1 }))
    .filter(({ rank }) => Number.isInteger(rank) && rank >= 1 && rank <= 3)
    .sort((left, right) => left.rank - right.rank)
    .filter((entry, index, list) => list.findIndex(item => item.rank === entry.rank) === index);
}

export type LoopPhase = 'preparing' | 'waiting' | 'running' | 'completed' | 'skipped' | 'cycle_complete';
export function motionLabel(primitive: Primitive): string {
  return { stand_hold: 'Holding a steady stance', head_scan: 'Looking around', short_walk: 'Walking / turning within the arena', ground_pick: 'Dipping toward the ground' }[primitive];
}
export function loopPhaseLabel(phase: LoopPhase): string {
  return { preparing: 'waiting for balance', waiting: 'waiting for balance', running: 'active', completed: 'action complete', skipped: 'skipped', cycle_complete: 'continuing to the next pass' }[phase];
}
export function behaviorLabel(value: string | null | undefined): string {
  if (!value) return 'Supported behavior';
  const labels: Record<string, string> = { watching_partner: 'Watching companion', orienting_to_partner: 'Turning toward companion', shared_attention: 'Shared attention', object_attention: 'Watching an object', focal_head_movement: 'Head movement', focal_walking: 'Walking', focal_foraging: 'Foraging' };
  if (labels[value]) return labels[value];
  const words = value.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}
export interface LoopProgress { cycle: number; rank: number | null; phase: LoopPhase; candidate: Candidate | null; }
export interface SequenceSlot { rank: number; candidate: Candidate | null; supported: boolean; }
export function sequenceSlots(candidates: Candidate[]): SequenceSlot[] {
  const ranked = visibleCandidates(candidates);
  return [1, 2, 3].map(rank => {
    const candidate = ranked.find(item => item.rank === rank)?.candidate ?? null;
    return { rank, candidate, supported: isEligible(candidate) };
  });
}
function cancelled(): DOMException { return new DOMException('The automatic sequence was stopped.', 'AbortError'); }
function checkSignal(signal: AbortSignal): void { if (signal.aborted) throw cancelled(); }

export function interruptible<T>(operation: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(cancelled());
  return new Promise((resolve, reject) => {
    const abort = () => { signal.removeEventListener('abort', abort); reject(cancelled()); };
    signal.addEventListener('abort', abort, { once: true });
    operation.then(value => { signal.removeEventListener('abort', abort); resolve(value); }, error => { signal.removeEventListener('abort', abort); reject(error); });
  });
}
export function waitFor(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(cancelled());
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(cancelled()); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}
async function waitUntilReady(status: () => string, signal: AbortSignal, timeoutMs: number): Promise<void> {
  const started = Date.now();
  while (true) {
    checkSignal(signal);
    const current = status();
    if (current === 'ready' || current === 'complete') return;
    if (current === 'failed') throw new Error('The simulator needs recovery. The automatic loop has stopped.');
    if (Date.now() - started >= timeoutMs) throw new Error('The simulator did not become ready. Reset before resuming the loop.');
    await waitFor(100, signal);
  }
}

export async function runReferenceLoop(options: {
  candidates: Candidate[];
  signal: AbortSignal;
  prepareCycle: () => Promise<void>;
  status: () => string;
  perform: (action: NonNullable<Candidate['action']>) => Promise<void>;
  onProgress: (progress: LoopProgress) => void;
  firstCycle?: number;
  transitionMs?: number;
  readinessTimeoutMs?: number;
}): Promise<void> {
  const { signal } = options;
  const slots = sequenceSlots(options.candidates);
  if (!slots.some(slot => slot.supported)) return;
  let cycle = options.firstCycle ?? 1;
  while (true) {
    checkSignal(signal);
    options.onProgress({ cycle, rank: null, phase: 'preparing', candidate: null });
    checkSignal(signal);
    await interruptible(options.prepareCycle(), signal);
    await waitUntilReady(options.status, signal, options.readinessTimeoutMs ?? 20000);
    for (const slot of slots) {
      checkSignal(signal);
      if (!slot.supported || !isEligible(slot.candidate)) {
        options.onProgress({ cycle, rank: slot.rank, phase: 'skipped', candidate: slot.candidate });
        await waitFor(options.transitionMs ?? 450, signal);
        continue;
      }
      options.onProgress({ cycle, rank: slot.rank, phase: 'waiting', candidate: slot.candidate });
      await waitUntilReady(options.status, signal, options.readinessTimeoutMs ?? 20000);
      checkSignal(signal);
      options.onProgress({ cycle, rank: slot.rank, phase: 'running', candidate: slot.candidate });
      checkSignal(signal);
      await interruptible(options.perform(slot.candidate.action), signal);
      checkSignal(signal);
      options.onProgress({ cycle, rank: slot.rank, phase: 'completed', candidate: slot.candidate });
      await waitFor(options.transitionMs ?? 450, signal);
    }
    options.onProgress({ cycle, rank: null, phase: 'cycle_complete', candidate: null });
    await waitFor(options.transitionMs ?? 450, signal);
    cycle += 1;
  }
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
    not_reviewed: 'This result has no supported evidence-based action. It is skipped in the automatic loop.',
    species_pair_not_established: 'The caption does not establish two animals of the selected species. This rank is skipped.',
    directed_interaction_not_established: 'The caption does not describe a supported action for an animal in this pair. This rank is skipped.',
    negated_or_uncertain_interaction: 'The caption denies the interaction or describes it as uncertain. This rank is skipped.',
    unsupported_interaction_behavior: 'The described interaction has no supported duck movement. This rank is skipped.',
    unsupported_retreat: 'The clip describes moving away, but the duck controller cannot reliably walk backward. This rank is skipped.',
    review_missing_interaction: 'This review does not establish the selected animal pair and interaction. This rank is skipped.',
    reference_changed: 'The reviewed reference changed. This action is skipped until the evidence is checked again.',
    incomplete_metadata: 'The source identity or segment timing is incomplete. Playback may be available, but this result cannot authorize imitation.',
    unsupported_behavior: 'The video behavior has no supported duck movement. This rank is skipped.',
    species_mismatch: 'The reviewed animal does not match this encounter. It can be watched, but it cannot authorize imitation.',
  };
  return reasons[candidate.eligibility_reason] ?? 'No supported action was returned for this reference. This rank is skipped.';
}

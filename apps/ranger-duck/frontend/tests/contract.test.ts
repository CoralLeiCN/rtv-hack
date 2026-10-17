import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getEncounters, getHealth, searchArchive, type Candidate, type SearchResult } from '../src/api';
import { isEligible, mmss, responseIsCurrent, runReferenceLoop, searchDeadlineMs, segmentTime, sequenceSlots, visibleCandidates, waitFor, type LoopProgress } from '../src/demo';

const candidate = (overrides: Partial<Candidate> = {}): Candidate => ({
  clip_id: 'opaque-clip', video_url: '/demo-api/clips/opaque-clip/video', caption: 'An animal lowers its head.', caption_hash: 'sha256:test', similarity: 0.42,
  review_status: 'unreviewed', eligibility_reason: 'not_reviewed', animal: null, reviewed_behavior: null,
  provenance: { dataset: null, source_label: 'Reference clip', parent_id: null, segment_start_sec: 12, segment_end_sec: 27 }, action: null,
  ...overrides,
});
const reviewed = (id = 'reviewed'): Candidate => candidate({ clip_id: id, review_status: 'reviewed', eligibility_reason: 'reviewed_match', animal: 'deer', reviewed_behavior: 'feeding', action: { primitive: 'ground_pick', evidence_id: 'reference-1', max_duration_ms: 8000 } });
const result: SearchResult = { encounter_id: 'encounter-002', search_id: 'search-1', mode: 'live', status: 'ok', query: 'deer feeding', elapsed_ms: 4000, candidates: [reviewed()], warnings: [] };

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('evidence authorization and asynchronous invalidation', () => {
  it('never enables copying from a caption or review badge alone', () => {
    expect(isEligible(candidate())).toBe(false);
    expect(isEligible(candidate({ review_status: 'reviewed', reviewed_behavior: 'feeding' }))).toBe(false);
    expect(isEligible({ ...reviewed(), eligibility_reason: 'species_mismatch', action: null })).toBe(false);
    expect(isEligible({ ...reviewed(), review_status: 'stale' })).toBe(false);
    expect(isEligible(reviewed())).toBe(true);
  });
  it('takes the first three compatible actions across all source ranks without empty slots', () => {
    const candidates = [candidate({ clip_id: '1', rank: 1 }), { ...reviewed('2'), rank: 2 }, candidate({ clip_id: '3', rank: 3 }), { ...reviewed('4'), rank: 4 }, { ...reviewed('6'), rank: 6 }, { ...reviewed('7'), rank: 7 }];
    expect(visibleCandidates(candidates).map(item => [item.candidate.clip_id, item.rank, item.sourceRank])).toEqual([['2', 1, 2], ['4', 2, 4], ['6', 3, 6]]);
    expect(sequenceSlots([candidate(), { ...reviewed('4'), rank: 4 }]).map(slot => [slot.rank, slot.sourceRank])).toEqual([[1, 4]]);
    expect(sequenceSlots([candidate()])).toEqual([]);
    expect(visibleCandidates([{ ...reviewed('7'), rank: 7 }, { ...reviewed('2'), rank: 2 }]).map(item => item.sourceRank)).toEqual([2, 7]);
  });
  it('permits explicit caption-derived actions while rejecting unsupported or empty evidence', () => {
    const inferred = candidate({ action_basis: 'video_caption', eligibility_reason: 'caption_interaction_match', inferred_behavior: 'nodding', action: { primitive: 'head_nod', evidence_id: 'caption:1', max_duration_ms: 2400 } });
    expect(isEligible(inferred)).toBe(true);
    expect(isEligible({ ...inferred, interaction_partner: null, eligibility_reason: 'caption_behavior_match' })).toBe(true);
    expect(inferred.review_status).toBe('unreviewed');
    expect(isEligible({ ...inferred, eligibility_reason: 'species_mismatch' })).toBe(false);
    expect(isEligible({ ...inferred, action: { ...inferred.action!, evidence_id: '' } })).toBe(false);
    expect(isEligible({ ...inferred, action: null })).toBe(false);
  });
  it('excludes passive results before taking three active actions, including reviewed or replayed results', () => {
    const candidates = (['head_scan', 'stand_hold', 'short_walk', 'head_scan', 'ground_pick', 'head_nod', 'sit_cycle'] as const).map((primitive, index) => ({
      ...reviewed(`clip-${index + 1}`), rank: index + 1, action: { primitive, evidence_id: `evidence-${index + 1}`, max_duration_ms: 2400 },
    }));
    expect(visibleCandidates(candidates).map(item => [item.rank, item.sourceRank, item.candidate.action?.primitive])).toEqual([[1, 3, 'short_walk'], [2, 5, 'ground_pick'], [3, 6, 'head_nod']]);
    expect(sequenceSlots(candidates.slice(0, 2))).toEqual([]);
    expect(isEligible(candidates[0])).toBe(false);
    expect(isEligible(candidates[1])).toBe(false);
  });
  it('rejects results after Reset, an overlapping retry, or a mismatched response ID', () => {
    expect(responseIsCurrent(result, 'encounter-002', 'encounter-002', 3, 3)).toBe(true);
    expect(responseIsCurrent(result, 'encounter-002', 'encounter-003', 3, 3)).toBe(false);
    expect(responseIsCurrent(result, 'encounter-002', 'encounter-002', 3, 4)).toBe(false);
    expect(responseIsCurrent({ ...result, encounter_id: 'encounter-001' }, 'encounter-002', 'encounter-002', 3, 3)).toBe(false);
  });
  it('keeps segment-local time separate from source-relative timing', () => {
    const sourceStart = 12;
    const currentTime = 4;
    expect(mmss(currentTime)).toBe('00:04');
    expect(mmss(sourceStart + currentTime)).toBe('00:16');
    expect(mmss(null)).toBe('—');
  });
  it('preserves short fractional archive intervals instead of showing a zero-length clip', () => {
    expect(`${segmentTime(20.08)}–${segmentTime(20.96)}`).toBe('00:20.08–00:20.96');
    expect(`${segmentTime(0)}–${segmentTime(0.54)}`).toBe('00:00–00:00.54');
    expect(segmentTime(59.9999)).toBe('01:00');
    expect(segmentTime(null)).toBe('—');
  });
});

describe('automatic top-three loop', () => {
  it.each(['completed', 'failed', 'cancelled'] as const)('captures the actual %s action outcome', async status => {
    const controller = new AbortController();
    const captured: string[] = [];
    const task = runReferenceLoop({
      candidates: [reviewed()], signal: controller.signal, prepareCycle: async () => {},
      approach: async () => {}, attend: async () => {}, status: () => 'ready',
      perform: async () => {
        if (status === 'failed') throw new Error('Controller failed');
        if (status === 'cancelled') controller.abort();
      },
      onAction: async (clip, cycle, state) => {
        expect(clip.clip_id).toBe('reviewed');
        expect(cycle).toBe(1);
        captured.push(state);
        if (state === 'completed') controller.abort();
      },
      onProgress: () => {},
    }).catch(error => error);
    await task;
    expect(captured).toEqual(['started', status]);
  });

  it('does not start an action when its capture cannot be persisted', async () => {
    const perform = vi.fn();
    await expect(runReferenceLoop({
      candidates: [reviewed()], signal: new AbortController().signal,
      prepareCycle: async () => {}, approach: async () => {}, attend: async () => {},
      status: () => 'ready', perform, onProgress: () => {},
      onAction: async () => { throw new Error('Capture unavailable'); },
    })).rejects.toThrow('Capture unavailable');
    expect(perform).not.toHaveBeenCalled();
  });
  it('approaches for compatible actions in source order, attends to the animal each cycle, and never overlaps actions', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const order: string[] = [];
    const progress: LoopProgress[] = [];
    let active = 0;
    const prepareCycle = vi.fn().mockResolvedValue(undefined);
    const approach = vi.fn().mockResolvedValue(undefined);
    const attend = vi.fn().mockResolvedValue(undefined);
    const task = runReferenceLoop({
      candidates: [candidate({ rank: 1 }), { ...reviewed('two'), rank: 2, action: { primitive: 'short_walk', evidence_id: 'two', max_duration_ms: 1800 } }, { ...reviewed('four'), rank: 4, action: { primitive: 'ground_pick', evidence_id: 'four', max_duration_ms: 8000 } }],
      signal: controller.signal,
      prepareCycle,
      approach,
      attend,
      attentionMs: 1,
      status: () => 'ready',
      transitionMs: 1,
      perform: async action => {
        expect(active).toBe(0);
        active += 1;
        order.push(action.evidence_id);
        await waitFor(10, controller.signal);
        active -= 1;
      },
      onProgress: event => {
        progress.push(event);
        if (event.phase === 'cycle_complete' && event.cycle === 2) controller.abort();
      },
    }).catch(error => error);
    await vi.advanceTimersByTimeAsync(100);
    expect((await task).name).toBe('AbortError');
    expect(order).toEqual(['two', 'four', 'two', 'four']);
    expect(prepareCycle).toHaveBeenCalledTimes(2);
    expect(approach).toHaveBeenCalledTimes(4);
    expect(attend).toHaveBeenCalledTimes(2);
    expect(progress.filter(event => event.phase === 'running').map(event => event.rank)).toEqual([1, 2, 1, 2]);
  });
  it('stopping during an action prevents the next rank even if the old action resolves late', async () => {
    let finishAction!: () => void;
    const action = new Promise<void>(resolve => { finishAction = resolve; });
    const controller = new AbortController();
    const perform = vi.fn().mockReturnValue(action);
    const task = runReferenceLoop({ candidates: [reviewed('1'), reviewed('2')], signal: controller.signal, prepareCycle: async () => {}, approach: async () => {}, attend: async () => {}, status: () => 'ready', perform, onProgress: () => {} }).catch(error => error);
    await vi.waitFor(() => expect(perform).toHaveBeenCalledTimes(1));
    controller.abort();
    expect((await task).name).toBe('AbortError');
    finishAction();
    await Promise.resolve();
    await Promise.resolve();
    expect(perform).toHaveBeenCalledTimes(1);
  });
  it('waits for observed simulator readiness and times out instead of overlapping recovery', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const perform = vi.fn();
    const task = runReferenceLoop({ candidates: [reviewed()], signal: controller.signal, prepareCycle: async () => {}, approach: async () => {}, attend: async () => {}, status: () => 'recovering', readinessTimeoutMs: 200, perform, onProgress: () => {} }).catch(error => error);
    await vi.advanceTimersByTimeAsync(300);
    expect((await task).message).toContain('did not become ready');
    expect(perform).not.toHaveBeenCalled();
  });
  it('cancels an approach before imitation even when navigation resolves after Stop', async () => {
    let finishApproach!: () => void;
    const navigation = new Promise<void>(resolve => { finishApproach = resolve; });
    const controller = new AbortController();
    const approach = vi.fn().mockReturnValue(navigation);
    const perform = vi.fn();
    const attend = vi.fn().mockResolvedValue(undefined);
    const task = runReferenceLoop({ candidates: [reviewed()], signal: controller.signal, prepareCycle: async () => {}, approach, attend, status: () => 'ready', perform, onProgress: () => {} }).catch(error => error);
    await vi.waitFor(() => expect(approach).toHaveBeenCalledTimes(1));
    controller.abort();
    finishApproach();
    expect((await task).name).toBe('AbortError');
    expect(perform).not.toHaveBeenCalled();
    expect(attend).not.toHaveBeenCalled();
  });
  it('stops between-cycle attention without beginning another approach', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const approach = vi.fn().mockResolvedValue(undefined);
    const attend = vi.fn().mockResolvedValue(undefined);
    const task = runReferenceLoop({ candidates: [reviewed()], signal: controller.signal, prepareCycle: async () => {}, approach, attend, status: () => 'ready', perform: async () => {}, transitionMs: 1, attentionMs: 2400, onProgress: () => {} }).catch(error => error);
    await vi.advanceTimersByTimeAsync(10);
    expect(attend).toHaveBeenCalledTimes(1);
    controller.abort();
    await vi.advanceTimersByTimeAsync(3000);
    expect((await task).name).toBe('AbortError');
    expect(approach).toHaveBeenCalledTimes(1);
  });
  it('aborts before a stopped simulator rejects and never reports completion or advances rank', async () => {
    let rejectMotion!: (error: Error) => void;
    const motion = new Promise<void>((_, reject) => { rejectMotion = reject; });
    const controller = new AbortController();
    const progress: LoopProgress[] = [];
    const perform = vi.fn().mockReturnValue(motion);
    const task = runReferenceLoop({ candidates: [reviewed('1'), reviewed('2')], signal: controller.signal, prepareCycle: async () => {}, approach: async () => {}, attend: async () => {}, status: () => 'ready', perform, onProgress: value => progress.push(value) }).catch(error => error);
    await vi.waitFor(() => expect(perform).toHaveBeenCalledTimes(1));
    // Visibility pause and manual Stop both invalidate the sequence first.
    controller.abort();
    rejectMotion(new Error('Movement cancelled'));
    expect((await task).name).toBe('AbortError');
    await Promise.resolve();
    expect(progress.some(value => value.phase === 'completed' || value.rank === 2)).toBe(false);
    expect(perform).toHaveBeenCalledTimes(1);
  });
  it('does not navigate or start a cycle when the entire response has no compatible actions', async () => {
    const prepareCycle = vi.fn();
    const perform = vi.fn();
    await runReferenceLoop({ candidates: [candidate(), candidate({ rank: 4 })], signal: new AbortController().signal, prepareCycle, approach: async () => {}, attend: async () => {}, status: () => 'ready', perform, onProgress: () => {} });
    expect(prepareCycle).not.toHaveBeenCalled();
    expect(perform).not.toHaveBeenCalled();
  });
});

describe('demo API boundary', () => {
  it('lets a configured backend finish before the browser aborts', () => {
    expect(searchDeadlineMs(1000)).toBe(6000);
    expect(searchDeadlineMs(30000)).toBe(35000);
    expect(searchDeadlineMs(60000)).toBe(65000);
    for (const invalid of [undefined, null, '30000', true, 0, 999, 60001, NaN, Infinity]) {
      expect(searchDeadlineMs(invalid)).toBe(35000);
    }
  });
  it('bootstraps the HttpOnly session with same-origin credentials and unwraps the catalog', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', api_version: '1', live_configured: true, reviewed_reference_count: 0 }))).mockResolvedValueOnce(new Response(JSON.stringify({ encounters: [{ id: 'deer-feeding' }] })));
    vi.stubGlobal('fetch', fetchMock);
    expect((await getHealth()).live_configured).toBe(true);
    expect(await getEncounters()).toEqual([{ id: 'deer-feeding' }]);
    expect(fetchMock.mock.calls.every(([, init]) => init.credentials === 'same-origin')).toBe(true);
  });
  it('sends explicit replay/scope fields and the cancel signal, without credentials in the body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...result, mode: 'replay' })));
    vi.stubGlobal('fetch', fetchMock);
    const signal = new AbortController().signal;
    const input = { encounter_id: 'encounter-002', scenario_id: 'deer-feeding', mode: 'replay' as const, broaden: true };
    const response = await searchArchive(input, signal);
    expect(response.mode).toBe('replay');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/demo-api/search');
    expect(JSON.parse(init.body)).toEqual(input);
    expect(init.signal).toBe(signal);
    expect(init.credentials).toBe('same-origin');
  });
  it('surfaces explicit replay unavailability and never substitutes cached success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'replay_unavailable', message: 'No saved run is available.', retryable: false } }), { status: 409 })));
    await expect(searchArchive({ encounter_id: 'encounter-002', scenario_id: 'deer-feeding', mode: 'replay', broaden: true }, new AbortController().signal)).rejects.toMatchObject({ code: 'replay_unavailable', message: 'No saved run is available.' });
  });
  it('reports non-JSON upstream/proxy failures without exposing raw HTML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>proxy error</html>', { status: 502 })));
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});

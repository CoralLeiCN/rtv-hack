import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getEncounters, getHealth, searchArchive, type Candidate, type SearchResult } from '../src/api';
import { isEligible, mmss, responseIsCurrent, segmentTime, visibleCandidates } from '../src/demo';

const candidate = (overrides: Partial<Candidate> = {}): Candidate => ({
  clip_id: 'opaque-clip', video_url: '/demo-api/clips/opaque-clip/video', caption: 'An animal lowers its head.', caption_hash: 'sha256:test', similarity: 0.42,
  review_status: 'unreviewed', eligibility_reason: 'not_reviewed', animal: null, reviewed_behavior: null,
  provenance: { dataset: null, source_label: 'Reference clip', parent_id: null, segment_start_sec: 12, segment_end_sec: 27 }, action: null,
  ...overrides,
});
const reviewed = (id = 'reviewed'): Candidate => candidate({ clip_id: id, review_status: 'reviewed', eligibility_reason: 'reviewed_match', animal: 'deer', reviewed_behavior: 'feeding', action: { primitive: 'ground_pick', evidence_id: 'reference-1', max_duration_ms: 8000 } });
const result: SearchResult = { encounter_id: 'encounter-002', search_id: 'search-1', mode: 'live', status: 'ok', query: 'deer feeding', elapsed_ms: 4000, candidates: [reviewed()], warnings: [] };

afterEach(() => vi.unstubAllGlobals());

describe('evidence authorization and asynchronous invalidation', () => {
  it('never enables copying from a caption or review badge alone', () => {
    expect(isEligible(candidate())).toBe(false);
    expect(isEligible(candidate({ review_status: 'reviewed', reviewed_behavior: 'feeding' }))).toBe(false);
    expect(isEligible({ ...reviewed(), eligibility_reason: 'species_mismatch', action: null })).toBe(false);
    expect(isEligible({ ...reviewed(), review_status: 'stale' })).toBe(false);
    expect(isEligible(reviewed())).toBe(true);
  });
  it('keeps a later eligible reference reachable without changing its original rank', () => {
    const candidates = [candidate({ clip_id: '1' }), candidate({ clip_id: '2' }), candidate({ clip_id: '3' }), reviewed('4')];
    expect(visibleCandidates(candidates).map(item => [item.candidate.clip_id, item.rank])).toEqual([['1', 1], ['2', 2], ['4', 4]]);
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

describe('demo API boundary', () => {
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

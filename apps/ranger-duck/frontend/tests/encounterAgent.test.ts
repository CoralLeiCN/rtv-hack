import { afterEach, describe, expect, it, vi } from 'vitest';
import { searchEncounter, encounterDeadlineMs } from '../src/encounterAgent';
import type { Health } from '../src/api';

const health: Health = { status: 'ok', api_version: '1', live_configured: true, reviewed_reference_count: 0 };
const input = { encounter_id: 'e1', scenario_id: 'cat-play', broaden: false, mode: 'live' as const };
const plan = { encounter_id: 'e1', plan_id: 'p1', query: 'A cat watches a toy or plays with another cat', query_reason: 'Either individual attention or social play matches this encounter.', query_basis: 'agent' };
const reply = (value: unknown) => new Response(JSON.stringify(value));
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('encounter agent planning and search', () => {
  it('publishes the generated query before searching and carries only its opaque plan ID into search', async () => {
    const order: string[] = [];
    const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
      order.push(url);
      if (url.endsWith('encounter-plan')) return reply(plan);
      expect(JSON.parse(init.body as string)).toEqual({ ...input, plan_id: 'p1' });
      return reply({ encounter_id: 'e1', query: plan.query, candidates: [] });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await searchEncounter(input, { health, signal: new AbortController().signal, onPlan: value => { expect(value.query).toBe(plan.query); order.push('query-visible'); } });
    expect(result.query).toBe(plan.query);
    expect(order).toEqual(['/demo-api/encounter-plan', 'query-visible', '/demo-api/search']);
    expect(fetchMock.mock.calls.every(([, init]) => init.credentials === 'same-origin')).toBe(true);
  });
  it('does not start archive search when a cancelled query plan returns late', async () => {
    let finish!: (value: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController(), onPlan = vi.fn();
    const run = searchEncounter(input, { health, signal: controller.signal, onPlan });
    const stopped = expect(run).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort(); finish(reply(plan)); await stopped;
    expect(onPlan).not.toHaveBeenCalled(); expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('rejects a mismatched encounter plan before displaying or searching it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply({ ...plan, encounter_id: 'old' })); vi.stubGlobal('fetch', fetchMock);
    const onPlan = vi.fn();
    await expect(searchEncounter(input, { health, signal: new AbortController().signal, onPlan })).rejects.toMatchObject({ code: 'invalid_encounter_plan' });
    expect(onPlan).not.toHaveBeenCalled(); expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('replays saved actions without invoking query planning', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply({ mode: 'replay' })); vi.stubGlobal('fetch', fetchMock);
    const onPlan = vi.fn();
    await searchEncounter({ ...input, mode: 'replay' }, { health, signal: new AbortController().signal, onPlan });
    expect(fetchMock).toHaveBeenCalledTimes(1); expect(fetchMock.mock.calls[0][0]).toBe('/demo-api/search');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty('plan_id'); expect(onPlan).not.toHaveBeenCalled();
  });
  it('uses bounded agent budgets and surfaces a query deadline as an agent error', async () => {
    expect(encounterDeadlineMs(60000, 'plan')).toBe(65000);
    expect(encounterDeadlineMs(180000, 'search')).toBe(185000);
    for (const value of [undefined, NaN, Infinity, 0, 999, 180001]) expect(encounterDeadlineMs(value, 'search')).toBe(185000);
    vi.useFakeTimers();
    const fetchMock = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => init.signal!.addEventListener('abort', () => reject(new DOMException('deadline', 'AbortError')), { once: true })));
    vi.stubGlobal('fetch', fetchMock);
    const run = searchEncounter(input, { health: { ...health, encounter_plan_timeout_ms: 1000 }, signal: new AbortController().signal, onPlan: vi.fn() });
    const timeout = expect(run).rejects.toMatchObject({ code: 'encounter_timeout', message: expect.stringContaining('Agent query planning') });
    await vi.advanceTimersByTimeAsync(6000); await timeout;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

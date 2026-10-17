import { afterEach, describe, expect, it, vi } from 'vitest';
import { DuckAdapter, type Runtime } from './adapter';

function fixture() {
  let now = 0;
  const runtime: Runtime = {
    mode: 'walk', groundPickPhase: null, recovery: null, respawnActive: false, inputLocked: false,
    data: { qpos: new Float64Array([-0.6, 0, 0.2, 1, 0, 0, 0]), qvel: new Float64Array(6), time: 0 },
    headTarget: new Float32Array(4),
    controller: { addSource: vi.fn() }, resetSim: vi.fn(),
  };
  const changed = vi.fn();
  const adapter = new DuckAdapter(runtime, changed, () => now);
  const advance = (wallMs: number, simMs = wallMs) => { now += wallMs; runtime.data.time += simMs / 1000; adapter.tick(); };
  return { adapter, runtime, advance, changed };
}

afterEach(() => vi.useRealTimers());

describe('reviewed primitive execution', () => {
  it('rejects missing evidence and unsupported primitives', async () => {
    const { adapter } = fixture();
    await expect(adapter.perform({ primitive: 'ground_pick', evidenceId: '' })).rejects.toThrow('reference');
    await expect(adapter.perform({ primitive: 'jump', evidenceId: 'review-1' })).rejects.toThrow('supported');
  });

  it('does not report a beak dip complete from a timer or an unaccepted action', async () => {
    const { adapter, advance } = fixture();
    const result = adapter.perform({ primitive: 'ground_pick', evidenceId: 'review-1' });
    const rejection = expect(result).rejects.toThrow('did not accept');
    advance(1500);
    await rejection;
    expect(adapter.status()).toBe('failed');
  });

  it('completes only after observed beak-dip phase and stable return to walk', async () => {
    const { adapter, runtime, advance } = fixture();
    const result = adapter.perform({ primitive: 'ground_pick', evidenceId: 'review-1' });
    runtime.mode = 'groundpick'; runtime.groundPickPhase = 0.1; advance(400);
    runtime.groundPickPhase = 0.68; advance(2300);
    expect(adapter.status()).toBe('busy');
    runtime.mode = 'walk'; runtime.groundPickPhase = null; advance(100); advance(350);
    await result;
    expect(adapter.status()).toBe('complete');
  });

  it('requires actual physics time for standing and clears cancelled work', async () => {
    const { adapter, advance } = fixture();
    const result = adapter.perform({ primitive: 'stand_hold', evidenceId: 'review-1' });
    advance(3100, 0);
    expect(adapter.status()).toBe('busy');
    const rejection = expect(result).rejects.toThrow('cancelled');
    adapter.stop();
    await rejection;
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
  });

  it('stops translation through the physics getter even with no render frames', async () => {
    let now = 0;
    const { runtime } = fixture();
    const adapter = new DuckAdapter(runtime, () => {}, () => now);
    const result = adapter.perform({ primitive: 'short_walk', evidenceId: 'review-1' });
    expect(adapter.source.command[0]).toBeGreaterThan(0);
    now = 2001;
    expect(adapter.source.command[0]).toBe(0);
    const rejection = expect(result).rejects.toThrow('cancelled');
    adapter.stop();
    await rejection;
  });

  it('fails an action when recovery begins, without claiming completion', async () => {
    const { adapter, runtime, advance } = fixture();
    const result = adapter.perform({ primitive: 'short_walk', evidenceId: 'review-1' });
    const rejection = expect(result).rejects.toThrow('lost balance');
    runtime.recovery = 'fallen'; advance(50);
    await rejection;
    expect(adapter.status()).toBe('recovering');
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { DuckAdapter, type Runtime } from './adapter';

function fixture() {
  let now = 0;
  const runtime: Runtime = {
    mode: 'walk', groundPickPhase: null, recovery: null, respawnActive: false, inputLocked: false,
    data: { qpos: new Float64Array([-0.6, 0, 0.2, 1, 0, 0, 0]), qvel: new Float64Array(6), time: 0 },
    headTarget: new Float32Array(4), headYaw: 0,
    controller: { addSource: vi.fn() }, resetSim: vi.fn(),
  };
  const changed = vi.fn();
  const adapter = new DuckAdapter(runtime, changed, () => now);
  const advance = (wallMs: number, simMs = wallMs) => { now += wallMs; runtime.data.time += simMs / 1000; adapter.tick(); };
  return { adapter, runtime, advance, changed };
}

afterEach(() => vi.useRealTimers());

describe('evidence primitive execution', () => {
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

  it('requires observed locomotion for walking instead of a timer', async () => {
    const { adapter, runtime, advance } = fixture();
    const result = adapter.perform({ primitive: 'short_walk', evidenceId: 'clip-1' });
    expect(adapter.source.command[0]).toBeGreaterThan(0);
    advance(2050);
    expect(adapter.status()).toBe('busy');
    (runtime.data.qpos as Float64Array)[0] = -0.52;
    advance(100); advance(350);
    await result;
    expect(adapter.status()).toBe('complete');
  });

  it('requires real head yaw range and a return to neutral for a scan', async () => {
    const { adapter, runtime, advance } = fixture();
    const result = adapter.perform({ primitive: 'head_scan', evidenceId: 'clip-1' });
    advance(600);
    expect(runtime.headTarget[2]).toBeGreaterThan(0.2);
    runtime.headYaw = 0.2; advance(400);
    runtime.headYaw = -0.2; advance(800);
    advance(700);
    expect(adapter.status()).toBe('busy');
    runtime.headYaw = 0.02; advance(100); advance(350);
    await result;
    expect(adapter.status()).toBe('complete');
    expect(runtime.headTarget[2]).toBe(0);
  });

  it('clears head targets at the bound even when animation frames pause', async () => {
    let now = 0;
    const { runtime } = fixture();
    const adapter = new DuckAdapter(runtime, () => {}, () => now);
    const result = adapter.perform({ primitive: 'head_scan', evidenceId: 'clip-1' });
    now = 600; void adapter.source.command;
    expect(runtime.headTarget[2]).toBeGreaterThan(0.2);
    now = 2500; void adapter.source.command;
    expect(runtime.headTarget[2]).toBe(0);
    const rejection = expect(result).rejects.toThrow('cancelled');
    adapter.stop();
    await rejection;
  });

  it('prepares a new cycle without resetting or changing the live pose', async () => {
    const { adapter, runtime, advance } = fixture();
    runtime.inputLocked = true;
    const result = adapter.prepareCycle();
    const position = Array.from(runtime.data.qpos);
    expect(runtime.resetSim).not.toHaveBeenCalled();
    advance(1000);
    expect(adapter.status()).toBe('recovering');
    runtime.inputLocked = false;
    advance(100); advance(250);
    await result;
    expect(adapter.status()).toBe('ready');
    expect(Array.from(runtime.data.qpos)).toEqual(position);
    expect(runtime.data.time).toBeGreaterThan(1);
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('steers before reaching the stage edge without resetting physics', async () => {
    const { adapter, runtime } = fixture();
    const q = runtime.data.qpos as Float64Array;
    q[0] = 0.32;
    const result = adapter.perform({ primitive: 'short_walk', evidenceId: 'clip-1' });
    expect(adapter.source.command[0]).toBeGreaterThan(0);
    expect(adapter.source.command[2]).toBeGreaterThan(0);
    expect(runtime.resetSim).not.toHaveBeenCalled();
    const rejection = expect(result).rejects.toThrow('cancelled');
    adapter.stop();
    await rejection;
  });

  it('cancels cycle preparation on Stop and rejects overlapping actions', async () => {
    const { adapter } = fixture();
    const preparation = adapter.prepareCycle();
    const rejection = expect(preparation).rejects.toThrow('cancelled');
    await expect(adapter.perform({ primitive: 'stand_hold', evidenceId: 'clip-1' })).rejects.toThrow('ready pose');
    adapter.stop();
    await rejection;
  });
});

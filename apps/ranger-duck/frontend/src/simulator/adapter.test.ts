import { afterEach, describe, expect, it, vi } from 'vitest';
import { DuckAdapter, type Runtime } from './adapter';

function fixture() {
  let now = 0;
  const runtime: Runtime = {
    mode: 'walk', groundPickPhase: null, recovery: null, respawnActive: false, inputLocked: false,
    data: { qpos: new Float64Array([-0.6, 0, 0.2, 1, 0, 0, 0]), qvel: new Float64Array(6), time: 0 },
    headTarget: new Float32Array(4), headYaw: 0, headPitch: 0.39, sitFlag: 0,
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

describe('separate continuous navigation', () => {
  it('accepts a facing arrival corridor instead of orbiting an exact point', async () => {
    const { adapter, runtime, advance } = fixture();
    const q = runtime.data.qpos as Float64Array;
    q[0] = 0.08; q[1] = -0.2;
    adapter.setCompanionTarget({ x: 1.05, y: 0.05 });
    const ready = adapter.approach();
    expect([...adapter.source.command]).toEqual([0,0,0]);
    advance(300); advance(300); await ready;
    expect(adapter.status()).toBe('ready');
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('holds one inward turn direction then steers toward the animal after alignment', async () => {
    const { adapter, runtime } = fixture();
    const q = runtime.data.qpos as Float64Array;
    q[0] = 0.17; q[1] = 0.1; q[3] = Math.cos(Math.PI/4); q[6] = Math.sin(Math.PI/4);
    adapter.setCompanionTarget({ x: 1.05, y: 0.05 });
    const ready = adapter.approach().catch(error => error);
    expect(adapter.telemetry().approach_phase).toBe('align');
    expect(adapter.source.command[2]).toBeGreaterThan(0); // Turn inward, continuing the left arc.
    q[0] = -0.21; q[1] = 0.05; q[3] = Math.cos(-Math.PI/4); q[6] = Math.sin(-Math.PI/4);
    expect(adapter.source.command[2]).toBe(1); // Crossing the arena center cannot flip the arc.
    q[0] = -0.24; q[1] = -0.18; q[3] = 1; q[6] = 0;
    const command = adapter.source.command;
    expect(adapter.telemetry().approach_phase).toBe('final');
    expect(command[0]).toBeGreaterThan(0);
    expect(command[2]).toBeGreaterThan(0);
    expect(command[2]).toBeLessThan(0.5);
    adapter.stop(); await ready;
    expect([...adapter.source.command]).toEqual([0,0,0]);
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('moves directly forward when already aligned just west of the arrival corridor', async () => {
    const { adapter, runtime } = fixture();
    (runtime.data.qpos as Float64Array)[0] = 0;
    adapter.setCompanionTarget({ x: 1.05, y: 0 });
    const result = adapter.approach().catch(error => error);
    expect(adapter.telemetry().approach_phase).toBe('final');
    expect([...adapter.source.command]).toEqual([0.25,0,0]);
    adapter.stop(); await result;
  });

  it('holds an already reached interaction pose with no extra locomotion', async () => {
    const { adapter, runtime, advance } = fixture();
    (runtime.data.qpos as Float64Array)[0] = 0.12;
    adapter.setCompanionTarget({ x: 1.05, y: 0.05 });
    const result = adapter.approach();
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
    advance(300); advance(300);
    await result;
    advance(20);
    expect(runtime.headTarget[2]).toBeGreaterThan(0);
    expect(runtime.headTarget[2]).toBeLessThan(0.1);
    expect(adapter.telemetry().target?.distance).toBeCloseTo(Math.hypot(0.93,0.05));
    expect(adapter.telemetry().commands.forward).toBe(0);
    expect(runtime.resetSim).not.toHaveBeenCalled();
    adapter.stop(); advance(20);
    adapter.tick(true); // A pending search cannot re-enable stopped attention.
    expect(runtime.headTarget[2]).toBe(0);
  });

  it('reports commanded navigation separately from evidence primitives', async () => {
    const { adapter } = fixture();
    adapter.setCompanionTarget({ x: 1.05, y: 0.05 });
    const result = adapter.approach().catch(error => error);
    expect(adapter.telemetry()).toMatchObject({ navigation: 'approaching', primitive: null, commands: { forward: 0.25, lateral: 0 } });
    adapter.stop(); await result;
    expect(adapter.telemetry()).toMatchObject({ navigation: 'idle', commands: { forward: 0, yaw: 0 } });
  });

  it('roams without an evidence action and Stop clears all navigation commands', () => {
    const { adapter, runtime } = fixture();
    adapter.roam();
    expect(adapter.navigationStatus()).toBe('roaming');
    expect(adapter.source.command[0]).toBeGreaterThan(0);
    adapter.stop();
    expect(adapter.navigationStatus()).toBe('idle');
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('requires observed approach position, facing, and stable balance', async () => {
    const { adapter, runtime, advance } = fixture();
    adapter.roam();
    const result = adapter.approach();
    advance(2000);
    expect(adapter.navigationStatus()).toBe('approaching');
    const q = runtime.data.qpos as Float64Array;
    q[0] = 0.06; q[1] = 0;
    q[3] = Math.cos(Math.PI / 4); q[6] = Math.sin(Math.PI / 4);
    advance(1000);
    expect(adapter.navigationStatus()).toBe('approaching');
    q[3] = 1; q[6] = 0;
    advance(100);
    expect(adapter.navigationStatus()).toBe('settling');
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
    advance(300);
    await result;
    expect(adapter.navigationStatus()).toBe('idle');
    expect(adapter.status()).toBe('ready');
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('cancels approach and blocks evidence movements during navigation', async () => {
    const { adapter } = fixture();
    const approach = adapter.approach();
    const rejection = expect(approach).rejects.toThrow('cancelled');
    await expect(adapter.perform({ primitive: 'head_scan', evidenceId: 'clip-1' })).rejects.toThrow('ready pose');
    adapter.stop();
    await rejection;
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
  });

  it('stops locomotion at the yellow-box safety margin even without render frames', () => {
    const { adapter, runtime, advance } = fixture();
    adapter.roam();
    (runtime.data.qpos as Float64Array)[0] = 0.57;
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
    advance(20);
    expect(adapter.navigationStatus()).toBe('idle');
    expect(adapter.status()).toBe('failed');
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('preparation stops roaming and settles without recentering physics', async () => {
    const { adapter, runtime, advance } = fixture();
    adapter.roam();
    const result = adapter.prepareCycle();
    expect(adapter.navigationStatus()).toBe('settling');
    expect([...adapter.source.command]).toEqual([0, 0, 0]);
    advance(500); advance(300);
    await result;
    expect(adapter.navigationStatus()).toBe('idle');
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });
});

describe('observed posture and vertical head actions', () => {
  it('requires real pitch travel and a return to the starting pitch for a nod', async () => {
    const { adapter, runtime, advance } = fixture();
    const result = adapter.perform({ primitive: 'head_nod', evidenceId: 'vertical-head-clip' });
    advance(600);
    expect(runtime.headTarget[1]).toBeGreaterThan(0.2);
    expect(runtime.headTarget[2]).toBe(0);
    runtime.headPitch = 0.65; advance(400);
    runtime.headPitch = 0.15; advance(800);
    advance(700);
    expect(adapter.status()).toBe('busy');
    runtime.headPitch = 0.39; advance(100); advance(350);
    await result;
    expect(adapter.status()).toBe('complete');
    expect([...runtime.headTarget]).toEqual([0, 0, 0, 0]);
  });

  it('observes the seated body height and native stand-up before completion', async () => {
    vi.useFakeTimers();
    const { adapter, runtime, advance } = fixture();
    adapter.source.onAction = vi.fn();
    const result = adapter.perform({ primitive: 'sit_cycle', evidenceId: 'sitting-clip' });
    expect(adapter.source.onAction).toHaveBeenCalledWith('sitToggle');
    runtime.mode = 'sitstand'; runtime.sitFlag = 1;
    advance(1000);
    expect(adapter.status()).toBe('busy');
    (runtime.data.qpos as Float64Array)[2] = 0.14; advance(500);
    vi.advanceTimersByTime(3000);
    expect(adapter.source.onAction).toHaveBeenCalledWith('walk');
    advance(1600);
    expect(adapter.status()).toBe('busy');
    runtime.mode = 'walk'; runtime.sitFlag = 0;
    (runtime.data.qpos as Float64Array)[2] = 0.2; advance(2100); advance(350);
    await result;
    expect(adapter.status()).toBe('complete');
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });

  it('rejects an unsafe short sit window and cancels a sit without a stale return timer', async () => {
    vi.useFakeTimers();
    const { adapter, runtime } = fixture();
    adapter.source.onAction = vi.fn();
    await expect(adapter.perform({ primitive: 'sit_cycle', evidenceId: 'clip', maxDurationMs: 2000 })).rejects.toThrow('enough time');
    const result = adapter.perform({ primitive: 'sit_cycle', evidenceId: 'clip' });
    const rejection = expect(result).rejects.toThrow('cancelled');
    adapter.stop();
    await rejection;
    expect(adapter.source.onAction).toHaveBeenLastCalledWith('walk');
    const calls = vi.mocked(adapter.source.onAction).mock.calls.length;
    vi.advanceTimersByTime(10000);
    expect(adapter.source.onAction).toHaveBeenCalledTimes(calls);
    expect(runtime.resetSim).not.toHaveBeenCalled();
  });
});

it('preserves the native sit-to-stand transition across repeated Stop/preparation calls', async () => {
  const { adapter, runtime, advance } = fixture();
  adapter.source.onAction = vi.fn(action => {
    if (action === 'sitToggle') { runtime.mode = 'sitstand'; runtime.sitFlag = 1; }
    if (action === 'walk') runtime.sitFlag = 0;
  });
  const result = adapter.perform({ primitive: 'sit_cycle', evidenceId: 'sitting-clip' });
  const rejection = expect(result).rejects.toThrow('cancelled');
  adapter.stop();
  await rejection;
  adapter.stop();
  const preparation = adapter.prepareCycle();
  expect(vi.mocked(adapter.source.onAction).mock.calls.filter(([action]) => action === 'walk')).toHaveLength(1);
  expect(runtime.mode).toBe('sitstand');
  runtime.mode = 'walk'; advance(2200); advance(300);
  await preparation;
  expect(runtime.resetSim).not.toHaveBeenCalled();
});

import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api';
import { runAgentLoop, playAndReact, runRoleActions, type AgentCycle, type ReactionOutcome } from '../src/agentLoop';

const cycle: AgentCycle = {
  session_id: 's', cycle_id: 'c', cycle: 1, query: 'two deer', query_reason: 'initial prompt', response_reason: 'look at companion',
  candidates: [],
  role_plan: { grounding: 'caption_roles', companion: { subject: 'Approaching deer', evidence: 'deer approach' },
    duck: { subject: 'Other deer', evidence: 'each other' }, duck_behavior: 'looking', companion_behavior: 'approach', companion_duration_ms: 3000, timing: 'companion_first' },
  action: { primitive: 'head_scan', evidence_id: 'e', max_duration_ms: 2400 },
  clip: { clip_id: 'v', video_url: '/demo-api/clips/v/video', caption: 'Two deer approach each other.', rank: 4, observed_behavior: 'social_approach', evidence_basis: 'video_caption', start_sec: 0, end_sec: 5 },
};
const outcome: ReactionOutcome = { cycle_id: 'c', primitive: 'head_scan', status: 'completed', playback: 'ended',
  companion: { behavior: 'approach', status: 'completed' },
  state: { status: 'complete', position: [0, 0, 0.2], head_yaw: 0, simulation_time: 12 } };
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return { promise, resolve };
}

// Event-driven media double: tests actual playing/ended/abort ordering, not elapsed timers.
class Video extends EventTarget {
  muted = false; src = ''; ended = false;
  play = vi.fn(async () => { this.dispatchEvent(new Event('playing')); });
  load = vi.fn(); pause = vi.fn();
  finish() { this.ended = true; this.dispatchEvent(new Event('ended')); }
  element() { return this as unknown as HTMLVideoElement; }
}

describe('agent loop sequencing', () => {
  it('waits for actual execution and acknowledged outcome before another search', async () => {
    const controller = new AbortController();
    const execution = deferred<ReactionOutcome>(); const acknowledgement = deferred<void>();
    const next = vi.fn().mockResolvedValue(cycle);
    const report = vi.fn(() => acknowledgement.promise);
    const run = runAgentLoop({ signal: controller.signal, next, execute: () => execution.promise, report, onSearch() {} });
    const stopped = expect(run).rejects.toThrow('stopped');
    await vi.waitFor(() => expect(next).toHaveBeenCalledTimes(1));
    expect(report).not.toHaveBeenCalled();
    execution.resolve(outcome);
    await vi.waitFor(() => expect(report).toHaveBeenCalledWith(outcome));
    expect(next).toHaveBeenCalledTimes(1);
    controller.abort(); acknowledgement.resolve();
    await stopped;
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('ignores a late search result after cancellation', async () => {
    const controller = new AbortController(); const search = deferred<AgentCycle>(); const execute = vi.fn();
    const run = runAgentLoop({ signal: controller.signal, next: () => search.promise, execute, report: vi.fn(), onSearch() {} });
    const stopped = expect(run).rejects.toThrow('stopped');
    controller.abort(); search.resolve(cycle); await stopped;
    expect(execute).not.toHaveBeenCalled();
  });

  it('bounds no-match retries and does not retry configuration errors', async () => {
    const next = vi.fn().mockRejectedValue(new ApiError('no_loop_match', 'No match'));
    const options = { signal: new AbortController().signal, next, execute: vi.fn(), report: vi.fn(), onSearch() {}, retryDelayMs: 0 };
    await expect(runAgentLoop(options)).rejects.toThrow('No match');
    expect(next).toHaveBeenCalledTimes(3);
    next.mockClear().mockRejectedValue(new ApiError('agent_unavailable', 'Install Codex'));
    await expect(runAgentLoop(options)).rejects.toThrow('Install Codex');
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('reports failed execution then pauses without another search', async () => {
    const next = vi.fn().mockResolvedValue(cycle); const report = vi.fn().mockResolvedValue({});
    await expect(runAgentLoop({ signal: new AbortController().signal, next, report, onSearch() {},
      execute: async () => ({ ...outcome, status: 'failed' }) })).rejects.toThrow('paused');
    expect(report).toHaveBeenCalledOnce(); expect(next).toHaveBeenCalledOnce();
  });
});

describe('playback and actual action completion', () => {
  it('waits for both playback end and actual action completion', async () => {
    const video = new Video(); const action = deferred<void>(); const perform = vi.fn(() => action.promise);
    let done = false;
    const run = playAndReact(video.element(), cycle, new AbortController().signal, perform, vi.fn()).then(() => { done = true; });
    expect(perform).toHaveBeenCalledOnce();
    video.finish(); await Promise.resolve(); expect(done).toBe(false);
    action.resolve(); await run; expect(done).toBe(true); expect(video.pause).toHaveBeenCalledOnce();
    video.dispatchEvent(new Event('playing')); expect(perform).toHaveBeenCalledOnce();
  });

  it('does not execute before blocked playback is explicitly started', async () => {
    const video = new Video(); const controller = new AbortController(); const blocked = vi.fn(); const perform = vi.fn(async () => {});
    video.play.mockRejectedValue(new DOMException('blocked', 'NotAllowedError'));
    const run = playAndReact(video.element(), cycle, controller.signal, perform, blocked);
    const stopped = expect(run).rejects.toThrow('stopped');
    await vi.waitFor(() => expect(blocked).toHaveBeenCalledOnce());
    expect(perform).not.toHaveBeenCalled();
    controller.abort(); await stopped;
    video.dispatchEvent(new Event('playing')); expect(perform).not.toHaveBeenCalled();
  });

  it('does not call an action twice on buffering or manual replay', async () => {
    const video = new Video(); const perform = vi.fn(async () => {});
    const run = playAndReact(video.element(), cycle, new AbortController().signal, perform, vi.fn());
    video.dispatchEvent(new Event('playing')); video.dispatchEvent(new Event('playing'));
    video.finish(); await run;
    expect(perform).toHaveBeenCalledOnce();
  });
});


describe('two video roles', () => {
  it('waits for the companion before starting a sequential duck reaction', async () => {
    const companion = deferred<void>(); const duck = vi.fn(async () => {});
    const run = runRoleActions(cycle.role_plan, new AbortController().signal, () => companion.promise, duck);
    expect(duck).not.toHaveBeenCalled();
    companion.resolve(); await run;
    expect(duck).toHaveBeenCalledOnce();
  });
  it('does not start the second role after cancellation', async () => {
    const first = deferred<void>(); const second = vi.fn(async () => {}); const controller = new AbortController();
    const run = runRoleActions({ ...cycle.role_plan, timing: 'duck_first' }, controller.signal, second, () => first.promise);
    const stopped = expect(run).rejects.toThrow('stopped');
    controller.abort(); first.resolve(); await stopped;
    expect(second).not.toHaveBeenCalled();
  });
  it('waits for both simultaneous roles', async () => {
    const companion = deferred<void>(); const duck = deferred<void>(); let complete = false;
    const run = runRoleActions({ ...cycle.role_plan, timing: 'together' }, new AbortController().signal,
      () => companion.promise, () => duck.promise).then(() => { complete = true; });
    duck.resolve(); await Promise.resolve(); expect(complete).toBe(false);
    companion.resolve(); await run; expect(complete).toBe(true);
  });
});

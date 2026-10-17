export type DuckStatus = 'loading' | 'ready' | 'busy' | 'recovering' | 'complete' | 'failed';
export type Primitive = 'ground_pick' | 'short_walk' | 'stand_hold';
export type DuckAction = { primitive: string; evidenceId: string; maxDurationMs?: number };

export interface Runtime {
  mode: string;
  groundPickPhase: number | null;
  recovery: string | null;
  respawnActive: boolean;
  inputLocked: boolean;
  data: { qpos: ArrayLike<number>; qvel: ArrayLike<number>; time: number };
  headTarget: Float32Array;
  controller: { addSource(source: object): void };
  resetSim(): void;
}

type Pending = {
  primitive: Primitive; start: number; simStart: number; x: number; y: number;
  duration: number; entered: boolean; maxPhase: number; stableSince: number | null;
  resolve(): void; reject(error: Error): void; deadline: ReturnType<typeof setTimeout>;
};

/** A narrow interface over upstream's controller. It never selects evidence. */
export class DuckAdapter {
  private state: DuckStatus = 'ready';
  private pending: Pending | null = null;
  private vector = new Float32Array(3);
  private commandUntil = 0;
  private disposed = false;
  readonly source: {
    id: string; connected: boolean; readonly command: Float32Array; axes: object;
    isActive(): boolean; poll(): void; onAction?: (action: string) => void;
  };

  constructor(private runtime: Runtime, private changed: (status: DuckStatus) => void, private clock = () => performance.now()) {
    const self = this;
    this.source = {
      id: 'ranger-duck-reviewed-action', connected: true, axes: {},
      // Read by the physics loop even when browser animation frames pause.
      get command() {
        const q = self.runtime.data.qpos;
        if (self.clock() >= self.commandUntil || Math.abs(q[0]) >= 1.15 || Math.abs(q[1]) >= 1.15 || self.runtime.recovery) self.vector.fill(0);
        return self.vector;
      },
      isActive: () => true,
      poll: () => {},
    };
    runtime.controller.addSource(this.source);
  }

  status() { return this.state; }
  private setStatus(next: DuckStatus) {
    if (next !== this.state) { this.state = next; this.changed(next); }
  }
  private clearCommand() { this.commandUntil = 0; this.vector.fill(0); this.runtime.headTarget.fill(0); }
  private upright() {
    const q = this.runtime.data.qpos;
    return Number.isFinite(q[2]) && q[2] > 0.08 && 1 - 2 * (q[4] * q[4] + q[5] * q[5]) > 0.85;
  }
  private fail(message: string, recovering = false) {
    const pending = this.pending;
    this.pending = null;
    this.clearCommand();
    if (pending) { clearTimeout(pending.deadline); pending.reject(new Error(message)); }
    this.setStatus(recovering ? 'recovering' : 'failed');
  }

  perform(action: DuckAction): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Simulator is unavailable.'));
    if (!action.evidenceId?.trim()) return Promise.reject(new Error('A reviewed reference is required.'));
    if (!['ground_pick', 'short_walk', 'stand_hold'].includes(action.primitive)) return Promise.reject(new Error('This movement is not supported.'));
    if (this.pending || this.runtime.inputLocked || this.runtime.respawnActive || this.runtime.recovery || this.runtime.mode !== 'walk') return Promise.reject(new Error('Wait for the duck to return to its ready pose.'));
    const primitive = action.primitive as Primitive;
    const bound = primitive === 'short_walk' ? 2000 : primitive === 'stand_hold' ? 3000 : 8000;
    const duration = Math.min(bound, Math.max(1, action.maxDurationMs ?? bound));
    if (primitive === 'ground_pick' && duration < 3000) return Promise.reject(new Error('The reference does not allow enough time for a complete beak dip.'));
    this.clearCommand();
    this.setStatus('busy');
    return new Promise((resolve, reject) => {
      const q = this.runtime.data.qpos;
      this.pending = {
        primitive, start: this.clock(), simStart: this.runtime.data.time, x: q[0], y: q[1], duration,
        entered: false, maxPhase: 0, stableSince: null, resolve, reject,
        deadline: setTimeout(() => this.fail('The movement did not complete within its time limit.'), primitive === 'ground_pick' ? duration : duration + 4000),
      };
      if (primitive === 'ground_pick') this.source.onAction?.('groundPick');
      if (primitive === 'short_walk') {
        // The pinned walking policy stays in its standing deadband at 0.12.
        // Use upstream's standard 0.25 m/s forward command, bounded to 2 s.
        this.vector[0] = 0.25;
        this.commandUntil = this.clock() + duration;
      }
    });
  }

  /** Called every render frame; completion requires observed physics progress. */
  tick(searching = false) {
    if (this.disposed) return;
    const runtime = this.runtime;
    if (runtime.recovery) {
      if (this.pending) this.fail('The duck lost balance and is recovering.', true);
      else this.setStatus('recovering');
      return;
    }
    if (runtime.inputLocked || runtime.respawnActive) {
      if (this.pending) this.fail('The simulator reset before the movement completed.');
      else this.setStatus('recovering');
      return;
    }
    const action = this.pending;
    if (!action) {
      if (runtime.mode !== 'walk') { this.setStatus('recovering'); return; }
      if (this.state === 'recovering') this.setStatus('ready');
      runtime.headTarget[2] = searching ? Math.sin(this.clock() / 1000) * 0.08 : 0;
      return;
    }
    const q = runtime.data.qpos;
    const elapsed = this.clock() - action.start;
    const simElapsed = (runtime.data.time - action.simStart) * 1000;
    if (simElapsed < -1) { this.fail('The simulator reset before the movement completed.'); return; }
    if (Math.abs(q[0]) >= 1.15 || Math.abs(q[1]) >= 1.15) { this.fail('The duck reached the demonstration boundary.'); return; }
    let finished = false;
    if (action.primitive === 'ground_pick') {
      if (runtime.mode === 'groundpick' && runtime.groundPickPhase !== null) {
        action.entered = true;
        action.maxPhase = Math.max(action.maxPhase, runtime.groundPickPhase);
      }
      finished = action.entered && action.maxPhase >= 0.6 && runtime.mode === 'walk';
      if (!action.entered && elapsed > 1200) { this.fail('The controller did not accept the beak dip.'); return; }
    } else if (action.primitive === 'short_walk') {
      action.entered ||= Math.hypot(q[0] - action.x, q[1] - action.y) > 0.015;
      if (elapsed >= action.duration) this.clearCommand();
      finished = action.entered && elapsed >= action.duration && simElapsed > 100 && runtime.mode === 'walk';
    } else {
      action.entered ||= simElapsed >= 100 && runtime.mode === 'walk' && this.upright();
      finished = action.entered && simElapsed >= action.duration && runtime.mode === 'walk';
    }
    const speed = Math.hypot(runtime.data.qvel[0], runtime.data.qvel[1]);
    if (finished && this.upright() && speed < 0.1) action.stableSince ??= this.clock();
    else action.stableSince = null;
    if (action.stableSince !== null && this.clock() - action.stableSince >= 300) {
      this.pending = null;
      clearTimeout(action.deadline);
      this.clearCommand();
      this.setStatus('complete');
      action.resolve();
    }
  }

  stop() {
    const pending = this.pending;
    this.pending = null;
    this.clearCommand();
    if (pending) { clearTimeout(pending.deadline); pending.reject(new Error('Movement cancelled.')); }
    // Existing policy transitions safely back to balance; physics keeps running.
    this.source.onAction?.('walk');
    this.setStatus(this.runtime.recovery || this.runtime.inputLocked || this.runtime.mode !== 'walk' ? 'recovering' : 'ready');
  }
  reset() { this.stop(); this.runtime.resetSim(); this.setStatus('recovering'); }
  dispose() { this.stop(); this.disposed = true; }
}

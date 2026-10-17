export type DuckStatus = 'loading' | 'ready' | 'busy' | 'recovering' | 'complete' | 'failed';
export type Primitive = 'ground_pick' | 'short_walk' | 'stand_hold' | 'head_scan';
export type DuckAction = { primitive: string; evidenceId: string; maxDurationMs?: number };

export interface Runtime {
  mode: string;
  groundPickPhase: number | null;
  recovery: string | null;
  respawnActive: boolean;
  inputLocked: boolean;
  data: { qpos: ArrayLike<number>; qvel: ArrayLike<number>; time: number };
  headTarget: Float32Array;
  headYaw: number;
  controller: { addSource(source: object): void };
  resetSim(): void;
}

type Pending = {
  primitive: Primitive; start: number; simStart: number; x: number; y: number;
  duration: number; entered: boolean; maxPhase: number; stableSince: number | null;
  minHeadYaw: number; maxHeadYaw: number; heading: number;
  resolve(): void; reject(error: Error): void; deadline: ReturnType<typeof setTimeout>;
};
type Preparation = {
  stableSince: number | null; resolve(): void; reject(error: Error): void;
  deadline: ReturnType<typeof setTimeout>;
};

/** A narrow interface over upstream's controller. It never selects evidence. */
export class DuckAdapter {
  private state: DuckStatus = 'ready';
  private pending: Pending | null = null;
  private preparation: Preparation | null = null;
  private vector = new Float32Array(3);
  private commandUntil = 0;
  private walkWaypoint = 0;
  private disposed = false;
  readonly source: {
    id: string; connected: boolean; readonly command: Float32Array; axes: object;
    isActive(): boolean; poll(): void; onAction?: (action: string) => void;
  };

  constructor(private runtime: Runtime, private changed: (status: DuckStatus) => void, private clock = () => performance.now()) {
    const self = this;
    this.source = {
      id: 'ranger-duck-evidence-action', connected: true, axes: {},
      // Read by the physics loop even when browser animation frames pause.
      get command() {
        const q = self.runtime.data.qpos;
        const action = self.pending;
        if (action?.primitive === 'head_scan') {
          const elapsed = self.clock() - action.start;
          self.runtime.headTarget[2] = elapsed < action.duration ? Math.sin(elapsed / action.duration * Math.PI * 2) * 0.3 : 0;
        }
        if (self.clock() >= self.commandUntil || Math.abs(q[0]) >= 1.15 || Math.abs(q[1]) >= 1.15 || self.runtime.recovery) self.vector.fill(0);
        else if (action?.primitive === 'short_walk') self.steerWalk();
        return self.vector;
      },
      isActive: () => true,
      poll: () => {},
    };
    runtime.controller.addSource(this.source);
  }

  status() { return this.state; }
  private yaw() {
    const q = this.runtime.data.qpos;
    return Math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2));
  }
  private steerWalk() {
    // Continuous, bounded path through the existing velocity controller.
    // Waypoint progress persists between videos/cycles; nothing teleports.
    const points = [[0.35, 0], [0.35, 0.45], [-0.55, 0.45], [-0.55, -0.45], [0.35, -0.45]];
    const q = this.runtime.data.qpos;
    let target = points[this.walkWaypoint];
    if (Math.hypot(target[0] - q[0], target[1] - q[1]) < 0.12) {
      this.walkWaypoint = (this.walkWaypoint + 1) % points.length;
      target = points[this.walkWaypoint];
    }
    if (Math.max(Math.abs(q[0]), Math.abs(q[1])) > 0.85) target = [-0.1, 0];
    const desired = Math.atan2(target[1] - q[1], target[0] - q[0]);
    const error = Math.atan2(Math.sin(desired - this.yaw()), Math.cos(desired - this.yaw()));
    // The pinned policy needs its walking command to produce a useful turn;
    // angular-only commands remain in the standing deadband.
    this.vector[0] = 0.25;
    this.vector[1] = 0;
    this.vector[2] = Math.max(-1, Math.min(1, error * 2.2));
  }
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
    if (!action.evidenceId?.trim()) return Promise.reject(new Error('An evidence reference is required.'));
    if (!['ground_pick', 'short_walk', 'stand_hold', 'head_scan'].includes(action.primitive)) return Promise.reject(new Error('This movement is not supported.'));
    if (this.pending || this.preparation || this.runtime.inputLocked || this.runtime.respawnActive || this.runtime.recovery || this.runtime.mode !== 'walk') return Promise.reject(new Error('Wait for the duck to return to its ready pose.'));
    const primitive = action.primitive as Primitive;
    const bound = { short_walk: 2000, stand_hold: 3000, ground_pick: 8000, head_scan: 2400 }[primitive];
    const duration = Math.min(bound, Math.max(1, action.maxDurationMs ?? bound));
    if (primitive === 'ground_pick' && duration < 3000) return Promise.reject(new Error('The reference does not allow enough time for a complete beak dip.'));
    this.clearCommand();
    this.setStatus('busy');
    return new Promise((resolve, reject) => {
      const q = this.runtime.data.qpos;
      this.pending = {
        primitive, start: this.clock(), simStart: this.runtime.data.time, x: q[0], y: q[1], duration,
        entered: false, maxPhase: 0, stableSince: null, resolve, reject,
        minHeadYaw: this.runtime.headYaw, maxHeadYaw: this.runtime.headYaw,
        heading: Math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2)),
        deadline: setTimeout(() => this.fail('The movement did not complete within its time limit.'), primitive === 'ground_pick' ? duration : duration + 4000),
      };
      if (primitive === 'ground_pick') this.source.onAction?.('groundPick');
      if (primitive === 'short_walk') {
        // The pinned walking policy stays in its standing deadband at 0.12.
        // Use upstream's standard 0.25 m/s forward command, bounded to 2 s.
        this.commandUntil = this.clock() + duration;
        this.steerWalk();
      }
    });
  }

  /** Called every render frame; completion requires observed physics progress. */
  tick(searching = false) {
    if (this.disposed) return;
    const runtime = this.runtime;
    if (this.preparation) {
      const preparation = this.preparation;
      const stable = !runtime.recovery && !runtime.inputLocked && !runtime.respawnActive && runtime.mode === 'walk' && runtime.data.time > 0.2 && this.upright() && Math.hypot(runtime.data.qvel[0], runtime.data.qvel[1]) < 0.1 && Math.abs(runtime.data.qvel[5]) < 0.5;
      if (stable) preparation.stableSince ??= this.clock();
      else preparation.stableSince = null;
      if (preparation.stableSince !== null && this.clock() - preparation.stableSince >= 200) {
        this.preparation = null;
        clearTimeout(preparation.deadline);
        this.setStatus('ready');
        preparation.resolve();
      } else this.setStatus('recovering');
      return;
    }
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
      const distance = Math.hypot(q[0] - action.x, q[1] - action.y);
      const turn = Math.abs(Math.atan2(Math.sin(this.yaw() - action.heading), Math.cos(this.yaw() - action.heading)));
      action.entered ||= distance > 0.015 || turn > 0.15;
      if (elapsed >= action.duration) this.clearCommand();
      finished = action.entered && elapsed >= action.duration && simElapsed > 100 && runtime.mode === 'walk';
    } else if (action.primitive === 'head_scan') {
      // Head motion is supplied through the existing walking-policy command.
      // Observe actual MuJoCo head yaw, not just the requested target.
      runtime.headTarget[2] = elapsed < action.duration ? Math.sin(elapsed / action.duration * Math.PI * 2) * 0.3 : 0;
      action.minHeadYaw = Math.min(action.minHeadYaw, runtime.headYaw);
      action.maxHeadYaw = Math.max(action.maxHeadYaw, runtime.headYaw);
      action.entered ||= action.maxHeadYaw - action.minHeadYaw > 0.18;
      finished = action.entered && elapsed >= action.duration && Math.abs(runtime.headYaw) < 0.1 && runtime.mode === 'walk';
    } else {
      action.entered ||= simElapsed >= 100 && runtime.mode === 'walk' && this.upright();
      finished = action.entered && simElapsed >= action.duration && runtime.mode === 'walk';
    }
    const speed = Math.hypot(runtime.data.qvel[0], runtime.data.qvel[1]);
    if (finished && this.upright() && speed < 0.1 && Math.abs(runtime.data.qvel[5]) < 0.5) action.stableSince ??= this.clock();
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
    const preparation = this.preparation;
    this.preparation = null;
    if (preparation) { clearTimeout(preparation.deadline); preparation.reject(new Error('Cycle preparation cancelled.')); }
    const pending = this.pending;
    this.pending = null;
    this.clearCommand();
    if (pending) { clearTimeout(pending.deadline); pending.reject(new Error('Movement cancelled.')); }
    // Existing policy transitions safely back to balance; physics keeps running.
    this.source.onAction?.('walk');
    this.setStatus(this.runtime.recovery || this.runtime.inputLocked || this.runtime.mode !== 'walk' ? 'recovering' : 'ready');
  }
  reset() { this.stop(); this.walkWaypoint = 0; this.runtime.resetSim(); this.setStatus('recovering'); }
  /** Wait for balance between loops, preserving position, time and controller. */
  prepareCycle(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Simulator is unavailable.'));
    this.stop();
    return new Promise((resolve, reject) => {
      this.preparation = {
        stableSince: null, resolve, reject,
        deadline: setTimeout(() => {
          this.preparation = null;
          this.clearCommand();
          this.setStatus('failed');
          reject(new Error('The duck did not return to a ready pose.'));
        }, 10000),
      };
    });
  }
  dispose() { this.stop(); this.disposed = true; }
}

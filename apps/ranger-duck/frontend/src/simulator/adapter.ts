export type DuckStatus = 'loading' | 'ready' | 'busy' | 'recovering' | 'complete' | 'failed';
export type NavigationStatus = 'idle' | 'roaming' | 'approaching' | 'settling';
export type Primitive = 'ground_pick' | 'short_walk' | 'stand_hold' | 'head_scan' | 'head_nod' | 'sit_cycle';
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
  headPitch: number;
  sitFlag: number;
  controller: { addSource(source: object): void };
  resetSim(): void;
}

type Pending = {
  primitive: Primitive; start: number; simStart: number; x: number; y: number;
  duration: number; entered: boolean; maxPhase: number; stableSince: number | null;
  minHead: number; maxHead: number; initialHead: number; initialHeight: number; heading: number;
  postureTimer?: ReturnType<typeof setTimeout>;
  resolve(): void; reject(error: Error): void; deadline: ReturnType<typeof setTimeout>;
};
type Navigation = {
  kind: 'roaming' | 'approaching'; stableSince: number | null; reached: boolean;
  approachPhase?: 'align' | 'final';
  turnDirection?: number;
  simStart: number; deadline?: ReturnType<typeof setTimeout>;
  resolve?(): void; reject?(error: Error): void;
};
// The forward-only turning policy needs room to turn back after a walking
// imitation. Keep the interaction stand-off inside the arena, not by its edge.
const APPROACH_POINT = [0.12, 0] as const;
// Keep the robot's body inside the visible yellow box, with room to turn.
const ROAM_POINTS = [[0.02, 0.18], [-0.35, 0.18], [-0.35, -0.18], [0.02, -0.18]];
type Preparation = {
  stableSince: number | null; resolve(): void; reject(error: Error): void;
  deadline: ReturnType<typeof setTimeout>;
};

/** A narrow interface over upstream's controller. It never selects evidence. */
export class DuckAdapter {
  private state: DuckStatus = 'ready';
  private pending: Pending | null = null;
  private preparation: Preparation | null = null;
  private navigation: Navigation | null = null;
  private navigationState: NavigationStatus = 'idle';
  private vector = new Float32Array(3);
  private commandUntil = 0;
  private walkWaypoint = 0;
  private disposed = false;
  private standingFromSit = false;
  private companionTarget: { x: number; y: number } | null = null;
  private attentionEnabled = false;
  readonly source: {
    id: string; connected: boolean; readonly command: Float32Array; axes: object;
    isActive(): boolean; poll(): void; onAction?: (action: string) => void;
  };

  constructor(private runtime: Runtime, private changed: (status: DuckStatus) => void, private clock = () => performance.now(), private navigationChanged: (status: NavigationStatus) => void = () => {}) {
    const self = this;
    this.source = {
      id: 'ranger-duck-evidence-action', connected: true, axes: {},
      // Read by the physics loop even when browser animation frames pause.
      get command() {
        const action = self.pending;
        if (action?.primitive === 'head_scan' || action?.primitive === 'head_nod') {
          const elapsed = self.clock() - action.start;
          self.runtime.headTarget[action.primitive === 'head_nod' ? 1 : 2] = elapsed < action.duration ? Math.sin(elapsed / action.duration * Math.PI * 2) * 0.3 : 0;
        }
        if (self.outsideGuard() || self.runtime.recovery || self.runtime.inputLocked || self.runtime.respawnActive) self.vector.fill(0);
        else if (self.navigation && !self.navigation.reached) {
          if (self.navigation.kind === 'roaming') self.steerWalk();
          else self.steerApproach();
        } else if (self.clock() >= self.commandUntil) self.vector.fill(0);
        else if (action?.primitive === 'short_walk') self.steerWalk();
        return self.vector;
      },
      isActive: () => true,
      poll: () => {},
    };
    runtime.controller.addSource(this.source);
  }

  status() { return this.state; }
  telemetry() {
    const command = this.source.command;
    const q = this.runtime.data.qpos;
    return { status: this.state, position: Array.from(this.runtime.data.qpos).slice(0, 3),
      head_yaw: this.runtime.headYaw, simulation_time: this.runtime.data.time,
      navigation: this.navigationState, approach_phase: this.navigation?.approachPhase ?? null, primitive: this.pending?.primitive ?? null,
      commands: { forward: command[0], lateral: command[1], yaw: command[2] }, body_yaw: this.yaw(),
      target: this.companionTarget ? { ...this.companionTarget,
        distance: Math.hypot(this.companionTarget.x - q[0], this.companionTarget.y - q[1]),
        facing_error: this.facingError() } : null };
  }
  setCompanionTarget(target: { x: number; y: number } | null) { this.companionTarget = target; }
  private facingError() {
    const q = this.runtime.data.qpos;
    const desired = this.companionTarget ? Math.atan2(this.companionTarget.y - q[1], this.companionTarget.x - q[0]) : 0;
    return Math.atan2(Math.sin(desired - this.yaw()), Math.cos(desired - this.yaw()));
  }
  private atInteractionPose() {
    const q = this.runtime.data.qpos;
    // The policy cannot turn in place. A corridor accepts a correctly facing
    // arrival without asking it to orbit a tiny point to satisfy two goals.
    return q[0] >= APPROACH_POINT[0] - 0.1 && q[0] <= APPROACH_POINT[0] + 0.1 &&
      Math.abs(q[1]) <= 0.28 && Math.abs(this.facingError()) < 0.45;
  }
  private atApproachEntry() {
    const q = this.runtime.data.qpos;
    return q[0] <= APPROACH_POINT[0] - 0.1 && Math.abs(q[1]) < 0.32 && Math.abs(this.facingError()) < 0.45;
  }
  private approachTurnDirection() {
    const q = this.runtime.data.qpos, yaw = this.yaw();
    // Compare conservative turning-circle envelopes. Keep one direction for
    // the entire arc; point pursuit can flip direction as it crosses a target.
    const radius = 0.23;
    const score = (direction: number) => {
      const x = q[0] - direction * radius * Math.sin(yaw);
      const y = q[1] + direction * radius * Math.cos(yaw);
      const boundary = Math.max(0, -0.70 - (x-radius)) + Math.max(0, x+radius-0.50) + Math.max(0, Math.abs(y)+radius-0.55);
      const exitY = y-direction*radius;
      return boundary*100 + Math.max(0,x-0.2)*10 + Math.abs(exitY);
    };
    return score(1) <= score(-1) ? 1 : -1;
  }
  private steerApproach() {
    const navigation = this.navigation;
    if (!navigation) return;
    if (navigation.approachPhase === 'align' && this.atApproachEntry()) navigation.approachPhase = 'final';
    if (navigation.approachPhase === 'align') {
      this.vector.set([0.25, 0, navigation.turnDirection ?? 1]);
    } else this.steerToward([this.companionTarget?.x ?? 1.05, this.companionTarget?.y ?? 0]);
  }
  private yaw() {
    const q = this.runtime.data.qpos;
    return Math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2));
  }
  navigationStatus() { return this.navigationState; }
  private setNavigation(next: NavigationStatus) {
    if (next !== this.navigationState) { this.navigationState = next; this.navigationChanged(next); }
  }
  private outsideGuard() {
    const q = this.runtime.data.qpos;
    return q[0] < -0.76 || q[0] > 0.56 || Math.abs(q[1]) > 0.61;
  }
  private steerToward(target: readonly number[]) {
    const q = this.runtime.data.qpos;
    const desired = Math.atan2(target[1] - q[1], target[0] - q[0]);
    const error = Math.atan2(Math.sin(desired - this.yaw()), Math.cos(desired - this.yaw()));
    // The pinned policy needs forward locomotion for a useful turn.
    this.vector[0] = 0.25;
    this.vector[1] = 0;
    this.vector[2] = Math.max(-1, Math.min(1, error * 2.2));
  }
  private steerWalk() {
    const q = this.runtime.data.qpos;
    let target = ROAM_POINTS[this.walkWaypoint];
    if (Math.hypot(target[0] - q[0], target[1] - q[1]) < 0.14) {
      this.walkWaypoint = (this.walkWaypoint + 1) % ROAM_POINTS.length;
      target = ROAM_POINTS[this.walkWaypoint];
    }
    this.steerToward(target);
  }
  private stable() {
    const r = this.runtime;
    return !r.recovery && !r.inputLocked && !r.respawnActive && r.mode === 'walk' && r.data.time > 0.2 && this.upright() && Math.hypot(r.data.qvel[0], r.data.qvel[1]) < 0.1 && Math.abs(r.data.qvel[5]) < 0.5;
  }
  /** Navigation has no evidence semantics and never overwrites the MuJoCo pose. */
  roam() {
    if (this.disposed || this.pending || this.preparation || this.runtime.recovery || this.runtime.inputLocked || this.runtime.mode !== 'walk') return;
    this.cancelNavigation();
    this.clearCommand();
    // Select the next point in front of the current heading where possible.
    const q = this.runtime.data.qpos;
    this.walkWaypoint = ROAM_POINTS.reduce((best, point, index) => {
      const score = (p: number[]) => Math.hypot(p[0] - q[0], p[1] - q[1]) + Math.abs(Math.atan2(Math.sin(Math.atan2(p[1] - q[1], p[0] - q[0]) - this.yaw()), Math.cos(Math.atan2(p[1] - q[1], p[0] - q[0]) - this.yaw()))) * 0.25;
      return score(point) < score(ROAM_POINTS[best]) ? index : best;
    }, 0);
    this.navigation = { kind: 'roaming', reached: false, stableSince: null, simStart: this.runtime.data.time };
    this.setNavigation('roaming');
    this.setStatus('ready');
  }
  approach(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Simulator is unavailable.'));
    if (this.pending || this.preparation || this.runtime.recovery || this.runtime.inputLocked || this.runtime.mode !== 'walk') return Promise.reject(new Error('Wait for the duck to return to its ready pose.'));
    this.cancelNavigation();
    this.clearCommand();
    this.attentionEnabled = true;
    this.setNavigation('approaching');
    this.setStatus('busy');
    return new Promise((resolve, reject) => {
      this.navigation = {
        kind: 'approaching', approachPhase: this.atApproachEntry() ? 'final' : 'align',
        turnDirection: this.approachTurnDirection(),
        reached: this.atInteractionPose(), stableSince: null, simStart: this.runtime.data.time, resolve, reject,
        deadline: setTimeout(() => this.failNavigation('The duck could not reach its interaction position in time.'), 25000),
      };
    });
  }
  private cancelNavigation(message = 'Navigation cancelled.') {
    const navigation = this.navigation;
    this.navigation = null;
    if (navigation?.deadline) clearTimeout(navigation.deadline);
    navigation?.reject?.(new Error(message));
    this.setNavigation('idle');
  }
  private failNavigation(message: string) {
    this.cancelNavigation(message);
    this.clearCommand();
    this.setStatus(this.runtime.recovery ? 'recovering' : 'failed');
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
    if (pending) {
      clearTimeout(pending.deadline); clearTimeout(pending.postureTimer);
      if (pending.primitive === 'sit_cycle') this.returnToWalk();
      pending.reject(new Error(message));
    }
    this.setStatus(recovering ? 'recovering' : 'failed');
  }

  perform(action: DuckAction): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Simulator is unavailable.'));
    if (!action.evidenceId?.trim()) return Promise.reject(new Error('An evidence reference is required.'));
    if (!['ground_pick', 'short_walk', 'stand_hold', 'head_scan', 'head_nod', 'sit_cycle'].includes(action.primitive)) return Promise.reject(new Error('This movement is not supported.'));
    if (this.pending || this.preparation || this.navigation || this.runtime.inputLocked || this.runtime.respawnActive || this.runtime.recovery || this.runtime.mode !== 'walk') return Promise.reject(new Error('Wait for the duck to return to its ready pose.'));
    const primitive = action.primitive as Primitive;
    const bound = { short_walk: 2000, stand_hold: 3000, ground_pick: 8000, head_scan: 2400, head_nod: 2400, sit_cycle: 6000 }[primitive];
    const duration = Math.min(bound, Math.max(1, action.maxDurationMs ?? bound));
    if (primitive === 'ground_pick' && duration < 3000) return Promise.reject(new Error('The reference does not allow enough time for a complete beak dip.'));
    if (primitive === 'sit_cycle' && duration < 5500) return Promise.reject(new Error('The reference does not allow enough time to sit and stand safely.'));
    this.clearCommand();
    this.setStatus('busy');
    return new Promise((resolve, reject) => {
      const q = this.runtime.data.qpos;
      this.pending = {
        primitive, start: this.clock(), simStart: this.runtime.data.time, x: q[0], y: q[1], duration,
        entered: false, maxPhase: 0, stableSince: null, resolve, reject,
        minHead: primitive === 'head_nod' ? this.runtime.headPitch : this.runtime.headYaw,
        maxHead: primitive === 'head_nod' ? this.runtime.headPitch : this.runtime.headYaw,
        initialHead: primitive === 'head_nod' ? this.runtime.headPitch : this.runtime.headYaw, initialHeight: q[2],
        heading: Math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2)),
        deadline: setTimeout(() => this.fail('The movement did not complete within its time limit.'), primitive === 'ground_pick' ? duration : duration + 4000),
      };
      if (primitive === 'ground_pick') this.source.onAction?.('groundPick');
      if (primitive === 'sit_cycle') {
        this.source.onAction?.('sitToggle');
        // Native sit/stand needs its own two-second hand-back. Schedule it
        // independently of render frames, and never interrupt it with a reset.
        this.pending.postureTimer = setTimeout(() => {
          if (this.pending?.primitive === 'sit_cycle') this.returnToWalk();
        }, duration - 3000);
      }
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
    if (runtime.mode === 'walk') this.standingFromSit = false;
    if (this.preparation) {
      const preparation = this.preparation;
      const stable = this.stable();
      if (stable) preparation.stableSince ??= this.clock();
      else preparation.stableSince = null;
      if (preparation.stableSince !== null && this.clock() - preparation.stableSince >= 200) {
        this.preparation = null;
        clearTimeout(preparation.deadline);
        this.setStatus('ready');
        this.setNavigation('idle');
        preparation.resolve();
      } else this.setStatus('recovering');
      return;
    }
    if (this.navigation) {
      const navigation = this.navigation;
      if (runtime.recovery || runtime.respawnActive || runtime.inputLocked || runtime.data.time < navigation.simStart) {
        this.failNavigation('Navigation stopped because the duck is recovering.'); return;
      }
      if (this.outsideGuard()) { this.failNavigation('Navigation stopped at the arena safety margin.'); return; }
      if (navigation.kind === 'approaching') {
        if (this.atInteractionPose()) navigation.reached = true;
        if (navigation.reached) {
          this.clearCommand();
          this.setNavigation('settling');
          if (this.stable()) navigation.stableSince ??= this.clock();
          else navigation.stableSince = null;
          if (navigation.stableSince !== null && this.clock() - navigation.stableSince >= 250) {
            this.navigation = null;
            clearTimeout(navigation.deadline);
            this.setNavigation('idle');
            this.setStatus('ready');
            navigation.resolve?.();
          }
        }
      }
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
      runtime.headTarget[2] = this.attentionEnabled && this.companionTarget
        ? Math.max(-0.3, Math.min(0.3, this.facingError()))
        : searching && !this.companionTarget ? Math.sin(this.clock() / 1000) * 0.08 : 0;
      return;
    }
    const q = runtime.data.qpos;
    const elapsed = this.clock() - action.start;
    const simElapsed = (runtime.data.time - action.simStart) * 1000;
    if (simElapsed < -1) { this.fail('The simulator reset before the movement completed.'); return; }
    if (this.outsideGuard()) { this.fail('The duck reached the demonstration boundary.'); return; }
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
    } else if (action.primitive === 'head_scan' || action.primitive === 'head_nod') {
      // Require actual MuJoCo joint travel and return to the starting pose.
      const nod = action.primitive === 'head_nod';
      const angle = nod ? runtime.headPitch : runtime.headYaw;
      runtime.headTarget[nod ? 1 : 2] = elapsed < action.duration ? Math.sin(elapsed / action.duration * Math.PI * 2) * 0.3 : 0;
      action.minHead = Math.min(action.minHead, angle);
      action.maxHead = Math.max(action.maxHead, angle);
      action.entered ||= action.maxHead - action.minHead > 0.18;
      finished = action.entered && elapsed >= action.duration && Math.abs(angle - (nod ? action.initialHead : 0)) < 0.1 && runtime.mode === 'walk';
    } else if (action.primitive === 'sit_cycle') {
      action.entered ||= runtime.mode === 'sitstand' && runtime.sitFlag === 1 && q[2] < action.initialHeight - 0.025;
      if (!action.entered && elapsed > 2400) { this.fail('The controller did not reach a seated pose.'); return; }
      finished = action.entered && runtime.mode === 'walk' && q[2] > action.initialHeight - 0.015;
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
      clearTimeout(action.postureTimer);
      this.clearCommand();
      this.setStatus('complete');
      action.resolve();
    }
  }

  private returnToWalk() {
    // A second native walk request during the two-second sit hand-back
    // cancels that timer and switches policy too early. Preserve it.
    if (this.runtime.mode === 'sitstand' && this.runtime.sitFlag === 0 && this.standingFromSit) return;
    this.standingFromSit = this.runtime.mode === 'sitstand' && this.runtime.sitFlag === 1;
    this.source.onAction?.('walk');
  }
  stop() {
    this.attentionEnabled = false;
    this.cancelNavigation();
    const preparation = this.preparation;
    this.preparation = null;
    if (preparation) { clearTimeout(preparation.deadline); preparation.reject(new Error('Cycle preparation cancelled.')); }
    const pending = this.pending;
    this.pending = null;
    this.clearCommand();
    if (pending) { clearTimeout(pending.deadline); clearTimeout(pending.postureTimer); pending.reject(new Error('Movement cancelled.')); }
    // Existing policy transitions safely back to balance; physics keeps running.
    this.returnToWalk();
    this.setStatus(this.runtime.recovery || this.runtime.inputLocked || this.runtime.mode !== 'walk' ? 'recovering' : 'ready');
  }
  reset() { this.stop(); this.walkWaypoint = 0; this.runtime.resetSim(); this.setStatus('recovering'); }
  /** Wait for balance between loops, preserving position, time and controller. */
  prepareCycle(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Simulator is unavailable.'));
    this.stop();
    this.setNavigation('settling');
    return new Promise((resolve, reject) => {
      this.preparation = {
        stableSince: null, resolve, reject,
        deadline: setTimeout(() => {
          this.preparation = null;
          this.clearCommand();
          this.setStatus('failed');
          this.setNavigation('idle');
          reject(new Error('The duck did not return to a ready pose.'));
        }, 10000),
      };
    });
  }
  dispose() { this.stop(); this.disposed = true; }
}

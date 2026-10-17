import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { DuckAdapter, type DuckAction, type DuckStatus, type NavigationStatus, type Runtime } from './adapter';
import { createClearing, type SceneEncounter, type CompanionAction } from './clearing';
import { InteractionCoordinator } from './interaction';
import type { AnimalSpecies } from './animals';
import { bootGame, disposeGame } from './upstream/game/game.js';
import { gameApi, useGame } from './upstream/store.js';

export type { DuckStatus, NavigationStatus } from './adapter';
export type { SceneEncounter } from './clearing';
export interface MicroduckSceneHandle {
  perform(action: DuckAction): Promise<void>;
  performCompanion(action: CompanionAction): Promise<void>;
  stopCompanion(): void;
  telemetry(): ReturnType<DuckAdapter['telemetry']>;
  stop(): void;
  reset(): void;
  prepareCycle(): Promise<void>;
  approach(): Promise<void>;
  ensureInteraction(): Promise<void>;
  roam(): void;
  startEncounter(encounter: SceneEncounter): void;
  updateEncounterBehavior(behaviorHint: string): void;
  status(): DuckStatus;
}
type Props = {
  loopAnimal?: AnimalSpecies;
  searching?: boolean;
  onReady?(): void;
  onError?(message: string): void;
  onMovementError?(message: string): void;
  onStatus?(status: DuckStatus): void;
  onNavigation?(status: NavigationStatus): void;
  onEncounterReady?(id: string): void;
};
type DebugRuntime = Runtime & {
  controls: {
    target: THREE.Vector3;
    maxDistance: number;
    update(): void;
    addEventListener(type: 'start', listener: () => void): void;
    removeEventListener(type: 'start', listener: () => void): void;
  };
  chaseCam: boolean;
};

const MicroduckScene = forwardRef<MicroduckSceneHandle, Props>(function MicroduckScene(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const callbacks = useRef(props);
  callbacks.current = props;
  const adapter = useRef<DuckAdapter | null>(null);
  const clearing = useRef<ReturnType<typeof createClearing> | null>(null);
  const status = useRef<DuckStatus>('loading');
  const pendingEncounter = useRef<SceneEncounter | null>(null);
  const interaction = useRef<InteractionCoordinator | null>(null);
  const autoInteraction = useRef(false);
  const stopMotion = () => {
    pendingEncounter.current = null;
    autoInteraction.current = false;
    interaction.current?.cancel();
    clearing.current?.stop();
    adapter.current?.stop();
  };
  const ensureInteraction = () => {
    autoInteraction.current = false;
    if (!clearing.current?.interactionTarget()) return Promise.reject(new Error('No animal is present.'));
    if (document.hidden) return Promise.reject(new DOMException('Approach paused while the tab is hidden.', 'AbortError'));
    return interaction.current?.ensure() ?? Promise.reject(new Error('Simulator is still loading.'));
  };

  useImperativeHandle(ref, () => ({
    perform: action => adapter.current?.perform(action) ?? Promise.reject(new Error('Simulator is still loading.')),
    stop: stopMotion,
    performCompanion: action => clearing.current?.performCompanion(action, performance.now()) ?? Promise.reject(new Error('Scene is still loading.')),
    stopCompanion: () => clearing.current?.stopRoleAction(),
    telemetry: () => {
      if (!adapter.current) throw new Error('Simulator is still loading.');
      const state = adapter.current.telemetry();
      return interaction.current?.phase === 'settling' ? { ...state, navigation: 'settling' } : state;
    },
    roam: () => { stopMotion(); adapter.current?.roam(); },
    approach: ensureInteraction,
    ensureInteraction,
    reset: () => { stopMotion(); pendingEncounter.current = null; clearing.current?.reset(); adapter.current?.reset(); },
    prepareCycle: () => { interaction.current?.cancel(); return adapter.current?.prepareCycle() ?? Promise.reject(new Error('Simulator is still loading.')); },
    startEncounter: encounter => {
      stopMotion();
      pendingEncounter.current = encounter;
      clearing.current?.reset();
      if (!encounter.preservePose) adapter.current?.reset();
    },
    updateEncounterBehavior: behaviorHint => {
      if (pendingEncounter.current) {
        pendingEncounter.current = { ...pendingEncounter.current, behavior_hint: behaviorHint };
        return;
      }
      if (!clearing.current) throw new Error('Scene is still loading.');
      clearing.current.updateEncounterBehavior(behaviorHint, performance.now());
    },
    status: () => status.current,
  }), []);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let raf = 0;
    let previous = performance.now();
    let ready = false;
    let booted = false;
    let cameraAdjusted = false;
    const cameraInteraction = () => { cameraAdjusted = true; };
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      status.current = 'failed';
      callbacks.current.onStatus?.('failed');
      callbacks.current.onError?.('WebGL is unavailable. Enable hardware acceleration and reload.');
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
    renderer.domElement.setAttribute('aria-label', 'Microduck physics simulation and scripted animal interaction in a shared clearing');
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#101b17');
    scene.fog = new THREE.Fog('#101b17', 3.5, 8);
    const camera = new THREE.PerspectiveCamera(39, 1, 0.02, 30);
    const cameraTarget = new THREE.Vector3(0.35, 0.18, 0);
    const viewDirection = new THREE.Vector3(0.8, 1.65, 2.5).normalize();
    const frameClearing = () => {
      // Include the full yellow arena, cyan encounter circle and standing
      // actors. Fit both axes so a shorter or narrower canvas stays complete.
      camera.position.copy(cameraTarget).add(viewDirection);
      camera.lookAt(cameraTarget);
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
      const halfVertical = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * 0.84;
      const halfHorizontal = halfVertical * camera.aspect;
      let distance = 0;
      for (const x of [-0.95, 1.65]) for (const y of [0, 0.65]) for (const z of [-0.8, 0.8]) {
        const point = new THREE.Vector3(x, y, z).sub(cameraTarget);
        distance = Math.max(distance, point.dot(viewDirection) + Math.max(Math.abs(point.dot(right)) / halfHorizontal, Math.abs(point.dot(up)) / halfVertical));
      }
      camera.position.copy(cameraTarget).addScaledVector(viewDirection, distance);
      camera.lookAt(cameraTarget);
      if (booted) {
        const controls = (window as unknown as { rl: DebugRuntime }).rl.controls;
        controls.target.copy(cameraTarget);
        controls.update();
      }
    };
    frameClearing();
    const ambient = new THREE.HemisphereLight('#f2ecdd', '#324328', 1.8);
    scene.add(ambient);
    const sun = new THREE.DirectionalLight('#fff2d1', 2.5);
    sun.position.set(-1, 4, 3);
    scene.add(sun);
    const rim = new THREE.DirectionalLight('#2ff0e6', 0.45);
    rim.position.set(1, 2, -2);
    scene.add(rim);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const environment = pmrem.fromScene(room);
    scene.environment = environment.texture;
    scene.environmentIntensity = 0.45;
    room.dispose();
    pmrem.dispose();
    clearing.current = createClearing(scene, () => {
      const rl = (window as unknown as { rl?: DebugRuntime }).rl;
      if (!booted || !rl) return { x: -0.6, z: 0, yaw: 0 };
      const q = rl.data.qpos;
      return { x: q[0], z: -q[1], yaw: Math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2)) };
    });
    if (import.meta.env.DEV) (window as unknown as { __rangerScene?: ReturnType<typeof createClearing> }).__rangerScene = clearing.current;
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (!cameraAdjusted) frameClearing();
    });
    resize.observe(element);
    status.current = 'loading';
    callbacks.current.onStatus?.('loading');
    useGame.setState({ bootDone: false, bootFailed: false, menuOpen: false });
    const api = gameApi as { frame?(dt: number): void; startEntrance?(): void };
    const runtime = () => (window as unknown as { rl: DebugRuntime }).rl;
    const changed = (next: DuckStatus) => { status.current = next; callbacks.current.onStatus?.(next); };

    bootGame({ scene, camera, renderer }).then(() => {
      if (disposed) { disposeGame(); return; }
      booted = true;
      const rl = runtime();
      rl.chaseCam = false;
      rl.controls.maxDistance = 10;
      frameClearing();
      rl.controls.addEventListener('start', cameraInteraction);
      adapter.current = new DuckAdapter(rl, changed, () => performance.now(), next => callbacks.current.onNavigation?.(next));
      const duck = adapter.current;
      interaction.current = new InteractionCoordinator({
        prepareDuck: () => duck.prepareCycle(),
        prepareAnimal: () => {
          callbacks.current.onNavigation?.('settling');
          return clearing.current?.prepareInteraction() ?? Promise.reject(new Error('Scene is unavailable.'));
        },
        approach: () => duck.approach(),
      });
      // Development-only smoke-test hook; omitted from production bundles.
      if (import.meta.env.DEV) (window as unknown as { __rangerDuck?: DuckAdapter }).__rangerDuck = adapter.current;
      api.startEntrance?.();
    }).catch((error: unknown) => {
      if (disposed) return;
      changed('failed');
      callbacks.current.onError?.(`Simulator could not load: ${error instanceof Error ? error.message : 'unknown error'}. Run the simulator asset setup and reload.`);
    });

    function frame(now: number) {
      if (disposed) return;
      const dt = Math.min((now - previous) / 1000, 0.05);
      previous = now;
      api.frame?.(dt);
      if (booted) {
        const animal = clearing.current?.interactionTarget();
        adapter.current?.setCompanionTarget(animal ? { x: animal.x, y: -animal.z } : null);
        adapter.current?.tick(callbacks.current.searching);
        const navigation = adapter.current?.navigationStatus();
        clearing.current?.setActivity(navigation === 'roaming' ? 'patrol' : navigation === 'approaching' || navigation === 'settling' || adapter.current?.status() === 'busy' ? 'interact' : 'hold', callbacks.current.searching);
        const rl = runtime();
        // Keep the shared clearing framed; orbit/zoom remains user controlled.
        if (!rl.inputLocked && !rl.respawnActive && !rl.recovery) {
          if (!ready) { ready = true; changed('ready'); callbacks.current.onReady?.(); }
          if (pendingEncounter.current) {
            const encounter = pendingEncounter.current;
            pendingEncounter.current = null;
            clearing.current?.start(encounter, now);
            autoInteraction.current = true;
          }
        }
        if (autoInteraction.current && !document.hidden && adapter.current?.status() === 'ready' && clearing.current?.interactionTarget()) {
          void ensureInteraction().catch(error => {
            if (error instanceof Error && error.name !== 'AbortError' && !/cancelled|stopped/i.test(error.message)) callbacks.current.onMovementError?.(error.message);
          });
        }
      }
      const encounterId = clearing.current?.frame(now);
      if (encounterId) callbacks.current.onEncounterReady?.(encounterId);
      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    // Let App abort its sequence first; then cover navigation begun before
    // a sequence exists (for example an animal newly selected in Loop mode).
    const hidden = () => { if (document.hidden) queueMicrotask(() => { if (document.hidden) stopMotion(); }); };
    document.addEventListener('visibilitychange', hidden);
    return () => {
      document.removeEventListener('visibilitychange', hidden);
      disposed = true;
      autoInteraction.current = false;
      interaction.current?.cancel();
      interaction.current = null;
      cancelAnimationFrame(raf);
      resize.disconnect();
      adapter.current?.dispose();
      adapter.current = null;
      if (import.meta.env.DEV) delete (window as unknown as { __rangerDuck?: DuckAdapter }).__rangerDuck;
      if (import.meta.env.DEV) delete (window as unknown as { __rangerScene?: ReturnType<typeof createClearing> }).__rangerScene;
      clearing.current?.dispose();
      clearing.current = null;
      if (booted) runtime().controls.removeEventListener('start', cameraInteraction);
      if (booted) disposeGame();
      environment.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  useEffect(() => {
    stopMotion();
    pendingEncounter.current = null;
    if (props.loopAnimal) { clearing.current?.showLoopAnimals(props.loopAnimal); autoInteraction.current = true; }
    else clearing.current?.reset();
  }, [props.loopAnimal]);

  return <div ref={host} style={{ position: 'absolute', inset: 0 }} />;
});

export { MicroduckScene };
export default MicroduckScene;

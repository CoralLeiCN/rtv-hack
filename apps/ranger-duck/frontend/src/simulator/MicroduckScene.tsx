import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { DuckAdapter, type DuckAction, type DuckStatus, type Runtime } from './adapter';
import { createClearing } from './clearing';
import { bootGame, disposeGame } from './upstream/game/game.js';
import { gameApi, useGame } from './upstream/store.js';

export type { DuckStatus } from './adapter';
export interface MicroduckSceneHandle {
  perform(action: DuckAction): Promise<void>;
  stop(): void;
  reset(): void;
  startEncounter(encounter: { id: string; behavior_hint: string }): void;
  status(): DuckStatus;
}
type Props = {
  searching?: boolean;
  onReady?(): void;
  onError?(message: string): void;
  onStatus?(status: DuckStatus): void;
  onEncounterReady?(id: string): void;
};
type DebugRuntime = Runtime & {
  controls: { target: THREE.Vector3; update(): void };
  chaseCam: boolean;
};

const MicroduckScene = forwardRef<MicroduckSceneHandle, Props>(function MicroduckScene(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const callbacks = useRef(props);
  callbacks.current = props;
  const adapter = useRef<DuckAdapter | null>(null);
  const clearing = useRef<ReturnType<typeof createClearing> | null>(null);
  const status = useRef<DuckStatus>('loading');
  const pendingEncounter = useRef<{ id: string; behavior_hint: string } | null>(null);

  useImperativeHandle(ref, () => ({
    perform: action => adapter.current?.perform(action) ?? Promise.reject(new Error('Simulator is still loading.')),
    stop: () => adapter.current?.stop(),
    reset: () => { pendingEncounter.current = null; clearing.current?.reset(); adapter.current?.reset(); },
    startEncounter: encounter => {
      pendingEncounter.current = encounter;
      clearing.current?.reset();
      adapter.current?.reset();
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
    renderer.domElement.setAttribute('aria-label', 'Microduck physics simulation and scripted deer in a shared clearing');
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#101b17');
    scene.fog = new THREE.Fog('#101b17', 3.5, 8);
    const camera = new THREE.PerspectiveCamera(39, 1, 0.02, 30);
    camera.position.set(1.25, 0.78, 1.6);
    camera.lookAt(0, 0.2, -0.1);
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
    clearing.current = createClearing(scene);
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
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
      rl.controls.target.set(0, 0.18, -0.08);
      camera.position.set(1.25, 0.78, 1.6);
      rl.controls.update();
      adapter.current = new DuckAdapter(rl, changed);
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
        adapter.current?.tick(callbacks.current.searching);
        const rl = runtime();
        if (!rl.inputLocked && !rl.respawnActive && !rl.recovery) {
          if (!ready) { ready = true; changed('ready'); callbacks.current.onReady?.(); }
          if (pendingEncounter.current) {
            const encounter = pendingEncounter.current;
            pendingEncounter.current = null;
            clearing.current?.start(encounter.id, encounter.behavior_hint, now);
          }
        }
      }
      const encounterId = clearing.current?.frame(now);
      if (encounterId) callbacks.current.onEncounterReady?.(encounterId);
      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    const hidden = () => { if (document.hidden) adapter.current?.stop(); };
    document.addEventListener('visibilitychange', hidden);
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      resize.disconnect();
      document.removeEventListener('visibilitychange', hidden);
      adapter.current?.dispose();
      adapter.current = null;
      if (import.meta.env.DEV) delete (window as unknown as { __rangerDuck?: DuckAdapter }).__rangerDuck;
      clearing.current?.dispose();
      clearing.current = null;
      if (booted) disposeGame();
      environment.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={host} style={{ position: 'absolute', inset: 0 }} />;
});

export { MicroduckScene };
export default MicroduckScene;

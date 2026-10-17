import * as THREE from 'three';
import { createCat, createDeer, type AnimalActor, type AnimalSpecies } from './animals';
import { ANIMAL_ANCHOR, createAnimalMotor, stepAnimalMotor, type AnimalActivity } from './animalMotor';
export { ANIMAL_ANCHOR } from './animalMotor';

export type SceneEncounter = {
  id: string; behavior_hint: string; animal?: AnimalSpecies;
  interaction_partner?: string;
};
export type DuckScenePose = { x: number; z: number; yaw: number };
type Interaction = 'feeding' | 'following' | 'greeting' | 'boundary' | 'alert' | 'play';
export function interactionFor(hint: string): Interaction {
  if (/hiss|defens|standoff|boundary/.test(hint)) return 'boundary';
  if (/greet|nose|friendly/.test(hint)) return 'greeting';
  if (/play|bat|chase/.test(hint)) return 'play';
  if (/feed|graze|eat/.test(hint)) return 'feeding';
  if (/walk|follow/.test(hint)) return 'following';
  return 'alert';
}

/** Visual scene actors only. The duck and flat floor remain MuJoCo bodies. */
export function createClearing(scene: THREE.Scene, getDuckPose: () => DuckScenePose = () => ({ x: -0.6, z: 0, yaw: 0 })) {
  const group = new THREE.Group();
  scene.add(group);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.MeshStandardMaterial({ color: '#202c20', roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.005;
  ground.receiveShadow = true;
  group.add(ground);
  const patch = new THREE.Mesh(new THREE.CircleGeometry(1.48, 40), new THREE.MeshStandardMaterial({ color: '#34402a', roughness: 1 }));
  patch.rotation.x = -Math.PI / 2;
  patch.position.y = -0.002;
  group.add(patch);
  const zone = new THREE.Mesh(new THREE.RingGeometry(0.35, 0.365, 48), new THREE.MeshBasicMaterial({ color: '#2ff0e6', side: THREE.DoubleSide, transparent: true, opacity: 0.75 }));
  zone.rotation.x = -Math.PI / 2;
  zone.position.set(ANIMAL_ANCHOR.x, 0.004, ANIMAL_ANCHOR.z);
  group.add(zone);
  const duckZone = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-0.85, 0.005, 0.7), new THREE.Vector3(0.65, 0.005, 0.7),
    new THREE.Vector3(0.65, 0.005, -0.7), new THREE.Vector3(-0.85, 0.005, -0.7),
  ]), new THREE.LineBasicMaterial({ color: '#ffd23f', transparent: true, opacity: 0.45 }));
  group.add(duckZone);

  const trunkGeometry = new THREE.CylinderGeometry(0.035, 0.06, 0.85, 5);
  const trunkMaterial = new THREE.MeshStandardMaterial({ color: '#3c3328' });
  const crownGeometries = [0, 1, 2].map(layer => new THREE.ConeGeometry(0.32 - layer * 0.06, 0.65, 5));
  const crownMaterials = [0, 1].map(layer => new THREE.MeshStandardMaterial({ color: layer ? '#263d2b' : '#1b3025', roughness: 1 }));
  for (let i = 0; i < 13; i++) {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(trunkGeometry, trunkMaterial);
    trunk.position.y = 0.4;
    tree.add(trunk);
    for (let layer = 0; layer < 3; layer++) {
      const crown = new THREE.Mesh(crownGeometries[layer], crownMaterials[layer % 2]);
      crown.position.y = 0.65 + layer * 0.25;
      tree.add(crown);
    }
    tree.position.set((i - 6) * 0.53, 0, -1.8 - (i % 3) * 0.24);
    tree.rotation.y = i * 1.7;
    tree.scale.setScalar(0.85 + (i % 4) * 0.14);
    group.add(tree);
  }

  // One visible animal is the duck's scene partner. Archive interactions
  // may contain multiple animals; that does not add actors to this scene.
  const actors: Partial<Record<AnimalSpecies, AnimalActor>> = {};
  let encounter: (SceneEncounter & { behavior: Interaction; start: number; reached: boolean }) | null = null;
  let primary: AnimalActor | null = null;
  let motor = createAnimalMotor();
  let activity: AnimalActivity = 'hold';
  let interaction: { resolve(): void; reject(error: Error): void; stable: number | null; timer: ReturnType<typeof setTimeout> } | null = null;
  let previous = 0;
  const hideActors = () => { for (const actor of Object.values(actors)) actor.root.visible = false; };
  const stop = () => {
    activity = 'hold'; motor.speed = 0;
    if (interaction) { clearTimeout(interaction.timer); interaction.reject(new Error('Animal approach cancelled.')); interaction = null; }
  };
  const actorFor = (species: AnimalSpecies) => {
    if (!actors[species]) {
      const actor = species === 'cat' ? createCat() : createDeer();
      actor.root.position.set(0, 0, 0);
      actor.root.scale.multiplyScalar(0.65);
      actor.root.visible = false;
      actor.root.name = `ranger-animal-${species}`;
      actor.root.userData.encounterAnimal = true;
      group.add(actor.root);
      actors[species] = actor;
    }
    return actors[species]!;
  };
  return {
    start(input: SceneEncounter, now: number) {
      stop();
      hideActors();
      encounter = { ...input, behavior: interactionFor(input.behavior_hint), start: now, reached: false };
      primary = actorFor(input.animal === 'cat' ? 'cat' : 'deer');
      primary.root.visible = true;
      motor = createAnimalMotor();
      primary.root.rotation.set(0, 0, 0);
      primary.root.position.set(ANIMAL_ANCHOR.x, 0, ANIMAL_ANCHOR.z);
      primary.pose('alert', 0);
      previous = now;
    },
    reset() { stop(); encounter = null; hideActors(); },
    stop,
    setActivity(next: AnimalActivity) { if (!interaction) activity = next; },
    inspect() {
      let meshes = 0, triangles = 0;
      const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
      primary?.root.traverseVisible(object => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        meshes += 1;
        triangles += (mesh.geometry.index?.count ?? mesh.geometry.getAttribute('position')?.count ?? 0) / 3;
        geometries.add(mesh.geometry);
        for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) materials.add(material);
      });
      return { species: encounter?.animal ?? null, activity, position: { x: motor.x, z: motor.z }, yaw: motor.yaw, speed: motor.speed, meshes, triangles, geometries: geometries.size, materials: materials.size };
    },
    prepareInteraction(): Promise<void> {
      stop();
      if (!encounter || !primary) return Promise.resolve();
      activity = 'interact';
      return new Promise((resolve, reject) => {
        interaction = { resolve, reject, stable: null, timer: setTimeout(() => {
          interaction = null; activity = 'hold'; motor.speed = 0;
          reject(new Error('The animal did not settle at its interaction position.'));
        }, 8000) };
      });
    },
    focus() {
      if (!encounter?.reached || !primary) return null;
      const duck = getDuckPose();
      return { x: (duck.x + primary.root.position.x) / 2, z: (duck.z + primary.root.position.z) / 2 };
    },
    frame(now: number): string | null {
      if (!encounter || !primary) return null;
      const duck = getDuckPose();
      const dt = Math.min(0.05, Math.max(0, (now - previous) / 1000));
      previous = now;
      const time = (now - encounter.start) / 1000;
      stepAnimalMotor(motor, activity, dt, duck);
      primary.root.position.set(motor.x, 0, motor.z);
      primary.root.rotation.y = motor.yaw;
      const observed = time >= 1.8;
      const t = Math.max(0, time - 1.8);
      const cycle = t % 5.5;
      let pose: Parameters<AnimalActor['pose']>[0] = 'alert';
      if (encounter.behavior === 'boundary') {
        pose = cycle > 1.2 && cycle < 3.8 && encounter.animal === 'cat' ? 'hissing' : 'alert';
      } else if (encounter.behavior === 'greeting') pose = 'greeting';
      else if (encounter.behavior === 'play') pose = cycle > 1.2 && cycle < 4.2 ? 'play' : 'greeting';
      else if (encounter.behavior === 'feeding') pose = 'feeding';
      const offAnchor = Math.hypot(motor.x - ANIMAL_ANCHOR.x, motor.z - ANIMAL_ANCHOR.z) > 0.012;
      // Distance-driven gait stays still while turning or paused.
      const walking = motor.speed > 0.004 || offAnchor;
      primary.pose(walking ? 'walking' : pose, walking ? motor.gait : t, dt);
      if (interaction) {
        const desiredYaw = Math.atan2(duck.z - motor.z, motor.x - duck.x);
        const facingError = Math.abs(Math.atan2(Math.sin(desiredYaw - motor.yaw), Math.cos(desiredYaw - motor.yaw)));
        if (!offAnchor && motor.speed < 0.01 && facingError < 0.15) interaction.stable ??= now;
        else interaction.stable = null;
        if (interaction.stable != null && now - interaction.stable >= 180) {
          const complete = interaction;
          interaction = null;
          clearTimeout(complete.timer);
          complete.resolve();
        }
      }
      if (observed && !encounter.reached) { encounter.reached = true; return encounter.id; }
      return null;
    },
    dispose() {
      stop();
      const disposedGeometries = new Set<THREE.BufferGeometry>();
      const disposedMaterials = new Set<THREE.Material>();
      group.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry && !disposedGeometries.has(mesh.geometry)) { disposedGeometries.add(mesh.geometry); mesh.geometry.dispose(); }
        const materials = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : [];
        for (const material of materials) if (!disposedMaterials.has(material)) {
          disposedMaterials.add(material);
          (material as THREE.SpriteMaterial).map?.dispose();
          material.dispose();
        }
      });
      scene.remove(group);
    },
  };
}

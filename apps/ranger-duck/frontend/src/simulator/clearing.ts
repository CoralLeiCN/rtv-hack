import * as THREE from 'three';
import { createCat, createDeer, type AnimalActor, type AnimalSpecies } from './animals';

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
  zone.position.set(0.65, 0.004, -0.15);
  group.add(zone);
  const duckZone = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-0.85, 0.005, 0.7), new THREE.Vector3(0.65, 0.005, 0.7),
    new THREE.Vector3(0.65, 0.005, -0.7), new THREE.Vector3(-0.85, 0.005, -0.7),
  ]), new THREE.LineBasicMaterial({ color: '#ffd23f', transparent: true, opacity: 0.45 }));
  group.add(duckZone);

  for (let i = 0; i < 13; i++) {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.06, 0.85, 5), new THREE.MeshStandardMaterial({ color: '#3c3328' }));
    trunk.position.y = 0.4;
    tree.add(trunk);
    for (let layer = 0; layer < 3; layer++) {
      const crown = new THREE.Mesh(new THREE.ConeGeometry(0.32 - layer * 0.06, 0.65, 5), new THREE.MeshStandardMaterial({ color: layer % 2 ? '#263d2b' : '#1b3025', roughness: 1 }));
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
  const actors = { cat: createCat(), deer: createDeer() };
  for (const [species, actor] of Object.entries(actors)) {
    actor.root.scale.multiplyScalar(0.65);
    actor.root.visible = false;
    actor.root.name = `ranger-animal-${species}`;
    actor.root.userData.encounterAnimal = true;
    group.add(actor.root);
  }

  let encounter: (SceneEncounter & { behavior: Interaction; start: number; reached: boolean }) | null = null;
  let primary: AnimalActor = actors.deer;
  let previous = 0;
  const hideActors = () => { for (const actor of Object.values(actors)) actor.root.visible = false; };
  const target = new THREE.Vector3();
  return {
    start(input: SceneEncounter, now: number) {
      hideActors();
      primary = input.animal === 'cat' ? actors.cat : actors.deer;
      primary.root.visible = true;
      encounter = { ...input, behavior: interactionFor(input.behavior_hint), start: now, reached: false };
      primary.root.rotation.set(0, 0, 0);
      primary.root.position.set(2.8, 0, -0.15);
      primary.pose('walking', 0);
      previous = now;
    },
    reset() { encounter = null; hideActors(); },
    focus() {
      if (!encounter?.reached) return null;
      const duck = getDuckPose();
      return { x: (duck.x + primary.root.position.x) / 2, z: (duck.z + primary.root.position.z) / 2 };
    },
    frame(now: number): string | null {
      if (!encounter) return null;
      const duck = getDuckPose();
      const dt = Math.min(0.05, Math.max(0, (now - previous) / 1000));
      previous = now;
      const time = (now - encounter.start) / 1000;
      const entrance = Math.min(1, time / 1.8);
      const t = Math.max(0, time - 1.8);
      const cycle = t % 5.5;
      let distance = 0.55;
      let side = -0.05;
      let pose: Parameters<AnimalActor['pose']>[0] = 'alert';
      if (encounter.behavior === 'boundary') {
        const warning = cycle > 1.2 && cycle < 3.8;
        distance = warning ? 0.65 : 0.57;
        pose = warning && encounter.animal === 'cat' ? 'hissing' : 'alert';
      } else if (encounter.behavior === 'greeting') {
        const approach = (1 - Math.cos(Math.min(cycle, 2) / 2 * Math.PI)) / 2;
        distance = 0.53 - approach * 0.19;
        pose = cycle < 2 ? 'walking' : 'greeting';
      } else if (encounter.behavior === 'play') {
        // Crouch and bat toward the duck, then pull back and invite it again.
        const approach = (1 - Math.cos(cycle / 5.5 * Math.PI * 2)) / 2;
        distance = 0.5 - approach * 0.14;
        side = Math.sin(cycle / 5.5 * Math.PI * 2) * 0.06;
        pose = cycle > 1.2 && cycle < 4.2 ? 'play' : 'walking';
      } else if (encounter.behavior === 'feeding') {
        distance = 0.5;
        side = -0.15;
        pose = 'feeding';
      } else if (encounter.behavior === 'following') {
        distance = -0.55;
        side = -0.08;
        pose = 'walking';
      }
      // MuJoCo yaw is Z-up; Three's ground plane is X/Z with reversed Z.
      const fx = Math.cos(duck.yaw), fz = -Math.sin(duck.yaw);
      target.set(duck.x + fx * distance - fz * side, 0, duck.z + fz * distance + fx * side);
      if (entrance < 1) {
        const ease = entrance * entrance * (3 - 2 * entrance);
        primary.root.position.set(THREE.MathUtils.lerp(2.8, target.x, ease), 0, THREE.MathUtils.lerp(-0.15, target.z, ease));
        primary.pose('walking', time);
      } else {
        primary.root.position.lerp(target, 1 - Math.exp(-3 * dt));
        primary.pose(pose, t);
      }
      const dx = duck.x - primary.root.position.x, dz = duck.z - primary.root.position.z;
      const desiredYaw = Math.atan2(dz, -dx); // each animal model faces local -X
      const difference = Math.atan2(Math.sin(desiredYaw - primary.root.rotation.y), Math.cos(desiredYaw - primary.root.rotation.y));
      primary.root.rotation.y += difference * (1 - Math.exp(-6 * Math.max(dt, 0.016)));
      zone.position.set(primary.root.position.x, 0.004, primary.root.position.z);
      if (entrance >= 1 && !encounter.reached) { encounter.reached = true; return encounter.id; }
      return null;
    },
    dispose() {
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

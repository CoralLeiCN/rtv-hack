import * as THREE from 'three';
import { createCat, createDeer, type AnimalActor, type AnimalSpecies } from './animals';

export type SceneEncounter = {
  id: string; behavior_hint: string; animal?: AnimalSpecies;
  interaction_partner?: string;
};
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
export function createClearing(scene: THREE.Scene) {
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
    new THREE.Vector3(-1.1, 0.005, 0.45), new THREE.Vector3(0.15, 0.005, 0.45),
    new THREE.Vector3(0.15, 0.005, -0.45), new THREE.Vector3(-1.1, 0.005, -0.45),
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

  const actors = {
    cat: [createCat(false), createCat(true)],
    deer: [createDeer(false), createDeer(true)],
  };
  for (const pair of Object.values(actors)) for (const actor of pair) {
    actor.root.scale.multiplyScalar(0.8);
    actor.root.visible = false;
    group.add(actor.root);
  }

  let encounter: (SceneEncounter & { behavior: Interaction; start: number; reached: boolean }) | null = null;
  let primary: AnimalActor = actors.deer[0];
  let partner: AnimalActor | null = actors.deer[1];
  const hideActors = () => { for (const pair of Object.values(actors)) for (const actor of pair) actor.root.visible = false; };
  return {
    start(input: SceneEncounter, now: number) {
      hideActors();
      const species = input.animal === 'cat' ? 'cat' : 'deer';
      const other = input.interaction_partner === 'duck' ? null : input.interaction_partner === 'cat' ? 'cat' : input.interaction_partner === 'deer' ? 'deer' : species;
      primary = actors[species][0];
      partner = other ? actors[other][1] : null;
      primary.root.visible = true;
      if (partner) partner.root.visible = true;
      encounter = { ...input, behavior: interactionFor(input.behavior_hint), start: now, reached: false };
      primary.root.rotation.set(0, partner ? Math.PI : 0, 0);
      primary.root.position.set(2.8, 0, -0.15);
      if (partner) { partner.root.rotation.set(0, 0, 0); partner.root.position.set(0.95, 0, -0.5); partner.pose('standing', 0); }
      primary.pose('walking', 0);
    },
    reset() { encounter = null; hideActors(); },
    frame(now: number): string | null {
      if (!encounter) return null;
      const time = (now - encounter.start) / 1000;
      const entrance = Math.min(1, time / 1.8);
      const ease = entrance * entrance * (3 - 2 * entrance);
      primary.root.position.set(THREE.MathUtils.lerp(2.8, 0.42, ease), 0, -0.15);
      if (entrance < 1) {
        // Enter facing the direction of travel, then turn toward the partner.
        primary.root.rotation.y = 0;
        primary.pose('walking', time);
        partner?.pose('alert', time);
        return null;
      }
      const t = time - 1.8;
      const cycle = t % 5.5;
      primary.root.rotation.y = partner ? Math.PI : 0;
      if (partner) {
        partner.root.position.set(0.95, 0, -0.5);
        partner.root.rotation.y = 0;
      }
      if (encounter.behavior === 'boundary') {
        // The visitor approaches; the focal animal warns, and the visitor
        // visibly yields space. This is a scripted interaction, not an agent.
        const warning = cycle > 1.2 && cycle < 3.8;
        primary.root.position.x = 0.35;
        primary.pose(warning && encounter.animal === 'cat' ? 'hissing' : 'alert', t);
        if (partner) {
          const approach = cycle < 1.2 ? cycle / 1.2 : cycle < 2 ? 1 : cycle < 3.8 ? Math.max(0, 1 - (cycle - 2) / 1.8) : 0;
          partner.root.position.x = 1.15 - approach * 0.15;
          partner.root.position.z = -0.15;
          partner.pose(cycle < 1.2 || (cycle >= 2 && cycle < 3.8) ? 'walking' : 'alert', t);
        }
      } else if (encounter.behavior === 'greeting') {
        const approach = (1 - Math.cos(Math.min(cycle, 2) / 2 * Math.PI)) / 2;
        primary.root.position.x = 0.38 + approach * 0.05;
        primary.root.position.z = -0.23;
        primary.pose(cycle < 2 ? 'walking' : 'greeting', t);
        if (partner) {
          partner.root.position.x = 1.02 - approach * 0.1;
          partner.root.position.z = -0.23;
          partner.pose(cycle < 2 ? 'walking' : 'greeting', t + 0.4);
        }
      } else if (encounter.behavior === 'play') {
        const focalTurn = cycle < 2.75;
        primary.root.position.x = 0.35 + Math.sin(cycle / 5.5 * Math.PI * 2) * 0.05;
        primary.root.position.z = -0.25;
        primary.pose(focalTurn ? 'play' : 'alert', t);
        if (partner) {
          partner.root.position.set(1.0 - Math.sin(cycle / 5.5 * Math.PI * 2) * 0.05, 0, -0.25);
          partner.pose(focalTurn ? 'alert' : 'play', t + 0.4);
        }
      } else if (encounter.behavior === 'feeding') {
        primary.root.rotation.y = 0.12;
        primary.pose('feeding', t);
        if (partner) { partner.root.position.set(0.95, 0, -0.65); partner.root.rotation.y = 0.12; partner.pose('feeding', t + 0.9); }
      } else if (encounter.behavior === 'following') {
        const travel = Math.sin(t * 0.65) * 0.1;
        primary.root.rotation.y = Math.PI;
        primary.root.position.set(0.3 + travel, 0, -0.38);
        primary.pose('walking', t);
        if (partner) { partner.root.position.set(0.94 + travel, 0, -0.38); partner.root.rotation.y = Math.PI; partner.pose('walking', t + 0.35); }
      } else {
        primary.pose('alert', t);
        partner?.pose('alert', t + 0.6);
      }
      if (!encounter.reached) { encounter.reached = true; return encounter.id; }
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

import * as THREE from 'three';
import { describe, expect, it, vi } from 'vitest';
import { ANIMAL_ANCHOR, createClearing } from './clearing';

vi.mock('./animals', async () => {
  const { Group } = await import('three');
  const actor = () => {
    const root = new Group(), pose = vi.fn();
    root.userData.testPose = pose;
    return { root, pose };
  };
  return { createCat: actor, createDeer: actor };
});

function visibleAnimals(scene: THREE.Scene) {
  const animals: THREE.Object3D[] = [];
  scene.traverse(object => { if (object.userData.encounterAnimal && object.visible) animals.push(object); });
  return animals;
}

describe('single animal encounter', () => {
  it('shows one animal even when the archive partner is the same species', () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'one', animal: 'cat', interaction_partner: 'cat', behavior_hint: 'play' }, 0);
    expect(visibleAnimals(scene).map(animal => animal.name)).toEqual(['ranger-animal-cat']);
    clearing.start({ id: 'two', animal: 'deer', interaction_partner: 'deer', behavior_hint: 'feeding' }, 0);
    expect(visibleAnimals(scene).map(animal => animal.name)).toEqual(['ranger-animal-deer']);
    clearing.reset();
    expect(visibleAnimals(scene)).toEqual([]);
    clearing.dispose();
  });

  it('keeps the animal fixed outside the box while facing the moving duck', () => {
    const scene = new THREE.Scene();
    const duck = { x: -0.6, z: 0, yaw: 0 };
    const clearing = createClearing(scene, () => duck);
    clearing.start({ id: 'play', animal: 'cat', behavior_hint: 'play' }, 0);
    const reached: string[] = [];
    for (let t = 0; t <= 5000; t += 16) { const id = clearing.frame(t); if (id) reached.push(id); }
    const cat = visibleAnimals(scene)[0];
    const before = cat.position.clone();
    duck.x = -0.2; duck.z = 0.25; duck.yaw = 0.6;
    for (let t = 5016; t <= 8500; t += 16) clearing.frame(t);
    expect(cat.position.equals(before)).toBe(true);
    expect(cat.position.x).toBe(ANIMAL_ANCHOR.x);
    expect(cat.position.x - 0.365).toBeGreaterThan(0.65);
    expect(cat.position.z).toBe(ANIMAL_ANCHOR.z);
    const facing = new THREE.Vector3(-1, 0, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), cat.rotation.y);
    const towardDuck = new THREE.Vector3(duck.x, 0, duck.z).sub(cat.position).normalize();
    expect(facing.dot(towardDuck)).toBeGreaterThan(0.98);
    expect(reached).toEqual(['play']);
    expect(visibleAnimals(scene)).toHaveLength(1);
    clearing.dispose();
  });
  it('settles an outside patrol at the anchor before resolving interaction readiness', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene, () => ({ x: 0.35, z: 0.1, yaw: 0 }));
    clearing.start({ id: 'patrol', animal: 'cat', behavior_hint: 'play' }, 0);
    clearing.setActivity('patrol');
    for (let t = 16; t <= 6000; t += 16) clearing.frame(t);
    const cat = visibleAnimals(scene)[0];
    expect(cat.position.distanceTo(new THREE.Vector3(ANIMAL_ANCHOR.x, 0, ANIMAL_ANCHOR.z))).toBeGreaterThan(0.05);
    let settled = false;
    const ready = clearing.prepareInteraction().then(() => { settled = true; });
    clearing.setActivity('hold'); // External phase updates cannot cancel preparation.
    expect(settled).toBe(false);
    for (let t = 6016; t <= 14000; t += 16) clearing.frame(t);
    await ready;
    expect(cat.position.x).toBe(ANIMAL_ANCHOR.x);
    expect(cat.position.z).toBe(ANIMAL_ANCHOR.z);
    clearing.dispose();
  });
  it('cancels pending animal readiness on Stop and prevents continued patrol', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'cancel', animal: 'deer', behavior_hint: 'following' }, 0);
    clearing.setActivity('patrol');
    for (let t = 16; t <= 3000; t += 16) clearing.frame(t);
    const ready = clearing.prepareInteraction().catch(error => error);
    clearing.stop();
    expect((await ready).message).toContain('cancelled');
    const position = visibleAnimals(scene)[0].position.clone();
    for (let t = 3016; t <= 5000; t += 16) clearing.frame(t);
    expect(visibleAnimals(scene)[0].position.equals(position)).toBe(true);
    clearing.dispose();
  });
  it('runs a grounded role on the existing encounter actor without a position jump', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'unified', animal: 'cat', behavior_hint: 'play', preservePose: true }, 0);
    const cat = visibleAnimals(scene)[0];
    const initial = cat.position.clone();
    const feeding = clearing.performCompanion({ behavior: 'feeding', durationMs: 1000 }, 2000);
    expect(cat.position.equals(initial)).toBe(true);
    clearing.frame(2500);
    expect(cat.position.equals(initial)).toBe(true);
    clearing.frame(3000);
    await feeding;
    expect(visibleAnimals(scene)).toEqual([cat]);
    clearing.dispose();
  });
  it('keeps a grounded retreat continuous, holds afterwards, then returns before readiness', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'retreat', animal: 'cat', behavior_hint: 'play' }, 0);
    const cat = visibleAnimals(scene)[0];
    const retreat = clearing.performCompanion({ behavior: 'retreat', durationMs: 1000 }, 2000);
    clearing.frame(2500);
    expect(cat.position.x).toBeCloseTo(ANIMAL_ANCHOR.x + 0.2);
    clearing.frame(3000);
    await retreat;
    const stopped = cat.position.clone();
    clearing.setActivity('interact'); // Duck motion cannot restart a completed companion role.
    clearing.frame(3500);
    expect(cat.position.equals(stopped)).toBe(true);
    const ready = clearing.prepareInteraction();
    for (let t = 3516; t < 11000; t += 16) clearing.frame(t);
    await ready;
    expect(cat.position.x).toBe(ANIMAL_ANCHOR.x);
    expect(cat.position.z).toBe(ANIMAL_ANCHOR.z);
    expect(cat.position.x - 0.365).toBeGreaterThan(0.65);
    clearing.dispose();
  });
  it('cancels a unified role on Stop and retains species and duration validation', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'cancel-role', animal: 'deer', behavior_hint: 'following' }, 0);
    await expect(clearing.performCompanion({ behavior: 'hissing', durationMs: 1000 }, 2000)).rejects.toThrow('Unsupported');
    await expect(clearing.performCompanion({ behavior: 'walking', durationMs: 3001 }, 2000)).rejects.toThrow('Unsupported');
    const action = clearing.performCompanion({ behavior: 'walking', durationMs: 1000 }, 2000);
    const rejected = expect(action).rejects.toThrow('stopped');
    clearing.frame(2400);
    clearing.stop();
    await rejected;
    const position = visibleAnimals(scene)[0].position.clone();
    clearing.frame(3000);
    expect(visibleAnimals(scene)[0].position.equals(position)).toBe(true);
    clearing.dispose();
  });
  it('changes the ambient interaction on the same actor without resetting its motor or observation', () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'adaptive', animal: 'cat', behavior_hint: 'greeting' }, 0);
    expect(clearing.frame(2000)).toBe('adaptive');
    const cat = visibleAnimals(scene)[0];
    const before = clearing.inspect();
    const position = cat.position.clone(), rotation = cat.quaternion.clone();
    clearing.updateEncounterBehavior('hissing', 2000);
    expect(visibleAnimals(scene)).toEqual([cat]);
    expect(cat.position.equals(position)).toBe(true);
    expect(cat.quaternion.equals(rotation)).toBe(true);
    expect(clearing.inspect()).toEqual({ ...before, behavior_hint: 'hissing' });
    expect(clearing.frame(4000)).toBeNull();
    expect(cat.userData.testPose).toHaveBeenLastCalledWith('hissing', 2, expect.any(Number));
    clearing.dispose();
  });
  it('guards an active role but allows a new preset while readiness is settling', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'adaptive', animal: 'cat', behavior_hint: 'greeting' }, 0);
    const role = clearing.performCompanion({ behavior: 'feeding', durationMs: 1000 }, 2000);
    expect(() => clearing.updateEncounterBehavior('play', 2500)).toThrow('companion action');
    clearing.frame(3000); await role;
    const ready = clearing.prepareInteraction();
    clearing.updateEncounterBehavior('play', 3000);
    for (let t = 3016; t < 5000; t += 16) clearing.frame(t);
    await ready;
    expect(visibleAnimals(scene)[0].userData.testPose).toHaveBeenLastCalledWith('play', expect.any(Number), expect.any(Number));
    expect(clearing.inspect().behavior_hint).toBe('play');
    clearing.dispose();
  });
  it('walks the following preset only during search and settles before playback', async () => {
    const scene = new THREE.Scene();
    const clearing = createClearing(scene);
    clearing.start({ id: 'following', animal: 'deer', behavior_hint: 'feeding' }, 0);
    clearing.frame(2000);
    const deer = visibleAnimals(scene)[0], start = deer.position.clone();
    clearing.updateEncounterBehavior('following', 2000);
    expect(deer.position.equals(start)).toBe(true);
    let travelled = 0;
    for (let t = 2016; t <= 8000; t += 16) {
      clearing.setActivity('hold', true);
      clearing.frame(t);
      travelled = Math.max(travelled, deer.position.distanceTo(start));
      expect(deer.position.x).toBeGreaterThanOrEqual(ANIMAL_ANCHOR.x);
      expect(deer.position.x).toBeLessThanOrEqual(1.29);
      expect(deer.position.z).toBeGreaterThanOrEqual(-0.32);
      expect(deer.position.z).toBeLessThanOrEqual(0.22);
    }
    expect(travelled).toBeGreaterThan(0.1);
    const ready = clearing.prepareInteraction();
    for (let t = 8016; t <= 15000; t += 16) {
      clearing.setActivity('hold', false); // Results are ready; playback waits for this preparation.
      clearing.frame(t);
    }
    await ready;
    expect(deer.position.x).toBe(ANIMAL_ANCHOR.x);
    expect(deer.position.z).toBe(ANIMAL_ANCHOR.z);
    const settled = deer.position.clone();
    clearing.frame(15500);
    expect(deer.position.equals(settled)).toBe(true);
    expect(visibleAnimals(scene)).toEqual([deer]);
    clearing.dispose();
  });
});

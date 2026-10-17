import * as THREE from 'three';
import { describe, expect, it, vi } from 'vitest';
import { createClearing } from './clearing';

vi.mock('./animals', async () => {
  const { Group } = await import('three');
  const actor = () => ({ root: new Group(), pose: vi.fn() });
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

  it('aims social play at the duck and follows its continuing position', () => {
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
    expect(cat.position.distanceTo(before)).toBeGreaterThan(0.2);
    expect(cat.position.distanceTo(new THREE.Vector3(duck.x, 0, duck.z))).toBeLessThan(0.55);
    const facing = new THREE.Vector3(-1, 0, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), cat.rotation.y);
    const towardDuck = new THREE.Vector3(duck.x, 0, duck.z).sub(cat.position).normalize();
    expect(facing.dot(towardDuck)).toBeGreaterThan(0.98);
    expect(reached).toEqual(['play']);
    expect(visibleAnimals(scene)).toHaveLength(1);
    clearing.dispose();
  });
});

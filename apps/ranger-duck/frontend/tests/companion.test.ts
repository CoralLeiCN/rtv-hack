import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

vi.mock('../src/simulator/animals', () => ({
  createCat: () => actor('cat'), createDeer: () => actor('deer'),
}));
function actor(species: string) {
  const root = new THREE.Group(); root.userData.species = species;
  return { root, pose: vi.fn() };
}
import { createClearing, ANIMAL_ANCHOR } from '../src/simulator/clearing';
function setup() {
  const scene = new THREE.Scene(); const clearing = createClearing(scene);
  const visible = () => { const found: THREE.Object3D[] = []; scene.traverse(o => { if (o.userData.species && o.visible) found.push(o); }); return found; };
  return { clearing, visible };
}

describe('single companion scene', () => {
  it('shows exactly one selected animal without emitting an encounter search', () => {
    const { clearing, visible } = setup();
    clearing.showLoopAnimals('deer'); expect(visible().map(o => o.userData.species)).toEqual(['deer']);
    expect(clearing.frame(10000)).toBeNull();
    clearing.showLoopAnimals('cat'); expect(visible().map(o => o.userData.species)).toEqual(['cat']);
    clearing.reset(); expect(visible()).toEqual([]);
    clearing.start({ id: 'encounter', animal: 'deer', behavior_hint: 'feeding' }, 0);
    expect(visible().map(o => o.userData.species)).toEqual(['deer']);
    expect(clearing.frame(1800)).toBe('encounter'); expect(clearing.frame(3000)).toBeNull();
    clearing.dispose();
  });
  it('finishes the bounded companion animation only on a completed render frame', async () => {
    const { clearing, visible } = setup(); clearing.showLoopAnimals('deer'); let completed = false;
    const run = clearing.performCompanion({ behavior: 'approach', durationMs: 3000 }, 100).then(() => { completed = true; });
    clearing.frame(1600); await Promise.resolve(); expect(completed).toBe(false);
    expect(visible()[0].position.x).toBeCloseTo(ANIMAL_ANCHOR.x + 0.2);
    clearing.frame(3100); await run; expect(visible()[0].position.x).toBeCloseTo(ANIMAL_ANCHOR.x);
    clearing.frame(100000); expect(visible()[0].position.x).toBeCloseTo(ANIMAL_ANCHOR.x);
    clearing.dispose();
  });
  it('cancels an animation on mode reset and never reports success later', async () => {
    const { clearing, visible } = setup(); clearing.showLoopAnimals('cat');
    const run = clearing.performCompanion({ behavior: 'retreat', durationMs: 3000 }, 0);
    const stopped = expect(run).rejects.toThrow('stopped');
    clearing.reset(); await stopped; clearing.frame(10000); expect(visible()).toEqual([]);
    clearing.dispose();
  });
  it('rejects unsupported species behavior and overlapping companion actions', async () => {
    const { clearing } = setup(); clearing.showLoopAnimals('deer');
    await expect(clearing.performCompanion({ behavior: 'hissing', durationMs: 3000 }, 0)).rejects.toThrow('Unsupported');
    const run = clearing.performCompanion({ behavior: 'feeding', durationMs: 3000 }, 0);
    const stopped = expect(run).rejects.toThrow('stopped');
    await expect(clearing.performCompanion({ behavior: 'alert', durationMs: 3000 }, 0)).rejects.toThrow('busy');
    clearing.stopRoleAction(); await stopped; clearing.dispose();
  });
});

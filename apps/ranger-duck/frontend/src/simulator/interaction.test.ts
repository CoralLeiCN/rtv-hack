import { describe, expect, it, vi } from 'vitest';
import { InteractionCoordinator } from './interaction';

describe('automatic and explicit interaction navigation', () => {
  it('shares one approach when animal appearance and an action request overlap', async () => {
    let settle!: () => void;
    const steps = { prepareDuck: vi.fn(() => new Promise<void>(resolve => { settle = resolve; })), prepareAnimal: vi.fn(async () => {}), approach: vi.fn(async () => {}) };
    const coordinator = new InteractionCoordinator(steps);
    const automatic = coordinator.ensure();
    const explicit = coordinator.ensure();
    expect(automatic).toBe(explicit);
    await Promise.resolve();
    expect(coordinator.phase).toBe('settling');
    settle();
    await explicit;
    expect(steps.prepareDuck).toHaveBeenCalledTimes(1);
    expect(steps.approach).toHaveBeenCalledTimes(1);
    expect(coordinator.phase).toBe('idle');
  });

  it('Stop during animal preparation prevents a late duck approach', async () => {
    let settle!: () => void;
    const steps = { prepareDuck: vi.fn(async () => {}), prepareAnimal: vi.fn(() => new Promise<void>(resolve => { settle = resolve; })), approach: vi.fn(async () => {}) };
    const coordinator = new InteractionCoordinator(steps);
    const stopped = coordinator.ensure().catch(error => error);
    await Promise.resolve(); await Promise.resolve();
    coordinator.cancel();
    settle();
    expect((await stopped).name).toBe('AbortError');
    expect(steps.approach).not.toHaveBeenCalled();
    expect(coordinator.phase).toBe('idle');
    steps.prepareAnimal.mockImplementation(async () => {});
    await coordinator.ensure();
    expect(steps.approach).toHaveBeenCalledTimes(1);
  });

  it('Stop before queued work begins does not move or reset the duck', async () => {
    const steps = { prepareDuck: vi.fn(async () => {}), prepareAnimal: vi.fn(async () => {}), approach: vi.fn(async () => {}) };
    const coordinator = new InteractionCoordinator(steps);
    const stopped = coordinator.ensure().catch(error => error);
    coordinator.cancel();
    expect((await stopped).name).toBe('AbortError');
    expect(steps.prepareDuck).not.toHaveBeenCalled();
    expect(steps.approach).not.toHaveBeenCalled();
  });
});

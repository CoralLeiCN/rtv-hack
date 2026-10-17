import { describe, expect, it } from 'vitest';
import { ANIMAL_ANCHOR, createAnimalMotor, stepAnimalMotor } from './animalMotor';
import * as THREE from 'three';

describe('animal visual motor', () => {
  it('walks outside the yellow box, returns to the anchor, and faces the duck', () => {
    const motor = createAnimalMotor();
    const duck = { x: 0.35, z: 0.1 };
    let distance = 0;
    for (let frame = 0; frame < 3600; frame++) {
      const before = { x: motor.x, z: motor.z };
      stepAnimalMotor(motor, 'patrol', 1 / 60, duck);
      distance += Math.hypot(motor.x - before.x, motor.z - before.z);
      expect(motor.x - 0.35).toBeGreaterThan(0.65);
      expect(motor.speed).toBeLessThanOrEqual(0.18);
    }
    expect(distance).toBeGreaterThan(2);
    for (let frame = 0; frame < 480; frame++) stepAnimalMotor(motor, 'interact', 1 / 60, duck);
    expect(motor.x).toBe(ANIMAL_ANCHOR.x);
    expect(motor.z).toBe(ANIMAL_ANCHOR.z);
    expect(motor.speed).toBe(0);
    const direction = new THREE.Vector3(-1, 0, 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), motor.yaw);
    expect(direction.dot(new THREE.Vector3(duck.x - motor.x, 0, duck.z - motor.z).normalize())).toBeGreaterThan(0.99);
  });
  it('holds position for Stop and clamps long frame gaps', () => {
    const motor = createAnimalMotor();
    const duck = { x: -0.6, z: 0 };
    for (let frame = 0; frame < 180; frame++) stepAnimalMotor(motor, 'patrol', 1 / 60, duck);
    const before = { x: motor.x, z: motor.z };
    stepAnimalMotor(motor, 'hold', 120, duck);
    expect({ x: motor.x, z: motor.z }).toEqual(before);
    stepAnimalMotor(motor, 'patrol', 120, duck);
    expect(Math.hypot(motor.x - before.x, motor.z - before.z)).toBeLessThan(0.01);
  });
});
